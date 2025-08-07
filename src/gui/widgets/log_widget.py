"""
日志显示Widget
"""

import logging
from datetime import datetime
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QComboBox, QLabel, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont

from src.services.log_service import LoggerMixin


class LogHandler(logging.Handler):
    """
    自定义日志处理器，将日志发送到GUI
    """
    
    def __init__(self, log_widget):
        super().__init__()
        self.log_widget = log_widget
        
    def emit(self, record):
        """发送日志记录"""
        try:
            msg = self.format(record)
            self.log_widget.append_log(msg, record.levelname)
        except:
            pass


class LogWidget(QWidget, LoggerMixin):
    """
    日志显示Widget
    """
    
    # 信号定义
    log_appended = pyqtSignal(str, str)  # 日志内容, 级别
    
    def __init__(self, parent=None):
        """
        初始化日志Widget
        
        Args:
            parent: 父widget
        """
        super().__init__(parent)
        
        # 日志级别颜色
        self.level_colors = {
            'DEBUG': QColor(128, 128, 128),
            'INFO': QColor(0, 0, 0),
            'WARNING': QColor(255, 165, 0),
            'ERROR': QColor(255, 0, 0),
            'CRITICAL': QColor(139, 0, 0)
        }
        
        # 最大日志行数
        self.max_lines = 1000
        self.auto_scroll = True
        
        self._init_ui()
        self._setup_logging()
        
        # 连接信号
        self.log_appended.connect(self._on_log_appended)
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 控制栏
        control_layout = QHBoxLayout()
        layout.addLayout(control_layout)
        
        # 日志级别过滤
        control_layout.addWidget(QLabel("级别:"))
        
        self.level_filter = QComboBox()
        self.level_filter.addItems(['全部', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.level_filter.setCurrentText('INFO')
        self.level_filter.currentTextChanged.connect(self._on_level_changed)
        control_layout.addWidget(self.level_filter)
        
        # 自动滚动
        self.auto_scroll_check = QCheckBox("自动滚动")
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.toggled.connect(self._on_auto_scroll_toggled)
        control_layout.addWidget(self.auto_scroll_check)
        
        control_layout.addStretch()
        
        # 清空按钮
        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self.clear)
        control_layout.addWidget(self.clear_btn)
        
        # 保存按钮
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save_log)
        control_layout.addWidget(self.save_btn)
        
        # 日志显示区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.log_text)
    
    def _setup_logging(self):
        """设置日志处理器"""
        # 创建日志处理器
        self.log_handler = LogHandler(self)
        self.log_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                            datefmt='%H:%M:%S')
        )
        
        # 添加到主应用logger (AFK2Auto)
        app_logger = logging.getLogger('AFK2Auto')
        app_logger.addHandler(self.log_handler)
        
        # 同时添加到根logger以捕获所有日志
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        
        # 设置级别
        self._set_log_level('INFO')
    
    def _set_log_level(self, level_name: str):
        """设置日志级别"""
        if level_name == '全部':
            level = logging.DEBUG
        else:
            level = getattr(logging, level_name, logging.INFO)
        
        self.log_handler.setLevel(level)
    
    def _on_level_changed(self, level_name: str):
        """日志级别改变"""
        self._set_log_level(level_name)
        self.logger.info(f"Log level changed to: {level_name}")
    
    def _on_auto_scroll_toggled(self, checked: bool):
        """自动滚动切换"""
        self.auto_scroll = checked
    
    def append_log(self, message: str, level: str = 'INFO'):
        """
        添加日志（线程安全）
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        # 使用信号确保线程安全
        self.log_appended.emit(message, level)
    
    def _on_log_appended(self, message: str, level: str):
        """
        在GUI线程中添加日志
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        # 移动到文档末尾
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # 设置文本格式
        format = QTextCharFormat()
        format.setForeground(self.level_colors.get(level, QColor(0, 0, 0)))
        
        # 插入文本
        cursor.insertText(message + '\n', format)
        
        # 限制行数
        self._limit_lines()
        
        # 自动滚动
        if self.auto_scroll:
            self.log_text.moveCursor(QTextCursor.MoveOperation.End)
    
    def _limit_lines(self):
        """限制日志行数"""
        document = self.log_text.document()
        if document.lineCount() > self.max_lines:
            # 删除前面的行
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(
                QTextCursor.MoveOperation.Down,
                QTextCursor.MoveMode.KeepAnchor,
                document.lineCount() - self.max_lines
            )
            cursor.removeSelectedText()
    
    def clear(self):
        """清空日志"""
        self.log_text.clear()
        self.logger.info("Log cleared")
    
    def _save_log(self):
        """保存日志到文件"""
        from PyQt6.QtWidgets import QFileDialog
        
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "保存日志",
            f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                self.logger.info(f"Log saved to: {filename}")
            except Exception as e:
                self.logger.error(f"Failed to save log: {e}")
    
    def closeEvent(self, event):
        """关闭事件"""
        # 移除日志处理器
        app_logger = logging.getLogger('AFK2Auto')
        app_logger.removeHandler(self.log_handler)
        
        root_logger = logging.getLogger()
        root_logger.removeHandler(self.log_handler)
        
        event.accept()