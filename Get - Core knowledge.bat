@echo off
title Archie Vault - Core knowledge
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set core
pause
