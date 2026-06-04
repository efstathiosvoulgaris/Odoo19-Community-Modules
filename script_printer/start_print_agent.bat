@echo off
title Odoo Print Agent
cd /d "%~dp0"
echo Starting Odoo Print Agent...
echo Dashboard: http://127.0.0.1:5000
echo Press Ctrl+C to stop.
echo.
python local_printer_service.py
if errorlevel 1 (
    echo.
    echo ERROR: Agent crashed. Check logs\print_agent.log for details.
    pause
)
