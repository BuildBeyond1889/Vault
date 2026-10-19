@echo off
title Archie Vault - Choose packs
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\get-vault.ps1" -Menu
pause
