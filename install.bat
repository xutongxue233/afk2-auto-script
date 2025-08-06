@echo off
echo ========================================
echo AFK2自动化脚本 - 依赖安装
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [信息] 检测到Python版本:
python --version
echo.

REM 升级pip
echo [步骤1] 升级pip...
python -m pip install --upgrade pip
echo.

REM 安装基础依赖
echo [步骤2] 安装基础依赖...
pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查错误信息
    pause
    exit /b 1
)
echo.

REM 询问是否安装开发依赖
set /p install_dev="是否安装开发依赖？(y/n): "
if /i "%install_dev%"=="y" (
    echo [步骤3] 安装开发依赖...
    pip install -r requirements-dev.txt
    echo.
)

REM 询问是否安装PaddleOCR
set /p install_paddle="是否安装PaddleOCR（可选，文件较大）？(y/n): "
if /i "%install_paddle%"=="y" (
    echo [步骤4] 安装PaddleOCR...
    pip install paddlepaddle paddleocr
    echo.
)

REM 检查Tesseract
echo [信息] 检查Tesseract-OCR...
tesseract --version >nul 2>&1
if errorlevel 1 (
    echo [警告] 未检测到Tesseract-OCR，OCR功能可能无法使用
    echo 下载地址: https://github.com/UB-Mannheim/tesseract/wiki
) else (
    echo [信息] Tesseract-OCR已安装
)
echo.

REM 检查ADB
echo [信息] 检查ADB...
adb version >nul 2>&1
if errorlevel 1 (
    echo [警告] 未检测到ADB，请确保ADB已安装并添加到PATH
    echo 下载地址: https://developer.android.com/studio/releases/platform-tools
) else (
    echo [信息] ADB已安装
    adb version
)
echo.

echo ========================================
echo 安装完成！
echo.
echo 运行程序:
echo   python run.py           - GUI模式
echo   python run.py --help    - 查看帮助
echo   python test_gui.py      - 测试环境
echo ========================================
pause