param(
  [string]$OutputDir = "$env:USERPROFILE\Desktop\zhinengti\4\FluentOps"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stage = $OutputDir
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item (Join-Path $root "cfd_agent") $stage -Recurse -Force
Copy-Item (Join-Path $root "viewer\dist") (Join-Path $stage "viewer") -Recurse -Force -ErrorAction SilentlyContinue
@"
@echo off
setlocal
python "%~dp0cfd_agent\pyfluent_runner.py" --project "%~dp0projects\UAV-2026-0915-01"
"@ | Set-Content (Join-Path $stage "启动FluentOps.cmd") -Encoding ascii

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
  Write-Warning "PyInstaller is not installed. Run: python -m pip install pyinstaller"
  Write-Host "Source bundle prepared at $stage"
  exit 0
}

python -m PyInstaller --noconfirm --clean --onefile --name FluentOps `
  --distpath $stage --workpath (Join-Path $env:TEMP "FluentOps-build") `
  (Join-Path $root "cfd_agent\pyfluent_runner.py")
Write-Host "EXE created: $(Join-Path $stage 'FluentOps.exe')"
