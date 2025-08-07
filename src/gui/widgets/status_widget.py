"""
状态栏Widget
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QPalette, QColor


class StatusWidget(QWidget):
    """
    状态栏Widget
    显示设备连接状态、游戏状态、任务状态等
    """
    
    def __init__(self, parent=None):
        """
        初始化状态Widget
        
        Args:
            parent: 父widget
        """
        super().__init__(parent)
        
        self._init_ui()
        
        # 状态更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_time)
        self.update_timer.start(1000)  # 每秒更新时间
    
    def _init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # 设备状态
        self.device_icon = QLabel("📱")
        layout.addWidget(self.device_icon)
        
        self.device_label = QLabel("设备: 未连接")
        self.device_label.setMinimumWidth(150)
        layout.addWidget(self.device_label)
        
        layout.addWidget(self._create_separator())
        
        # 任务状态
        self.task_icon = QLabel("📋")
        layout.addWidget(self.task_icon)
        
        self.task_label = QLabel("任务: 0/0")
        self.task_label.setMinimumWidth(100)
        layout.addWidget(self.task_label)
        
        layout.addWidget(self._create_separator())
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setMinimumWidth(100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()  # 默认隐藏
        layout.addWidget(self.progress_bar)
        
        # 弹性空间
        layout.addStretch()
        
        # 消息区域
        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.message_label)
        
        layout.addWidget(self._create_separator())
        
        # 时间显示
        self.time_label = QLabel("")
        self.time_label.setMinimumWidth(80)
        layout.addWidget(self.time_label)
    
    def _create_separator(self) -> QLabel:
        """创建分隔符"""
        separator = QLabel("|")
        separator.setStyleSheet("color: #ccc; padding: 0 5px;")
        return separator
    
    def _update_time(self):
        """更新时间显示"""
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.setText(current_time)
    
    def update_device_status(self, connected: bool, device_id: Optional[str] = None):
        """
        更新设备状态
        
        Args:
            connected: 是否连接
            device_id: 设备ID
        """
        if connected:
            self.device_icon.setText("📱")
            self.device_label.setText(f"设备: {device_id or '已连接'}")
            self.device_label.setStyleSheet("color: green;")
        else:
            self.device_icon.setText("📵")
            self.device_label.setText("设备: 未连接")
            self.device_label.setStyleSheet("color: red;")
    
    
    def update_task_status(self, running: int, total: int):
        """
        更新任务状态
        
        Args:
            running: 运行中的任务数
            total: 总任务数
        """
        self.task_label.setText(f"任务: {running}/{total}")
        
        if running > 0:
            self.task_label.setStyleSheet("color: blue;")
        elif total > 0:
            self.task_label.setStyleSheet("color: orange;")
        else:
            self.task_label.setStyleSheet("color: gray;")
    
    def update_status(self, device_status: Optional[str] = None,
                     task_status: Optional[str] = None):
        """
        批量更新状态
        
        Args:
            device_status: 设备状态文本
            task_status: 任务状态文本
        """
        if device_status:
            if "已连接" in device_status or "连接" in device_status:
                self.device_icon.setText("📱")
                self.device_label.setStyleSheet("color: green;")
            else:
                self.device_icon.setText("📵")
                self.device_label.setStyleSheet("color: red;")
            self.device_label.setText(f"设备: {device_status}")
        
        if task_status:
            self.task_label.setText(task_status)
            if "/" in task_status:
                running, total = task_status.split(":")[-1].strip().split("/")
                if int(running) > 0:
                    self.task_label.setStyleSheet("color: blue;")
                elif int(total) > 0:
                    self.task_label.setStyleSheet("color: orange;")
                else:
                    self.task_label.setStyleSheet("color: gray;")
    
    def show_message(self, message: str, timeout: int = 3000):
        """
        显示临时消息
        
        Args:
            message: 消息内容
            timeout: 显示时长（毫秒）
        """
        self.message_label.setText(message)
        
        if timeout > 0:
            QTimer.singleShot(timeout, lambda: self.message_label.setText(""))
    
    def show_progress(self, value: int, maximum: int = 100, text: Optional[str] = None):
        """
        显示进度
        
        Args:
            value: 当前值
            maximum: 最大值
            text: 显示文本
        """
        self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(value)
        
        if text:
            self.progress_bar.setFormat(text)
        else:
            self.progress_bar.setFormat("%p%")
        
        self.progress_bar.show()
    
    def hide_progress(self):
        """隐藏进度条"""
        self.progress_bar.hide()
    
    def reset(self):
        """重置状态"""
        self.update_device_status(False)
        self.update_task_status(0, 0)
        self.hide_progress()
        self.message_label.setText("")