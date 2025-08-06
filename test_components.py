#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
组件测试脚本
测试各个组件是否正常工作
"""

import sys
from pathlib import Path

def test_imports():
    """测试所有模块导入"""
    print("测试模块导入...")
    
    modules = [
        # Services
        "src.services.config_service",
        "src.services.log_service",
        "src.services.adb_service",
        
        # Models
        "src.models.config",
        "src.models.device",
        "src.models.task",
        
        # Recognition
        "src.recognition.image_recognizer",
        "src.recognition.ocr_engine",
        
        # Controller
        "src.controller.base_controller",
        "src.controller.afk2_controller",
        
        # Task Management
        "src.tasks.task_manager",
        "src.tasks.task_scheduler",
        "src.tasks.task_executor",
        
        # Utils
        "src.utils.exceptions",
        "src.utils.retry",
        "src.utils.singleton",
    ]
    
    failed = []
    for module in modules:
        try:
            __import__(module)
            print(f"  [OK] {module}")
        except ImportError as e:
            print(f"  [FAIL] {module}: {e}")
            failed.append(module)
    
    if failed:
        print(f"\n失败的模块: {', '.join(failed)}")
        return False
    else:
        print("\n所有模块导入成功！")
        return True


def test_config():
    """测试配置系统"""
    print("\n测试配置系统...")
    
    try:
        from src.services.config_service import ConfigService
        config_service = ConfigService()
        config = config_service.config
        
        print(f"  [OK] 配置加载成功")
        print(f"    - ADB路径: {config.adb.adb_path}")
        print(f"    - 游戏包名: {config.game.package_name}")
        print(f"    - OCR引擎: {config.recognition.ocr_engine}")
        print(f"    - UI主题: {config.ui.theme}")
        return True
        
    except Exception as e:
        print(f"  [FAIL] 配置测试失败: {e}")
        return False


def test_logging():
    """测试日志系统"""
    print("\n测试日志系统...")
    
    try:
        from src.services.log_service import LoggerMixin
        
        class TestClass(LoggerMixin):
            def test_log(self):
                self.logger.debug("Debug message")
                self.logger.info("Info message")
                self.logger.warning("Warning message")
                self.logger.error("Error message")
        
        test_obj = TestClass()
        test_obj.test_log()
        
        print(f"  [OK] 日志系统正常")
        return True
        
    except Exception as e:
        print(f"  [FAIL] 日志测试失败: {e}")
        return False


def test_exceptions():
    """测试异常系统"""
    print("\n测试异常系统...")
    
    try:
        from src.utils.exceptions import (
            ADBConnectionError,
            GameNotRunningError,
            ImageNotFoundError,
            OCRRecognitionError,
            TaskExecutionError,
            ConfigLoadError,
            get_user_friendly_message
        )
        
        # 测试异常创建
        exc1 = ADBConnectionError("test_device")
        exc2 = GameNotRunningError()
        exc3 = ImageNotFoundError("template.png", 0.8)
        
        # 测试友好消息
        msg = get_user_friendly_message(exc1)
        
        print(f"  [OK] 异常系统正常")
        print(f"    - 已定义异常类型: ADB, Game, Recognition, Task, Config, Network")
        return True
        
    except Exception as e:
        print(f"  [FAIL] 异常测试失败: {e}")
        return False


def test_task_system():
    """测试任务系统"""
    print("\n测试任务系统...")
    
    try:
        from src.models.task import TaskInfo, TaskStatus, TaskPriority
        from src.tasks.task_manager import TaskManager
        
        # 创建测试任务
        task = TaskInfo(
            task_id="test_task",
            name="测试任务",
            priority=TaskPriority.NORMAL,
            handler=lambda: print("Task executed")
        )
        
        # 创建任务管理器
        manager = TaskManager(max_workers=2)
        
        print(f"  [OK] 任务系统正常")
        print(f"    - 任务状态: {', '.join([s.value for s in TaskStatus])}")
        print(f"    - 任务优先级: {', '.join([p.value for p in TaskPriority])}")
        return True
        
    except Exception as e:
        print(f"  [FAIL] 任务测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("=" * 50)
    print("AFK2自动化脚本 - 组件测试")
    print("=" * 50)
    
    results = []
    
    # 运行各项测试
    results.append(("模块导入", test_imports()))
    results.append(("配置系统", test_config()))
    results.append(("日志系统", test_logging()))
    results.append(("异常系统", test_exceptions()))
    results.append(("任务系统", test_task_system()))
    
    # 输出总结
    print("\n" + "=" * 50)
    print("测试结果总结:")
    print("-" * 50)
    
    passed = 0
    failed = 0
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print("-" * 50)
    print(f"总计: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        print("\n[SUCCESS] 所有组件测试通过！")
    else:
        print(f"\n[WARNING] 有 {failed} 个组件测试失败，请检查。")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)