@echo off
title Archie Vault - Make a Vault zip
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Zip
pause
