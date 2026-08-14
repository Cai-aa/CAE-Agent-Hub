param(
    [string]$Project = ""
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

$Arguments = @(Join-Path $PSScriptRoot "run_heat_smoke.py")
if ($Project) {
    $Arguments += @("--project", $Project)
}
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Run scripts/install.ps1 first; missing $Python"
}
& $Python @Arguments
