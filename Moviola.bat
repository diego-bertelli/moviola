@echo off
cd /d "%~dp0"
if exist ultimo-error.log del ultimo-error.log
start "" pythonw app.py %*
