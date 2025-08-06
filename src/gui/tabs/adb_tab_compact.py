"""
ADB配置标签页 - 紧凑版
"""

from typing import Optional, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QTextEdit, QGridLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from src.services.adb_service import ADBService
from src.models.device import Device, DeviceStatus
from src.services.log_service import LoggerMixin


class DeviceScanThread(QThread):
    """设备扫描线程"""
    devices_found = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, adb_service: ADBService):
        super().__init__()
        self.adb_service = adb_service
    
    def run(self):
        """运行扫描"""
        try:
            # 先检查ADB是否可用
            if not self.adb_service.is_adb_available():
                self.error_occurred.emit("ADB未安装或不可用")
                self.devices_found.emit([])
                return
                
            devices = self.adb_service.get_devices()
            self.devices_found.emit(devices)
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.devices_found.emit([])


class WakeGameThread(QThread):
    """唤醒游戏线程"""
    finished_signal = pyqtSignal(bool, str)  # (success, message)
    progress_signal = pyqtSignal(str)  # 进度信息
    
    def __init__(self, adb_service: ADBService):
        super().__init__()
        self.adb_service = adb_service
    
    def run(self):
        """运行唤醒游戏"""
        try:
            self.progress_signal.emit("正在唤醒设备...")
            
            # 执行唤醒和启动游戏
            success = self.adb_service.wake_and_start_game()
            
            if success:
                self.finished_signal.emit(True, "游戏已成功启动")
            else:
                self.finished_signal.emit(False, "无法启动游戏")
                
        except Exception as e:
            self.finished_signal.emit(False, f"启动游戏失败: {str(e)}")


