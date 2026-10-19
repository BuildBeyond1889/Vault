@echo off
title Archie Vault - Kids
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set kids
pause
