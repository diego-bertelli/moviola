@echo off
chcp 65001 >nul
title Instalador de Moviola
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalador\instalar.ps1" %*
set "COD=%errorlevel%"
echo.
if not "%MOVIOLA_SIN_PAUSA%"=="1" pause
exit /b %COD%
