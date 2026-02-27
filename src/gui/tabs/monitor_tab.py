"""
实时监控标签页
"""

from typing import Optional, Union
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QCheckBox, QSlider,
    QSplitter, QTextEdit, QScrollArea, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap, QImage, QPainter

from src.services.adb_service import ADBService
from src.controller.afk2_controller import AFK2Controller
from src.services.log_service import LoggerMixin
from PIL import Image
import cv2
import numpy as np
import time

try:
    import scrcpy
    SCRCPY_AVAILABLE = True
except ImportError:
    SCRCPY_AVAILABLE = False


class ScreenCaptureThread(QThread):
    """ADB屏幕捕获线程，使用numpy路径实现高帧率"""
    frame_ready = pyqtSignal(object)  # numpy ndarray (BGR)
    error_occurred = pyqtSignal(str)

    def __init__(self, adb_service: ADBService):
        super().__init__()
        self.adb_service = adb_service
        self.running = False
        self.capture_interval = 1000  # 默认1秒
        self._frame_pending = False

    def set_interval(self, interval: int):
        """设置捕获间隔"""
        self.capture_interval = interval

    def start_capture(self):
        """开始捕获"""
        self.running = True
        self._frame_pending = False
        self.start()

    def stop_capture(self):
        """停止捕获"""
        self.running = False
        self.wait()

    def mark_frame_consumed(self):
        """GUI处理完一帧后调用"""
        self._frame_pending = False

    def run(self):
        """运行捕获循环"""
        while self.running:
            start_time = time.perf_counter()

            if not self._frame_pending:
                try:
                    frame = self.adb_service.screenshot_numpy(cache_ms=0)
                    if frame is not None:
                        self._frame_pending = True
                        self.frame_ready.emit(frame)
                    else:
                        self.error_occurred.emit("截图失败")
                except Exception as e:
                    self.error_occurred.emit(str(e))

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            sleep_time = max(1, self.capture_interval - elapsed_ms)
            self.msleep(sleep_time)


class ScrcpyCaptureThread(QThread):
    """scrcpy视频流采集线程，支持快速失败检测"""
    frame_ready = pyqtSignal(object)  # numpy ndarray (BGR)
    error_occurred = pyqtSignal(str)
    # fast_fail=True 表示服务端根本不兼容，不应重试
    fast_fail = pyqtSignal()

    # 连接后存活不到此秒数视为"快速失败"
    FAST_FAIL_THRESHOLD_SEC = 3.0

    def __init__(self, device_serial: str, max_fps: int = 60,
                 max_width: int = 800, bitrate: int = 8000000):
        super().__init__()
        self.device_serial = device_serial
        self.max_fps = max_fps
        self.max_width = max_width
        self.bitrate = bitrate
        self._client = None
        self._frame_pending = False
        self._stop_requested = False
        self._got_first_frame = False

    def _on_frame(self, frame):
        """scrcpy帧回调"""
        if frame is not None:
            self._got_first_frame = True
            if not self._frame_pending:
                self._frame_pending = True
                self.frame_ready.emit(frame)

    def mark_frame_consumed(self):
        """GUI处理完一帧后调用"""
        self._frame_pending = False

    def run(self):
        """运行scrcpy客户端，单次尝试，由外层负责重试策略"""
        start_time = time.perf_counter()
        try:
            self._client = scrcpy.Client(
                device=self.device_serial,
                max_fps=self.max_fps,
                max_width=self.max_width,
                bitrate=self.bitrate,
            )
            self._client.add_listener(scrcpy.EVENT_FRAME, self._on_frame)
            self._client.start(threaded=False)
        except Exception as e:
            if self._stop_requested:
                return
            elapsed = time.perf_counter() - start_time
            if elapsed < self.FAST_FAIL_THRESHOLD_SEC and not self._got_first_frame:
                self.fast_fail.emit()
            else:
                self.error_occurred.emit(str(e))
        finally:
            self._client = None

    def stop_capture(self):
        """停止scrcpy客户端"""
        self._stop_requested = True
        if self._client:
            try:
                self._client.stop()
            except Exception:
                pass
            self._client = None
        self.wait(3000)


