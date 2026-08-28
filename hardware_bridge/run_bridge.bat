@echo off
title Tuan Chau Resort - Door Lock Hardware Bridge
color 0A
echo ====================================================================
echo  TUAN CHAU RESORT HẠ LONG (CONG TY CP NGHI DUONG DAO)
echo  LOCAL HARDWARE BRIDGE SERVICE - KHOA THE TU PHONG KHACH SAN
echo ====================================================================
echo.
echo Dang khoi chay Hardware Bridge Service tren cong 8765...
python "%~dp0server.py" 8765
pause
