@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo   知拾 - 后端服务
echo ================================================
echo.

if not exist "..\.venv\Scripts\python.exe" (
    echo [错误] 未找到 ..\.venv\Scripts\python.exe
    echo 请在项目根目录创建虚拟环境:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r backend\requirements.txt
    echo.
    pause
    exit /b 1
)

call "..\.venv\Scripts\activate.bat"

echo [启动] 后端: http://127.0.0.1:8765
echo [文档] API:  http://127.0.0.1:8765/docs
echo [退出] 按 Ctrl+C 停止
echo ================================================
echo.

uvicorn server:app --host 127.0.0.1 --port 8765 --reload

pause
