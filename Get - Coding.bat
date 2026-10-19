@echo off
title Archie Vault - Coding
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set code
pause
