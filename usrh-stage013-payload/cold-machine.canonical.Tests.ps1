# Requires -Version 7.4
# Requires -Modules Pester
$ErrorActionPreference='Stop'
Describe 'Universal Resource Harvester cold-machine release' {
    BeforeAll {
        $script:ReleaseRoot=[IO.Path]::GetFullPath($env:USRH_RELEASE_ROOT)
        $script:InstallRoot=Join-Path $TestDrive 'URH'
        $script:Manifest=Get-Content (Join-Path $script:ReleaseRoot 'release/RELEASE_MANIFEST.json') -Raw | ConvertFrom-Json -Depth 100
        function script:Read-NativeFrame([IO.Stream]$Stream){
            $header=New-Object byte[] 4; $offset=0
            while($offset -lt 4){$n=$Stream.Read($header,$offset,4-$offset);if($n -le 0){throw 'native host closed before frame header'};$offset+=$n}
            $length=[BitConverter]::ToUInt32($header,0); if($length -gt 1048576){throw "native frame too large: $length"}
            $body=New-Object byte[] $length; $offset=0
            while($offset -lt $length){$n=$Stream.Read($body,$offset,$length-$offset);if($n -le 0){throw 'native host closed before frame body'};$offset+=$n}
            return ([Text.Encoding]::UTF8.GetString($body) | ConvertFrom-Json -Depth 100)
        }
        function script:Write-NativeFrame([IO.Stream]$Stream,[object]$Message){
            $body=[Text.Encoding]::UTF8.GetBytes(($Message | ConvertTo-Json -Depth 100 -Compress))
            $header=[BitConverter]::GetBytes([uint32]$body.Length)
            $Stream.Write($header,0,$header.Length); $Stream.Write($body,0,$body.Length); $Stream.Flush()
        }
    }
    It 'verifies all release hashes before installation' {
        $result=& (Join-Path $ReleaseRoot 'VERIFY_INSTALL.ps1') -SourceRoot $ReleaseRoot -VerifyOnly | ConvertFrom-Json
        $result.decision | Should -Be 'PASS_RELEASE_HASHES'
        $result.mismatches.Count | Should -Be 0
    }
    It 'uses a stable extension ID and an HKCU-only plan' {
        $plan=& (Join-Path $ReleaseRoot 'Install-UniversalResourceHarvester.ps1') -SourceRoot $ReleaseRoot -InstallRoot $InstallRoot -PlanOnly | ConvertFrom-Json
        $plan.extension_id | Should -Be $Manifest.extensionId
        $plan.registry_scope | Should -Be 'HKCU'
        $plan.requires_admin | Should -BeFalse
        @($plan.registry_keys).Count | Should -Be 2
    }
    It 'installs without administrator rights and registers both browsers' {
        $result=& (Join-Path $ReleaseRoot 'Install-UniversalResourceHarvester.ps1') -SourceRoot $ReleaseRoot -InstallRoot $InstallRoot -NoOpenExplorer | ConvertFrom-Json
        $result.decision | Should -Be 'INSTALLED'
        Test-Path (Join-Path $InstallRoot 'payload/runtime/node.exe') | Should -BeTrue
        Test-Path (Join-Path $InstallRoot 'payload/runtime/pagefind.exe') | Should -BeTrue
        Test-Path (Join-Path $InstallRoot 'payload/bin/usrh-native-host.exe') | Should -BeTrue
        foreach($key in @($result.registry_keys)){ Test-Path $key | Should -BeTrue }
    }
    It 'completes a native handshake and synthetic crawl round trip' {
        $hostPath=Join-Path $InstallRoot 'payload/bin/usrh-native-host.exe'
        $psi=[Diagnostics.ProcessStartInfo]::new($hostPath)
        $psi.UseShellExecute=$false; $psi.RedirectStandardInput=$true; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
        $psi.Environment['USRH_DB_PATH']=(Join-Path $TestDrive 'cold-machine.sqlite')
        $process=[Diagnostics.Process]::Start($psi)
        try {
            $ready=Read-NativeFrame $process.StandardOutput.BaseStream
            $ready.type | Should -Be 'host.ready'
            $token=[string]$ready.payload.capabilityToken
            $start=[ordered]@{
                protocolVersion='1.0';jobId='cold-machine-job';sequence=1;type='job.start';capabilityToken=$token
                payload=[ordered]@{
                    seedUrl='http://127.0.0.1:8765/start';
                    scope=[ordered]@{mode='smart';allowedHosts=@('127.0.0.1');allowedPathPrefixes=@('/');terminalResourceHosts=@();limits=[ordered]@{maxPages=5;maxDepth=1;maxBytes=1048576;maxRuntimeSeconds=60;maxRequestsPerMinute=30;maxExternalHops=0}}
                    authorization=[ordered]@{artifactSha256=('a'*64);allowedActions=@('navigate','download');forbiddenDataClasses=@('credentials','cookies','authorization-headers','browser-storage','student-records')}
                }
            }
            Write-NativeFrame $process.StandardInput.BaseStream $start
            (Read-NativeFrame $process.StandardOutput.BaseStream).type | Should -Be 'ack'
            $lease=[ordered]@{protocolVersion='1.0';jobId='cold-machine-job';sequence=2;type='page.lease';capabilityToken=$token;payload=[ordered]@{owner='cold-machine';leaseMs=30000}}
            Write-NativeFrame $process.StandardInput.BaseStream $lease
            $leaseAck=Read-NativeFrame $process.StandardOutput.BaseStream
            $leaseAck.type | Should -Be 'ack'
            $observation=[ordered]@{url='http://127.0.0.1:8765/start';canonicalUrl='http://127.0.0.1:8765/start';title='Synthetic Start';depth=0;links=@();frames=@();interactionCandidates=@();privacySignals=@()}
            $observe=[ordered]@{protocolVersion='1.0';jobId='cold-machine-job';sequence=3;type='page.observation';capabilityToken=$token;payload=[ordered]@{canonicalUrl=$observation.canonicalUrl;owner='cold-machine';eventId='cold-observation-1';observation=$observation;discovered=@()}}
            Write-NativeFrame $process.StandardInput.BaseStream $observe
            $observed=Read-NativeFrame $process.StandardOutput.BaseStream
            $observed.type | Should -Be 'ack'
            $observed.payload.acceptedType | Should -Be 'page.observation'
        } finally {
            try{$process.StandardInput.Close()}catch{}
            if(-not $process.WaitForExit(5000)){$process.Kill($true)}
            $process.Dispose()
        }
    }
    It 'uninstalls and can reinstall entirely from the local release' {
        $removed=& (Join-Path $ReleaseRoot 'Uninstall-UniversalResourceHarvester.ps1') -InstallRoot $InstallRoot -NoOpenExplorer | ConvertFrom-Json
        $removed.decision | Should -Be 'UNINSTALLED'
        Test-Path $InstallRoot | Should -BeFalse
        $again=& (Join-Path $ReleaseRoot 'Install-UniversalResourceHarvester.ps1') -SourceRoot $ReleaseRoot -InstallRoot $InstallRoot -NoOpenExplorer | ConvertFrom-Json
        $again.decision | Should -Be 'INSTALLED'
    }
    AfterAll {
        if(Test-Path $InstallRoot){ & (Join-Path $ReleaseRoot 'Uninstall-UniversalResourceHarvester.ps1') -InstallRoot $InstallRoot -NoOpenExplorer | Out-Null }
    }
}
