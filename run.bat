@echo off
chcp 65001 > nul
title منصة شبح | SHABAH NEON PLATFORM
color 0b

echo.
echo ========================================================
echo    💀 تشغيل منصة شبح (SHABAH NEON PLATFORM) 💀
echo ========================================================
echo.

python -m pip install -r requirements.txt
echo.
echo [✓] جاري تشغيل خادم المنصة وبوت تلجرام...
echo.

python main.py
pause
