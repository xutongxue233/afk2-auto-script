"""
设置标签页
"""

from typing import Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QComboBox,
    QSpinBox, QCheckBox, QTextEdit, QFileDialog,
    QMessageBox, QScrollArea, QFormLayout
)
from PyQt6.QtCore import Qt

from src.services.config_service import ConfigService
from src.services.log_service import LoggerMixin


class SettingsTab(QWidget, LoggerMixin):
    """
    设置标签页
    管理应用配置
    """
    
    def __init__(self, config_service: ConfigService):
        """
        初始化设置标签页
        
        Args:
            config_service: 配置服务
        """
        super().__init__()
        self.config_service = config_service
        
        # 配置输入控件
        self.config_widgets: Dict[str, Any] = {}
        
        self._init_ui()
        self._load_config()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        # 滚动内容
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        
        # ADB设置组
        adb_group = self._create_adb_settings()
        content_layout.addWidget(adb_group)
        
        # 游戏设置组
        game_group = self._create_game_settings()
        content_layout.addWidget(game_group)
        
        # 识别设置组
        recognition_group = self._create_recognition_settings()
        content_layout.addWidget(recognition_group)
        
        # 任务设置组
        task_group = self._create_task_settings()
        content_layout.addWidget(task_group)
        
        # 日志设置组
        log_group = self._create_log_settings()
        content_layout.addWidget(log_group)
        
        content_layout.addStretch()
        
        # 按钮栏
        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)
        
        button_layout.addStretch()
        
        # 导入配置
        self.import_btn = QPushButton("导入配置")
        self.import_btn.clicked.connect(self._import_config)
        button_layout.addWidget(self.import_btn)
        
        # 导出配置
        self.export_btn = QPushButton("导出配置")
        self.export_btn.clicked.connect(self._export_config)
        button_layout.addWidget(self.export_btn)
        
        # 重置默认
        self.reset_btn = QPushButton("重置默认")
        self.reset_btn.clicked.connect(self._reset_config)
        button_layout.addWidget(self.reset_btn)
        
        # 应用按钮
        self.apply_btn = QPushButton("应用")
        self.apply_btn.clicked.connect(self._apply_config)
        button_layout.addWidget(self.apply_btn)
        
        # 保存按钮
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save_config)
        button_layout.addWidget(self.save_btn)
    
    def _create_adb_settings(self) -> QGroupBox:
        """创建ADB设置组"""
        group = QGroupBox("ADB设置")
        layout = QFormLayout()
        group.setLayout(layout)
        
        # ADB路径
        adb_layout = QHBoxLayout()
        self.adb_path = QLineEdit()
        self.config_widgets['adb_path'] = self.adb_path
        adb_layout.addWidget(self.adb_path)
        
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._browse_adb_path)
        adb_layout.addWidget(browse_btn)
        
        layout.addRow("ADB路径:", adb_layout)
        
        # 连接超时
        self.connect_timeout = QSpinBox()
        self.connect_timeout.setRange(1, 60)
        self.connect_timeout.setSuffix(" 秒")
        self.config_widgets['connect_timeout'] = self.connect_timeout
        layout.addRow("连接超时:", self.connect_timeout)
        
        # 命令超时
        self.command_timeout = QSpinBox()
        self.command_timeout.setRange(1, 60)
        self.command_timeout.setSuffix(" 秒")
        self.config_widgets['command_timeout'] = self.command_timeout
        layout.addRow("命令超时:", self.command_timeout)
        
        # 自动重连
        self.auto_reconnect = QCheckBox("自动重连")
        self.config_widgets['auto_reconnect'] = self.auto_reconnect
        layout.addRow("", self.auto_reconnect)
        
        return group
    
    def _create_game_settings(self) -> QGroupBox:
        """创建游戏设置组"""
        group = QGroupBox("游戏设置")
        layout = QFormLayout()
        group.setLayout(layout)
        
        # 包名
        self.package_name = QLineEdit()
        self.package_name.setText("com.lilith.odyssey.cn")
        self.config_widgets['package_name'] = self.package_name
        layout.addRow("包名:", self.package_name)
        
        # 启动Activity
        self.activity_name = QLineEdit()
        self.config_widgets['activity_name'] = self.activity_name
        layout.addRow("Activity:", self.activity_name)
        
        # 启动等待时间
        self.start_wait_time = QSpinBox()
        self.start_wait_time.setRange(1, 30)
        self.start_wait_time.setSuffix(" 秒")
        self.config_widgets['start_wait_time'] = self.start_wait_time
        layout.addRow("启动等待:", self.start_wait_time)
        
        # 操作延迟
        self.operation_delay = QSpinBox()
        self.operation_delay.setRange(100, 5000)
        self.operation_delay.setSuffix(" ms")
        self.operation_delay.setSingleStep(100)
        self.config_widgets['operation_delay'] = self.operation_delay
        layout.addRow("操作延迟:", self.operation_delay)
        
        return group
    
    def _create_recognition_settings(self) -> QGroupBox:
        """创建识别设置组"""
        group = QGroupBox("识别设置")
        layout = QFormLayout()
        group.setLayout(layout)
        
        # OCR引擎
        self.ocr_engine = QComboBox()
        self.ocr_engine.addItems(["pytesseract", "paddleocr"])
        self.config_widgets['ocr_engine'] = self.ocr_engine
        layout.addRow("OCR引擎:", self.ocr_engine)
        
        # OCR语言
        self.ocr_lang = QLineEdit()
        self.ocr_lang.setText("chi_sim+eng")
        self.config_widgets['ocr_lang'] = self.ocr_lang
        layout.addRow("OCR语言:", self.ocr_lang)
        
        # 图像匹配阈值
        self.match_threshold = QSpinBox()
        self.match_threshold.setRange(50, 100)
        self.match_threshold.setSuffix(" %")
        self.config_widgets['match_threshold'] = self.match_threshold
        layout.addRow("匹配阈值:", self.match_threshold)
        
        # 缓存模板
        self.cache_templates = QCheckBox("缓存模板图像")
        self.config_widgets['cache_templates'] = self.cache_templates
        layout.addRow("", self.cache_templates)
        
        return group
    
    def _create_task_settings(self) -> QGroupBox:
        """创建任务设置组"""
        group = QGroupBox("任务设置")
        layout = QFormLayout()
        group.setLayout(layout)
        
        # 最大并发任务
        self.max_concurrent_tasks = QSpinBox()
        self.max_concurrent_tasks.setRange(1, 10)
        self.config_widgets['max_concurrent_tasks'] = self.max_concurrent_tasks
        layout.addRow("最大并发:", self.max_concurrent_tasks)
        
        # 任务重试次数
        self.max_retries = QSpinBox()
        self.max_retries.setRange(0, 10)
        self.config_widgets['max_retries'] = self.max_retries
        layout.addRow("重试次数:", self.max_retries)
        
        # 任务超时
        self.task_timeout = QSpinBox()
        self.task_timeout.setRange(10, 3600)
        self.task_timeout.setSuffix(" 秒")
        self.config_widgets['task_timeout'] = self.task_timeout
        layout.addRow("任务超时:", self.task_timeout)
        
        # 保存任务历史
        self.save_task_history = QCheckBox("保存任务历史")
        self.config_widgets['save_task_history'] = self.save_task_history
        layout.addRow("", self.save_task_history)
        
        return group
    
    def _create_log_settings(self) -> QGroupBox:
        """创建日志设置组"""
        group = QGroupBox("日志设置")
        layout = QFormLayout()
        group.setLayout(layout)
        
        # 日志级别
        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.config_widgets['log_level'] = self.log_level
        layout.addRow("日志级别:", self.log_level)
        
        # 日志文件
        log_file_layout = QHBoxLayout()
        self.log_file = QLineEdit()
        self.config_widgets['log_file'] = self.log_file
        log_file_layout.addWidget(self.log_file)
        
        browse_log_btn = QPushButton("浏览")
        browse_log_btn.clicked.connect(self._browse_log_file)
        log_file_layout.addWidget(browse_log_btn)
        
        layout.addRow("日志文件:", log_file_layout)
        
        # 日志保留天数
        self.log_retention_days = QSpinBox()
        self.log_retention_days.setRange(1, 365)
        self.log_retention_days.setSuffix(" 天")
        self.config_widgets['log_retention_days'] = self.log_retention_days
        layout.addRow("保留天数:", self.log_retention_days)
        
        return group
    
    def _load_config(self):
        """加载配置到UI"""
        config = self.config_service.config
        
        # ADB设置
        self.adb_path.setText(config.adb.adb_path or "adb")
        self.connect_timeout.setValue(config.adb.connect_timeout)
        self.command_timeout.setValue(config.adb.command_timeout)
        self.auto_reconnect.setChecked(config.adb.auto_reconnect)
        
        # 游戏设置
        self.package_name.setText(config.game.package_name)
        self.activity_name.setText(config.game.activity_name or "")
        self.start_wait_time.setValue(config.game.start_wait_time)
        self.operation_delay.setValue(config.game.operation_delay)
        
        # 识别设置
        self.ocr_engine.setCurrentText(config.recognition.ocr_engine)
        self.ocr_lang.setText(config.recognition.ocr_lang)
        self.match_threshold.setValue(int(config.recognition.match_threshold * 100))
        self.cache_templates.setChecked(config.recognition.cache_templates)
        
        # 任务设置
        self.max_concurrent_tasks.setValue(config.max_concurrent_tasks)
        self.max_retries.setValue(config.task.max_retries)
        self.task_timeout.setValue(config.task.timeout)
        self.save_task_history.setChecked(config.task.save_history)
        
        # 日志设置
        self.log_level.setCurrentText(config.log_level)
        self.log_file.setText(config.log_file or "")
        self.log_retention_days.setValue(config.log_retention_days)
    
    def _apply_config(self):
        """应用配置（不保存）"""
        try:
            # 更新配置对象
            config = self.config_service.config
            
            # ADB设置
            config.adb.adb_path = self.adb_path.text() or None
            config.adb.connect_timeout = self.connect_timeout.value()
            config.adb.command_timeout = self.command_timeout.value()
            config.adb.auto_reconnect = self.auto_reconnect.isChecked()
            
            # 游戏设置
            config.game.package_name = self.package_name.text()
            config.game.activity_name = self.activity_name.text() or None
            config.game.start_wait_time = self.start_wait_time.value()
            config.game.operation_delay = self.operation_delay.value()
            
            # 识别设置
            config.recognition.ocr_engine = self.ocr_engine.currentText()
            config.recognition.ocr_lang = self.ocr_lang.text()
            config.recognition.match_threshold = self.match_threshold.value() / 100.0
            config.recognition.cache_templates = self.cache_templates.isChecked()
            
            # 任务设置
            config.max_concurrent_tasks = self.max_concurrent_tasks.value()
            config.task.max_retries = self.max_retries.value()
            config.task.timeout = self.task_timeout.value()
            config.task.save_history = self.save_task_history.isChecked()
            
            # 日志设置
            config.log_level = self.log_level.currentText()
            config.log_file = self.log_file.text() or None
            config.log_retention_days = self.log_retention_days.value()
            
            # 通知监听器
            self.config_service.notify_listeners()
            
            QMessageBox.information(self, "成功", "配置已应用")
            self.logger.info("Configuration applied")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"应用配置失败: {e}")
            self.logger.error(f"Failed to apply config: {e}")
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            # 先应用配置
            self._apply_config()
            
            # 保存到文件
            self.config_service.save_config()
            
            QMessageBox.information(self, "成功", "配置已保存")
            self.logger.info("Configuration saved")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置失败: {e}")
            self.logger.error(f"Failed to save config: {e}")
    
    def _reset_config(self):
        """重置为默认配置"""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置为默认配置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 重新加载默认配置
            self.config_service.reset_to_default()
            self._load_config()
            QMessageBox.information(self, "成功", "已重置为默认配置")
    
    def _import_config(self):
        """导入配置"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "导入配置",
            "",
            "YAML Files (*.yaml *.yml);;JSON Files (*.json);;All Files (*)"
        )
        
        if filename:
            try:
                self.config_service.load_config(filename)
                self._load_config()
                QMessageBox.information(self, "成功", "配置已导入")
                self.logger.info(f"Config imported from: {filename}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导入配置失败: {e}")
    
    def _export_config(self):
        """导出配置"""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "导出配置",
            "config.yaml",
            "YAML Files (*.yaml);;JSON Files (*.json);;All Files (*)"
        )
        
        if filename:
            try:
                self.config_service.save_config(filename)
                QMessageBox.information(self, "成功", "配置已导出")
                self.logger.info(f"Config exported to: {filename}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出配置失败: {e}")
    
    def _browse_adb_path(self):
        """浏览ADB路径"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择ADB程序",
            "",
            "Executable Files (*.exe);;All Files (*)"
        )
        
        if filename:
            self.adb_path.setText(filename)
    
    def _browse_log_file(self):
        """浏览日志文件"""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "选择日志文件",
            "afk2_auto.log",
            "Log Files (*.log);;All Files (*)"
        )
        
        if filename:
            self.log_file.setText(filename)