#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AFK2自动化脚本主程序
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from src.services.log_service import setup_logging
from src.services.adb_service import ADBService
from src.services.config_service import config_service
from src.controller.afk2_controller import AFK2Controller
from src.recognition.image_recognizer import ImageRecognizer
from src.recognition.ocr_engine import OCREngine, OCRConfig
from src.tasks.task_manager import TaskManager
from src.tasks.task_scheduler import TaskScheduler
from src.tasks.task_executor import TaskExecutor
from src.tasks.builtin_tasks import DailyIdleRewardTaskBuilder


def setup_components():
    """
    初始化所有组件
    
    Returns:
        组件字典
    """
    # 加载配置
    config = config_service.config
    
    # 初始化ADB服务
    adb_service = ADBService(config.adb)
    
    # 初始化识别器
    image_recognizer = ImageRecognizer(
        template_dir=Path("templates"),
        cache_templates=True
    )
    
    ocr_config = OCRConfig(
        lang=config.recognition.ocr_language
    )
    # 启动时预加载OCR引擎，避免首次使用时的延迟
    ocr_engine = OCREngine(ocr_config, preload=True)
    
    # 初始化游戏控制器
    game_controller = AFK2Controller(
        adb_service=adb_service,
        config=config.game,
        image_recognizer=image_recognizer,
        ocr_engine=ocr_engine
    )
    
    # 初始化任务管理器
    task_manager = TaskManager(
        max_concurrent_tasks=3,  # 默认最大并发任务数
        task_history_dir=Path("task_history")
    )
    
    task_executor = TaskExecutor(game_controller=game_controller)
    
    task_scheduler = TaskScheduler(
        task_manager=task_manager,
        task_executor=task_executor,
        max_workers=3  # 默认最大并发任务数
    )
    
    return {
        'config': config,
        'adb': adb_service,
        'recognizer': image_recognizer,
        'ocr': ocr_engine,
        'controller': game_controller,
        'task_manager': task_manager,
        'task_executor': task_executor,
        'task_scheduler': task_scheduler
    }


def run_daily_idle_reward(components):
    """
    运行每日挂机奖励任务
    
    Args:
        components: 组件字典
    """
    print("开始运行每日挂机奖励任务...")
    
    controller = components['controller']
    adb_service = components['adb_service']
    image_recognizer = components['image_recognizer']
    ocr_engine = components['ocr_engine']
    
    # 创建唤醒游戏任务
    from src.tasks.wake_game_task import WakeGameTask
    wake_task = WakeGameTask()
    
    # 执行唤醒游戏任务
    print("正在唤醒游戏...")
    if wake_task.execute(controller):
        print("游戏唤醒成功")
    else:
        print("游戏唤醒失败")
        return False
    
    # 运行每日挂机奖励任务
    from src.tasks.daily_idle_reward_task import DailyIdleRewardTask
    task = DailyIdleRewardTask(adb_service, image_recognizer, ocr_engine)
    result = task.execute()
    
    if result:
        print("✓ 每日挂机奖励领取成功")
    else:
        print("✗ 每日挂机奖励领取失败")
    
    return result

# 保留原来的函数名以保持兼容性
def run_daily_tasks(components):
    return run_daily_idle_reward(components)


def run_campaign(components, max_battles=10):
    """
    征战任务（已移除）
    
    Args:
        components: 组件字典
        max_battles: 最大战斗次数
    """
    print("征战任务已被移除，请使用每日挂机奖励任务")
    return False


