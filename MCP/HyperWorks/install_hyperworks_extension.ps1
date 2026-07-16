param(
    [string] $Destination = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Altair\CustomPlugins\HyperWorksMCP'),
    [string] $ConfigPath = (Join-Path $env:LOCALAPPDATA 'HyperWorksMCP\bridge.json'),
    [string] $Workspace = (Join-Path $PSScriptRoot 'workspace'),
    [int] $Port = 48761,
    [bool] $RegisterExtension = $true,
    [string] $ExtensionRegistry = (Join-Path $env:USERPROFILE '.altair\extensions.xml')
)

$ErrorActionPreference = 'Stop'

if ($Port -lt 1024 -or $Port -gt 65535) {
    throw 'Port must be between 1024 and 65535.'
}

$source = Join-Path $PSScriptRoot 'hyperworks_extension'
if (-not (Test-Path -LiteralPath (Join-Path $source 'extension.xml') -PathType Leaf)) {
    throw "Extension source not found: $source"
}

$workspaceFull = [IO.Path]::GetFullPath($Workspace)
$destinationFull = [IO.Path]::GetFullPath($Destination)
$configFull = [IO.Path]::GetFullPath($ConfigPath)

New-Item -ItemType Directory -Force -Path $destinationFull | Out-Null
New-Item -ItemType Directory -Force -Path $workspaceFull | Out-Null
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($configFull)) | Out-Null

Copy-Item -LiteralPath (Join-Path $source 'extension.xml') -Destination $destinationFull -Force
Copy-Item -LiteralPath (Join-Path $source 'load.py') -Destination $destinationFull -Force
Copy-Item -LiteralPath (Join-Path $source 'unload.py') -Destination $destinationFull -Force
$packageSource = Join-Path $source 'hyperworks_mcp_extension'
$packageDestination = Join-Path $destinationFull 'hyperworks_mcp_extension'
New-Item -ItemType Directory -Force -Path $packageDestination | Out-Null
Get-ChildItem -LiteralPath $packageSource -File -Filter '*.py' |
    Copy-Item -Destination $packageDestination -Force
$installedCache = Join-Path $packageDestination '__pycache__'
if (Test-Path -LiteralPath $installedCache -PathType Container) {
    Remove-Item -LiteralPath $installedCache -Recurse -Force
}

$token = $null
if (Test-Path -LiteralPath $configFull -PathType Leaf) {
    try {
        $existing = Get-Content -Raw -LiteralPath $configFull | ConvertFrom-Json
        if ($existing.token -and ([string]$existing.token).Length -ge 32) {
            $token = [string]$existing.token
        }
    } catch {
        Write-Warning "Existing bridge config was invalid and will be replaced: $configFull"
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
    allowed_roots = @($workspaceFull)
    request_timeout_seconds = 600
}
$json = $config | ConvertTo-Json -Depth 4
[IO.File]::WriteAllText($configFull, $json, (New-Object Text.UTF8Encoding($false)))

if ($RegisterExtension) {
    $registryFull = [IO.Path]::GetFullPath($ExtensionRegistry)
    $registryDirectory = [IO.Path]::GetDirectoryName($registryFull)
    New-Item -ItemType Directory -Force -Path $registryDirectory | Out-Null

    if (Test-Path -LiteralPath $registryFull -PathType Leaf) {
        [xml] $registry = Get-Content -Raw -LiteralPath $registryFull
    } else {
        [xml] $registry = @'
<?xml version="1.0" encoding="UTF-8"?>
<section name="Altair Settings">
  <section name="Unity">
    <section name="Session">
      <section name="ExtensionManager">
        <section name="UserExtensions">
          <section name="Registered" />
        </section>
      </section>
    </section>
  </section>
</section>
'@
    }

    $registered = $registry.SelectSingleNode(
        "/section[@name='Altair Settings']/section[@name='Unity']/section[@name='Session']/section[@name='ExtensionManager']/section[@name='UserExtensions']/section[@name='Registered']"
    )
    if (-not $registered) {
        throw "Unsupported Altair extension registry structure: $registryFull"
    }

    foreach ($existingEntry in @($registered.SelectNodes("entry[@name='HyperWorks MCP Bridge']"))) {
        [void] $registered.RemoveChild($existingEntry)
    }
    $entry = $registry.CreateElement('entry')
    $entry.SetAttribute('name', 'HyperWorks MCP Bridge')
    $entry.SetAttribute('value', (Join-Path $destinationFull 'extension.xml'))
    $entry.SetAttribute('type', 'string')
    [void] $registered.AppendChild($entry)

    $settings = New-Object Xml.XmlWriterSettings
    $settings.Encoding = New-Object Text.UTF8Encoding($false)
    $settings.Indent = $true
    $settings.NewLineChars = "`r`n"
    $writer = [Xml.XmlWriter]::Create($registryFull, $settings)
    try {
        $registry.Save($writer)
    } finally {
        $writer.Dispose()
    }
}

Write-Host "Installed HyperWorks MCP Extension: $destinationFull"
Write-Host "Bridge config: $configFull"
Write-Host "Allowed save root: $workspaceFull"
if ($RegisterExtension) {
    Write-Host "Registered extension: $registryFull"
}
Write-Host 'Restart HyperMesh, then enable HyperWorks MCP Bridge in File > Extension Manager if it is not already enabled.'
