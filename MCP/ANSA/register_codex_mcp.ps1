param(
    [Parameter(Mandatory = $true)]
    [string] $PythonExe,
    [string] $Workspace = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'ANSAMCP\workspace'),
    [string] $ConfigPath = (Join-Path $env:LOCALAPPDATA 'ANSAMCP\bridge.json'),
    [string] $AnsaHome = $env:ANSA_HOME,
    [string] $AnsaExecutable = $env:ANSA_EXECUTABLE,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Test-ExactJsonInteger {
    param($Value)

    return ($Value -is [sbyte] -or
        $Value -is [byte] -or
        $Value -is [int16] -or
        $Value -is [uint16] -or
        $Value -is [int32] -or
        $Value -is [uint32] -or
        $Value -is [int64] -or
        $Value -is [uint64])
}

function Test-AbsoluteFileSystemPath {
    param([string] $Value)

    if ([string]::IsNullOrWhiteSpace($Value) -or -not [IO.Path]::IsPathRooted($Value)) {
        return $false
    }
    try {
        $root = [IO.Path]::GetPathRoot($Value)
        $null = [IO.Path]::GetFullPath($Value)
    }
    catch {
        return $false
    }

    # Path.IsPathRooted accepts drive-relative values such as C:folder and
    # root-relative values such as \folder. Require a complete drive or UNC
    # root so containment is independent of the process current directory.
    return ($root -match '^[A-Za-z]:[\\/]$' -or
        $root -match '^\\\\[^\\/]+[\\/][^\\/]+[\\/]?$')
}

function Get-CanonicalPath {
    param([Parameter(Mandatory = $true)][string] $Value)

    $full = [IO.Path]::GetFullPath($Value).Replace(
        [IO.Path]::AltDirectorySeparatorChar,
        [IO.Path]::DirectorySeparatorChar
    )
    $root = [IO.Path]::GetPathRoot($full)
    while ($full.Length -gt $root.Length -and
        ($full.EndsWith([string] [IO.Path]::DirectorySeparatorChar) -or
            $full.EndsWith([string] [IO.Path]::AltDirectorySeparatorChar))) {
        $full = $full.Substring(0, $full.Length - 1)
    }
    return $full
}

