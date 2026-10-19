@echo off
title Archie Vault - Make a Vault drive
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -CopyDrive
pause
