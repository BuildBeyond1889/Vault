@echo off
title Archie Vault - Big Libraries
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set big
pause