function Test-PathWithinRoot {
    param(
        [Parameter(Mandatory = $true)][string] $Candidate,
        [Parameter(Mandatory = $true)][string] $Root
    )

    if ([string]::Equals($Candidate, $Root, [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $prefix = if ($Root.EndsWith([string] [IO.Path]::DirectorySeparatorChar)) {
        $Root
    }
    else {
        $Root + [IO.Path]::DirectorySeparatorChar
    }
    return $Candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Invoke-CapturedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Command,
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    # Capture native output so a failing dependency cannot accidentally echo
    # bridge configuration (and therefore its bearer token) to the console.
    $lines = @(& $Command @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {
        $exitCode = 0
    }
    return [pscustomobject]@{
        ExitCode = [int] $exitCode
        Output = (($lines | ForEach-Object { [string] $_ }) -join "`n")
    }
}

function Invoke-PythonImportPreflight {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Command,
        [Parameter(Mandatory = $true)]
        [hashtable] $Environment
    )

    $saved = @{}
    try {
        foreach ($name in $Environment.Keys) {
            $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            [Environment]::SetEnvironmentVariable($name, [string] $Environment[$name], 'Process')
        }

        $preflightCode = "from ansa_mcp.server import mcp; assert getattr(mcp, 'strict_input_validation', None) is True"
        $result = Invoke-CapturedCommand -Command $Command -Arguments @('-c', $preflightCode)
        if ($result.ExitCode -ne 0) {
            throw "Python preflight could not load the strict ansa_mcp server (exit code $($result.ExitCode))."
        }
    }
    finally {
        foreach ($name in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
        }
    }
}

function ConvertTo-TomlBasicString {
    param([Parameter(Mandatory = $true)][string] $Value)

    $builder = New-Object System.Text.StringBuilder
    foreach ($character in $Value.ToCharArray()) {
        switch ([int] $character) {
            8  { [void] $builder.Append('\b'); continue }
            9  { [void] $builder.Append('\t'); continue }
            10 { [void] $builder.Append('\n'); continue }
            12 { [void] $builder.Append('\f'); continue }
            13 { [void] $builder.Append('\r'); continue }
            34 { [void] $builder.Append('\"'); continue }
            92 { [void] $builder.Append('\\'); continue }
            default {
                if ([int] $character -lt 0x20) {
                    [void] $builder.Append(('\u{0:x4}' -f [int] $character))
                }
                else {
                    [void] $builder.Append($character)
                }
            }
        }
    }
    return '"' + $builder.ToString() + '"'
}

function Get-AnsaSection {
    param([Parameter(Mandatory = $true)][string] $Text)

    $headerPattern = '(?m)^[ \t]*\[mcp_servers\.(?:ansa|"ansa")\][ \t]*(?:#.*)?(?:\r?\n|$)'
    $header = [regex]::Match($Text, $headerPattern)
    if (-not $header.Success) {
        throw 'Codex configuration does not contain the exact mcp_servers.ansa table.'
    }

    $bodyStart = $header.Index + $header.Length
    $tail = $Text.Substring($bodyStart)
    $nextHeader = [regex]::Match($tail, '(?m)^[ \t]*\[')
    $bodyLength = if ($nextHeader.Success) { $nextHeader.Index } else { $tail.Length }

    return [pscustomobject]@{
        HeaderEnd = $bodyStart
        BodyLength = $bodyLength
        Body = $Text.Substring($bodyStart, $bodyLength)
    }
}

function Set-AnsaCodexSettings {
    param(
        [Parameter(Mandatory = $true)][string] $CodexConfigPath,
        [Parameter(Mandatory = $true)][string] $WorkingDirectory
    )

    if (-not (Test-Path -LiteralPath $CodexConfigPath -PathType Leaf)) {
        throw 'Codex did not create its configuration file.'
    }

    $text = [IO.File]::ReadAllText($CodexConfigPath)
    $section = Get-AnsaSection -Text $text
    $newline = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }

    # These keys belong to the parent mcp_servers.ansa table, before any
    # [mcp_servers.ansa.env] subtable. Remove stale copies only from that exact
    # parent body, then insert the authoritative values.
    $managedPattern = '(?m)^[ \t]*(?:cwd|startup_timeout_sec|tool_timeout_sec)[ \t]*=[^\r\n]*(?:\r?\n|$)'
    $cleanBody = [regex]::Replace($section.Body, $managedPattern, '')
    $managed = 'cwd = ' + (ConvertTo-TomlBasicString -Value $WorkingDirectory) + $newline +
        'startup_timeout_sec = 30' + $newline +
        'tool_timeout_sec = 180' + $newline

    $updated = $text.Substring(0, $section.HeaderEnd) + $managed + $cleanBody +
        $text.Substring($section.HeaderEnd + $section.BodyLength)

    $temporaryPath = $CodexConfigPath + '.ansa-mcp-write-' + [guid]::NewGuid().ToString('N') + '.tmp'
    $replaceBackupPath = $CodexConfigPath + '.ansa-mcp-replace-' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        $encoding = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($temporaryPath, $updated, $encoding)
        [IO.File]::Replace($temporaryPath, $CodexConfigPath, $replaceBackupPath)
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            [IO.File]::Delete($temporaryPath)
        }
        if (Test-Path -LiteralPath $replaceBackupPath -PathType Leaf) {
            [IO.File]::Delete($replaceBackupPath)
        }
    }
}

