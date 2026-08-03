@echo off
chcp 65001 >nul
echo ================================================
echo   知拾 KT 后端启动脚本
echo ================================================
echo.

REM 检测 conda 环境
call conda activate xzs 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] conda 环境 'xzs' 不存在
    echo 请先运行: conda create -n xzs python=3.14 -y
    pause
    exit /b 1
)

REM 检测 Python 版本
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [信息] Python 版本: %PYVER%
if not "%PYVER:~0,4%"=="3.14" (
    echo [警告] Python 不是 3.14，.pyd 文件可能无法加载
    echo 当前版本: %PYVER%
)

REM 检测 logic_matrix.npy
if not exist "..\data\knowledge_graph\logic_matrix.npy" (
    echo [警告] logic_matrix.npy 不存在，正在生成默认示例...
    python generate_matrix.py
)

REM 检测 .pyd 文件
set PYD_COUNT=0
for %%f in (lekt_api lekt_core ladl_operator metrics_LVR_VS) do (
    if exist "%%f.cp314-win_amd64.pyd" set /a PYD_COUNT+=1
)
echo [信息] .pyd 文件: %PYD_COUNT%/4 个

if %PYD_COUNT% LSS 4 (
    echo [警告] .pyd 文件缺失，将使用纯 NumPy 回退算法
    echo 功能不受影响，但精度略低于 .pyd 优化版
)

echo.
echo [启动] 后端服务: http://127.0.0.1:8765
echo [文档] API 文档:  http://127.0.0.1:8765/docs
echo [退出] 按 Ctrl+C 停止服务
echo ================================================
echo.

uvicorn server:app --host 127.0.0.1 --port 8765

pause
