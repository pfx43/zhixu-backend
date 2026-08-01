@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo   知拾 - 前端开发服务
echo ================================================
echo.

if not exist "node_modules" (
    echo [提示] 未找到 node_modules，正在安装依赖...
    call npm install
    if errorlevel 1 (
        echo [错误] npm install 失败
        pause
        exit /b 1
    )
    echo.
)

echo [启动] 前端: http://127.0.0.1:5173
echo [退出] 按 Ctrl+C 停止
echo ================================================
echo.

npm run dev

pause
