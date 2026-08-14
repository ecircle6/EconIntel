@echo off
chcp 65001 >nul
title EconIntel 更新
cd /d "%~dp0..\.."

echo ==========================================
echo   EconIntel 更新（采集 - 分析 - 生成网站）
echo ==========================================

if not exist ".venv\Scripts\python.exe" (
    echo [首次运行] 创建虚拟环境并安装依赖...
    python -m venv .venv
    if errorlevel 1 (echo 创建虚拟环境失败，请确认已安装 Python 3.10+ & pause & exit /b 1)
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (echo 依赖安装失败 & pause & exit /b 1)
)

echo [1/2] 开始采集与更新...
.venv\Scripts\python.exe generator\scripts\daily.py
if errorlevel 1 (
    echo.
    echo 更新失败，请检查网络或上面的错误信息。
    pause
    exit /b 1
)

echo [2/2] 打开网站...
start "" "site\index.html"
pause
