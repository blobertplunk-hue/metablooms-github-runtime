[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArtifactPath,
    [Parameter(Mandatory = $true)][string]$ContractPath,
    [Parameter(Mandatory = $true)][string]$ExpectedArtifactSha256,
    [Parameter(Mandatory = $true)][string]$ExpectedContractSha256,
    [Parameter(Mandatory = $true)][string]$ExpectedVerifierCommit,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$PackageSubdir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-CanonicalJson {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $json = $Value | ConvertTo-Json -Depth 16
    [IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Get-RuntimeInfo {
    param([Parameter(Mandatory = $true)][string]$Executable)
    $resolved = (Get-Command $Executable -ErrorAction Stop).Source
    $raw = & $resolved -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString() + "|" + $PSVersionTable.PSEdition'
    if ($LASTEXITCODE -ne 0) { throw "runtime metadata probe failed: $resolved" }
    $parts = ([string]$raw).Trim().Split('|', 2)
    if ($parts.Count -ne 2) { throw "runtime metadata probe malformed: $resolved => $raw" }
    [ordered]@{ path = $resolved; version = $parts[0]; edition = $parts[1] }
}

function Resolve-MatrixRuntime {
    param([Parameter(Mandatory = $true)][string]$Leg)
    if ($Leg -match '^Windows PowerShell\s+(.+)$') {
        $info = Get-RuntimeInfo -Executable 'powershell.exe'
        if ($info.edition -ne 'Desktop' -or -not $info.version.StartsWith($Matches[1])) { throw "Windows PowerShell matrix mismatch: expected $Leg observed $($info.edition) $($info.version)" }
        return $info
    }
    if ($Leg -match '^PowerShell\s+(.+)$') {
        $info = Get-RuntimeInfo -Executable 'pwsh.exe'
        if ($info.edition -ne 'Core' -or $info.version -ne $Matches[1]) { throw "PowerShell matrix mismatch: expected $Leg observed $($info.edition) $($info.version)" }
        return $info
    }
    if ($Leg -match '^\d+(?:\.\d+)+$') {
        $info = Get-RuntimeInfo -Executable 'pwsh.exe'
        if ($info.edition -ne 'Core' -or $info.version -ne $Leg) { throw "PowerShell matrix mismatch: expected $Leg observed $($info.edition) $($info.version)" }
        return $info
    }
    throw "unsupported PowerShell matrix leg: $Leg"
}

function Convert-RuntimeToLeg {
    param([Parameter(Mandatory = $true)]$RuntimeInfo)
    if ($RuntimeInfo.edition -eq 'Desktop') {
        $parts = ([string]$RuntimeInfo.version).Split('.')
        $family = if ($parts.Count -ge 2) { "$($parts[0]).$($parts[1])" } else { [string]$RuntimeInfo.version }
        return "Windows PowerShell $family"
    }
    return "PowerShell $($RuntimeInfo.version)"
}

function Get-ObservedChildRuntime {
    param([Parameter(Mandatory = $true)][int]$ParentPid,[Parameter(Mandatory = $true)][string]$SourceIdentifier)
    $events = @(Get-Event -SourceIdentifier $SourceIdentifier -ErrorAction SilentlyContinue)
    foreach ($event in $events) {
        $newEvent = $event.SourceEventArgs.NewEvent
        if ($null -eq $newEvent) { continue }
        if ([int]$newEvent.ParentProcessID -ne $ParentPid) { continue }
        $name = ([string]$newEvent.ProcessName).ToLowerInvariant()
        if ($name -eq 'pwsh.exe') { return Get-RuntimeInfo -Executable 'pwsh.exe' }
        if ($name -eq 'powershell.exe') { return Get-RuntimeInfo -Executable 'powershell.exe' }
    }
    return $null
}

function Invoke-ObservedProcess {
    param([Parameter(Mandatory = $true)][string]$FilePath,[Parameter(Mandatory = $true)][string[]]$ArgumentList,[string]$PathOverride = "")
    $sourceId = "metablooms-process-start-$([guid]::NewGuid().ToString('N'))"
    $subscription = $null
    try {
        $subscription = Register-CimIndicationEvent -Query 'SELECT * FROM Win32_ProcessStartTrace' -SourceIdentifier $sourceId
        Start-Sleep -Milliseconds 100
        $psi = [Diagnostics.ProcessStartInfo]::new()
        $psi.FileName = $FilePath
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        foreach ($arg in $ArgumentList) { [void]$psi.ArgumentList.Add($arg) }
        if ($PathOverride) { $psi.Environment['PATH'] = $PathOverride }
        $proc = [Diagnostics.Process]::new(); $proc.StartInfo = $psi
        if (-not $proc.Start()) { throw "process failed to start: $FilePath" }
        $stdoutTask = $proc.StandardOutput.ReadToEndAsync(); $stderrTask = $proc.StandardError.ReadToEndAsync()
        $proc.WaitForExit(); $stdoutTask.Wait(); $stderrTask.Wait(); Start-Sleep -Milliseconds 300
        $runtime = Get-ObservedChildRuntime -ParentPid $proc.Id -SourceIdentifier $sourceId
        return [ordered]@{ exit_code = $proc.ExitCode; stdout = $stdoutTask.Result; stderr = $stderrTask.Result; observed_child_runtime = $runtime }
    }
    finally {
        Get-Event -SourceIdentifier $sourceId -ErrorAction SilentlyContinue | Remove-Event -ErrorAction SilentlyContinue
        Unregister-Event -SourceIdentifier $sourceId -ErrorAction SilentlyContinue
        if ($null -ne $subscription) { Remove-Job -Id $subscription.Id -Force -ErrorAction SilentlyContinue }
    }
}

function Invoke-ExactEntrypoint {
    param([Parameter(Mandatory = $true)][string]$PackageRoot,[Parameter(Mandatory = $true)][string]$Entrypoint,[string]$MatrixLeg = "",[switch]$SelectionProbe)
    $entrypointPath = Join-Path $PackageRoot $Entrypoint
    if (-not (Test-Path -LiteralPath $entrypointPath -PathType Leaf)) {
        return [ordered]@{ declared_matrix_leg=$MatrixLeg; selected_runtime_path=""; powershell_version=""; powershell_edition=""; entrypoint=$Entrypoint; entrypoint_executed=$false; decision='FAIL'; exit_code=127; failure_class='ENTRYPOINT_MISSING_AFTER_INSTALL'; stdout_sha256=""; stderr_sha256=""; execution_kind=if($SelectionProbe){'selection_probe'}else{'matrix_leg'} }
    }
    $extension = [IO.Path]::GetExtension($entrypointPath).ToLowerInvariant(); $runtime=$null; $result=$null; $pathOverride=""
    if ($extension -eq '.cmd' -or $extension -eq '.bat') {
        if (-not $SelectionProbe) {
            $runtime = Resolve-MatrixRuntime -Leg $MatrixLeg
            $runtimeDir = Split-Path -Parent $runtime.path; $systemRoot = [Environment]::GetEnvironmentVariable('SystemRoot')
            $pathOverride = @($runtimeDir,(Join-Path $systemRoot 'System32'),$systemRoot,(Join-Path $systemRoot 'System32\Wbem')) -join ';'
        }
        $cmdArgument = '"' + $entrypointPath + '"'
        $result = Invoke-ObservedProcess -FilePath $env:ComSpec -ArgumentList @('/d','/s','/c',$cmdArgument) -PathOverride $pathOverride
        $observed = $result.observed_child_runtime; if ($null -ne $observed) { $runtime = $observed }
    } elseif ($extension -eq '.ps1') {
        if ($SelectionProbe) { throw 'selection probe is only valid for launcher entrypoints (.cmd/.bat)' }
        $runtime = Resolve-MatrixRuntime -Leg $MatrixLeg
        $result = Invoke-ObservedProcess -FilePath $runtime.path -ArgumentList @('-NoLogo','-NoProfile','-File',$entrypointPath)
    } else {
        if ($SelectionProbe) { throw 'selection probe requires a PowerShell-selecting launcher entrypoint' }
        $result = Invoke-ObservedProcess -FilePath $entrypointPath -ArgumentList @()
    }
    $effectiveLeg = $MatrixLeg
    if ($SelectionProbe) { $effectiveLeg = if ($null -ne $runtime) { Convert-RuntimeToLeg -RuntimeInfo $runtime } else { 'UNOBSERVED' } }
    $stdoutPath = Join-Path $OutputDir ("stdout-"+[guid]::NewGuid().ToString('N')+'.txt'); $stderrPath=Join-Path $OutputDir ("stderr-"+[guid]::NewGuid().ToString('N')+'.txt')
    [IO.File]::WriteAllText($stdoutPath,[string]$result.stdout,[Text.UTF8Encoding]::new($false)); [IO.File]::WriteAllText($stderrPath,[string]$result.stderr,[Text.UTF8Encoding]::new($false))
    [ordered]@{ declared_matrix_leg=$effectiveLeg; selected_runtime_path=if($null-ne$runtime){[string]$runtime.path}else{""}; powershell_version=if($null-ne$runtime){[string]$runtime.version}else{""}; powershell_edition=if($null-ne$runtime){[string]$runtime.edition}else{""}; entrypoint=$Entrypoint; entrypoint_executed=$true; decision=if($result.exit_code-eq0){'PASS'}else{'FAIL'}; exit_code=[int]$result.exit_code; stdout_sha256=Get-Sha256Hex -Path $stdoutPath; stderr_sha256=Get-Sha256Hex -Path $stderrPath; execution_kind=if($SelectionProbe){'selection_probe'}else{'matrix_leg'} }
}

if (-not $IsWindows) { throw 'hosted_plane_driver.ps1 requires native Windows; Linux/WSL evidence cannot satisfy H2' }
$artifact=(Resolve-Path -LiteralPath $ArtifactPath).Path; $contract=(Resolve-Path -LiteralPath $ContractPath).Path; $out=[IO.Path]::GetFullPath($OutputDir); New-Item -ItemType Directory -Path $out -Force|Out-Null
$artifactSha=Get-Sha256Hex -Path $artifact; $contractSha=Get-Sha256Hex -Path $contract
if($artifactSha-ne$ExpectedArtifactSha256.ToLowerInvariant()){throw "artifact SHA-256 mismatch: $artifactSha"}; if($contractSha-ne$ExpectedContractSha256.ToLowerInvariant()){throw "contract SHA-256 mismatch: $contractSha"}; if($ExpectedVerifierCommit-notmatch'^[0-9a-fA-F]{40}$'){throw 'ExpectedVerifierCommit must be an exact 40-hex Git commit SHA'}
$contractData=Get-Content -LiteralPath $contract -Raw|ConvertFrom-Json; if($contractData.contract_generation-lt1){throw 'contract_generation invalid'}; if(-not$contractData.entrypoints -or -not$contractData.declared_powershell_matrix){throw 'contract lacks entrypoints or declared_powershell_matrix'}
$installRoot=Join-Path $out 'fresh_install'; if(Test-Path -LiteralPath $installRoot){Remove-Item -LiteralPath $installRoot -Recurse -Force}; New-Item -ItemType Directory -Path $installRoot -Force|Out-Null; Expand-Archive -LiteralPath $artifact -DestinationPath $installRoot -Force
$packageRoot=if($PackageSubdir){Join-Path $installRoot $PackageSubdir}else{$installRoot}; if(-not(Test-Path -LiteralPath $packageRoot -PathType Container)){throw "package subdir missing after install: $PackageSubdir"}
$os=Get-CimInstance Win32_OperatingSystem; $envPacket=[ordered]@{schema='mb.powershell.hosted_environment.v1';os_family='windows';native_windows=$true;host_os=[string]$os.Caption;host_version=[string]$os.Version;host_build=[string]$os.BuildNumber;architecture=[string]$env:PROCESSOR_ARCHITECTURE;runner_name=[string]$env:RUNNER_NAME;runner_os=[string]$env:RUNNER_OS}; $envPath=Join-Path $out 'hosted_environment.json'; Write-CanonicalJson -Value $envPacket -Path $envPath
$treeRows=@(); Get-ChildItem -LiteralPath $packageRoot -File -Recurse|Sort-Object FullName|ForEach-Object{$relative=[IO.Path]::GetRelativePath($packageRoot,$_.FullName).Replace('\','/');$treeRows+=[ordered]@{path=$relative;sha256=Get-Sha256Hex -Path $_.FullName;bytes=[int64]$_.Length}}; $treePacket=[ordered]@{schema='mb.powershell.install_tree_manifest.v1';artifact_sha256=$artifactSha;package_subdir=$PackageSubdir;file_count=$treeRows.Count;files=$treeRows};$treePath=Join-Path $out 'install_tree_manifest.json';Write-CanonicalJson -Value $treePacket -Path $treePath
$runtimeInventory=@(); foreach($name in @('powershell.exe','pwsh.exe')){try{$info=Get-RuntimeInfo -Executable $name;$runtimeInventory+=[ordered]@{name=$name;path=$info.path;version=$info.version;edition=$info.edition}}catch{$runtimeInventory+=[ordered]@{name=$name;available=$false;error=$_.Exception.Message}}};$pesterVersion=$null;$psaVersion=$null;$pester=Get-Module -ListAvailable Pester|Sort-Object Version -Descending|Select-Object -First 1;if($null-ne$pester){$pesterVersion=[string]$pester.Version};$psa=Get-Module -ListAvailable PSScriptAnalyzer|Sort-Object Version -Descending|Select-Object -First 1;if($null-ne$psa){$psaVersion=[string]$psa.Version};$toolchainPacket=[ordered]@{schema='mb.powershell.hosted_toolchain_lock.v1';verifier_commit=$ExpectedVerifierCommit.ToLowerInvariant();runtimes=$runtimeInventory;pester_version=$pesterVersion;psscriptanalyzer_version=$psaVersion;driver_sha256=Get-Sha256Hex -Path $PSCommandPath};$toolchainPath=Join-Path $out 'toolchain_lock.json';Write-CanonicalJson -Value $toolchainPacket -Path $toolchainPath;$toolchainSha=Get-Sha256Hex -Path $toolchainPath
$executions=@();foreach($entrypoint in @($contractData.entrypoints)){$entryPath=Join-Path $packageRoot ([string]$entrypoint);$extension=[IO.Path]::GetExtension($entryPath).ToLowerInvariant();if($extension-eq'.cmd'-or$extension-eq'.bat'){$executions+=Invoke-ExactEntrypoint -PackageRoot $packageRoot -Entrypoint ([string]$entrypoint) -SelectionProbe};foreach($leg in @($contractData.declared_powershell_matrix)){$executions+=Invoke-ExactEntrypoint -PackageRoot $packageRoot -Entrypoint ([string]$entrypoint) -MatrixLeg ([string]$leg)}}
$executionPacket=[ordered]@{schema='mb.powershell.hosted_entrypoint_execution.v1';artifact_sha256=$artifactSha;contract_sha256=$contractSha;verifier_commit=$ExpectedVerifierCommit.ToLowerInvariant();executions=$executions};$executionPath=Join-Path $out 'entrypoint_execution.json';Write-CanonicalJson -Value $executionPacket -Path $executionPath
$receipt=[ordered]@{schema='mb.powershell.hosted_plane_receipt.v1';phase_id='H2-HOSTED-WINDOWS';artifact_sha256=$artifactSha;contract_sha256=$contractSha;contract_generation=[int]$contractData.contract_generation;verifier_commit=$ExpectedVerifierCommit.ToLowerInvariant();toolchain_lock_sha256=$toolchainSha;evidence_sha256=[ordered]@{'hosted_environment.json'=Get-Sha256Hex -Path $envPath;'install_tree_manifest.json'=Get-Sha256Hex -Path $treePath;'entrypoint_execution.json'=Get-Sha256Hex -Path $executionPath};environment=$envPacket;executions=$executions};$receiptPath=Join-Path $out 'hosted_plane_receipt.json';Write-CanonicalJson -Value $receipt -Path $receiptPath;Write-Output $receiptPath
