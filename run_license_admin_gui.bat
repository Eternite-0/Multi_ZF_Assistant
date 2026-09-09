@echo off
chcp 65001 >nul
cd /d "%~dp0"
.\.venv\Scripts\python.exe scripts\license_admin_gui.py
pause
