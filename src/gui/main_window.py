"""
GUI主窗口
"""

import sys
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTextEdit, QMenuBar, QMenu, QStatusBar,
    QToolBar, QMessageBox, QSplitter, QDockWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QIcon, QFont, QTextCursor

from src.services.log_service import LoggerMixin, get_logger
from src.gui.tabs.adb_tab_compact import ADBTab
from src.gui.tabs.task_tab import TaskTab
from src.gui.tabs.settings_tab import SettingsTab
from src.gui.tabs.monitor_tab import MonitorTab
from src.gui.widgets.log_widget import LogWidget
from src.gui.widgets.status_widget import StatusWidget
from src.services.adb_service import ADBService
from src.services.config_service import config_service
from src.controller.afk2_controller import AFK2Controller
from src.tasks.task_manager import TaskManager
from src.tasks.task_scheduler import TaskScheduler
from src.tasks.task_executor import TaskExecutor
from src.recognition.image_recognizer import ImageRecognizer
from src.recognition.ocr_engine import OCREngine, OCRConfig
from pathlib import Path


class MainWindow(QMainWindow, LoggerMixin):
    """
    主窗口类
    """
    
    def __init__(self):
        """初始化主窗口"""
        super().__init__()
        
        # 初始化组件
        self._init_components()
        
        # 初始化UI
        self._init_ui()
        
        # 初始化菜单栏
        self._init_menu_bar()
        
        # 初始化工具栏
        self._init_tool_bar()
        
        # 初始化状态栏
        self._init_status_bar()
        
        # 加载设置
        self._load_settings()
        
        # 启动后台服务
        self._start_services()
        
        self.logger.info("Main window initialized")
    
    def _init_components(self):
        """初始化核心组件"""
        # 加载配置
        self.config = config_service.config
        
        # 初始化ADB服务
        self.adb_service = ADBService(self.config.adb)
        
        # 初始化识别器
        self.image_recognizer = ImageRecognizer(
            template_dir=Path("templates"),
            cache_templates=True
        )
        
        ocr_config = OCRConfig(
            lang=self.config.recognition.ocr_language
        )
        # 创建OCR引擎，但不立即预加载以避免启动时报错
        try:
            self.ocr_engine = OCREngine(ocr_config, preload=False)
            # 异步预加载OCR引擎
            QTimer.singleShot(1000, self._preload_ocr_engine)
        except Exception as e:
            self.logger.warning(f"Failed to create OCR engine: {e}")
            self.ocr_engine = None
        
        # 初始化游戏控制器
        self.game_controller = AFK2Controller(
            adb_service=self.adb_service,
            config=self.config.game,
            image_recognizer=self.image_recognizer,
            ocr_engine=self.ocr_engine
        )
        
        # 初始化任务管理器
        self.task_manager = TaskManager(
            max_concurrent_tasks=3,  # 默认最大并发任务数
            task_history_dir=Path("task_history")
        )
        
        self.task_executor = TaskExecutor(
            game_controller=self.game_controller, 
            adb_service=self.adb_service,
            ocr_engine=self.ocr_engine
        )
        
        self.task_scheduler = TaskScheduler(
            task_manager=self.task_manager,
            task_executor=self.task_executor,
            max_workers=3  # 默认最大并发任务数
        )
    
    def _init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("AFK2 自动化脚本 v1.0")
        # 设置窗口大小
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(1000, 700)
        self.setMaximumSize(1600, 1000)
        
        # 设置窗口样式 - 紧凑的样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: white;
            }
            QTabBar::tab {
                padding: 4px 12px;
                margin-right: 2px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #4CAF50;
            }
            QToolBar {
                spacing: 2px;
                padding: 2px;
                max-height: 30px;
            }
            QStatusBar {
                max-height: 22px;
                font-size: 11px;
            }
        """)
        
        # 创建中心widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局（水平布局）
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)
        
        # 创建水平分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        splitter.addWidget(self.tab_widget)
        
        # 添加各个标签页
        self._add_tabs()
        
        # 创建日志窗口（放在右侧）
        self.log_widget = LogWidget()
        self.log_widget.setMinimumWidth(300)  # 日志窗口最小宽度
        splitter.addWidget(self.log_widget)
        
        # 设置分割器比例（左侧标签页：右侧日志 = 7:3）
        splitter.setSizes([700, 300])
    
    def _add_tabs(self):
        """添加标签页"""
        # ADB配置标签页
        self.adb_tab = ADBTab(self.adb_service)
        self.tab_widget.addTab(self.adb_tab, "ADB配置")
        
        # 任务管理标签页
        self.task_tab = TaskTab(
            self.task_manager,
            self.task_scheduler,
            self.game_controller
        )
        self.tab_widget.addTab(self.task_tab, "任务管理")
        
        # 监控标签页
        self.monitor_tab = MonitorTab(
            self.adb_service,
            self.game_controller
        )
        self.tab_widget.addTab(self.monitor_tab, "实时监控")
        
        # 设置标签页
        self.settings_tab = SettingsTab(config_service)
        self.tab_widget.addTab(self.settings_tab, "设置")
    
    
    def _init_menu_bar(self):
        """初始化菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        # 导入配置
        import_action = QAction("导入配置", self)
        import_action.triggered.connect(self._import_config)
        file_menu.addAction(import_action)
        
        # 导出配置
        export_action = QAction("导出配置", self)
        export_action.triggered.connect(self._export_config)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        # 退出
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具")
        
        # 截图工具
        screenshot_action = QAction("截图工具", self)
        screenshot_action.triggered.connect(self._open_screenshot_tool)
        tools_menu.addAction(screenshot_action)
        
        # 模板管理
        template_action = QAction("模板管理", self)
        template_action.triggered.connect(self._open_template_manager)
        tools_menu.addAction(template_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        # 使用说明
        manual_action = QAction("使用说明", self)
        manual_action.triggered.connect(self._show_manual)
        help_menu.addAction(manual_action)
        
        # 关于
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _init_tool_bar(self):
        """初始化工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # 连接设备
        connect_action = QAction("连接设备", self)
        connect_action.triggered.connect(self._connect_device)
        toolbar.addAction(connect_action)
        
        toolbar.addSeparator()
        
        # 启动游戏
        start_game_action = QAction("启动游戏", self)
        start_game_action.triggered.connect(self._start_game)
        toolbar.addAction(start_game_action)
        
        # 停止游戏
        stop_game_action = QAction("停止游戏", self)
        stop_game_action.triggered.connect(self._stop_game)
        toolbar.addAction(stop_game_action)
        
        toolbar.addSeparator()
        
        # 开始任务
        start_task_action = QAction("开始任务", self)
        start_task_action.triggered.connect(self._start_tasks)
        toolbar.addAction(start_task_action)
        
        # 停止任务
        stop_task_action = QAction("停止任务", self)
        stop_task_action.triggered.connect(self._stop_tasks)
        toolbar.addAction(stop_task_action)
        
        toolbar.addSeparator()
        
        # 清空日志
        clear_log_action = QAction("清空日志", self)
        clear_log_action.triggered.connect(self.log_widget.clear)
        toolbar.addAction(clear_log_action)
    
    def _init_status_bar(self):
        """初始化状态栏"""
        self.status_widget = StatusWidget()
        self.statusBar().addPermanentWidget(self.status_widget)
        
        # 定时更新状态 - 降低频率减少性能消耗
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(5000)  # 每5秒更新一次状态
    
    def _load_settings(self):
        """加载设置"""
        # TODO: 从配置文件加载窗口设置
        pass
    
    def _save_settings(self):
        """保存设置"""
        # TODO: 保存窗口设置到配置文件
        pass
    
    def _start_services(self):
        """启动后台服务"""
        # 启动任务调度器
        self.task_scheduler.start()
        self.logger.info("Task scheduler started")
    
    def _stop_services(self):
        """停止后台服务"""
        # 停止任务调度器
        self.task_scheduler.stop(wait=True)
        self.logger.info("Task scheduler stopped")
    
    def _update_status(self):
        """更新状态栏 - 简化版本，只更新设备和任务状态"""
        try:
            # 缓存上次的状态，避免重复更新
            if not hasattr(self, '_last_status_cache'):
                self._last_status_cache = {}
            
            # 更新设备状态（从内存缓存获取，不执行ADB命令）
            if self.adb_service.current_device:
                device_status = f"已连接: {self.adb_service.current_device.device_id}"
            else:
                device_status = "未连接"
            
            # 任务状态（内存获取，无IO开销）
            stats = self.task_manager.get_statistics()
            task_status = f"任务: {stats['running']}/{stats['total']}"
            
            # 检查状态是否变化，避免无用的UI更新
            current_status = {
                'device': device_status,
                'task': task_status
            }
            
            if self._last_status_cache != current_status:
                # 只有状态变化时才更新UI
                try:
                    self.status_widget.update_status(
                        device_status=device_status,
                        task_status=task_status
                    )
                    self._last_status_cache = current_status
                except Exception as e:
                    self.logger.error(f"Failed to update status widget: {e}")
                    
        except Exception as e:
            # 捕获所有异常，防止定时器任务崩溃导致程序退出
            self.logger.error(f"Status update error (non-critical): {e}")
            # 不重新抛出异常，让程序继续运行
    
    # ========== 槽函数 ==========
    
    def _connect_device(self):
        """连接设备"""
        if self.adb_service.connect_device():
            QMessageBox.information(self, "成功", "设备连接成功")
        else:
            QMessageBox.warning(self, "失败", "设备连接失败")
    
    def _start_game(self):
        """启动游戏"""
        try:
            self.game_controller.start_game()
            QMessageBox.information(self, "成功", "游戏启动成功")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"游戏启动失败: {e}")
    
    def _stop_game(self):
        """停止游戏"""
        try:
            self.game_controller.stop_game()
            QMessageBox.information(self, "成功", "游戏已停止")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"停止游戏失败: {e}")
    
    def _start_tasks(self):
        """开始任务"""
        self.task_tab.start_selected_tasks()
    
    def _stop_tasks(self):
        """停止任务"""
        self.task_tab.stop_all_tasks()
    
    def _import_config(self):
        """导入配置"""
        # TODO: 实现配置导入
        QMessageBox.information(self, "提示", "配置导入功能开发中")
    
    def _export_config(self):
        """导出配置"""
        # TODO: 实现配置导出
        QMessageBox.information(self, "提示", "配置导出功能开发中")
    
    def _open_screenshot_tool(self):
        """打开截图工具"""
        # TODO: 实现截图工具
        QMessageBox.information(self, "提示", "截图工具开发中")
    
    def _open_template_manager(self):
        """打开模板管理器"""
        # TODO: 实现模板管理器
        QMessageBox.information(self, "提示", "模板管理器开发中")
    
    def _show_manual(self):
        """显示使用说明"""
        QMessageBox.information(
            self,
            "使用说明",
            "AFK2自动化脚本使用说明：\n\n"
            "1. 在ADB配置页面连接设备\n"
            "2. 在任务管理页面选择要执行的任务\n"
            "3. 点击开始任务按钮执行\n"
            "4. 在实时监控页面查看执行状态\n"
            "5. 在设置页面调整参数"
        )
    
    def _show_about(self):
        """显示关于"""
        QMessageBox.about(
            self,
            "关于",
            "AFK2自动化脚本 v1.0\n\n"
            "基于Python + PyQt6 + ADB开发\n"
            "支持自动化日常任务、征战推图等功能"
        )
    
    def closeEvent(self, event):
        """关闭事件"""
        # 确认退出
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 停止状态定时器
            if hasattr(self, 'status_timer'):
                self.status_timer.stop()
            
            # 清理各个标签页的资源
            if hasattr(self, 'adb_tab'):
                self.adb_tab.cleanup()
            
            # 保存设置
            self._save_settings()
            
            # 停止服务
            self._stop_services()
            
            event.accept()
        else:
            event.ignore()
    
    def _preload_ocr_engine(self):
        """异步预加载OCR引擎"""
        if self.ocr_engine:
            try:
                self.logger.info("Starting OCR engine preload...")
                if self.ocr_engine.preload():
                    self.logger.info("OCR engine preloaded successfully")
                else:
                    self.logger.warning("OCR engine preload failed")
            except Exception as e:
                self.logger.warning(f"OCR engine preload error: {e}")


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    main()