function Assert-AnsaCodexSettings {
    param(
        [Parameter(Mandatory = $true)][string] $CodexConfigPath,
        [Parameter(Mandatory = $true)][string] $WorkingDirectory
    )

    $text = [IO.File]::ReadAllText($CodexConfigPath)
    $body = (Get-AnsaSection -Text $text).Body
    $expectedCwd = 'cwd = ' + (ConvertTo-TomlBasicString -Value $WorkingDirectory)
    if (-not [regex]::IsMatch($body, '(?m)^[ \t]*startup_timeout_sec[ \t]*=[ \t]*30[ \t]*(?:#.*)?$')) {
        throw 'Codex startup timeout was not persisted.'
    }
    if (-not [regex]::IsMatch($body, '(?m)^[ \t]*tool_timeout_sec[ \t]*=[ \t]*180[ \t]*(?:#.*)?$')) {
        throw 'Codex tool timeout was not persisted.'
    }
    if (-not (($body -split '\r?\n') -contains $expectedCwd)) {
        throw 'Codex MCP working directory was not persisted.'
    }
}

function Get-CodexConfigPath {
    $configuredRoot = [Environment]::GetEnvironmentVariable('CODEX_HOME', 'Process')
    if ([string]::IsNullOrWhiteSpace($configuredRoot)) {
        $configuredRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
    }
    return Join-Path ([IO.Path]::GetFullPath($configuredRoot)) 'config.toml'
}

$pythonFull = [IO.Path]::GetFullPath($PythonExe)
if (-not (Test-Path -LiteralPath $pythonFull -PathType Leaf)) {
    throw "Python executable not found: $pythonFull"
}

$workspaceFull = Get-CanonicalPath -Value $Workspace
$configFull = [IO.Path]::GetFullPath($ConfigPath)
if (-not (Test-Path -LiteralPath $configFull -PathType Leaf)) {
    throw "Bridge config not found: $configFull. Run install_ansa_bridge.ps1 first."
}

$bridgeConfigText = [IO.File]::ReadAllText($configFull)
if ($bridgeConfigText -notmatch '^\s*\{') {
    throw "Bridge config root must be a JSON object: $configFull"
}
try {
    $bridgeConfig = ConvertFrom-Json -InputObject $bridgeConfigText
}
catch {
    throw "Bridge config is not valid JSON: $configFull"
}
if ($null -eq $bridgeConfig -or -not ($bridgeConfig -is [pscustomobject])) {
    throw "Bridge config root must be a JSON object: $configFull"
}
$bridgePropertyNames = @($bridgeConfig.PSObject.Properties.Name)
if ('version' -notin $bridgePropertyNames -or
    'host' -notin $bridgePropertyNames -or
    'port' -notin $bridgePropertyNames -or
    'token' -notin $bridgePropertyNames -or
    'allowed_roots' -notin $bridgePropertyNames) {
    throw "Bridge config is missing required fields: $configFull"
}
if (-not (Test-ExactJsonInteger $bridgeConfig.version) -or [int64] $bridgeConfig.version -ne 1) {
    throw "Bridge config version must be the integer 1: $configFull"
}
if (-not ($bridgeConfig.host -is [string]) -or
    -not [string]::Equals($bridgeConfig.host, '127.0.0.1', [StringComparison]::Ordinal)) {
    throw "Bridge config host must be 127.0.0.1: $configFull"
}
if (-not (Test-ExactJsonInteger $bridgeConfig.port) -or
    [int64] $bridgeConfig.port -lt 1024 -or [int64] $bridgeConfig.port -gt 65535) {
    throw "Bridge config port must be an integer from 1024 through 65535: $configFull"
}
if (-not ($bridgeConfig.token -is [string]) -or
    $bridgeConfig.token -notmatch '^[0-9a-fA-F]{64}$') {
    throw "Bridge config contains an invalid credential: $configFull"
}
if ('request_timeout_seconds' -in $bridgePropertyNames -and
    (-not (Test-ExactJsonInteger $bridgeConfig.request_timeout_seconds) -or
        [int64] $bridgeConfig.request_timeout_seconds -lt 10 -or
        [int64] $bridgeConfig.request_timeout_seconds -gt 3600)) {
    throw "Bridge config request_timeout_seconds must be an integer from 10 through 3600: $configFull"
}

