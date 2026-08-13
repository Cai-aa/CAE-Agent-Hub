[CmdletBinding(SupportsShouldProcess)]
param(
  [Parameter(Mandatory = $true)]
  [string]$RunRoot,

  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[a-z0-9][a-z0-9-]{1,62}$')]
  [string]$CaseName,

  [Parameter(Mandatory = $true)]
  [string]$Objective,

  [ValidateSet('BUILD_MODE', 'SMOKE_MODE', 'FULL_MODE', 'LOW_MEMORY_MODE')]
  [string]$Mode = 'SMOKE_MODE',

  [ValidateRange(1, 256)]
  [int]$BatchCores = 1,

  [switch]$ForceManifest
)

$ErrorActionPreference = 'Stop'
$resolvedRunRoot = [System.IO.Path]::GetFullPath($RunRoot)
$runDirectory = Join-Path $resolvedRunRoot $CaseName
$manifestPath = Join-Path $runDirectory 'run-request.json'

if ((Test-Path -LiteralPath $manifestPath) -and -not $ForceManifest) {
  throw "Run manifest already exists: $manifestPath. Use -ForceManifest only when replacement is intended."
}

$directories = @(
  $runDirectory,
  (Join-Path $runDirectory 'config'),
  (Join-Path $runDirectory 'scripts'),
  (Join-Path $runDirectory 'inputs'),
  (Join-Path $runDirectory 'models'),
  (Join-Path $runDirectory 'logs'),
  (Join-Path $runDirectory 'exports'),
  (Join-Path $runDirectory 'exports\geometry'),
  (Join-Path $runDirectory 'exports\mesh'),
  (Join-Path $runDirectory 'exports\modes'),
  (Join-Path $runDirectory 'exports\electromagnetic'),
  (Join-Path $runDirectory 'exports\vibroacoustic'),
  (Join-Path $runDirectory 'exports\campbell'),
  (Join-Path $runDirectory 'validation')
)

if ($PSCmdlet.ShouldProcess($runDirectory, 'Create COMSOL motor NVH run scaffold')) {
  foreach ($directory in $directories) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
  }

  $manifest = [ordered]@{
    schema_version = 1
    solver = 'comsol'
    case_name = $CaseName
    objective = $Objective
    created_utc = [DateTime]::UtcNow.ToString('o')
    mode = $Mode
    batch_cores = $BatchCores
    status = 'PENDING'
    toolchain = [ordered]@{
      root = '${COMSOL_ROOT}'
      batch = '${COMSOL_BATCH}'
      compile = '${COMSOL_COMPILE}'
      java = '${COMSOL_JAVA}'
      temp = '${COMSOL_TMPDIR}'
    }
    checkpoints = @(
      'models/01_built.mph'
      'models/02_modes_solved.mph'
      'models/03_em_solved.mph'
      'models/04_smoke_solved.mph'
      'models/05_final_solved.mph'
    )
    evidence = [ordered]@{
      compile_log = 'logs/comsol_compile.log'
      build_log = 'logs/build.log'
      study1_log = 'logs/study1_modes.log'
      study2_log = 'logs/study2_electromagnetic.log'
      smoke_log = 'logs/study3_smoke.log'
      full_log = 'logs/study3_full.log'
      report = 'validation/final_acceptance.md'
    }
  }

  $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
}

[pscustomobject]@{
  status = 'created'
  run_directory = $runDirectory
  manifest = $manifestPath
}
