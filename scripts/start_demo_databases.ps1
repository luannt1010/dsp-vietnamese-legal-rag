# Start local database dependencies. Keep published ports and demo.env in sync.
param(
    [ValidateRange(1, 65535)][int]$PostgresPort = 15432,
    [switch]$RecreateStoppedContainers
)

$ErrorActionPreference = 'Stop'
$defaultPostgresPort = $PostgresPort
$explicitPostgresPort = $PSBoundParameters.ContainsKey('PostgresPort')
$null = docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop must be running and accessible.' }

$runtimeDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\.runtime'))
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$credentials = Join-Path $runtimeDir 'demo.env'

if (-not (Test-Path -LiteralPath $credentials)) {
    $existingVolumes = @(docker volume ls --format '{{.Name}}')
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect Docker volumes.' }
    if (($existingVolumes -contains 'legalrag-pgdata') -or ($existingVolumes -contains 'legalrag-neo4j-data')) {
        throw 'Database volumes already exist but .runtime/demo.env is missing. Restore its original credentials before starting; do not generate new passwords for existing data.'
    }
    $pgPassword = [guid]::NewGuid().ToString('N')
    $graphPassword = [guid]::NewGuid().ToString('N')
    @(
        'RAG__DATABASE__VECTOR__HOST=127.0.0.1'
        "RAG__DATABASE__VECTOR__PORT=$PostgresPort"
        'RAG__DATABASE__VECTOR__DATABASE=legal_rag'
        'RAG__DATABASE__VECTOR__USERNAME=rag'
        "RAG__DATABASE__VECTOR__PASSWORD=$pgPassword"
        'RAG__DATABASE__GRAPH__URI=bolt://127.0.0.1:17687'
        'RAG__DATABASE__GRAPH__USERNAME=neo4j'
        "RAG__DATABASE__GRAPH__PASSWORD=$graphPassword"
    ) | Set-Content -LiteralPath $credentials -Encoding utf8
}

$values = @{}
Get-Content -LiteralPath $credentials | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { $values[$matches[1]] = $matches[2] }
}
if (-not $explicitPostgresPort -and $values.ContainsKey('RAG__DATABASE__VECTOR__PORT')) {
    $PostgresPort = [int]$values['RAG__DATABASE__VECTOR__PORT']
}
if ($PostgresPort -lt 1 -or $PostgresPort -gt 65535) { throw 'Invalid PostgreSQL port in demo.env.' }
if ($values['RAG__DATABASE__VECTOR__HOST'] -notin @('localhost', '127.0.0.1')) {
    throw 'This launcher only manages local databases. Use your existing database service for a remote host.'
}
$graphUri = [Uri]$values['RAG__DATABASE__GRAPH__URI']
if ($graphUri.Host -notin @('localhost', '127.0.0.1') -or $graphUri.Port -lt 1) {
    throw 'This launcher requires a local Neo4j URI with an explicit port in demo.env.'
}
$graphPort = $graphUri.Port
$pgEnv = Join-Path $runtimeDir 'postgres.env'
@(
    "POSTGRES_DB=$($values['RAG__DATABASE__VECTOR__DATABASE'])"
    "POSTGRES_USER=$($values['RAG__DATABASE__VECTOR__USERNAME'])"
    "POSTGRES_PASSWORD=$($values['RAG__DATABASE__VECTOR__PASSWORD'])"
) | Set-Content -LiteralPath $pgEnv -Encoding utf8
$graphEnv = Join-Path $runtimeDir 'neo4j.env'
@(
    "NEO4J_AUTH=neo4j/$($values['RAG__DATABASE__GRAPH__PASSWORD'])"
    'NEO4J_server_memory_heap_initial__size=256m'
    'NEO4J_server_memory_heap_max__size=512m'
    'NEO4J_server_memory_pagecache_size=128m'
) | Set-Content -LiteralPath $graphEnv -Encoding utf8

function Test-PublishPort {
    param([int]$Port)
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    $listener.Server.ExclusiveAddressUse = $true
    try { $listener.Start() }
    catch {
        throw "Cannot bind 127.0.0.1:$Port. The port is in use or reserved by Windows. Check: netsh interface ipv4 show excludedportrange protocol=tcp. For PostgreSQL, retry with -PostgresPort $defaultPostgresPort (or another available port) -RecreateStoppedContainers."
    }
    finally { $listener.Stop() }
}

function Get-ContainerField {
    param([string]$Name, [string]$Field)
    # Avoid literal JSON property quotes in --format: Windows PowerShell 5.1
    # strips those quotes when passing native arguments to Docker.
    $value = docker inspect --format "{{json .$Field}}" $Name
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect $Name ($Field)." }
    return ($value | ConvertFrom-Json)
}