class ADBTab(QWidget, LoggerMixin):
    """
    ADB配置标签页 - 紧凑版
    """
    
    def __init__(self, adb_service: ADBService):
        """
        初始化ADB配置标签页
        
        Args:
            adb_service: ADB服务实例
        """
        super().__init__()
        self.adb_service = adb_service
        self.devices: List[Device] = []
        self.scan_thread: Optional[DeviceScanThread] = None
        
        self._init_ui()
        
        # 自动扫描设备
        self._scan_devices()
        
        # 定时刷新设备列表
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._scan_devices)
        self.refresh_timer.start(5000)  # 每5秒刷新
        
        # 定时刷新游戏状态
        self.game_status_timer = QTimer()
        self.game_status_timer.timeout.connect(self._check_game_status)
        self.game_status_timer.start(3000)  # 每3秒刷新游戏状态
    
    def _init_ui(self):
        """初始化UI - 紧凑版"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # 顶部状态栏
        status_layout = QHBoxLayout()
        main_layout.addLayout(status_layout)
        
        # 连接状态标签
        status_label = QLabel("连接状态:")
        status_label.setFixedWidth(70)
        status_layout.addWidget(status_label)
        
        self.connection_status = QLabel("未连接")
        self.connection_status.setStyleSheet("""
            QLabel {
                padding: 3px 10px;
                background-color: #ffebee;
                border: 1px solid #f44336;
                border-radius: 3px;
                color: #c62828;
                font-weight: bold;
            }
        """)
        status_layout.addWidget(self.connection_status)
        status_layout.addStretch()
        
        # 内容区域 - 使用网格布局
        content_widget = QWidget()
        content_layout = QGridLayout(content_widget)
        content_layout.setSpacing(5)
        main_layout.addWidget(content_widget)
        
        # 左上 - 设备列表
        device_group = QGroupBox("设备列表")
        device_layout = QVBoxLayout()
        device_layout.setSpacing(3)
        device_group.setLayout(device_layout)
        content_layout.addWidget(device_group, 0, 0)
        
        # 设备操作按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(3)
        device_layout.addLayout(button_layout)
        
        self.scan_btn = QPushButton("刷新")
        self.scan_btn.setMaximumHeight(25)
        self.scan_btn.clicked.connect(self._scan_devices)
        button_layout.addWidget(self.scan_btn)
        
        self.connect_btn = QPushButton("连接")
        self.connect_btn.setMaximumHeight(25)
        self.connect_btn.clicked.connect(self._connect_selected)
        self.connect_btn.setEnabled(False)
        button_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("断开")
        self.disconnect_btn.setMaximumHeight(25)
        self.disconnect_btn.clicked.connect(self._disconnect_device)
        self.disconnect_btn.setEnabled(False)
        button_layout.addWidget(self.disconnect_btn)
        
        # 设备表格
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(3)
        self.device_table.setHorizontalHeaderLabels(["设备ID", "名称", "状态"])
        
        # 设置列宽
        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        
        self.device_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.device_table.itemSelectionChanged.connect(self._on_device_selected)
        self.device_table.setMaximumHeight(100)  # 限制高度
        self.device_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 设置紧凑的行高
        self.device_table.verticalHeader().setDefaultSectionSize(25)
        self.device_table.verticalHeader().setVisible(False)
        
        device_layout.addWidget(self.device_table)
        
        # 右上 - 设备信息
        info_group = QGroupBox("设备信息")
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)
        info_group.setLayout(info_layout)
        content_layout.addWidget(info_group, 0, 1)
        
        self.device_info = QTextEdit()
        self.device_info.setReadOnly(True)
        self.device_info.setFont(QFont("Consolas", 8))
        self.device_info.setPlaceholderText("选择设备后显示信息")
        self.device_info.setMaximumHeight(100)
        info_layout.addWidget(self.device_info)
        
        # 下方左 - WiFi连接
        wifi_group = QGroupBox("WiFi连接")
        wifi_layout = QHBoxLayout()
        wifi_layout.setSpacing(5)
        wifi_group.setLayout(wifi_layout)
        content_layout.addWidget(wifi_group, 1, 0)
        
        wifi_layout.addWidget(QLabel("IP:"))
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        self.ip_input.setMaximumWidth(100)
        wifi_layout.addWidget(self.ip_input)
        
        wifi_layout.addWidget(QLabel("端口:"))
        self.port_input = QLineEdit()
        self.port_input.setText("5555")
        self.port_input.setMaximumWidth(50)
        wifi_layout.addWidget(self.port_input)
        
        self.wifi_connect_btn = QPushButton("连接")
        self.wifi_connect_btn.setMaximumHeight(25)
        self.wifi_connect_btn.clicked.connect(self._connect_wifi)
        wifi_layout.addWidget(self.wifi_connect_btn)
        
        wifi_layout.addStretch()
        
        # 下方右 - 游戏操作
        game_group = QGroupBox("游戏操作")
        game_layout = QVBoxLayout()
        game_layout.setSpacing(3)
        game_group.setLayout(game_layout)
        content_layout.addWidget(game_group, 1, 1)
        
        # 游戏操作按钮布局
        game_btn_layout = QHBoxLayout()
        game_btn_layout.setSpacing(3)
        game_layout.addLayout(game_btn_layout)
        
        # 唤醒游戏按钮
        self.wake_game_btn = QPushButton("唤醒游戏")
        self.wake_game_btn.setMaximumHeight(25)
        self.wake_game_btn.clicked.connect(self._wake_and_start_game)
        self.wake_game_btn.setEnabled(False)
        self.wake_game_btn.setToolTip("唤醒设备并启动剑与远征：启程")
        game_btn_layout.addWidget(self.wake_game_btn)
        
        # 停止游戏按钮
        self.stop_game_btn = QPushButton("停止游戏")
        self.stop_game_btn.setMaximumHeight(25)
        self.stop_game_btn.clicked.connect(self._stop_game)
        self.stop_game_btn.setEnabled(False)
        self.stop_game_btn.setToolTip("停止剑与远征：启程")
        game_btn_layout.addWidget(self.stop_game_btn)
        
        game_btn_layout.addStretch()
        
        # 游戏状态标签
        self.game_status_label = QLabel("游戏状态: 未检测")
        self.game_status_label.setStyleSheet("QLabel { color: #666; font-size: 11px; padding: 3px; }")
        game_layout.addWidget(self.game_status_label)
        
        # 添加一个提示标签
        tip_label = QLabel("提示: 确保设备已开启USB调试，首次连接需在设备上授权")
        tip_label.setStyleSheet("QLabel { color: #666; font-size: 11px; padding: 5px; }")
        main_layout.addWidget(tip_label)
        
        # 添加弹性空间
        main_layout.addStretch()
    
    def _scan_devices(self):
        """扫描设备"""
        if self.scan_thread and self.scan_thread.isRunning():
            return
        
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("扫描中...")
        
        self.scan_thread = DeviceScanThread(self.adb_service)
        self.scan_thread.devices_found.connect(self._on_devices_found)
        self.scan_thread.error_occurred.connect(self._on_scan_error)
        self.scan_thread.finished.connect(lambda: self.scan_btn.setEnabled(True))
        self.scan_thread.finished.connect(lambda: self.scan_btn.setText("刷新"))
        self.scan_thread.start()
    
    def _on_devices_found(self, devices: List[Device]):
        """设备扫描完成"""
        self.devices = devices
        self._update_device_table()
        
        if not devices:
            self.device_info.setText("未发现设备")
    
    def _on_scan_error(self, error_msg: str):
        """扫描错误处理"""
        self.logger.warning(f"Device scan error: {error_msg}")
        self.device_info.setText(f"扫描错误: {error_msg}\n请检查ADB是否正确安装")
    
    def _update_device_table(self):
        """更新设备表格"""
        try:
            self.device_table.setRowCount(len(self.devices))
            
            for i, device in enumerate(self.devices):
                # 设备ID
                id_item = QTableWidgetItem(device.device_id)
                id_item.setFont(QFont("Consolas", 8))
                self.device_table.setItem(i, 0, id_item)
                
                # 设备名
                name_item = QTableWidgetItem(device.device_name or "未知")
                name_item.setFont(QFont("Arial", 8))
                self.device_table.setItem(i, 1, name_item)
                
                # 状态 - 安全获取
                if hasattr(device, 'status') and device.status:
                    if hasattr(device.status, 'value'):
                        status_text = device.status.value
                    else:
                        status_text = str(device.status)
                else:
                    status_text = "unknown"
                    
                status_item = QTableWidgetItem(status_text)
                status_item.setFont(QFont("Arial", 8))
                
                # 设置颜色
                if device.status == DeviceStatus.ONLINE:
                    status_item.setForeground(Qt.GlobalColor.green)
                elif device.status == DeviceStatus.OFFLINE:
                    status_item.setForeground(Qt.GlobalColor.red)
                else:
                    status_item.setForeground(Qt.GlobalColor.yellow)
                self.device_table.setItem(i, 2, status_item)
        except Exception as e:
            self.logger.error(f"Error updating device table: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
        
        # 自动选中当前连接的设备
        if self.adb_service.current_device:
            for i, device in enumerate(self.devices):
                if device.device_id == self.adb_service.current_device.device_id:
                    self.device_table.selectRow(i)
                    self._update_connection_status(True, device.device_id)
                    break
    
    def _on_device_selected(self):
        """设备选中事件"""
        try:
            row = self.device_table.currentRow()
            if row >= 0 and row < len(self.devices):
                device = self.devices[row]
                self.logger.debug(f"Device selected: {device.device_id}, status: {device.status}")
                self._show_device_info(device)
                
                # 根据设备状态启用/禁用连接按钮
                if device.status == DeviceStatus.ONLINE:
                    is_connected = (self.adb_service.current_device is not None and 
                                  self.adb_service.current_device.device_id == device.device_id)
                    if hasattr(self, 'connect_btn') and self.connect_btn:
                        self.connect_btn.setEnabled(not is_connected)
                    if hasattr(self, 'disconnect_btn') and self.disconnect_btn:
                        self.disconnect_btn.setEnabled(bool(is_connected))
                else:
                    if hasattr(self, 'connect_btn') and self.connect_btn:
                        self.connect_btn.setEnabled(False)
                    if hasattr(self, 'disconnect_btn') and self.disconnect_btn:
                        self.disconnect_btn.setEnabled(False)
        except Exception as e:
            self.logger.error(f"Error in _on_device_selected: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
    
    def _show_device_info(self, device: Device):
        """显示设备信息（简化版）"""
        try:
            info_text = f"ID: {device.device_id}\n"
            info_text += f"名称: {device.device_name or '未知'}\n"
            
            # 安全获取状态
            if hasattr(device, 'status') and device.status:
                if hasattr(device.status, 'value'):
                    info_text += f"状态: {device.status.value}\n"
                else:
                    info_text += f"状态: {str(device.status)}\n"
            else:
                info_text += "状态: 未知\n"
            
            # 安全获取连接类型
            if hasattr(device, 'connection_type') and device.connection_type:
                if hasattr(device.connection_type, 'value'):
                    info_text += f"连接: {device.connection_type.value.upper()}"
                else:
                    info_text += f"连接: {str(device.connection_type).upper()}"
            else:
                info_text += "连接: 未知"
            
            self.device_info.setText(info_text)
        except Exception as e:
            self.logger.error(f"Error showing device info: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            self.device_info.setText("获取设备信息失败")
    
    def _connect_selected(self):
        """连接选中的设备"""
        row = self.device_table.currentRow()
        if row < 0 or row >= len(self.devices):
            QMessageBox.warning(self, "提示", "请先选择设备")
            return
        
        device = self.devices[row]
        
        if device.status != DeviceStatus.ONLINE:
            QMessageBox.warning(self, "警告", "设备不在线")
            return
        
        if self.adb_service.connect_device(device.device_id):
            self._update_connection_status(True, device.device_id)
            self.logger.info(f"Connected to device: {device.device_id}")
            
            # 更新按钮状态
            if hasattr(self, 'connect_btn') and self.connect_btn:
                self.connect_btn.setEnabled(False)
            if hasattr(self, 'disconnect_btn') and self.disconnect_btn:
                self.disconnect_btn.setEnabled(True)
            
            # 刷新设备信息
            self._show_device_info(device)
        else:
            QMessageBox.critical(self, "错误", "连接失败")
    
    def _disconnect_device(self):
        """断开连接"""
        if not self.adb_service.current_device:
            return
        
        self.adb_service.disconnect_device()
        self._update_connection_status(False)
        
        # 更新按钮状态
        if hasattr(self, 'connect_btn') and self.connect_btn:
            self.connect_btn.setEnabled(True)
        if hasattr(self, 'disconnect_btn') and self.disconnect_btn:
            self.disconnect_btn.setEnabled(False)
        
        # 清空设备信息
        self.device_info.setText("设备已断开")
    
    def _connect_wifi(self):
        """WiFi连接"""
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip() or "5555"
        
        if not ip:
            QMessageBox.warning(self, "提示", "请输入IP地址")
            return
        
        address = f"{ip}:{port}"
        
        if self.adb_service.connect_wifi_device(address):
            self._update_connection_status(True, address)
            self.logger.info(f"Connected to WiFi device: {address}")
            self._scan_devices()
        else:
            QMessageBox.critical(self, "错误", "WiFi连接失败")
    
    def _update_connection_status(self, connected: bool, device_id: str = None):
        """更新连接状态显示"""
        if connected:
            self.connection_status.setText(f"已连接: {device_id}")
            self.connection_status.setStyleSheet("""
                QLabel {
                    padding: 3px 10px;
                    background-color: #e8f5e9;
                    border: 1px solid #4caf50;
                    border-radius: 3px;
                    color: #2e7d32;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)
            # 启用游戏操作按钮
            self.wake_game_btn.setEnabled(True)
            self.stop_game_btn.setEnabled(True)
            # 检查游戏状态
            self._check_game_status()
        else:
            self.connection_status.setText("未连接")
            self.connection_status.setStyleSheet("""
                QLabel {
                    padding: 3px 10px;
                    background-color: #ffebee;
                    border: 1px solid #f44336;
                    border-radius: 3px;
                    color: #c62828;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)
            # 禁用游戏操作按钮
            self.wake_game_btn.setEnabled(False)
            self.stop_game_btn.setEnabled(False)
            self.game_status_label.setText("游戏状态: 未检测")
    
    def _check_game_status(self):
        """检查游戏状态"""
        if not self.adb_service.current_device:
            self.game_status_label.setText("游戏状态: 设备未连接")
            return
        
        try:
            # 检查游戏是否在运行
            package_name = "com.lilithgame.igame.android.cn"
            if self.adb_service.is_app_running(package_name):
                self.game_status_label.setText("游戏状态: 运行中")
                self.game_status_label.setStyleSheet("QLabel { color: #2e7d32; font-size: 11px; padding: 3px; }")
            else:
                self.game_status_label.setText("游戏状态: 未运行")
                self.game_status_label.setStyleSheet("QLabel { color: #666; font-size: 11px; padding: 3px; }")
        except Exception as e:
            self.logger.debug(f"Failed to check game status: {e}")
            self.game_status_label.setText("游戏状态: 未知")
            self.game_status_label.setStyleSheet("QLabel { color: #666; font-size: 11px; padding: 3px; }")
    
    def _wake_and_start_game(self):
        """唤醒并启动游戏"""
        if not self.adb_service.current_device:
            QMessageBox.warning(self, "提示", "请先连接设备")
            return
        
        # 禁用按钮防止重复点击
        self.wake_game_btn.setEnabled(False)
        self.wake_game_btn.setText("启动中...")
        
        # 创建并启动线程
        self.wake_game_thread = WakeGameThread(self.adb_service)
        self.wake_game_thread.progress_signal.connect(self._on_wake_game_progress)
        self.wake_game_thread.finished_signal.connect(self._on_wake_game_finished)
        self.wake_game_thread.start()
    
    def _on_wake_game_progress(self, message: str):
        """唤醒游戏进度更新"""
        self.wake_game_btn.setText(message[:10] + "...")  # 限制按钮文字长度
        self.logger.info(message)
    
    def _on_wake_game_finished(self, success: bool, message: str):
        """唤醒游戏完成"""
        # 恢复按钮状态
        self.wake_game_btn.setEnabled(True)
        self.wake_game_btn.setText("唤醒游戏")
        
        # 显示结果
        if success:
            QMessageBox.information(self, "成功", message)
            self._check_game_status()
        else:
            QMessageBox.warning(self, "失败", message)
        
        # 清理线程
        if hasattr(self, 'wake_game_thread'):
            self.wake_game_thread.deleteLater()
            self.wake_game_thread = None
    
    def _stop_game(self):
        """停止游戏"""
        if not self.adb_service.current_device:
            QMessageBox.warning(self, "提示", "请先连接设备")
            return
        
        package_name = "com.lilithgame.igame.android.cn"
        
        try:
            if self.adb_service.stop_app(package_name):
                QMessageBox.information(self, "成功", "游戏已停止")
                self._check_game_status()
            else:
                QMessageBox.warning(self, "失败", "无法停止游戏")
        except Exception as e:
            self.logger.error(f"Failed to stop game: {e}")
            QMessageBox.critical(self, "错误", f"停止游戏失败: {str(e)}")