class MonitorTab(QWidget, LoggerMixin):
    """
    实时监控标签页
    显示设备屏幕实时画面和识别结果
    """

    def __init__(self, adb_service: ADBService,
                 game_controller: AFK2Controller):
        super().__init__()
        self.adb_service = adb_service
        self.game_controller = game_controller

        # 采集线程
        self.capture_thread: Optional[Union[ScreenCaptureThread, ScrcpyCaptureThread]] = None
        self.is_monitoring = False
        self._active_capture_mode: Optional[str] = None
        self._scrcpy_error_count = 0
        self._scrcpy_known_broken = False  # scrcpy快速失败后标记为不可用

        # 当前帧数据
        self.current_screenshot: Optional[Image.Image] = None
        self._current_numpy_frame: Optional[np.ndarray] = None
        self._pil_cache_dirty = True

        # FPS计数
        self._frame_count = 0
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_actual_fps)
        self._fps_timer.setInterval(1000)

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

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(False)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        screen_layout.addWidget(scroll_area)

        # 屏幕显示标签
        self.screen_label = QLabel()
        self.screen_label.setMinimumSize(300, 500)
        self.screen_label.setScaledContents(False)
        self.screen_label.setStyleSheet("""
            QLabel {
                border: 2px solid #ccc;
                background-color: #000;
            }
        """)
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_label.setText("未连接设备")

        scroll_area.setWidget(self.screen_label)
        self.scroll_area = scroll_area

        # 屏幕信息
        self.screen_info = QLabel("分辨率: - | FPS: - | 实际FPS: - | 缩放: 100%")
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

        self.fit_btn = QPushButton("适应窗口")
        self.fit_btn.clicked.connect(self._fit_to_window)
        zoom_layout.addWidget(self.fit_btn)

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

        self.ocr_btn = QPushButton("执行OCR识别")
        self.ocr_btn.clicked.connect(self._perform_ocr_once)
        ocr_control_layout.addWidget(self.ocr_btn)

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

        # 采集模式选择
        layout.addWidget(QLabel("采集模式:"))
        self.capture_mode_combo = QComboBox()
        self.capture_mode_combo.addItem("自动", "auto")
        if SCRCPY_AVAILABLE:
            self.capture_mode_combo.addItem("scrcpy", "scrcpy")
        else:
            self.capture_mode_combo.addItem("scrcpy (未安装)", "scrcpy_disabled")
        self.capture_mode_combo.addItem("ADB截图", "adb")
        self.capture_mode_combo.currentIndexChanged.connect(self._on_capture_mode_changed)
        layout.addWidget(self.capture_mode_combo)

        # 更新频率滑块
        layout.addWidget(QLabel("FPS:"))

        self.fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.fps_slider.setMinimum(1)
        self.fps_slider.setMaximum(60)
        self.fps_slider.setValue(30)
        self.fps_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.fps_slider.setTickInterval(5)
        self.fps_slider.valueChanged.connect(self._on_fps_changed)
        layout.addWidget(self.fps_slider)

        self.fps_label = QLabel("30 FPS")
        layout.addWidget(self.fps_label)

        # 实际FPS显示
        self.actual_fps_label = QLabel("实际: -")
        self.actual_fps_label.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.actual_fps_label)

        # 识别开关
        self.enable_recognition = QCheckBox("启用场景识别")
        self.enable_recognition.setChecked(False)
        layout.addWidget(self.enable_recognition)

        layout.addStretch()

        return group

    def _on_capture_mode_changed(self, index: int):
        """采集模式变更"""
        mode = self.capture_mode_combo.currentData()
        if mode == "scrcpy_disabled":
            self.capture_mode_combo.setCurrentIndex(0)
            self.logger.warning("scrcpy-client未安装, 无法使用scrcpy模式")
            return

        # 所有模式统一60 FPS上限，实际帧率由截图速度决定
        self.fps_slider.setMaximum(60)

    def _get_selected_capture_mode(self) -> str:
        """获取当前选择的采集模式"""
        mode = self.capture_mode_combo.currentData()
        if mode == "scrcpy_disabled":
            return "adb"
        return mode

    def _resolve_capture_mode(self) -> str:
        """根据配置和可用性决定实际使用的采集模式"""
        selected = self._get_selected_capture_mode()

        if selected == "scrcpy":
            if self._scrcpy_known_broken:
                self.logger.warning("scrcpy此前已检测到不兼容, 降级到ADB模式")
                return "adb"
            if SCRCPY_AVAILABLE:
                return "scrcpy"
            self.logger.warning("scrcpy-client未安装, 降级到ADB模式")
            return "adb"

        # auto 和 adb 都直接走 ADB
        return "adb"

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

        mode = self._resolve_capture_mode()
        self._active_capture_mode = mode
        self._scrcpy_error_count = 0
        self.is_monitoring = True
        self.monitor_btn.setText("停止监控")

        # 重置FPS计数
        self._frame_count = 0
        self._fps_timer.start()

        if mode == "scrcpy":
            self._start_scrcpy_capture()
        else:
            self._start_adb_capture()

        self.logger.info(f"Monitoring started, mode={mode}")

    def _start_adb_capture(self):
        """启动ADB截图采集"""
        fps = self.fps_slider.value()

        self.capture_thread = ScreenCaptureThread(self.adb_service)
        self.capture_thread.frame_ready.connect(self._on_frame_ready_numpy)
        self.capture_thread.error_occurred.connect(self._on_capture_error)

        interval = 1000 // max(fps, 1)
        self.capture_thread.set_interval(interval)
        self.capture_thread.start_capture()

    def _calc_scrcpy_params(self):
        """计算scrcpy参数"""
        monitor_cfg = None
        controller_cfg = getattr(self.game_controller, "config", None)
        if controller_cfg and hasattr(controller_cfg, "monitor"):
            monitor_cfg = controller_cfg.monitor

        fps_setting = self.fps_slider.value()
        max_fps_cfg = monitor_cfg.scrcpy_max_fps if monitor_cfg else fps_setting
        max_fps = min(fps_setting, max_fps_cfg)

        width = monitor_cfg.scrcpy_max_width if monitor_cfg else 800
        bitrate = monitor_cfg.scrcpy_bitrate if monitor_cfg else 8000000

        return width, bitrate, max_fps

    def _start_scrcpy_capture(self):
        """启动scrcpy视频流采集"""
        device_serial = self.adb_service.current_device.device_id

        max_width, bitrate, max_fps = self._calc_scrcpy_params()

        self.capture_thread = ScrcpyCaptureThread(
            device_serial=device_serial,
            max_fps=max_fps,
            max_width=max_width,
            bitrate=bitrate,
        )
        self.capture_thread.frame_ready.connect(self._on_frame_ready_numpy)
        self.capture_thread.error_occurred.connect(self._on_scrcpy_error)
        self.capture_thread.fast_fail.connect(self._on_scrcpy_fast_fail)
        self.capture_thread.start()

    def _stop_monitoring(self):
        """停止监控"""
        self.is_monitoring = False
        self.monitor_btn.setText("开始监控")
        self._fps_timer.stop()
        self.actual_fps_label.setText("实际: -")

        if self.capture_thread:
            if isinstance(self.capture_thread, ScrcpyCaptureThread):
                self.capture_thread.stop_capture()
            else:
                self.capture_thread.stop_capture()
            self.capture_thread = None

        self._active_capture_mode = None
        self.logger.info("Monitoring stopped")

    def _capture_once(self):
        """单次截图"""
        if not self.adb_service.current_device:
            self.logger.warning("No device connected")
            return

        try:
            frame = self.adb_service.screenshot_numpy(cache_ms=0)
            if frame is not None:
                self._on_frame_ready_numpy(frame)
            else:
                self.logger.error("Failed to capture screenshot")
        except Exception as e:
            self.logger.error(f"Screenshot error: {e}")

    def _on_fps_changed(self, value: int):
        """FPS改变"""
        self.fps_label.setText(f"{value} FPS")

        if not self.capture_thread:
            return

        if isinstance(self.capture_thread, ScreenCaptureThread):
            interval = 1000 // max(value, 1)
            self.capture_thread.set_interval(interval)

    def _on_zoom_changed(self, value: int):
        """缩放改变"""
        self.zoom_label.setText(f"{value}%")

        if self._current_numpy_frame is not None:
            self._display_frame_numpy(self._current_numpy_frame)
        elif self.current_screenshot:
            self._display_screenshot(self.current_screenshot)

    def _fit_to_window(self):
        """适应窗口大小"""
        pil_img = self._get_current_pil_image()
        if not pil_img:
            return

        scroll_size = self.scroll_area.size()
        img_width, img_height = pil_img.size

        scale_w = (scroll_size.width() - 20) / img_width
        scale_h = (scroll_size.height() - 20) / img_height
        scale = min(scale_w, scale_h)

        zoom_value = int(scale * 100)
        zoom_value = max(25, min(200, zoom_value))
        self.zoom_slider.setValue(zoom_value)

    def _original_size(self):
        """原始大小"""
        self.zoom_slider.setValue(100)

    def _update_actual_fps(self):
        """每秒更新实际FPS"""
        self.actual_fps_label.setText(f"实际: {self._frame_count}")
        self._frame_count = 0

    # --- numpy快速显示路径 ---

    def _on_frame_ready_numpy(self, frame: np.ndarray):
        """接收scrcpy的BGR numpy帧"""
        self._current_numpy_frame = frame
        self._pil_cache_dirty = True
        self._frame_count += 1
        self.save_btn.setEnabled(True)
        self.ocr_btn.setEnabled(True)

        self._display_frame_numpy(frame)

        if self.enable_recognition.isChecked():
            pil_img = self._get_current_pil_image()
            if pil_img:
                self._perform_recognition(pil_img)

        # 更新屏幕信息
        h, w = frame.shape[:2]
        fps = self.fps_slider.value() if self.is_monitoring else "-"
        zoom = self.zoom_slider.value()
        mode_label = self._active_capture_mode or "?"
        # 如果是ADB模式，显示具体截图策略
        if mode_label == "adb" and hasattr(self.adb_service, '_screencap_method'):
            strategy = self.adb_service._screencap_method or "auto"
            mode_label = f"adb/{strategy}"
        self.screen_info.setText(
            f"分辨率: {w}x{h} | FPS: {fps} | 缩放: {zoom}% | {mode_label}"
        )

        if self.capture_thread:
            self.capture_thread.mark_frame_consumed()

    def _display_frame_numpy(self, frame: np.ndarray):
        """使用numpy快速显示BGR帧"""
        try:
            zoom = self.zoom_slider.value() / 100.0
            h, w = frame.shape[:2]
            new_w = int(w * zoom)
            new_h = int(h * zoom)

            # BGR -> RGB
            rgb = frame[:, :, ::-1]

            if zoom != 1.0:
                rgb = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

            rgb = np.ascontiguousarray(rgb)
            bytes_per_line = 3 * new_w
            qimage = QImage(rgb.data, new_w, new_h,
                            bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimage)

            if pixmap.isNull():
                return

            self.screen_label.setPixmap(pixmap)
            self.screen_label.resize(pixmap.size())
        except Exception as e:
            self.logger.error(f"Error displaying numpy frame: {e}")

    # --- PIL图像惰性转换 ---

    def _get_current_pil_image(self) -> Optional[Image.Image]:
        """获取当前PIL图像, 仅在需要时从numpy帧转换"""
        if self._current_numpy_frame is not None and self._pil_cache_dirty:
            rgb = self._current_numpy_frame[:, :, ::-1]
            rgb = np.ascontiguousarray(rgb)
            self.current_screenshot = Image.fromarray(rgb, 'RGB')
            self._pil_cache_dirty = False
        return self.current_screenshot

    # --- ADB截图路径 ---

    def _on_screenshot_ready(self, screenshot: Image.Image):
        """ADB截图准备就绪"""
        self.current_screenshot = screenshot
        self._current_numpy_frame = None
        self._pil_cache_dirty = False
        self._frame_count += 1
        self.save_btn.setEnabled(True)
        self.ocr_btn.setEnabled(True)

        self._display_screenshot(screenshot)

        if self.enable_recognition.isChecked():
            self._perform_recognition(screenshot)

        width, height = screenshot.size
        fps = self.fps_slider.value() if self.is_monitoring else "-"
        zoom = self.zoom_slider.value()
        self.screen_info.setText(
            f"分辨率: {width}x{height} | FPS: {fps} | 缩放: {zoom}% | ADB"
        )

        if self.capture_thread and isinstance(self.capture_thread, ScreenCaptureThread):
            self.capture_thread.mark_frame_consumed()

    def _display_screenshot(self, screenshot: Image.Image):
        """显示PIL截图"""
        try:
            zoom = self.zoom_slider.value() / 100.0

            if screenshot.mode != 'RGB':
                screenshot_rgb = screenshot.convert('RGB')
            else:
                screenshot_rgb = screenshot

            width, height = screenshot_rgb.size
            new_width = int(width * zoom)
            new_height = int(height * zoom)

            if zoom != 1.0:
                screenshot_rgb = screenshot_rgb.resize(
                    (new_width, new_height),
                    Image.Resampling.BILINEAR
                )

            arr = np.asarray(screenshot_rgb)
            bytes_per_line = 3 * new_width
            qimage = QImage(arr.data, new_width, new_height,
                            bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimage)

            if pixmap.isNull():
                self.logger.error("Failed to create QPixmap")
                return

            self.screen_label.setPixmap(pixmap)
            self.screen_label.resize(pixmap.size())

        except Exception as e:
            self.logger.error(f"Error displaying screenshot: {e}")
            self.screen_label.setText(f"显示错误: {str(e)}")

    # --- 错误处理和降级 ---

    def _on_scrcpy_fast_fail(self):
        """scrcpy快速失败，服务端不兼容，立即降级到ADB"""
        self._scrcpy_known_broken = True
        self.logger.error(
            "scrcpy server不兼容当前设备 (scrcpy-client内置server版本1.20), "
            "立即降级到ADB模式"
        )
        self._cleanup_scrcpy_thread()
        if self.is_monitoring:
            self._active_capture_mode = "adb"
            self._start_adb_capture()
            self.logger.info("已降级到ADB截图模式")

    def _on_scrcpy_error(self, error: str):
        """scrcpy运行中出错，有限重试后降级到ADB"""
        self._scrcpy_error_count += 1
        self.logger.error(f"scrcpy error: {error} (#{self._scrcpy_error_count})")

        if not self.is_monitoring:
            return

        # 最多重试一次，然后降级
        if self._scrcpy_error_count <= 1:
            self.logger.info("Retrying scrcpy capture...")
            self._cleanup_scrcpy_thread()
            self._start_scrcpy_capture()
        else:
            self.logger.error("scrcpy repeated failure, falling back to ADB mode")
            self._cleanup_scrcpy_thread()
            self._active_capture_mode = "adb"
            self._start_adb_capture()
            self.logger.info("已降级到ADB截图模式")

    def _cleanup_scrcpy_thread(self):
        """安全清理scrcpy采集线程"""
        if self.capture_thread and isinstance(self.capture_thread, ScrcpyCaptureThread):
            try:
                self.capture_thread.stop_capture()
            except Exception:
                pass
        self.capture_thread = None


    def _on_capture_error(self, error: str):
        """ADB捕获错误"""
        self.logger.error(f"Capture error: {error}")
        self.screen_label.setText(f"错误: {error}")

    # --- 识别和保存 ---

    def _perform_recognition(self, screenshot: Image.Image):
        """执行图像识别"""
        try:
            scene = self.game_controller.detect_scene(screenshot)
            if scene:
                self.scene_label.setText(scene)
                self.recognition_text.append(f"检测到场景: {scene}")
            else:
                self.scene_label.setText("未知场景")
        except Exception as e:
            self.logger.error(f"Recognition error: {e}")

    def _perform_ocr_once(self):
        """手动执行一次OCR识别"""
        pil_img = self._get_current_pil_image()
        if not pil_img:
            self.ocr_text.setText("请先截图")
            return

        self.ocr_btn.setEnabled(False)
        self.ocr_text.setText("正在识别...")

        try:
            if hasattr(self.game_controller, 'ocr') and self.game_controller.ocr:
                self.logger.info("Starting OCR recognition...")

                if not self.game_controller.ocr.is_engine_available():
                    self.logger.warning("OCR engine not available, trying to initialize...")
                    self.ocr_text.setText("OCR引擎未可用，正在初始化...")

                    try:
                        self.game_controller.ocr._ensure_engine_initialized()
                    except Exception as init_error:
                        self.ocr_text.setText(f"OCR引擎初始化失败: {str(init_error)}")
                        return

                text = self.game_controller.ocr.recognize_text(pil_img)
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
            self.ocr_btn.setEnabled(True)

    def _save_screenshot(self):
        """保存截图"""
        pil_img = self._get_current_pil_image()
        if not pil_img:
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
                pil_img.save(filename)
                self.logger.info(f"Screenshot saved to: {filename}")
            except Exception as e:
                self.logger.error(f"Failed to save screenshot: {e}")

    def closeEvent(self, event):
        """关闭事件"""
        self._fps_timer.stop()
        if self.is_monitoring:
            self._stop_monitoring()
        event.accept()
