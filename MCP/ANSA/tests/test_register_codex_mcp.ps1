param(
    [string] $ScriptPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'register_codex_mcp.ps1')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-True {
    param([bool] $Condition, [string] $Message)
    if (-not $Condition) {
        throw "ASSERTION FAILED: $Message"
    }
}

function Set-TextUtf8 {
    param([string] $Path, [string] $Text)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Get-FileBase64 {
    param([string] $Path)
    return [Convert]::ToBase64String([IO.File]::ReadAllBytes($Path))
}

function New-BridgeConfigJson {
    param(
        [Parameter(Mandatory = $true)][string] $AllowedRoot,
        [Parameter(Mandatory = $true)][string] $Secret,
        [hashtable] $Changes = @{}
    )

    $data = [ordered]@{
        version = 1
        host = '127.0.0.1'
        port = 48762
        token = $Secret
        allowed_roots = @($AllowedRoot)
        request_timeout_seconds = 120
    }
    foreach ($key in $Changes.Keys) {
        $data[$key] = $Changes[$key]
    }
    return ($data | ConvertTo-Json -Depth 4)
}

function ConvertTo-WindowsCommandLineArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string] $Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') {
        return $Value
    }

    $builder = New-Object System.Text.StringBuilder
    [void] $builder.Append('"')
    $backslashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') {
            $backslashes += 1
            continue
        }
        if ($character -eq '"') {
            [void] $builder.Append(('\' * (($backslashes * 2) + 1)))
            [void] $builder.Append('"')
            $backslashes = 0
            continue
        }
        if ($backslashes -gt 0) {
            [void] $builder.Append(('\' * $backslashes))
            $backslashes = 0
        }
        [void] $builder.Append($character)
    }
    if ($backslashes -gt 0) {
        [void] $builder.Append(('\' * ($backslashes * 2)))
    }
    [void] $builder.Append('"')
    return $builder.ToString()
}

function Invoke-RegistrationCase {
    param(
        [string] $PythonExe,
        [string] $Workspace,
        [string] $BridgeConfig,
        [string] $MockBin,
        [string] $CodexRoot,
        [string] $ActionLog,
        [string] $PythonLog,
        [bool] $UseForce = $false,
        [bool] $FailAdd = $false,
        [bool] $FailPython = $false,
        [string] $AnsaHome = '',
        [string] $AnsaExecutable = ''
    )

    # Run each case in a clean child process so command discovery cannot reuse a
    # cached real codex.cmd from the developer's interactive session.
    $hostExecutable = (Get-Process -Id $PID).Path
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $hostExecutable
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $childArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath,
        '-PythonExe', $PythonExe, '-Workspace', $Workspace, '-ConfigPath', $BridgeConfig)
    if ($UseForce) { $childArguments += '-Force' }
    if (-not [string]::IsNullOrWhiteSpace($AnsaHome)) {
        $childArguments += @('-AnsaHome', $AnsaHome)
    }
    if (-not [string]::IsNullOrWhiteSpace($AnsaExecutable)) {
        $childArguments += @('-AnsaExecutable', $AnsaExecutable)
    }
    $startInfo.Arguments = (($childArguments | ForEach-Object { ConvertTo-WindowsCommandLineArgument -Value $_ }) -join ' ')
    $startInfo.EnvironmentVariables['PATH'] = $MockBin
    $startInfo.EnvironmentVariables['CODEX_HOME'] = $CodexRoot
    $startInfo.EnvironmentVariables['MOCK_ACTION_LOG'] = $ActionLog
    $startInfo.EnvironmentVariables['MOCK_PYTHON_LOG'] = $PythonLog
    if ($FailAdd) { $startInfo.EnvironmentVariables['MOCK_ADD_FAIL'] = '1' } else { [void] $startInfo.EnvironmentVariables.Remove('MOCK_ADD_FAIL') }
    if ($FailPython) { $startInfo.EnvironmentVariables['MOCK_PYTHON_FAIL'] = '1' } else { [void] $startInfo.EnvironmentVariables.Remove('MOCK_PYTHON_FAIL') }

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void] $process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $output = $stdoutTask.Result + $stderrTask.Result
    return [pscustomobject]@{
        Succeeded = ($process.ExitCode -eq 0)
        Output = $output
    }
}

$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref] $tokens, [ref] $parseErrors) | Out-Null
Assert-True ($parseErrors.Count -eq 0) ('PowerShell parser errors: ' + (($parseErrors | ForEach-Object { $_.ToString() }) -join '; '))

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('ansa-register-test-' + [guid]::NewGuid().ToString('N'))
$mockBin = Join-Path $testRoot 'bin'
$codexRoot = Join-Path $testRoot 'codex'
$allowedRoot = Join-Path $testRoot 'allowed'
$workspace = Join-Path $allowedRoot 'workspace'
$bridgeConfig = Join-Path $testRoot 'bridge.json'
$actionLog = Join-Path $testRoot 'codex-actions.log'
$pythonLog = Join-Path $testRoot 'python-actions.log'
$codexConfig = Join-Path $codexRoot 'config.toml'
$secret = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'

