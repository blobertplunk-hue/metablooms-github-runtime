@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title Lakeland Offline Student Data Hub 4.0.0-rc5 - One-Click Recipient Test

set "PAYLOAD=%~dp0Lakeland_Offline_Student_Data_Hub_v4.0.0-rc5-instrumented.zip"
set "EXPECTED_SHA256=2d091c4b357b1bdf7e416e844d70ba8bdda4d43827454606b3b2d411c0eef42e"
set "PWSH=%ProgramFiles%\PowerShell\7\pwsh.exe"

if not exist "%PAYLOAD%" (
  echo ERROR: Payload ZIP is not beside this CMD file.
  echo Expected: %PAYLOAD%
  goto :fatal
)

if not exist "%PWSH%" (
  set "PWSH="
  for /f "delims=" %%P in ('where pwsh.exe 2^>nul') do if not defined PWSH set "PWSH=%%P"
)
if not defined PWSH (
  echo ERROR: PowerShell 7 was not found.
  echo Required runtime: exact PowerShell 7.6.3 for this qualification.
  goto :fatal
)
if not exist "%PWSH%" (
  echo ERROR: PowerShell 7 path could not be opened: %PWSH%
  goto :fatal
)

set "PAYLOAD_PATH=%PAYLOAD%"
set "PWSH_PATH=%PWSH%"
set "RUNNER_PATH=%~f0"

echo.
echo ============================================================
echo Lakeland Offline Student Data Hub 4.0.0-rc5
echo ONE-CLICK FAKE-DATA RECIPIENT QUALIFICATION
echo ============================================================
echo This run uses only the bundled fake/sanitized test fixtures.
echo It does NOT launch the real-data importer.
echo.

"%PWSH%" -NoLogo -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; if($PSVersionTable.PSVersion -ne [version]'7.6.3'){Write-Error ('Exact PowerShell 7.6.3 required. Found '+$PSVersionTable.PSVersion); exit 20}; if($PSVersionTable.PSEdition -ne 'Core'){Write-Error ('PowerShell Core required. Found '+$PSVersionTable.PSEdition); exit 22}; $actual=(Get-FileHash -LiteralPath $env:PAYLOAD_PATH -Algorithm SHA256).Hash.ToLowerInvariant(); if($actual -ne $env:EXPECTED_SHA256){Write-Error ('Payload SHA-256 mismatch. Expected '+$env:EXPECTED_SHA256+' actual '+$actual); exit 21}; Write-Host ('PASS payload ZIP SHA-256: '+$actual)"
if errorlevel 1 goto :fatal

:pick_run_dir
set "RUN_DIR=%TEMP%\LakelandHub_rc5_%RANDOM%_%RANDOM%"
if exist "%RUN_DIR%" goto :pick_run_dir
mkdir "%RUN_DIR%" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Could not create temporary extraction folder.
  goto :fatal
)
set "RUN_DIR_PATH=%RUN_DIR%"

"%PWSH%" -NoLogo -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; Expand-Archive -LiteralPath $env:PAYLOAD_PATH -DestinationPath $env:RUN_DIR_PATH -Force"
if errorlevel 1 (
  echo ERROR: Payload extraction failed.
  goto :fatal_cleanup
)

set "APP_ROOT=%RUN_DIR%\Lakeland_Offline_Student_Data_Hub"
if not exist "%APP_ROOT%\RunSelfTest.ps1" (
  echo ERROR: Extracted self-test entry point is missing.
  goto :fatal_cleanup
)

:pick_result_dir
set "RESULT_DIR=%~dp0Lakeland_rc5_RESULT_%RANDOM%_%RANDOM%"
if exist "%RESULT_DIR%" goto :pick_result_dir
mkdir "%RESULT_DIR%" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Could not create the result folder beside this CMD file.
  goto :fatal_cleanup
)
set "RESULT_DIR_ENV=%RESULT_DIR%"
set "CONSOLE_LOG=%RESULT_DIR%\SELF_TEST_CONSOLE.txt"
set "RESULT_RECEIPT=%RESULT_DIR%\SELF_TEST_RECEIPT.json"
set "RESULT_RECEIPT_ENV=%RESULT_RECEIPT%"
set "SUMMARY_PATH=%RESULT_DIR%\RUN_SUMMARY.json"
set "SUMMARY_PATH_ENV=%SUMMARY_PATH%"

set "RUN_MARKER=%RESULT_DIR%\RUN_STARTED.marker"
set "RUN_MARKER_PATH=%RUN_MARKER%"

"%PWSH%" -NoLogo -NoProfile -NonInteractive -Command "$selfRoot=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Lakeland Student Data Hub\Self Test'; $receipt=Join-Path $selfRoot 'SELF_TEST_RECEIPT.json'; Remove-Item -LiteralPath $receipt -Force -ErrorAction SilentlyContinue; [DateTime]::UtcNow.ToString('o') | Set-Content -LiteralPath $env:RUN_MARKER_PATH -Encoding ascii"

echo Running the instrumented recipient self-test...
echo.
"%PWSH%" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%APP_ROOT%\RunSelfTest.ps1" > "%CONSOLE_LOG%" 2>&1
set "TEST_RC=%ERRORLEVEL%"
type "%CONSOLE_LOG%"

