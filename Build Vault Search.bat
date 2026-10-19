@echo off
rem Builds "Vault Search.exe" on this computer (needs Python 3). GitHub builds it too: see .github/workflows.
title Build Vault Search
cd /d "%~dp0"
set "PY="
if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3 is needed to build. Install it from python.org, then run this again.
  pause
  exit /b
)
echo Installing the build tools (first time only)...
%PY% -m pip install --quiet pyinstaller libzim
echo Building Vault Search.exe (a minute or two)...
%PY% -m PyInstaller --noconfirm --onefile --name "Vault Search" --collect-all libzim --add-data "web;web" --add-data "tools/packs.csv;tools" tools/vault_app.py
if not exist "dist\Vault Search.exe" (
  echo The build failed. The messages above say why.
  pause
  exit /b
)
copy /y "dist\Vault Search.exe" . >nul
echo.
echo Built: Vault Search.exe is in this folder. Double-click it to try it.
pause
