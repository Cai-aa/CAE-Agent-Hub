param(
    [Parameter(Mandatory = $true)]
    [string] $Destination,
    [string] $ConfigPath = (Join-Path $env:LOCALAPPDATA 'ANSAMCP\bridge.json'),
    [string] $Workspace = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'ANSAMCP\workspace'),
    [int] $Port = 48762
)

$ErrorActionPreference = 'Stop'

if ($Port -lt 1024 -or $Port -gt 65535) {
    throw 'Port must be between 1024 and 65535.'
}

$source = Join-Path $PSScriptRoot 'ansa_plugin'
$startScript = Join-Path $source 'start_ansa_mcp.py'
if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) {
    throw "ANSA bridge source was not found: $startScript"
}

$sourceFull = [IO.Path]::GetFullPath($source)
$destinationFull = [IO.Path]::GetFullPath($Destination)
$workspaceFull = [IO.Path]::GetFullPath($Workspace)
$configFull = [IO.Path]::GetFullPath($ConfigPath)
$sourcePrefix = $sourceFull.TrimEnd(
    [IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar
) + [IO.Path]::DirectorySeparatorChar

New-Item -ItemType Directory -Force -Path $destinationFull | Out-Null
New-Item -ItemType Directory -Force -Path $workspaceFull | Out-Null
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($configFull)) | Out-Null

# Copy only this project's bridge payload.  In particular, never create,
# replace, rename, or delete ANSA_TRANSL.py in the selected script directory.
$files = Get-ChildItem -LiteralPath $sourceFull -File -Recurse |
    Where-Object {
        $_.Name -ne 'ANSA_TRANSL.py' -and
        $_.Extension -ne '.pyc' -and
        $_.FullName -notmatch '[\\/]__pycache__[\\/]'
    }
foreach ($file in $files) {
    # IO.Path.GetRelativePath is unavailable in Windows PowerShell 5.1.  Every
    # item came from Get-ChildItem under $sourceFull, but still verify the
    # prefix before deriving a relative payload path.
    if (-not $file.FullName.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Bridge payload escaped its source directory: $($file.FullName)"
    }
    $relative = $file.FullName.Substring($sourcePrefix.Length)
    if ([IO.Path]::GetFileName($relative) -eq 'ANSA_TRANSL.py') {
        continue
    }
    $target = Join-Path $destinationFull $relative
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($target)) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
}

$token = $null
if (Test-Path -LiteralPath $configFull -PathType Leaf) {
    try {
        $existing = Get-Content -Raw -LiteralPath $configFull | ConvertFrom-Json
        if ($existing.token -and ([string] $existing.token) -match '^[0-9a-fA-F]{64}$') {
            $token = [string] $existing.token
        }
    } catch {
        Write-Warning "Existing bridge config is invalid and will be replaced: $configFull"
    }
}
if (-not $token) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    $token = ([BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
}

$config = [ordered]@{
    version = 1
    host = '127.0.0.1'
    port = $Port
    token = $token
    plugin_root = $destinationFull
    allowed_roots = @($workspaceFull)
    request_timeout_seconds = 120
}
$json = $config | ConvertTo-Json -Depth 4
[IO.File]::WriteAllText($configFull, $json, (New-Object Text.UTF8Encoding($false)))

# ANSA can inherit a different LOCALAPPDATA than a packaged MCP host. Pin the
# installed loader to this exact config without copying its secret token into
# the plugin directory. start_ansa_mcp.py checks the plugin_root on readback.
$configPointer = Join-Path $destinationFull 'bridge_config_path.txt'
[IO.File]::WriteAllText(
    $configPointer,
    $configFull + [Environment]::NewLine,
    (New-Object Text.UTF8Encoding($false))
)

Write-Host "Installed ANSA MCP bridge files: $destinationFull"
Write-Host "Bridge config: $configFull"
Write-Host "Bridge config path pointer: $configPointer"
Write-Host "Allowed workspace: $workspaceFull"
if (Test-Path -LiteralPath (Join-Path $destinationFull 'ANSA_TRANSL.py') -PathType Leaf) {
    Write-Host 'Existing ANSA_TRANSL.py was left unchanged.'
}
Write-Host 'No ANSA process was started, stopped, or restarted.'
Write-Host "In the intended ANSA session, manually load: $(Join-Path $destinationFull 'start_ansa_mcp.py')"
Write-Host "For Start/Status/Stop buttons without Plugin Manager, load: $(Join-Path $destinationFull 'ansa_mcp_controls.py')"
