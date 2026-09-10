@echo off
title Go bo Tu khoi dong cung Windows - Hardware Bridge
echo ====================================================================
echo  TUAN CHAU RESORT - GO BO HARDWARE BRIDGE KHOI STARTUP
echo ====================================================================
echo.

powershell -NoProfile -Command "$startupDir = [System.Environment]::GetFolderPath('Startup'); $lnk = \"$startupDir\TuanChau_Hardware_Bridge.lnk\"; if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host \"Da go bo: $lnk\" -ForegroundColor Green } else { Write-Host \"Khong tim thay shortcut trong Startup!\" -ForegroundColor Yellow }"

echo.
pause
