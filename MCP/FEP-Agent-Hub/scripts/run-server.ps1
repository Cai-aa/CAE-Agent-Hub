param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("freecad", "elmer", "paraview")]
    [string]$Server
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$env:OPEN_CAE_CONFIG = Join-Path $Root "configs\open-cae.local.toml"
$env:PYTHONPATH = @(
    (Join-Path $Root "packages\open-cae-core\src"),
    (Join-Path $Root "mcp\freecad\src"),
    (Join-Path $Root "mcp\elmer\src"),
    (Join-Path $Root "mcp\paraview\src")
) -join ";"

$Module = @{
    freecad = "freecad_mcp.server"
    elmer = "elmer_mcp.server"
    paraview = "paraview_mcp.server"
}[$Server]

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Run scripts/install.ps1 first; missing $Python"
}
& $Python -m $Module
