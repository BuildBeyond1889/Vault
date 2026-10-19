@echo off
title Archie Vault - Maps
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set maps
pause
