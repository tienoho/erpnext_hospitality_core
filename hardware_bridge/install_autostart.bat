@echo off
title Cai dat Tu khoi dong cung Windows - Hardware Bridge
echo ====================================================================
echo  TUAN CHAU RESORT - CAI DAT HARDWARE BRIDGE KHOI DONG CUNG WINDOWS
echo ====================================================================
echo.
echo Dang tao Shortcut trong thu muc Windows Startup...

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $startupDir = [System.Environment]::GetFolderPath('Startup'); $s = $ws.CreateShortcut(\"$startupDir\TuanChau_Hardware_Bridge.lnk\"); $s.TargetPath = \"wscript.exe\"; $s.Arguments = \"`\"%~dp0run_bridge_silent.vbs`\"\"; $s.WorkingDirectory = \"%~dp0\"; $s.Description = 'Tuan Chau Resort Hardware Keycard Bridge'; $s.Save(); Write-Host \"Da tao Shortcut thanh cong tai: $startupDir\TuanChau_Hardware_Bridge.lnk\" -ForegroundColor Green"

echo.
echo Hoan tat! Tu nay moi khi may tinh khoi dong, dich vu Hardware Bridge se tu dong chay ngam.
echo.
pause
