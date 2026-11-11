@echo off
cd /d "%~dp0"
echo Arrancando con consola. Cerra esta ventana para cortar la app.
python app.py --debug %*
echo.
echo La app termino con codigo %errorlevel%.
pause
