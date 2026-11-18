@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python
py -3 lancer.py
goto result
:python
where python >nul 2>nul
if errorlevel 1 goto missing
python lancer.py
goto result
:missing
echo Installez Python 3.11 ou plus recent depuis python.org puis relancez ce fichier.
pause
exit /b 1
:result
if errorlevel 1 pause
