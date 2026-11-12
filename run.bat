@echo off
chcp 65001 >nul
title x-direct-cn - X 关注动态实时提醒
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [!] 没找到 Python。请先安装 Python 3.8+ 并勾选 "Add Python to PATH"
  echo     https://www.python.org/downloads/
  pause
  exit /b 1
)

echo.
echo   x-direct-cn 启动中... 按 Ctrl+C 停止
echo   数据源: api.fxtwitter.com  ^|  国内直连 / 免费 / 零 Key
echo   日志:   %~dp0watch.log
echo.
python x_watch.py
pause
