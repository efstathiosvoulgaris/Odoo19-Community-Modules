@echo off
:: ==========================================================
:: 1-CLICK DEPLOYMENT FOR ODOO DIRECT PRINT
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
echo 1. INSTALLING PYTHON DEPENDENCIES
echo ==========================================================
pip install -r requirements.txt

echo.
echo ==========================================================
echo 2. SETTING UP SUMATRA PDF
echo ==========================================================
powershell -Command "if (-not (Test-Path 'SumatraPDF.exe')) { Write-Host 'Downloading SumatraPDF...'; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.sumatrapdfreader.org/dl/rel/3.6.1/SumatraPDF-3.6.1-64.zip' -OutFile 'SumatraPDF.zip'; Expand-Archive -Path 'SumatraPDF.zip' -DestinationPath '.' -Force; Remove-Item 'SumatraPDF.zip'; Get-ChildItem -Filter 'SumatraPDF*.exe' | Rename-Item -NewName 'SumatraPDF.exe' -Force } else { Write-Host 'SumatraPDF already exists.' }"

echo.
echo ==========================================================
echo 3. CREATING AUTO-START SHORTCUT
echo ==========================================================
powershell -ExecutionPolicy Bypass -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut(\"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Start_Print_Agent.lnk\"); $Shortcut.TargetPath = \"$PWD\start_print_agent.bat\"; $Shortcut.WorkingDirectory = \"$PWD\"; $Shortcut.WindowStyle = 7; $Shortcut.Save(); Write-Host 'Auto-start shortcut created.'"

echo.
echo ==========================================================
echo 4. LOCATING AND CONFIGURING ODOO
echo ==========================================================
powershell -ExecutionPolicy Bypass -File "deploy_logic.ps1"

echo.
echo ==========================================================
echo DEPLOYMENT COMPLETE!
echo.
echo NEXT STEPS (manual):
echo 1. Copy the 'direct_print' folder to your Odoo addons directory.
echo    (usually C:\Program Files\Odoo 19.0.xxxxx\server\addons\)
echo 2. Open Odoo, enable Developer Mode (Settings - bottom of page).
echo 3. Go to Apps, click 'Update Apps List'.
echo 4. Search for 'Direct Print' and click Install.
echo 5. Go to Direct Print - Settings to select your printers.
echo.
echo The Print Agent is now running. Dashboard: http://127.0.0.1:5000
echo ==========================================================
pause
