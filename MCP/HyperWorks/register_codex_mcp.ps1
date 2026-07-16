param(
    [Parameter(Mandatory = $true)] [string] $PythonExe,
    [string] $HyperWorksHome = "G:\Program Files\Altair\2026",
    [string] $Workspace = "$env:USERPROFILE\Documents\hyperworks-mcp-workspace"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python executable not found: $PythonExe"
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
