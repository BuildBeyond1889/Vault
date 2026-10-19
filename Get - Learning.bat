@echo off
title Archie Vault - Learning
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set learn
pause
