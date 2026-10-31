@echo off
rem SoilSense Desktop - double-click to install (first time) and start the app
cd /d "%~dp0"
title SoilSense Desktop

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (python --version >nul 2>nul && set "PY=python")
if not defined PY goto nopython

echo Using:
%PY% --version

if exist ".deps_ok" goto run
echo.
echo First run: installing the libraries the app needs - this takes a minute...
%PY% -m pip install --upgrade pip >nul 2>nul
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto pipfail
echo ok> ".deps_ok"

:run
echo.
echo Starting SoilSense... (keep this window open while you use the app)
%PY% main.py
if errorlevel 1 (
  echo.
  echo The app closed with an error - see the message above.
  pause
)
exit /b

:nopython
echo.
echo Python was not found on this computer.
echo Install Python 3.10 or newer from https://www.python.org/downloads/ and tick
echo "Add python.exe to PATH" on the first installer screen,
echo then double-click this file again.
pause
exit /b 1

:pipfail
echo.
echo Installing the libraries failed - check your internet connection and try again.
pause
exit /b 1
