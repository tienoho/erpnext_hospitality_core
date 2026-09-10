@echo off
title Dung Hardware Bridge - Tuan Chau Resort
echo ====================================================================
echo  TUAN CHAU RESORT - DUNG DICH VU HARDWARE BRIDGE DANG CHAY
echo ====================================================================
echo.
echo Dang tim tien trinh dang lang nghe tren cong 8765...

powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force; Write-Host \"Da dung tien trinh PID: $_\" }"

echo.
echo Kiem tra trang thai cong 8765:
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue) { Write-Host 'Cong 8765 van dang bận!' -ForegroundColor Red } else { Write-Host 'Cong 8765 da duoc giai phong hoan toan!' -ForegroundColor Green }"
echo.
pause
