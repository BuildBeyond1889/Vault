@echo off
title Archie Vault - Pocket Set
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set pocket
pause
