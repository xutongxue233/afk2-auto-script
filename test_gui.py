#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试GUI是否能正常启动
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """测试导入"""
    try:
        print("测试导入PyQt6...")
        from PyQt6.QtWidgets import QApplication, QMainWindow
        print("✓ PyQt6导入成功")
    except ImportError as e:
        print(f"✗ PyQt6导入失败: {e}")
        return False
    
    try:
        print("测试导入PIL...")
        from PIL import Image
        print("✓ PIL导入成功")
    except ImportError as e:
        print(f"✗ PIL导入失败: {e}")
        print("请安装: pip install Pillow")
        return False
    
    try:
        print("测试导入OpenCV...")
        import cv2
        print("✓ OpenCV导入成功")
    except ImportError as e:
        print(f"✗ OpenCV导入失败: {e}")
        print("请安装: pip install opencv-python")
        return False
    
    try:
        print("测试导入其他依赖...")
        import yaml
        import numpy
        print("✓ 其他依赖导入成功")
    except ImportError as e:
        print(f"✗ 依赖导入失败: {e}")
        return False
    
    return True

def test_simple_gui():
    """测试简单的GUI窗口"""
    try:
        from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel
        from PyQt6.QtCore import Qt
        
        app = QApplication(sys.argv)
        
        window = QMainWindow()
        window.setWindowTitle("AFK2自动化脚本 - 测试窗口")
        window.setGeometry(100, 100, 400, 300)
        
        label = QLabel("GUI测试成功！\n\n如果你能看到这个窗口，说明GUI环境正常。\n\n关闭窗口继续...")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        window.setCentralWidget(label)
        
        window.show()
        
        return app.exec()
    except Exception as e:
        print(f"GUI测试失败: {e}")
        return 1

def main():
    """主函数"""
    print("=" * 50)
    print("AFK2自动化脚本 - 环境测试")
    print("=" * 50)
    
    # 测试导入
    if not test_imports():
        print("\n环境检查失败，请安装缺失的依赖包")
        return 1
    
    print("\n所有依赖已安装，测试GUI...")
    
    # 测试GUI
    return test_simple_gui()

if __name__ == "__main__":
    sys.exit(main())