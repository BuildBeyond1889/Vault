@echo off
title Archie Vault - Shelters and Soup Kitchens
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Set shelter
pause
