"""
实时监控标签页
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QCheckBox, QSlider,
    QSplitter, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap, QImage, QPainter

from src.services.adb_service import ADBService
from src.controller.afk2_controller import AFK2Controller
from src.services.log_service import LoggerMixin
from PIL import Image
import numpy as np


class ScreenCaptureThread(QThread):
    """屏幕捕获线程"""
    screenshot_ready = pyqtSignal(object)  # PIL Image
    error_occurred = pyqtSignal(str)
    
    def __init__(self, adb_service: ADBService):
        super().__init__()
        self.adb_service = adb_service
        self.running = False
        self.capture_interval = 1000  # 默认1秒
    
    def set_interval(self, interval: int):
        """设置捕获间隔（毫秒）"""
        self.capture_interval = interval
    
    def start_capture(self):
        """开始捕获"""
        self.running = True
        self.start()
    
    def stop_capture(self):
        """停止捕获"""
        self.running = False
        self.wait()
    
    def run(self):
        """运行捕获循环"""
        while self.running:
            try:
                # 截图
                screenshot = self.adb_service.screenshot()
                if screenshot:
                    self.screenshot_ready.emit(screenshot)
                else:
                    self.error_occurred.emit("截图失败")
            except Exception as e:
                self.error_occurred.emit(str(e))
            
            # 等待间隔
            self.msleep(self.capture_interval)


class MonitorTab(QWidget, LoggerMixin):
    """
    实时监控标签页
    显示设备屏幕实时画面和识别结果
    """
    
    def __init__(self, adb_service: ADBService, 
                 game_controller: AFK2Controller):
        """
        初始化监控标签页
        
        Args:
            adb_service: ADB服务
            game_controller: 游戏控制器
        """
        super().__init__()
        self.adb_service = adb_service
        self.game_controller = game_controller
        
        # 截图线程
        self.capture_thread: Optional[ScreenCaptureThread] = None
        self.is_monitoring = False
        
        # 当前截图
        self.current_screenshot: Optional[Image.Image] = None
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 控制面板
        control_panel = self._create_control_panel()
        layout.addWidget(control_panel)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # 左侧 - 屏幕显示
        screen_group = QGroupBox("设备屏幕")
        screen_layout = QVBoxLayout()
        screen_group.setLayout(screen_layout)
        splitter.addWidget(screen_group)
        
        # 屏幕显示标签
        self.screen_label = QLabel()
        self.screen_label.setMinimumSize(360, 640)
        self.screen_label.setMaximumSize(540, 960)
        self.screen_label.setScaledContents(True)
        self.screen_label.setStyleSheet("""
            QLabel {
                border: 2px solid #ccc;
                background-color: #000;
            }
        """)
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_label.setText("未连接设备")
        screen_layout.addWidget(self.screen_label)
        
        # 屏幕信息
        self.screen_info = QLabel("分辨率: - | FPS: -")
        screen_layout.addWidget(self.screen_info)
        
        # 右侧 - 识别结果
        info_group = QGroupBox("识别信息")
        info_layout = QVBoxLayout()
        info_group.setLayout(info_layout)
        splitter.addWidget(info_group)
        
        # 场景识别
        scene_layout = QHBoxLayout()
        info_layout.addLayout(scene_layout)
        
        scene_layout.addWidget(QLabel("当前场景:"))
        self.scene_label = QLabel("未知")
        self.scene_label.setStyleSheet("font-weight: bold; color: blue;")
        scene_layout.addWidget(self.scene_label)
        scene_layout.addStretch()
        
        # 识别结果显示
        self.recognition_text = QTextEdit()
        self.recognition_text.setReadOnly(True)
        self.recognition_text.setMaximumHeight(200)
        info_layout.addWidget(self.recognition_text)
        
        # OCR结果
        ocr_label = QLabel("OCR文字识别:")
        info_layout.addWidget(ocr_label)
        
        self.ocr_text = QTextEdit()
        self.ocr_text.setReadOnly(True)
        info_layout.addWidget(self.ocr_text)
        
        # 设置分割器比例
        splitter.setSizes([400, 400])
    
    def _create_control_panel(self) -> QGroupBox:
        """创建控制面板"""
        group = QGroupBox("监控控制")
        layout = QHBoxLayout()
        group.setLayout(layout)
        
        # 开始/停止按钮
        self.monitor_btn = QPushButton("开始监控")
        self.monitor_btn.clicked.connect(self._toggle_monitoring)
        layout.addWidget(self.monitor_btn)
        
        # 截图按钮
        self.capture_btn = QPushButton("单次截图")
        self.capture_btn.clicked.connect(self._capture_once)
        layout.addWidget(self.capture_btn)
        
        # 保存截图
        self.save_btn = QPushButton("保存截图")
        self.save_btn.clicked.connect(self._save_screenshot)
        self.save_btn.setEnabled(False)
        layout.addWidget(self.save_btn)
        
        layout.addWidget(QLabel("更新频率:"))
        
        # 更新频率滑块
        self.fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.fps_slider.setMinimum(1)
        self.fps_slider.setMaximum(10)
        self.fps_slider.setValue(2)
        self.fps_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.fps_slider.setTickInterval(1)
        self.fps_slider.valueChanged.connect(self._on_fps_changed)
        layout.addWidget(self.fps_slider)
        
        self.fps_label = QLabel("2 FPS")
        layout.addWidget(self.fps_label)
        
        # 识别开关
        self.enable_recognition = QCheckBox("启用识别")
        self.enable_recognition.setChecked(True)
        layout.addWidget(self.enable_recognition)
        
        self.enable_ocr = QCheckBox("启用OCR")
        self.enable_ocr.setChecked(False)
        layout.addWidget(self.enable_ocr)
        
        layout.addStretch()
        
        return group
    
    def _toggle_monitoring(self):
        """切换监控状态"""
        if self.is_monitoring:
            self._stop_monitoring()
        else:
            self._start_monitoring()
    
    def _start_monitoring(self):
        """开始监控"""
        if not self.adb_service.current_device:
            self.logger.warning("No device connected")
            return
        
        self.is_monitoring = True
        self.monitor_btn.setText("停止监控")
        
        # 创建并启动截图线程
        self.capture_thread = ScreenCaptureThread(self.adb_service)
        self.capture_thread.screenshot_ready.connect(self._on_screenshot_ready)
        self.capture_thread.error_occurred.connect(self._on_capture_error)
        
        # 设置FPS
        fps = self.fps_slider.value()
        interval = 1000 // fps
        self.capture_thread.set_interval(interval)
        
        self.capture_thread.start_capture()
        self.logger.info("Monitoring started")
    
    def _stop_monitoring(self):
        """停止监控"""
        self.is_monitoring = False
        self.monitor_btn.setText("开始监控")
        
        if self.capture_thread:
            self.capture_thread.stop_capture()
            self.capture_thread = None
        
        self.logger.info("Monitoring stopped")
    
    def _capture_once(self):
        """单次截图"""
        if not self.adb_service.current_device:
            self.logger.warning("No device connected")
            return
        
        try:
            screenshot = self.adb_service.screenshot()
            if screenshot:
                self._on_screenshot_ready(screenshot)
            else:
                self.logger.error("Failed to capture screenshot")
        except Exception as e:
            self.logger.error(f"Screenshot error: {e}")
    
    def _on_fps_changed(self, value: int):
        """FPS改变"""
        self.fps_label.setText(f"{value} FPS")
        
        if self.capture_thread:
            interval = 1000 // value
            self.capture_thread.set_interval(interval)
    
    def _on_screenshot_ready(self, screenshot: Image.Image):
        """截图准备就绪"""
        self.current_screenshot = screenshot
        self.save_btn.setEnabled(True)
        
        # 显示截图
        self._display_screenshot(screenshot)
        
        # 执行识别
        if self.enable_recognition.isChecked():
            self._perform_recognition(screenshot)
        
        if self.enable_ocr.isChecked():
            self._perform_ocr(screenshot)
        
        # 更新屏幕信息
        width, height = screenshot.size
        fps = self.fps_slider.value() if self.is_monitoring else "-"
        self.screen_info.setText(f"分辨率: {width}x{height} | FPS: {fps}")
    
    def _display_screenshot(self, screenshot: Image.Image):
        """显示截图"""
        # 转换为QPixmap
        screenshot_rgb = screenshot.convert('RGB')
        data = screenshot_rgb.tobytes('raw', 'RGB')
        qimage = QImage(data, screenshot_rgb.width, screenshot_rgb.height, 
                       QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage)
        
        # 缩放到合适大小
        scaled_pixmap = pixmap.scaled(
            self.screen_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.screen_label.setPixmap(scaled_pixmap)
    
    def _perform_recognition(self, screenshot: Image.Image):
        """执行图像识别"""
        try:
            # 场景检测
            scene = self.game_controller.scene_detector.detect_scene(screenshot)
            if scene:
                self.scene_label.setText(scene.value)
                self.recognition_text.append(f"检测到场景: {scene.value}")
            
            # 其他识别结果
            # TODO: 添加更多识别功能
            
        except Exception as e:
            self.logger.error(f"Recognition error: {e}")
    
    def _perform_ocr(self, screenshot: Image.Image):
        """执行OCR识别"""
        try:
            # OCR识别
            text = self.game_controller.ocr_engine.recognize_text(screenshot)
            if text:
                self.ocr_text.setText(text)
            else:
                self.ocr_text.setText("未识别到文字")
        except Exception as e:
            self.logger.error(f"OCR error: {e}")
    
    def _on_capture_error(self, error: str):
        """捕获错误"""
        self.logger.error(f"Capture error: {error}")
        self.screen_label.setText(f"错误: {error}")
    
    def _save_screenshot(self):
        """保存截图"""
        if not self.current_screenshot:
            return
        
        from PyQt6.QtWidgets import QFileDialog
        from datetime import datetime
        
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "保存截图",
            f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)"
        )
        
        if filename:
            try:
                self.current_screenshot.save(filename)
                self.logger.info(f"Screenshot saved to: {filename}")
            except Exception as e:
                self.logger.error(f"Failed to save screenshot: {e}")
    
    def closeEvent(self, event):
        """关闭事件"""
        # 停止监控
        if self.is_monitoring:
            self._stop_monitoring()
        event.accept()