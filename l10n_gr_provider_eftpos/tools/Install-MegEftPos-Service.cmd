@echo off
REM Double-click entry point: re-launches itself elevated, then runs the
REM PowerShell installer next to it. Pass /uninstall to remove the service.
setlocal
set "PS1=%~dp0install_megeftpos_service.ps1"

net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

set "ARGS="
if /i "%~1"=="/uninstall" set "ARGS=-Uninstall"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %ARGS%
echo.
pause
