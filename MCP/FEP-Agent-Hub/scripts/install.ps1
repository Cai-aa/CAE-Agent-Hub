param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"

& $Python -m venv --system-site-packages $Venv
$VenvPython = Join-Path $Venv "Scripts\python.exe"
foreach ($Package in @("packages\open-cae-core", "mcp\freecad", "mcp\elmer", "mcp\paraview")) {
    & $VenvPython -m pip install --no-deps --no-build-isolation -e (Join-Path $Root $Package)
}

& $VenvPython -c "import mcp, meshio, open_cae_core, freecad_mcp, elmer_mcp, paraview_mcp; print('OpenCAE runtime imports: OK')"

Write-Host "Installed OpenCAE into $Venv"
