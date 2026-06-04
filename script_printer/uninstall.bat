@echo off
:: ==========================================================
:: UNINSTALLER FOR ODOO DIRECT PRINT
:: ==========================================================

:: 1. Self-Elevate to Administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [INFO] Administrative permissions confirmed.
) else (
    echo [INFO] Requesting administrative privileges...
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b
)

:: Ensure we are in the correct directory after elevation
cd /d "%~dp0"

echo.
echo ==========================================================
echo WARNING: ODOO MODULE UNINSTALLATION
echo ==========================================================
echo Before continuing, please ensure you have UNINSTALLED 
echo the 'Direct Print' module from the Odoo Apps menu. 
echo If you delete the files while the module is still installed, 
echo Odoo may crash!
echo.
pause

echo.
echo ==========================================================
echo 1. REMOVING AUTO-START SHORTCUT
echo ==========================================================
powershell -Command "if (Test-Path \"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Start_Print_Agent.lnk\") { Remove-Item \"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Start_Print_Agent.lnk\" -Force; Write-Host 'Shortcut removed.' } else { Write-Host 'Shortcut not found.' }"

echo.
echo ==========================================================
echo 2. LOCATING AND REMOVING ODOO ADDON
echo ==========================================================
powershell -ExecutionPolicy Bypass -File "uninstall_logic.ps1"

echo.
echo ==========================================================
echo UNINSTALL COMPLETE!
echo.
echo The Print Agent startup shortcut has been removed and
echo the Odoo service has been restarted to clear its cache.
echo.
echo You can now safely delete this script_printer folder.
echo ==========================================================
pause
