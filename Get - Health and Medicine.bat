@echo off
title Archie Vault - Health and Medicine
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set health
pause