try {
    [IO.Directory]::CreateDirectory($mockBin) | Out-Null
    [IO.Directory]::CreateDirectory($codexRoot) | Out-Null
    $validBridgeConfigText = New-BridgeConfigJson -AllowedRoot $allowedRoot -Secret $secret
    Set-TextUtf8 $bridgeConfig $validBridgeConfigText

    $pythonScript = @'
Add-Content -LiteralPath $env:MOCK_PYTHON_LOG -Value ('python|' + ($args -join '|') + '|config=' + $env:ANSA_MCP_BRIDGE_CONFIG + '|workspace=' + $env:ANSA_MCP_WORKSPACE)
if ($env:MOCK_PYTHON_FAIL -eq '1') { exit 23 }
$expected = "from ansa_mcp.server import mcp; assert getattr(mcp, 'strict_input_validation', None) is True"
if ($args.Count -ne 2 -or $args[0] -ne '-c' -or $args[1] -ne $expected) { exit 24 }
exit 0
'@
    Set-TextUtf8 (Join-Path $mockBin 'fake-python.ps1') $pythonScript
    $powershellExe = (Get-Process -Id $PID).Path
    Set-TextUtf8 (Join-Path $mockBin 'fake-python.cmd') ('@"' + $powershellExe + '" -NoProfile -ExecutionPolicy Bypass -File "%~dp0fake-python.ps1" %*' + "`r`n")

    $codexScript = @'
$commandLine = $args -join '|'
Add-Content -LiteralPath $env:MOCK_ACTION_LOG -Value $commandLine
$configPath = Join-Path $env:CODEX_HOME 'config.toml'
$verb = if ($args.Count -ge 2) { $args[1] } else { '' }
switch ($verb) {
    'get' {
        $text = if (Test-Path -LiteralPath $configPath) { [IO.File]::ReadAllText($configPath) } else { '' }
        if ($text -match '(?m)^\[mcp_servers\.ansa\]\r?$') {
            Write-Output '{"name":"ansa","transport":{"type":"stdio","command":"fake","args":[],"env":{}}}'
            exit 0
        }
        [Console]::Error.WriteLine("Error: No MCP server named 'ansa' found.")
        exit 1
    }
    'remove' {
        [IO.File]::WriteAllText($configPath, "[unrelated]`nvalue = `"keep`"`n", (New-Object System.Text.UTF8Encoding($false)))
        exit 0
    }
    'add' {
        if ($env:MOCK_ADD_FAIL -eq '1') {
            [Console]::Error.WriteLine('simulated add failure')
            exit 17
        }
        $newText = @"
[unrelated]
value = "keep"

[mcp_servers.ansa]
command = "fake-python"
args = ["-m", "ansa_mcp"]

[mcp_servers.ansa.env]
PYTHONUTF8 = "1"
"@
        [IO.File]::WriteAllText($configPath, $newText, (New-Object System.Text.UTF8Encoding($false)))
        exit 0
    }
    default { exit 90 }
}
'@
    Set-TextUtf8 (Join-Path $mockBin 'mock-codex.ps1') $codexScript
    Set-TextUtf8 (Join-Path $mockBin 'codex.cmd') ('@"' + $powershellExe + '" -NoProfile -ExecutionPolicy Bypass -File "%~dp0mock-codex.ps1" %*' + "`r`n")

    $initialConfig = @'
[unrelated]
value = "keep"

[mcp_servers.ansa]
command = "old-python"
args = ["-m", "old_server"]
startup_timeout_sec = 9
tool_timeout_sec = 10

[mcp_servers.ansa.env]
OLD_VALUE = "preserve"
'@

    # Every bridge-contract rejection must happen before workspace creation,
    # Python import, or any Codex command. Include a valid first root followed
    # by a bad root to prove the complete array is validated before containment.
    $validationCases = @(
        [pscustomobject]@{ Name = 'root-array'; Text = '[]'; Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-root-array\workspace') },
        [pscustomobject]@{ Name = 'version-bool'; Text = (New-BridgeConfigJson $allowedRoot $secret @{ version = $true }); Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-version-bool\workspace') },
        [pscustomobject]@{ Name = 'version-string'; Text = (New-BridgeConfigJson $allowedRoot $secret @{ version = '1' }); Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-version-string\workspace') },
        [pscustomobject]@{ Name = 'host'; Text = (New-BridgeConfigJson $allowedRoot $secret @{ host = 'localhost' }); Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-host\workspace') },
        [pscustomobject]@{ Name = 'port-fraction'; Text = (New-BridgeConfigJson $allowedRoot $secret @{ port = 48762.5 }); Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-port-fraction\workspace') },
        [pscustomobject]@{ Name = 'port-range'; Text = (New-BridgeConfigJson $allowedRoot $secret @{ port = 1023 }); Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-port-range\workspace') },
        [pscustomobject]@{ Name = 'token'; Text = (New-BridgeConfigJson $allowedRoot ('a' * 63) @{}); Probe = ('a' * 63); Workspace = (Join-Path $allowedRoot 'rejected-token\workspace') },
        [pscustomobject]@{ Name = 'roots-empty'; Text = (New-BridgeConfigJson $allowedRoot $secret @{ allowed_roots = [object[]]@() }); Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-roots-empty\workspace') },
        [pscustomobject]@{ Name = 'roots-mixed'; Text = (New-BridgeConfigJson $allowedRoot $secret @{ allowed_roots = @($allowedRoot, 'relative-root') }); Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-roots-mixed\workspace') },
        [pscustomobject]@{ Name = 'timeout-fraction'; Text = (New-BridgeConfigJson $allowedRoot $secret @{ request_timeout_seconds = 120.5 }); Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-timeout-fraction\workspace') },
        [pscustomobject]@{ Name = 'timeout-range'; Text = (New-BridgeConfigJson $allowedRoot $secret @{ request_timeout_seconds = 9 }); Probe = $secret; Workspace = (Join-Path $allowedRoot 'rejected-timeout-range\workspace') },
        [pscustomobject]@{ Name = 'workspace-outside'; Text = $validBridgeConfigText; Probe = $secret; Workspace = (Join-Path $testRoot 'outside\workspace') }
    )

    foreach ($case in $validationCases) {
        Set-TextUtf8 $bridgeConfig $case.Text
        Set-TextUtf8 $codexConfig $initialConfig
        Remove-Item -LiteralPath $actionLog, $pythonLog -Force -ErrorAction SilentlyContinue
        $before = Get-FileBase64 $codexConfig
        $result = Invoke-RegistrationCase -PythonExe (Join-Path $mockBin 'fake-python.cmd') -Workspace $case.Workspace -BridgeConfig $bridgeConfig -MockBin $mockBin -CodexRoot $codexRoot -ActionLog $actionLog -PythonLog $pythonLog -UseForce $true
        Assert-True (-not $result.Succeeded) ("validation case '$($case.Name)' unexpectedly succeeded")
        Assert-True (-not (Test-Path -LiteralPath $actionLog)) ("validation case '$($case.Name)' called Codex")
        Assert-True (-not (Test-Path -LiteralPath $pythonLog)) ("validation case '$($case.Name)' called Python")
        Assert-True ((Get-FileBase64 $codexConfig) -eq $before) ("validation case '$($case.Name)' changed Codex config")
        Assert-True (-not (Test-Path -LiteralPath $case.Workspace)) ("validation case '$($case.Name)' created the workspace")
        Assert-True ($result.Output -notmatch [regex]::Escape($case.Probe)) ("validation case '$($case.Name)' exposed a token")
    }
    Set-TextUtf8 $bridgeConfig $validBridgeConfigText

    # Existing registration: default behavior must fail closed before remove.
    Set-TextUtf8 $codexConfig $initialConfig
    if (Test-Path -LiteralPath $actionLog) { Remove-Item -LiteralPath $actionLog -Force }
    if (Test-Path -LiteralPath $pythonLog) { Remove-Item -LiteralPath $pythonLog -Force }
    $before = Get-FileBase64 $codexConfig
    $result = Invoke-RegistrationCase -PythonExe (Join-Path $mockBin 'fake-python.cmd') -Workspace $workspace -BridgeConfig $bridgeConfig -MockBin $mockBin -CodexRoot $codexRoot -ActionLog $actionLog -PythonLog $pythonLog
    Assert-True (-not $result.Succeeded) 'existing registration should require -Force'
    Assert-True ($result.Output -match '-Force') 'refusal should explain the -Force opt-in'
    Assert-True ((Get-FileBase64 $codexConfig) -eq $before) 'default refusal changed Codex config'
    $actions = @(Get-Content -LiteralPath $actionLog)
    Assert-True ($actions.Count -eq 1 -and $actions[0] -eq 'mcp|get|ansa|--json') 'default refusal called remove or add'
    Assert-True ((Get-Content -LiteralPath $pythonLog -Raw) -match 'python\|-c\|from ansa_mcp\.server import mcp;.+strict_input_validation') 'strict FastMCP import preflight did not run first'
    Assert-True ($result.Output -notmatch [regex]::Escape($secret)) 'default refusal exposed the bridge token'

    # Explicit replacement: settings must be written to the exact parent table.
    Set-TextUtf8 $codexConfig $initialConfig
    Remove-Item -LiteralPath $actionLog, $pythonLog -Force -ErrorAction SilentlyContinue
    $result = Invoke-RegistrationCase -PythonExe (Join-Path $mockBin 'fake-python.cmd') -Workspace $workspace -BridgeConfig $bridgeConfig -MockBin $mockBin -CodexRoot $codexRoot -ActionLog $actionLog -PythonLog $pythonLog -UseForce $true -AnsaHome 'C:\Program Files\BETA_CAE_Systems' -AnsaExecutable 'C:\Program Files\BETA_CAE_Systems\ansa.exe'
    Assert-True $result.Succeeded ('forced replacement failed: ' + $result.Output)
    $updated = [IO.File]::ReadAllText($codexConfig)
    Assert-True ($updated -match '(?m)^startup_timeout_sec = 30$') 'startup timeout was not persisted'
    Assert-True ($updated -match '(?m)^tool_timeout_sec = 180$') 'tool timeout was not persisted'
    $escapedDirectory = (Split-Path -Parent $ScriptPath).Replace('\', '\\')
    Assert-True ($updated.Contains('cwd = "' + $escapedDirectory + '"')) 'cwd was not TOML-escaped/persisted'
    Assert-True ($updated -match '(?m)^\[mcp_servers\.ansa\.env\]$') 'env subtable was damaged'
    Assert-True ($updated -match '(?m)^\[unrelated\]$') 'unrelated configuration was damaged'
    Assert-True ((Get-Content -LiteralPath $actionLog -Raw) -match 'ANSA_HOME=C:\\Program Files\\BETA_CAE_Systems') 'optional ANSA_HOME was not forwarded'
    Assert-True ((Get-Content -LiteralPath $actionLog -Raw) -match 'ANSA_EXECUTABLE=C:\\Program Files\\BETA_CAE_Systems\\ansa.exe') 'optional ANSA_EXECUTABLE was not forwarded'
    Assert-True (@(Get-ChildItem -LiteralPath $codexRoot -Filter 'config.toml.ansa-mcp-backup-*.tmp').Count -eq 0) 'successful registration left a backup behind'
    Assert-True ($result.Output -notmatch [regex]::Escape($secret)) 'successful registration exposed the bridge token'

    # A failed add after remove must restore the old file byte-for-byte.
    Set-TextUtf8 $codexConfig $initialConfig
    Remove-Item -LiteralPath $actionLog, $pythonLog -Force -ErrorAction SilentlyContinue
    $before = Get-FileBase64 $codexConfig
    $result = Invoke-RegistrationCase -PythonExe (Join-Path $mockBin 'fake-python.cmd') -Workspace $workspace -BridgeConfig $bridgeConfig -MockBin $mockBin -CodexRoot $codexRoot -ActionLog $actionLog -PythonLog $pythonLog -UseForce $true -FailAdd $true
    Assert-True (-not $result.Succeeded) 'simulated add failure unexpectedly succeeded'
    Assert-True ($result.Output -match 'previous Codex configuration was restored') 'rollback was not reported'
    Assert-True ((Get-FileBase64 $codexConfig) -eq $before) 'failed replacement did not restore exact config bytes'
    Assert-True (@(Get-ChildItem -LiteralPath $codexRoot -Filter 'config.toml.ansa-mcp-backup-*.tmp').Count -eq 0) 'rollback left a backup behind'
    Assert-True ($result.Output -notmatch [regex]::Escape($secret)) 'failed replacement exposed the bridge token'

    # A failed import must occur before any Codex inspection/mutation.
    Set-TextUtf8 $codexConfig $initialConfig
    Remove-Item -LiteralPath $actionLog, $pythonLog -Force -ErrorAction SilentlyContinue
    $before = Get-FileBase64 $codexConfig
    $result = Invoke-RegistrationCase -PythonExe (Join-Path $mockBin 'fake-python.cmd') -Workspace $workspace -BridgeConfig $bridgeConfig -MockBin $mockBin -CodexRoot $codexRoot -ActionLog $actionLog -PythonLog $pythonLog -UseForce $true -FailPython $true
    Assert-True (-not $result.Succeeded) 'simulated import failure unexpectedly succeeded'
    Assert-True (-not (Test-Path -LiteralPath $actionLog)) 'Codex was called after import preflight failed'
    Assert-True ((Get-FileBase64 $codexConfig) -eq $before) 'import failure changed Codex config'
    Assert-True ($result.Output -notmatch [regex]::Escape($secret)) 'import failure exposed the bridge token'

    $totalCases = $validationCases.Count + 4
    Write-Output "REGISTER_CODEX_MCP_TESTS_OK cases=$totalCases parser=pass"
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