set "TEST_EXIT_CODE=%TEST_RC%"
set "COLLECTOR_B64=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"
set "COLLECTOR_SHA256=0799b07f4f1e926d18b93a6cd5c5eeb506655043009d01f46d7d28f7105440b1"
set "LOG_COLLECTION_RECEIPT=%RESULT_DIR%\LOG_COLLECTION_RECEIPT.json"
set "LOG_COLLECTION_RECEIPT_ENV=%LOG_COLLECTION_RECEIPT%"
"%PWSH%" -NoLogo -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; $selfRoot=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Lakeland Student Data Hub\Self Test'; $receipt=Join-Path $selfRoot 'SELF_TEST_RECEIPT.json'; if(-not (Test-Path -LiteralPath $receipt -PathType Leaf)){throw 'SELF_TEST_RECEIPT.json was not found after the run.'}; Copy-Item -LiteralPath $receipt -Destination $env:RESULT_RECEIPT_ENV -Force; $raw=[Convert]::FromBase64String($env:COLLECTOR_B64); $ms=[IO.MemoryStream]::new([byte[]]$raw); $gz=[IO.Compression.GzipStream]::new($ms,[IO.Compression.CompressionMode]::Decompress); $sr=[IO.StreamReader]::new($gz,[Text.Encoding]::UTF8); $collector=$sr.ReadToEnd(); $sr.Dispose();$gz.Dispose();$ms.Dispose(); $actual=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($collector))).ToLowerInvariant(); if($actual -ne $env:COLLECTOR_SHA256){throw 'Embedded collector SHA-256 mismatch.'}; . ([scriptblock]::Create($collector)); $logsRoot=Join-Path $selfRoot 'Logs'; $r=Collect-ExactSelfTestEvidence -ReceiptPath $env:RESULT_RECEIPT_ENV -LogsRoot $logsRoot -ResultDir $env:RESULT_DIR_ENV -ExpectedTestExitCode ([int]$env:TEST_EXIT_CODE) -RunMarkerPath $env:RUN_MARKER_PATH; Write-Host ('Collected receipt-bound suite logs for run '+$r.source_run_id)"
set "EVIDENCE_RC=%ERRORLEVEL%"

"%PWSH%" -NoLogo -NoProfile -NonInteractive -Command "$payloadMotw=$false;$runnerMotw=$false;try{$payloadMotw=$null -ne (Get-Item -LiteralPath $env:PAYLOAD_PATH -Stream 'Zone.Identifier' -ErrorAction SilentlyContinue)}catch{};try{$runnerMotw=$null -ne (Get-Item -LiteralPath $env:RUNNER_PATH -Stream 'Zone.Identifier' -ErrorAction SilentlyContinue)}catch{}; $verified=$false;$runId='';if(Test-Path -LiteralPath $env:LOG_COLLECTION_RECEIPT_ENV -PathType Leaf){try{$lc=Get-Content -Raw -LiteralPath $env:LOG_COLLECTION_RECEIPT_ENV|ConvertFrom-Json;$verified=([string]$lc.decision -eq 'PASS');$runId=[string]$lc.source_run_id}catch{}}; $obj=[ordered]@{schema='mb.lakeland_student_data_hub.one_click_result.v3';release='4.0.0-rc5';payload_sha256=$env:EXPECTED_SHA256;test_exit_code=[int]$env:TEST_EXIT_CODE;evidence_exit_code=[int]$env:EVIDENCE_RC;started_at_utc=(Get-Content -Raw -LiteralPath $env:RUN_MARKER_PATH).Trim();completed_at_utc=[DateTime]::UtcNow.ToString('o');receipt_collected=(Test-Path -LiteralPath $env:RESULT_RECEIPT_ENV -PathType Leaf);suite_logs_collected=$verified;log_collection_verified=$verified;self_test_log_run_id=$runId;payload_motw_present=$payloadMotw;runner_motw_present=$runnerMotw}; $obj | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $env:SUMMARY_PATH_ENV -Encoding utf8NoBOM"

del /q "%RUN_MARKER%" >nul 2>&1

set "RESULT_ZIP=%RESULT_DIR%.zip"
set "RESULT_ZIP_ENV=%RESULT_ZIP%"
"%PWSH%" -NoLogo -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; Compress-Archive -Path (Join-Path $env:RESULT_DIR_ENV '*') -DestinationPath $env:RESULT_ZIP_ENV -Force"
if errorlevel 1 (
  echo ERROR: Could not create the result ZIP.
  goto :fatal_cleanup
)

rmdir /s /q "%RUN_DIR%" >nul 2>&1

set "FINAL_RC=%TEST_RC%"
if "%TEST_RC%"=="0" if not "%EVIDENCE_RC%"=="0" set "FINAL_RC=31"

echo.
if not "%TEST_RC%"=="0" (
  echo ============================================================
  echo SELF-TEST FAILED with error code %TEST_RC%
  echo ============================================================
) else if not "%EVIDENCE_RC%"=="0" (
  echo ============================================================
  echo SELF-TEST PASSED BUT EVIDENCE COLLECTION FAILED
  echo Evidence error code: %EVIDENCE_RC%
  echo ============================================================
) else (
  echo ============================================================
  echo SELF-TEST PASSED AND RECEIPT-BOUND EVIDENCE VERIFIED
  echo ============================================================
)
echo Result bundle: %RESULT_ZIP%
echo Send ONLY that result ZIP back in this chat.
echo It contains the fake-data test console, structured receipt, run summary,
echo and receipt-bound suite logs plus LOG_COLLECTION_RECEIPT.json. It does not include source student reports.
if exist "%RESULT_ZIP%" explorer.exe /select,"%RESULT_ZIP%" >nul 2>&1
pause
exit /b %FINAL_RC%

:fatal_cleanup
if defined RUN_DIR if exist "%RUN_DIR%" rmdir /s /q "%RUN_DIR%" >nul 2>&1
:fatal
echo.
echo ONE-CLICK RUNNER COULD NOT START THE SELF-TEST.
pause
exit /b 1