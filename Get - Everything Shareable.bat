@echo off
title Archie Vault - Everything Shareable
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set everything
pause
