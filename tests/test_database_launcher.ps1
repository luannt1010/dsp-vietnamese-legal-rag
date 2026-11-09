# Focused launcher regression tests. Docker and bind probes are simulated.
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot '../scripts/start_demo_databases.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    [System.IO.Path]::GetFullPath($scriptPath), [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors) { throw 'Launcher failed PowerShell parsing.' }
$functions = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
foreach ($definition in $functions) { . ([scriptblock]::Create($definition.Extent.Text)) }

function Test-PublishPort {
    param([int]$Port)
    if ($script:BlockedPort -eq $Port) { throw 'Port blocked in test.' }
}

function docker {
    $arguments = @($args)
    $global:LASTEXITCODE = 0
    $script:Calls.Add(($arguments -join ' ')) | Out-Null
    switch ($arguments[0]) {
        'container' { return 'legalrag-pgvector' }
        'inspect' {
            switch ($arguments[2]) {
                '{{json .State.Running}}' { return (ConvertTo-Json -InputObject $script:Running -Compress) }
                '{{json .Config.Image}}' { return (ConvertTo-Json -InputObject 'pgvector/pgvector:pg16' -Compress) }
                '{{json .HostConfig.PortBindings}}' { return (ConvertTo-Json -InputObject @{ '5432/tcp' = @(@{ HostIp = '127.0.0.1'; HostPort = [string]$script:SavedPort }) } -Depth 4 -Compress) }
                '{{json .Mounts}}' { return (ConvertTo-Json -InputObject @(@{ Type = 'volume'; Name = $script:Volume; Destination = '/var/lib/postgresql/data' }) -Depth 4 -Compress) }
            }
            throw 'Unexpected inspect field.'
        }
        'start' { return 'legalrag-pgvector' }
        'rename' { return }
        'run' { return 'simulated-container-id' }
        default { throw 'Unexpected Docker command.' }
    }
}

function Reset-Fixture {
    $script:Calls = [System.Collections.Generic.List[string]]::new()
    $script:Running = $false
    $script:SavedPort = 15432
    $script:Volume = 'legalrag-pgdata'
    $script:BlockedPort = 0
    $script:PostgresPort = 15432
    $script:defaultPostgresPort = 15432
    $script:RecreateStoppedContainers = $false
}

function Invoke-Launcher {
    Start-DemoDatabase -Name 'legalrag-pgvector' -Image 'pgvector/pgvector:pg16' `
        -Volume 'legalrag-pgdata' -MountPath '/var/lib/postgresql/data' `
        -Ports @{ '5432/tcp' = 15432 } -RunArguments @('--memory', '512m') | Out-Null
}

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Rejected {
    param([string]$MessagePart)
    $caught = $false
    try { Invoke-Launcher } catch {
        $caught = $true
        Assert-That ($_.Exception.Message.Contains($MessagePart)) "Wrong failure: $($_.Exception.Message)"
    }
    Assert-That $caught 'Expected a refusal.'
    Assert-That (@($script:Calls | Where-Object { $_ -match '^(rename|run|start) ' }).Count -eq 0) 'A refusal mutated the container.'
}

Reset-Fixture
$script:Running = $true
Invoke-Launcher
Assert-That (@($script:Calls | Where-Object { $_ -match '^(rename|run|start) ' }).Count -eq 0) 'Running container was recreated.'

Reset-Fixture
Invoke-Launcher
Assert-That ($script:Calls -contains 'start legalrag-pgvector') 'Stopped matching container was not started.'

Reset-Fixture
$script:SavedPort = 55433
Assert-Rejected 'RecreateStoppedContainers'

Reset-Fixture
$script:SavedPort = 55433
$script:RecreateStoppedContainers = $true
Invoke-Launcher
Assert-That (@($script:Calls | Where-Object { $_ -match '^rename legalrag-pgvector legalrag-pgvector-port-backup-' }).Count -eq 1) 'Stopped container was not retained.'
$run = @($script:Calls | Where-Object { $_ -match '^run ' })
Assert-That ($run.Count -eq 1 -and $run[0].Contains('127.0.0.1:15432:5432') -and $run[0].Contains('legalrag-pgdata:/var/lib/postgresql/data')) 'Migration did not retain the named data volume and new mapping.'
Assert-That (@($script:Calls | Where-Object { $_ -match '^(rm|volume rm|stop) ' }).Count -eq 0) 'Migration deleted or stopped resources.'

Reset-Fixture
$script:SavedPort = 55433
$script:Running = $true
$script:RecreateStoppedContainers = $true
Assert-Rejected 'Stop this project'

Reset-Fixture
$script:Volume = 'another-project'
$script:RecreateStoppedContainers = $true
Assert-Rejected 'unrelated container'

Reset-Fixture
$script:SavedPort = 55433
$script:BlockedPort = 15432
$script:RecreateStoppedContainers = $true
Assert-Rejected 'Port blocked'

Write-Output '7 launcher regression scenarios passed; no Docker services or files were changed.'
