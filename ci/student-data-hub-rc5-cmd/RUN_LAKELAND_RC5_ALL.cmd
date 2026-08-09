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
"%PWSH%" -NoLogo -NoProfile -NonInteractive -Command "$selfRoot=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Lakeland Student Data Hub\Self Test'; $receipt=Join-Path $selfRoot 'SELF_TEST_RECEIPT.json'; if(Test-Path -LiteralPath $receipt -PathType Leaf){Copy-Item -LiteralPath $receipt -Destination $env:RESULT_RECEIPT_ENV -Force; Write-Host ('Collected receipt: '+$env:RESULT_RECEIPT_ENV)}else{Write-Warning 'SELF_TEST_RECEIPT.json was not found after the run.'}; $logsRoot=Join-Path $selfRoot 'Logs'; $cut=(Get-Item -LiteralPath $env:RUN_MARKER_PATH).LastWriteTimeUtc.AddSeconds(-2); $new=$null; if(Test-Path -LiteralPath $logsRoot -PathType Container){$new=Get-ChildItem -LiteralPath $logsRoot -Directory | Where-Object {$_.LastWriteTimeUtc -ge $cut} | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1}; if($null -ne $new){Copy-Item -LiteralPath $new.FullName -Destination (Join-Path $env:RESULT_DIR_ENV 'SUITE_LOGS') -Recurse -Force; Write-Host 'Collected current-run suite logs.'}else{Write-Warning 'No current-run suite log directory was found.'}"

"%PWSH%" -NoLogo -NoProfile -NonInteractive -Command "$payloadMotw=$false;$runnerMotw=$false;try{$payloadMotw=$null -ne (Get-Item -LiteralPath $env:PAYLOAD_PATH -Stream 'Zone.Identifier' -ErrorAction SilentlyContinue)}catch{};try{$runnerMotw=$null -ne (Get-Item -LiteralPath $env:RUNNER_PATH -Stream 'Zone.Identifier' -ErrorAction SilentlyContinue)}catch{}; $obj=[ordered]@{schema='mb.lakeland_student_data_hub.one_click_result.v2';release='4.0.0-rc5';payload_sha256=$env:EXPECTED_SHA256;test_exit_code=[int]$env:TEST_EXIT_CODE;started_at_utc=(Get-Content -Raw -LiteralPath $env:RUN_MARKER_PATH).Trim();completed_at_utc=[DateTime]::UtcNow.ToString('o');receipt_collected=(Test-Path -LiteralPath $env:RESULT_RECEIPT_ENV -PathType Leaf);suite_logs_collected=(Test-Path -LiteralPath (Join-Path $env:RESULT_DIR_ENV 'SUITE_LOGS') -PathType Container);payload_motw_present=$payloadMotw;runner_motw_present=$runnerMotw}; $obj | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $env:SUMMARY_PATH_ENV -Encoding utf8NoBOM"

del /q "%RUN_MARKER%" >nul 2>&1

set "RESULT_ZIP=%RESULT_DIR%.zip"
set "RESULT_ZIP_ENV=%RESULT_ZIP%"
"%PWSH%" -NoLogo -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; Compress-Archive -Path (Join-Path $env:RESULT_DIR_ENV '*') -DestinationPath $env:RESULT_ZIP_ENV -Force"
if errorlevel 1 (
  echo ERROR: Could not create the result ZIP.
  goto :fatal_cleanup
)

rmdir /s /q "%RUN_DIR%" >nul 2>&1

echo.
if "%TEST_RC%"=="0" (
  echo ============================================================
  echo SELF-TEST PASSED
  echo ============================================================
) else (
  echo ============================================================
  echo SELF-TEST FAILED with error code %TEST_RC%
  echo ============================================================
)
echo Result bundle: %RESULT_ZIP%
echo Send ONLY that result ZIP back in this chat.
echo It contains the fake-data test console, structured receipt, run summary,
echo and current-run suite logs. It does not include source student reports.
if exist "%RESULT_ZIP%" explorer.exe /select,"%RESULT_ZIP%" >nul 2>&1
pause
exit /b %TEST_RC%

:fatal_cleanup
if defined RUN_DIR if exist "%RUN_DIR%" rmdir /s /q "%RUN_DIR%" >nul 2>&1
:fatal
echo.
echo ONE-CLICK RUNNER COULD NOT START THE SELF-TEST.
pause
exit /b 1
