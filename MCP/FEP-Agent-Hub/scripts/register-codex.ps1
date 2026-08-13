$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Config = Join-Path $Root "configs\open-cae.local.toml"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Run scripts/install.ps1 first; missing $Python"
}

foreach ($Server in @(
    @{ Name = "open-cae-freecad"; Module = "freecad_mcp.server" },
    @{ Name = "open-cae-elmer"; Module = "elmer_mcp.server" },
    @{ Name = "open-cae-paraview"; Module = "paraview_mcp.server" }
)) {
    & codex mcp add -c 'service_tier="fast"' $Server.Name --env "OPEN_CAE_CONFIG=$Config" -- $Python -m $Server.Module
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to register $($Server.Name)"
    }
}

Write-Host "Registered three OpenCAE stdio MCP servers with Codex."
