#!/bin/bash

echo "========================================"
echo "AFK2自动化脚本 - 依赖安装"
echo "========================================"
echo

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[错误] 未检测到Python3，请先安装Python 3.8+${NC}"
    echo "Ubuntu/Debian: sudo apt-get install python3 python3-pip"
    echo "macOS: brew install python3"
    exit 1
fi

echo -e "${GREEN}[信息] 检测到Python版本:${NC}"
python3 --version
echo

# 创建虚拟环境（可选）
read -p "是否创建虚拟环境？(y/n): " create_venv
if [[ $create_venv == "y" || $create_venv == "Y" ]]; then
    echo -e "${GREEN}[步骤1] 创建虚拟环境...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    echo -e "${GREEN}虚拟环境已激活${NC}"
    echo
fi

# 升级pip
echo -e "${GREEN}[步骤2] 升级pip...${NC}"
python3 -m pip install --upgrade pip
echo

# 安装基础依赖
echo -e "${GREEN}[步骤3] 安装基础依赖...${NC}"
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}[错误] 依赖安装失败，请检查错误信息${NC}"
    exit 1
fi
echo

# 询问是否安装开发依赖
read -p "是否安装开发依赖？(y/n): " install_dev
if [[ $install_dev == "y" || $install_dev == "Y" ]]; then
    echo -e "${GREEN}[步骤4] 安装开发依赖...${NC}"
    pip install -r requirements-dev.txt
    echo
fi

# 询问是否安装PaddleOCR
read -p "是否安装PaddleOCR（可选，文件较大）？(y/n): " install_paddle
if [[ $install_paddle == "y" || $install_paddle == "Y" ]]; then
    echo -e "${GREEN}[步骤5] 安装PaddleOCR...${NC}"
    pip install paddlepaddle paddleocr
    echo
fi

# 检查Tesseract
echo -e "${GREEN}[信息] 检查Tesseract-OCR...${NC}"
if ! command -v tesseract &> /dev/null; then
    echo -e "${YELLOW}[警告] 未检测到Tesseract-OCR，OCR功能可能无法使用${NC}"
    echo "Ubuntu/Debian: sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim"
    echo "macOS: brew install tesseract tesseract-lang"
else
    echo -e "${GREEN}[信息] Tesseract-OCR已安装${NC}"
    tesseract --version | head -n 1
fi
echo

# 检查ADB
echo -e "${GREEN}[信息] 检查ADB...${NC}"
if ! command -v adb &> /dev/null; then
    echo -e "${YELLOW}[警告] 未检测到ADB，请确保ADB已安装${NC}"
    echo "Ubuntu/Debian: sudo apt-get install android-tools-adb"
    echo "macOS: brew install android-platform-tools"
else
    echo -e "${GREEN}[信息] ADB已安装${NC}"
    adb version | head -n 1
fi
echo

# 设置执行权限
chmod +x run.py test_gui.py

echo "========================================"
echo -e "${GREEN}安装完成！${NC}"
echo
echo "运行程序:"
echo "  python3 run.py           - GUI模式"
echo "  python3 run.py --help    - 查看帮助"
echo "  python3 test_gui.py      - 测试环境"
echo
if [[ $create_venv == "y" || $create_venv == "Y" ]]; then
    echo "激活虚拟环境: source venv/bin/activate"
fi
echo "========================================"