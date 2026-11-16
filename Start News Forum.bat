@echo off
cd /d "%~dp0"
rem The Windows "py" launcher finds Python 3.13 wherever it is installed.
py -3.13 -m news
pause
