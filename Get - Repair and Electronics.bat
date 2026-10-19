@echo off
title Archie Vault - Repair and Electronics
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set repair
pause
