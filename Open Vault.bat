@echo off
title Archie Vault
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
  echo The Vault needs Python 3, which is free.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo or type this in a terminal:  winget install Python.Python.3.12
  echo Then double-click Open Vault.bat again.
  pause
  exit /b
)
%PY% -c "import libzim" >nul 2>nul || (
  echo First run: installing the .zim reader ^(libzim^)...
  %PY% -m pip install --user libzim
)
%PY% tools\vault_app.py
pause
