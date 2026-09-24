@echo off
rem Publica o site no GitHub Pages. Veja tools\publicar.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publicar.ps1" %*
echo.
pause
