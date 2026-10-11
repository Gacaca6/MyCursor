@echo off
powershell.exe -NoProfile -Command "Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0tools\allow_phone_firewall.ps1""'"
