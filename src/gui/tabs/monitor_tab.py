"""
实时监控标签页
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QCheckBox, QSlider,
    QSplitter, QTextEdit, QScrollArea
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
        
        # 左侧 - 屏幕显示（使用滚动区域）
        screen_group = QGroupBox("设备屏幕")
        screen_layout = QVBoxLayout()
        screen_group.setLayout(screen_layout)
        splitter.addWidget(screen_group)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(False)  # 不自动调整大小
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        screen_layout.addWidget(scroll_area)
        
        # 屏幕显示标签
        self.screen_label = QLabel()
        self.screen_label.setMinimumSize(300, 500)  # 最小尺寸
        self.screen_label.setScaledContents(False)  # 不自动缩放内容
        self.screen_label.setStyleSheet("""
            QLabel {
                border: 2px solid #ccc;
                background-color: #000;
            }
        """)
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_label.setText("未连接设备")
        
        # 将标签添加到滚动区域
        scroll_area.setWidget(self.screen_label)
        self.scroll_area = scroll_area
        
        # 屏幕信息
        self.screen_info = QLabel("分辨率: - | FPS: - | 缩放: 100%")
        screen_layout.addWidget(self.screen_info)
        
        # 缩放控制
        zoom_layout = QHBoxLayout()
        screen_layout.addLayout(zoom_layout)
        
        zoom_layout.addWidget(QLabel("缩放:"))
        
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(25)
        self.zoom_slider.setMaximum(200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.zoom_slider.setTickInterval(25)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        zoom_layout.addWidget(self.zoom_slider)
        
        self.zoom_label = QLabel("100%")
        zoom_layout.addWidget(self.zoom_label)
        
        # 适应窗口按钮
        self.fit_btn = QPushButton("适应窗口")
        self.fit_btn.clicked.connect(self._fit_to_window)
        zoom_layout.addWidget(self.fit_btn)
        
        # 原始大小按钮
        self.original_btn = QPushButton("原始大小")
        self.original_btn.clicked.connect(self._original_size)
        zoom_layout.addWidget(self.original_btn)
        
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
        
        # OCR控制区域
        ocr_control_layout = QHBoxLayout()
        info_layout.addLayout(ocr_control_layout)
        
        ocr_control_layout.addWidget(QLabel("OCR文字识别:"))
        
        # OCR按钮 - 手动触发OCR识别
        self.ocr_btn = QPushButton("执行OCR识别")
        self.ocr_btn.clicked.connect(self._perform_ocr_once)
        ocr_control_layout.addWidget(self.ocr_btn)
        
        # 清空OCR结果按钮
        self.clear_ocr_btn = QPushButton("清空结果")
        self.clear_ocr_btn.clicked.connect(lambda: self.ocr_text.clear())
        ocr_control_layout.addWidget(self.clear_ocr_btn)
        
        ocr_control_layout.addStretch()
        
        # OCR结果显示
        self.ocr_text = QTextEdit()
        self.ocr_text.setReadOnly(True)
        info_layout.addWidget(self.ocr_text)
        
        # 设置分割器比例
        splitter.setSizes([500, 400])
    
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
        
        # 更新频率滑块 - 降低默认值，减少性能消耗
        self.fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.fps_slider.setMinimum(1)
        self.fps_slider.setMaximum(10)  # 降低最大值到10FPS，避免过高负载
        self.fps_slider.setValue(3)  # 默认3FPS，显著降低资源消耗
        self.fps_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.fps_slider.setTickInterval(1)
        self.fps_slider.valueChanged.connect(self._on_fps_changed)
        layout.addWidget(self.fps_slider)
        
        self.fps_label = QLabel("3 FPS")
        layout.addWidget(self.fps_label)
        
        # 识别开关
        self.enable_recognition = QCheckBox("启用场景识别")
        self.enable_recognition.setChecked(False)  # 默认关闭
        layout.addWidget(self.enable_recognition)
        
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
    
    def _on_zoom_changed(self, value: int):
        """缩放改变"""
        self.zoom_label.setText(f"{value}%")
        
        # 重新显示当前截图
        if self.current_screenshot:
            self._display_screenshot(self.current_screenshot)
    
    def _fit_to_window(self):
        """适应窗口大小"""
        if not self.current_screenshot:
            return
        
        # 计算适合窗口的缩放比例
        scroll_size = self.scroll_area.size()
        img_width, img_height = self.current_screenshot.size
        
        # 计算缩放比例
        scale_w = (scroll_size.width() - 20) / img_width  # 减去滚动条宽度
        scale_h = (scroll_size.height() - 20) / img_height
        scale = min(scale_w, scale_h)
        
        # 设置缩放值
        zoom_value = int(scale * 100)
        zoom_value = max(25, min(200, zoom_value))  # 限制范围
        self.zoom_slider.setValue(zoom_value)
    
    def _original_size(self):
        """原始大小"""
        self.zoom_slider.setValue(100)
    
    def _on_screenshot_ready(self, screenshot: Image.Image):
        """截图准备就绪"""
        self.current_screenshot = screenshot
        self.save_btn.setEnabled(True)
        self.ocr_btn.setEnabled(True)
        
        # 显示截图
        self._display_screenshot(screenshot)
        
        # 执行场景识别（如果启用）
        if self.enable_recognition.isChecked():
            self._perform_recognition(screenshot)
        
        # 更新屏幕信息
        width, height = screenshot.size
        fps = self.fps_slider.value() if self.is_monitoring else "-"
        zoom = self.zoom_slider.value()
        self.screen_info.setText(f"分辨率: {width}x{height} | FPS: {fps} | 缩放: {zoom}%")
    
    def _display_screenshot(self, screenshot: Image.Image):
        """显示截图"""
        try:
            # 获取缩放比例
            zoom = self.zoom_slider.value() / 100.0
            
            # 转换为QPixmap
            screenshot_rgb = screenshot.convert('RGB')
            width, height = screenshot_rgb.size
            
            # 根据缩放比例调整大小
            new_width = int(width * zoom)
            new_height = int(height * zoom)
            
            # 使用PIL进行缩放
            if zoom != 1.0:
                screenshot_rgb = screenshot_rgb.resize(
                    (new_width, new_height), 
                    Image.Resampling.LANCZOS
                )
            
            # 创建QImage
            bytes_per_line = 3 * new_width
            data = screenshot_rgb.tobytes('raw', 'RGB')
            
            qimage = QImage(data, new_width, new_height, 
                           bytes_per_line, QImage.Format.Format_RGB888)
            
            # 确保QImage有效
            if qimage.isNull():
                self.logger.error("Failed to create QImage from screenshot")
                return
                
            pixmap = QPixmap.fromImage(qimage)
            
            # 确保pixmap有效
            if pixmap.isNull():
                self.logger.error("Failed to create QPixmap from QImage")
                return
            
            # 设置到标签（不再缩放，已经在上面处理过了）
            self.screen_label.setPixmap(pixmap)
            self.screen_label.resize(pixmap.size())
            
        except Exception as e:
            self.logger.error(f"Error displaying screenshot: {e}")
            self.screen_label.setText(f"显示错误: {str(e)}")
    
    def _perform_recognition(self, screenshot: Image.Image):
        """执行图像识别"""
        try:
            # 场景检测 - 使用控制器的detect_scene方法
            scene = self.game_controller.detect_scene(screenshot)
            if scene:
                self.scene_label.setText(scene)
                self.recognition_text.append(f"检测到场景: {scene}")
            else:
                self.scene_label.setText("未知场景")
            
            # 其他识别结果
            # TODO: 添加更多识别功能
            
        except Exception as e:
            self.logger.error(f"Recognition error: {e}")
    
    def _perform_ocr_once(self):
        """手动执行一次OCR识别"""
        if not self.current_screenshot:
            self.ocr_text.setText("请先截图")
            return
        
        # 禁用按钮防止重复点击
        self.ocr_btn.setEnabled(False)
        self.ocr_text.setText("正在识别...")
        
        try:
            # OCR识别 - 使用控制器的ocr属性
            if hasattr(self.game_controller, 'ocr') and self.game_controller.ocr:
                # 添加调试日志
                self.logger.info("Starting OCR recognition...")
                
                # 确保OCR引擎已初始化
                if not self.game_controller.ocr.is_engine_available():
                    self.logger.warning("OCR engine not available, trying to initialize...")
                    self.ocr_text.setText("OCR引擎未可用，正在初始化...")
                    
                    # 尝试初始化
                    try:
                        self.game_controller.ocr._ensure_engine_initialized()
                    except Exception as init_error:
                        self.ocr_text.setText(f"OCR引擎初始化失败: {str(init_error)}")
                        return
                
                # 执行识别
                text = self.game_controller.ocr.recognize_text(self.current_screenshot)
                self.logger.info(f"OCR result: {text[:100] if text else 'No text found'}")
                
                if text and text.strip():
                    self.ocr_text.setText(f"识别结果:\n{text}")
                else:
                    self.ocr_text.setText("未识别到文字")
            else:
                self.ocr_text.setText("OCR未初始化")
                self.logger.warning("OCR not initialized in game controller")
                
        except Exception as e:
            self.logger.error(f"OCR error: {e}", exc_info=True)
            self.ocr_text.setText(f"OCR错误: {str(e)}")
        finally:
            # 重新启用按钮
            self.ocr_btn.setEnabled(True)
    
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