# Start isolated local database dependencies; no application deployment.

$ErrorActionPreference = 'Stop'
$runtimeDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\.runtime'))
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$credentials = Join-Path $runtimeDir 'demo.env'

if (-not (Test-Path -LiteralPath $credentials)) {
    $pgPassword = [guid]::NewGuid().ToString('N')
    $graphPassword = [guid]::NewGuid().ToString('N')
    @(
        'RAG__DATABASE__VECTOR__HOST=127.0.0.1'
        'RAG__DATABASE__VECTOR__PORT=55433'
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

function Start-DemoDatabase {
    param([string]$Name, [string[]]$RunArguments)
    $exists = docker container ls -a --filter "name=^/$Name`$" --format '{{.Names}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop must be running.' }
    if ($exists -eq $Name) {
        docker start $Name | Out-Null
    } else {
        docker run --detach --name $Name @RunArguments | Out-Null
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not start $Name" }
    Write-Output "$Name started. Credentials: .runtime/demo.env (not committed)."
}

Start-DemoDatabase -Name 'legalrag-pgvector' -RunArguments @(
    '--publish', '127.0.0.1:55433:5432', '--memory', '512m',
    '--volume', 'legalrag-pgdata:/var/lib/postgresql/data', '--env-file', $pgEnv,
    'pgvector/pgvector:pg16'
)
Start-DemoDatabase -Name 'legalrag-neo4j' -RunArguments @(
    '--publish', '127.0.0.1:17474:7474', '--publish', '127.0.0.1:17687:7687',
    '--memory', '1g', '--volume', 'legalrag-neo4j-data:/data', '--env-file', $graphEnv,
    'neo4j:5.26-community'
)