function Start-DemoDatabase {
    param(
        [string]$Name, [string]$Image, [string]$Volume, [string]$MountPath,
        [hashtable]$Ports, [string[]]$RunArguments
    )
    $exists = docker container ls -a --filter "name=^/$Name`$" --format '{{.Names}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop must be running.' }
    if ($exists -eq $Name) {
        # Inspect only identity/mounts/ports; do not print container environment secrets.
        $info = [PSCustomObject]@{
            running = Get-ContainerField $Name 'State.Running'
            image = Get-ContainerField $Name 'Config.Image'
            ports = Get-ContainerField $Name 'HostConfig.PortBindings'
            mounts = @(Get-ContainerField $Name 'Mounts')
        }
        $ownedVolume = @($info.mounts | Where-Object { $_.Type -eq 'volume' -and $_.Name -eq $Volume -and $_.Destination -eq $MountPath })
        $unexpectedMounts = @($info.mounts | Where-Object {
            $_.Destination -ne $MountPath -and -not ($Image -eq 'neo4j:5.26-community' -and $_.Destination -eq '/logs' -and $_.Type -eq 'volume')
        })
        if ($info.image -ne $Image -or $ownedVolume.Count -ne 1 -or $unexpectedMounts.Count -gt 0) {
            throw "$Name does not match this project's image and named volume. Refusing to replace or start an unrelated container."
        }
        $matches = @($info.ports.PSObject.Properties | Where-Object { $null -ne $_.Value }).Count -eq $Ports.Count
        foreach ($entry in $Ports.GetEnumerator()) {
            $bindings = @($info.ports.PSObject.Properties[$entry.Key].Value)
            if ($bindings.Count -ne 1 -or $bindings[0].HostIp -ne '127.0.0.1' -or $bindings[0].HostPort -ne [string]$entry.Value) { $matches = $false }
        }
        if ($matches -and $info.running) {
            Write-Output "$Name already running with the configured ports."
            return
        }
        if (-not $matches) {
            if ($info.running) { throw "$Name has different ports and is running. Stop this project's container before changing its ports." }
            if (-not $RecreateStoppedContainers) {
                throw "$Name has different port mappings. Rerun with -PostgresPort $PostgresPort -RecreateStoppedContainers to retain the stopped container as backup and reuse its named volume."
            }
        }
        foreach ($port in $Ports.Values) { Test-PublishPort $port }
        if ($matches) {
            docker start $Name | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Could not start $Name." }
            Write-Output "$Name started. Credentials: .runtime/demo.env (not committed)."
            return
        }
        # Port publishing is fixed at creation. Keep the old stopped container;
        # its named volume and database credentials are reused without deletion.
        $backup = "$Name-port-backup-$(Get-Date -Format 'yyyyMMddHHmmssfff')"
        docker rename $Name $backup
        if ($LASTEXITCODE -ne 0) { throw "Could not retain $Name as backup." }
        Write-Output "Stopped container retained as $backup. Data stays in volume $Volume."
    } else {
        foreach ($port in $Ports.Values) { Test-PublishPort $port }
    }
    $publishArguments = @()
    foreach ($entry in $Ports.GetEnumerator()) {
        $containerPort = $entry.Key.Split('/')[0]
        $publishArguments += @('--publish', "127.0.0.1:$($entry.Value):$containerPort")
    }
    docker run --detach --name $Name @publishArguments --volume "${Volume}:$MountPath" @RunArguments $Image | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not start $Name" }
    Write-Output "$Name started. Credentials: .runtime/demo.env (not committed)."
}

Start-DemoDatabase -Name 'legalrag-pgvector' -Image 'pgvector/pgvector:pg16' `
    -Volume 'legalrag-pgdata' -MountPath '/var/lib/postgresql/data' `
    -Ports @{ '5432/tcp' = $PostgresPort } -RunArguments @('--memory', '512m', '--env-file', $pgEnv)

# Commit the connection port only after PostgreSQL starts successfully.
$credentialLines = @(Get-Content -LiteralPath $credentials)
$portKey = 'RAG__DATABASE__VECTOR__PORT'
if (@($credentialLines | Where-Object { $_ -match "^$portKey=" }).Count -gt 0) {
    $credentialLines = @($credentialLines | ForEach-Object { if ($_ -match "^$portKey=") { "$portKey=$PostgresPort" } else { $_ } })
} else { $credentialLines += "$portKey=$PostgresPort" }
$credentialLines | Set-Content -LiteralPath $credentials -Encoding utf8

Start-DemoDatabase -Name 'legalrag-neo4j' -Image 'neo4j:5.26-community' `
    -Volume 'legalrag-neo4j-data' -MountPath '/data' `
    -Ports @{ '7474/tcp' = 17474; '7687/tcp' = $graphPort } `
    -RunArguments @('--memory', '1g', '--env-file', $graphEnv)

Write-Output "PostgreSQL: 127.0.0.1:$PostgresPort; Neo4j Bolt port: $graphPort; Neo4j Browser: http://127.0.0.1:17474"
if ($env:RAG__DATABASE__VECTOR__PORT -and $env:RAG__DATABASE__VECTOR__PORT -ne [string]$PostgresPort) {
    Write-Warning 'The process RAG__DATABASE__VECTOR__PORT overrides demo.env. Update that variable before running doctor/prepare/API.'
}
