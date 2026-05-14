@echo off
rem Windows entry point for the air-gap migration workflow. Forwards every
rem argument to the sibling airgap_migrate.ps1, which carries the actual
rem logic. This shim exists so operators on cmd.exe (or double-clicking from
rem Explorer) can run the same subcommands the bash script offers without
rem invoking PowerShell directly.
rem
rem Usage: scripts\airgap_migrate.bat <command>
rem        scripts\airgap_migrate.bat --help
rem
rem Same subcommands as scripts/airgap_migrate.sh:
rem   configure | todos | check | validate-migrations | build-images |
rem   push-images | values | render | install | status | all

setlocal

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%airgap_migrate.ps1"

if not exist "%PS_SCRIPT%" (
    >&2 echo error: cannot find %PS_SCRIPT%
    exit /b 1
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
    >&2 echo error: powershell.exe not found on PATH
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
exit /b %ERRORLEVEL%