$allowedRootValues = $bridgeConfig.allowed_roots
if (-not ($allowedRootValues -is [System.Array]) -or $allowedRootValues.Count -eq 0) {
    throw "Bridge config allowed_roots must be a non-empty JSON array: $configFull"
}

# Validate and normalize every root before considering workspace containment.
# This prevents one good first entry from hiding a malformed later entry.
$normalizedAllowedRoots = @()
$rootIndex = 0
foreach ($allowedRoot in $allowedRootValues) {
    if (-not ($allowedRoot -is [string]) -or
        [string]::IsNullOrWhiteSpace($allowedRoot) -or
        -not (Test-AbsoluteFileSystemPath -Value $allowedRoot)) {
        throw "Bridge config allowed_roots[$rootIndex] must be a non-empty absolute path: $configFull"
    }
    try {
        $normalizedAllowedRoots += Get-CanonicalPath -Value $allowedRoot
    }
    catch {
        throw "Bridge config allowed_roots[$rootIndex] is not a valid absolute path: $configFull"
    }
    $rootIndex += 1
}

$workspaceAllowed = $false
foreach ($allowedRoot in $normalizedAllowedRoots) {
    if (Test-PathWithinRoot -Candidate $workspaceFull -Root $allowedRoot) {
        $workspaceAllowed = $true
        break
    }
}
if (-not $workspaceAllowed) {
    throw "Workspace must equal or be contained by a configured allowed_root: $workspaceFull"
}

New-Item -ItemType Directory -Force -Path $workspaceFull | Out-Null
if (-not (Test-Path -LiteralPath $workspaceFull -PathType Container)) {
    throw "Workspace directory is not available: $workspaceFull"
}

$targetEnvironment = @{
    ANSA_MCP_BRIDGE_CONFIG = $configFull
    ANSA_MCP_WORKSPACE = $workspaceFull
    PYTHONUTF8 = '1'
}
$ansaHomeFull = $null
if (-not [string]::IsNullOrWhiteSpace($AnsaHome)) {
    $ansaHomeFull = [IO.Path]::GetFullPath($AnsaHome)
    $targetEnvironment.ANSA_HOME = $ansaHomeFull
}
$ansaExecutableFull = $null
if (-not [string]::IsNullOrWhiteSpace($AnsaExecutable)) {
    $ansaExecutableFull = [IO.Path]::GetFullPath($AnsaExecutable)
    $targetEnvironment.ANSA_EXECUTABLE = $ansaExecutableFull
}

# Validate the exact Python/environment tuple before examining or changing the
# user's Codex registration. This constructs the FastMCP server and verifies its
# strict input mode, but does not start the stdio transport.
Invoke-PythonImportPreflight -Command $pythonFull -Environment $targetEnvironment

$codexCommand = Get-Command codex.cmd -ErrorAction SilentlyContinue
if (-not $codexCommand) {
    $codexCommand = Get-Command codex -ErrorAction Stop
}
$codexPath = $codexCommand.Source

$getResult = Invoke-CapturedCommand -Command $codexPath -Arguments @('mcp', 'get', 'ansa', '--json')
$registrationExists = $false
$existingSnapshot = $null
if ($getResult.ExitCode -eq 0) {
    try {
        $existingSnapshot = $getResult.Output | ConvertFrom-Json
        if ($null -eq $existingSnapshot) {
            throw 'empty snapshot'
        }
    }
    catch {
        throw 'Codex returned an invalid snapshot for the existing ansa registration; no changes were made.'
    }
    $registrationExists = $true
}
elseif ($getResult.Output -notmatch '(?i)(no MCP server named|MCP server.+not found|unknown MCP server|does not exist)') {
    throw "Could not safely determine whether the ansa MCP registration exists (exit code $($getResult.ExitCode)); no changes were made."
}

if ($registrationExists -and -not $Force) {
    throw "Codex MCP server 'ansa' already exists. Re-run with -Force to replace it transactionally."
}