def run_with_scheduler(components):
    """
    使用调度器运行
    
    Args:
        components: 组件字典
    """
    print("启动任务调度器...")
    
    task_manager = components['task_manager']
    task_scheduler = components['task_scheduler']
    
    # 创建每日挂机奖励任务
    daily_idle = DailyIdleRewardTaskBuilder(task_manager)
    
    # 设置每日任务（早上8点和晚上8点）
    morning_time = datetime.now().replace(hour=8, minute=0, second=0)
    evening_time = datetime.now().replace(hour=20, minute=0, second=0)
    
    # 如果当前时间已过，设置为明天
    now = datetime.now()
    if morning_time < now:
        morning_time = morning_time.replace(day=morning_time.day + 1)
    if evening_time < now:
        evening_time = evening_time.replace(day=evening_time.day + 1)
    
    # 创建定时任务
    morning_task = daily_idle.create(scheduled_time=morning_time)
    evening_task = daily_idle.create(scheduled_time=evening_time)
    
    print(f"已设置定时任务（每日挂机奖励）：")
    print(f"  早上: {morning_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"  晚上: {evening_time.strftime('%Y-%m-%d %H:%M')}")
    
    # 启动调度器
    task_scheduler.start()
    
    print("\n调度器运行中，按Ctrl+C退出...")
    
    try:
        while True:
            import time
            time.sleep(60)
            
            # 打印状态
            stats = task_manager.get_statistics()
            queue_status = task_scheduler.get_queue_status()
            
            print(f"\r任务状态 - 总数:{stats['total']} 待运行:{stats['pending']} "
                  f"运行中:{stats['running']} 已完成:{stats['completed']} "
                  f"队列:{queue_status['queue_size']}", end="")
            
    except KeyboardInterrupt:
        print("\n\n正在停止调度器...")
        task_scheduler.stop(wait=True)
        print("已停止")


def test_connection(components):
    """
    测试ADB连接
    
    Args:
        components: 组件字典
    """
    print("测试ADB连接...")
    
    adb = components['adb']
    
    # 获取设备列表
    devices = adb.get_devices()
    
    if not devices:
        print("未找到设备！请检查：")
        print("  1. 设备是否已通过USB连接或WiFi连接")
        print("  2. 设备是否已开启开发者USB调试")
        print("  3. ADB驱动是否正确安装")
        return False
    
    print(f"找到 {len(devices)} 个设备：")
    for device in devices:
        print(f"  - {device.device_id} ({device.device_name}) - {device.status.value}")
    
    # 连接第一个设备
    if adb.connect_device():
        print(f"\n已连接到设备: {adb.current_device.device_id}")
        
        # 测试截图
        print("测试截图功能...")
        screenshot = adb.screenshot()
        if screenshot:
            print("截图成功！")
            # 保存截图
            screenshot.save("test_screenshot.png")
            print("截图已保存: test_screenshot.png")
        
        return True
    else:
        print("设备连接失败！")
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='AFK2自动化脚本')
    parser.add_argument('--mode', choices=['daily', 'idle_reward', 'scheduler', 'test', 'gui'],
                       default='gui', help='运行模式 (默认: gui)')
    parser.add_argument('--battles', type=int, default=10,
                       help='征战最大战斗次数')
    parser.add_argument('--config', type=str, default='config.yaml',
                       help='配置文件路径')
    parser.add_argument('--debug', action='store_true',
                       help='开启调试模式')
    
    # 如果没有提供参数，直接运行GUI模式
    if len(sys.argv) == 1:
        # 启动GUI
        try:
            from PyQt6.QtWidgets import QApplication
            from src.gui.main_window import MainWindow
            
            print("=" * 50)
            print("AFK2自动化脚本 - GUI模式")
            print("=" * 50)
            print("启动图形界面...")
            
            # 创建Qt应用
            app = QApplication(sys.argv)
            app.setStyle("Fusion")
            
            # 创建并显示主窗口
            window = MainWindow()
            window.show()
            
            # 运行应用
            return app.exec()
        except ImportError as e:
            print(f"无法启动GUI: {e}")
            print("请确保已安装PyQt6: pip install PyQt6")
            return 1
    
    args = parser.parse_args()
    
    # 设置日志
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(log_level)
    
    print("=" * 50)
    print("AFK2自动化脚本 v1.0")
    print("=" * 50)
    
    try:
        # 初始化组件
        print("初始化组件...")
        components = setup_components()
        print("初始化完成！\n")
        
        # 根据模式运行
        if args.mode == 'test':
            # 测试连接
            test_connection(components)
            
        elif args.mode == 'daily' or args.mode == 'idle_reward':
            # 运行每日挂机奖励任务
            run_daily_idle_reward(components)
            
        elif args.mode == 'scheduler':
            # 使用调度器
            run_with_scheduler(components)
            
        elif args.mode == 'gui':
            # 启动GUI
            try:
                from PyQt6.QtWidgets import QApplication
                from src.gui.main_window import MainWindow
                
                print("启动GUI模式...")
                
                # 创建Qt应用
                app = QApplication(sys.argv)
                app.setStyle("Fusion")
                
                # 创建并显示主窗口
                window = MainWindow()
                window.show()
                
                # 运行应用
                return app.exec()
            except ImportError as e:
                print(f"无法启动GUI: {e}")
                print("请确保已安装PyQt6: pip install PyQt6")
                return 1
            
    except KeyboardInterrupt:
        print("\n\n用户取消")
    except Exception as e:
        print(f"\n错误: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())