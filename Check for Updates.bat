@echo off
title Archie Vault - Check for updates
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Updates
pause