$codexConfigPath = Get-CodexConfigPath
$codexConfigExisted = Test-Path -LiteralPath $codexConfigPath -PathType Leaf
$backupPath = $null
if ($codexConfigExisted) {
    $backupPath = $codexConfigPath + '.ansa-mcp-backup-' + [guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::Copy($codexConfigPath, $backupPath, $false)
}

$transactionStarted = $false
try {
    if ($registrationExists) {
        $transactionStarted = $true
        $removeResult = Invoke-CapturedCommand -Command $codexPath -Arguments @('mcp', 'remove', 'ansa')
        if ($removeResult.ExitCode -ne 0) {
            throw "Codex could not remove the prior ansa registration (exit code $($removeResult.ExitCode))."
        }
    }

    $arguments = @(
        'mcp', 'add', 'ansa',
        '--env', "ANSA_MCP_BRIDGE_CONFIG=$configFull",
        '--env', "ANSA_MCP_WORKSPACE=$workspaceFull",
        '--env', 'PYTHONUTF8=1'
    )
    if ($null -ne $ansaHomeFull) {
        $arguments += @('--env', "ANSA_HOME=$ansaHomeFull")
    }
    if ($null -ne $ansaExecutableFull) {
        $arguments += @('--env', "ANSA_EXECUTABLE=$ansaExecutableFull")
    }
    $arguments += @('--', $pythonFull, '-m', 'ansa_mcp')

    $transactionStarted = $true
    $addResult = Invoke-CapturedCommand -Command $codexPath -Arguments $arguments
    if ($addResult.ExitCode -ne 0) {
        throw "Codex MCP add failed with exit code $($addResult.ExitCode)."
    }

    $workingDirectory = [IO.Path]::GetFullPath($PSScriptRoot)
    Set-AnsaCodexSettings -CodexConfigPath $codexConfigPath -WorkingDirectory $workingDirectory
    Assert-AnsaCodexSettings -CodexConfigPath $codexConfigPath -WorkingDirectory $workingDirectory

    # A second JSON read validates that Codex can parse the persisted TOML and
    # resolve the newly registered server. Its output remains captured/redacted.
    $verifyResult = Invoke-CapturedCommand -Command $codexPath -Arguments @('mcp', 'get', 'ansa', '--json')
    if ($verifyResult.ExitCode -ne 0) {
        throw "Codex could not read back the ansa registration (exit code $($verifyResult.ExitCode))."
    }
    try {
        $verifiedSnapshot = $verifyResult.Output | ConvertFrom-Json
        if ($null -eq $verifiedSnapshot) {
            throw 'empty snapshot'
        }
    }
    catch {
        throw 'Codex returned invalid JSON while verifying the ansa registration.'
    }

    if ($null -ne $backupPath -and (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
        [IO.File]::Delete($backupPath)
    }
}
catch {
    $failureMessage = $_.Exception.Message
    $restoreFailure = $null
    if ($transactionStarted) {
        try {
            if ($codexConfigExisted) {
                if ($null -eq $backupPath -or -not (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
                    throw 'The Codex configuration backup is unavailable.'
                }
                [IO.File]::Copy($backupPath, $codexConfigPath, $true)
            }
            elseif (Test-Path -LiteralPath $codexConfigPath -PathType Leaf) {
                [IO.File]::Delete($codexConfigPath)
            }
        }
        catch {
            $restoreFailure = $_.Exception.Message
        }
    }

    if ($null -eq $restoreFailure) {
        if ($null -ne $backupPath -and (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
            [IO.File]::Delete($backupPath)
        }
        if ($transactionStarted) {
            throw "Codex MCP registration failed; the previous Codex configuration was restored. $failureMessage"
        }
        throw $failureMessage
    }

    throw "Codex MCP registration failed and automatic restoration also failed. Backup retained at: $backupPath. Restore error: $restoreFailure"
}

Write-Host 'Registered MCP server: ansa'
Write-Host 'Persisted startup_timeout_sec=30 and tool_timeout_sec=180.'
Write-Host 'Verify registration with: codex.cmd mcp get ansa'
Write-Host 'Registration alone does not prove that the in-ANSA bridge is loaded.'
