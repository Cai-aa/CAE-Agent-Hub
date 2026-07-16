param(
    [Parameter(Mandatory = $true)] [string] $PythonExe,
    [string] $HyperWorksHome = $env:HYPERWORKS_HOME,
    [string] $Workspace = "$env:USERPROFILE\Documents\hyperworks-mcp-workspace"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python executable not found: $PythonExe"
}

if ([string]::IsNullOrWhiteSpace($HyperWorksHome)) {
    $candidateBases = @(
        "$env:ProgramFiles\Altair"
        "$env:ProgramW6432\Altair"
        "$env:SystemDrive\Altair"
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Container } |
        Select-Object -Unique

    $HyperWorksHome = $candidateBases |
        ForEach-Object { Get-ChildItem -LiteralPath $_ -Directory -ErrorAction SilentlyContinue } |
        Sort-Object Name -Descending |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'hwdesktop') } |
        Select-Object -First 1 -ExpandProperty FullName
}

if ([string]::IsNullOrWhiteSpace($HyperWorksHome)) {
    throw 'HyperWorks installation was not detected. Set HYPERWORKS_HOME or pass -HyperWorksHome.'
}
if (-not (Test-Path -LiteralPath $HyperWorksHome -PathType Container)) {
    throw "HyperWorks installation root not found: $HyperWorksHome"
}

& codex mcp remove hyperworks 2>$null
& codex mcp add hyperworks `
    --env "HYPERWORKS_HOME=$HyperWorksHome" `
    --env "HYPERWORKS_MCP_WORKSPACE=$Workspace" `
    --env "PYTHONUTF8=1" `
    -- $PythonExe -m hyperworks_mcp

Write-Host "Registered hyperworks MCP. Verify it with: codex mcp get hyperworks"
