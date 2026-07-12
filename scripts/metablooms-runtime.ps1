param(
  [switch]$VerifyOnly,
  [switch]$Extract,
  [switch]$Boot,
  [switch]$FullBoot,
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "metablooms_runtime.py"
$args = @($script)
if ($VerifyOnly) { $args += "--verify-only" }
if ($Extract) { $args += "--extract" }
if ($Boot) { $args += "--boot" }
if ($FullBoot) { $args += "--full-boot" }
& $Python @args
exit $LASTEXITCODE
