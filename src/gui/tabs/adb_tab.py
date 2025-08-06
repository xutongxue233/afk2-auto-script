"""
ADB配置标签页 - 简化版
"""

from typing import Optional, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from src.services.adb_service import ADBService
from src.models.device import Device, DeviceStatus
from src.services.log_service import LoggerMixin


class DeviceScanThread(QThread):
    """设备扫描线程"""
    devices_found = pyqtSignal(list)
    
    def __init__(self, adb_service: ADBService):
        super().__init__()
        self.adb_service = adb_service
    
    def run(self):
        """运行扫描"""
        devices = self.adb_service.get_devices()
        self.devices_found.emit(devices)


class ADBTab(QWidget, LoggerMixin):
    """
    ADB配置标签页 - 简化版，只提供基本的设备连接功能
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
        self._last_scan_time = 0
        self._device_cache_timeout = 30  # 设备缓存超时时间(秒)
        self._scanning_in_progress = False
        
        self._init_ui()
        
        # 初始扫描设备
        self._scan_devices()
        
        # 条件性刷新定时器 - 延长间隔并添加条件检查
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._conditional_scan)
        self.refresh_timer.start(30000)  # 每30秒检查一次是否需要扫描
    
    def _init_ui(self):
        """初始化UI - 简化版"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 主要内容区域
        main_layout = QHBoxLayout()
        layout.addLayout(main_layout)
        
        # 左侧 - 设备列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        main_layout.addWidget(left_widget, 3)
        
        # 设备列表组
        device_group = QGroupBox("设备列表")
        device_layout = QVBoxLayout()
        device_group.setLayout(device_layout)
        left_layout.addWidget(device_group)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        device_layout.addLayout(button_layout)
        
        self.scan_btn = QPushButton("🔄 刷新设备")
        self.scan_btn.clicked.connect(self._scan_devices)
        button_layout.addWidget(self.scan_btn)
        
        self.connect_btn = QPushButton("🔗 连接设备")
        self.connect_btn.clicked.connect(self._connect_selected)
        self.connect_btn.setEnabled(False)
        button_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("❌ 断开连接")
        self.disconnect_btn.clicked.connect(self._disconnect_device)
        self.disconnect_btn.setEnabled(False)
        button_layout.addWidget(self.disconnect_btn)
        
        button_layout.addStretch()
        
        # 设备表格
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(3)
        self.device_table.setHorizontalHeaderLabels(["设备ID", "设备名称", "状态"])
        self.device_table.horizontalHeader().setStretchLastSection(True)
        self.device_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.device_table.itemSelectionChanged.connect(self._on_device_selected)
        self.device_table.setMaximumHeight(120)  # 限制表格高度，大约显示3-4个设备
        self.device_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # 需要时显示滚动条
        device_layout.addWidget(self.device_table)
        
        # WiFi连接组
        wifi_group = QGroupBox("WiFi连接（可选）")
        wifi_layout = QVBoxLayout()
        wifi_group.setLayout(wifi_layout)
        left_layout.addWidget(wifi_group)
        
        # IP地址输入
        ip_layout = QHBoxLayout()
        wifi_layout.addLayout(ip_layout)
        
        ip_layout.addWidget(QLabel("IP地址:"))
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        ip_layout.addWidget(self.ip_input)
        
        ip_layout.addWidget(QLabel("端口:"))
        self.port_input = QLineEdit()
        self.port_input.setText("5555")
        self.port_input.setMaximumWidth(80)
        ip_layout.addWidget(self.port_input)
        
        self.wifi_connect_btn = QPushButton("WiFi连接")
        self.wifi_connect_btn.clicked.connect(self._connect_wifi)
        ip_layout.addWidget(self.wifi_connect_btn)
        
        # 右侧 - 设备信息和状态
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        main_layout.addWidget(right_widget, 2)
        
        # 当前连接状态
        status_group = QGroupBox("连接状态")
        status_layout = QVBoxLayout()
        status_group.setLayout(status_layout)
        right_layout.addWidget(status_group)
        
        self.connection_status = QLabel("未连接")
        self.connection_status.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status.setStyleSheet("""
            QLabel {
                padding: 10px;
                background-color: #f0f0f0;
                border: 2px solid #ccc;
                border-radius: 5px;
                color: #666;
            }
        """)
        status_layout.addWidget(self.connection_status)
        
        # 设备信息
        info_group = QGroupBox("设备信息")
        info_layout = QVBoxLayout()
        info_group.setLayout(info_layout)
        right_layout.addWidget(info_group)
        
        self.device_info = QTextEdit()
        self.device_info.setReadOnly(True)
        self.device_info.setFont(QFont("Consolas", 9))
        self.device_info.setPlaceholderText("选择设备后显示详细信息...")
        self.device_info.setMaximumHeight(120)  # 限制设备信息显示高度
        info_layout.addWidget(self.device_info)
        
        # 使用提示
        tip_group = QGroupBox("快速提示")
        tip_layout = QVBoxLayout()
        tip_group.setLayout(tip_layout)
        right_layout.addWidget(tip_group)
        
        tips = QLabel(
            "• 确保设备已开启USB调试\n"
            "• 首次连接需在设备上授权\n"
            "• 连接成功后可执行自动化任务"
        )
        tips.setWordWrap(True)
        tips.setStyleSheet("QLabel { padding: 5px; background-color: #fffef0; font-size: 11px; }")
        tip_layout.addWidget(tips)
        
        right_layout.addStretch()
    
    def _conditional_scan(self):
        """
        条件性扫描设备 - 只在必要时才执行扫描
        """
        import time
        current_time = time.time()
        
        # 检查是否需要扫描的条件
        should_scan = False
        
        # 条件1：如果还没有设备列表，需要扫描
        if not self.devices:
            should_scan = True
            self.logger.debug("Conditional scan: No devices cached, scanning...")
        
        # 条件2：如果当前没有连接的设备，且缓存已过期
        elif not self.adb_service.current_device and (current_time - self._last_scan_time) > self._device_cache_timeout:
            should_scan = True
            self.logger.debug("Conditional scan: No connected device and cache expired, scanning...")
        
        # 条件3：如果有连接的设备但不在设备列表中（可能是新连接的）
        elif self.adb_service.current_device:
            device_found = False
            for device in self.devices:
                if device.device_id == self.adb_service.current_device.device_id:
                    device_found = True
                    break
            
            if not device_found:
                should_scan = True
                self.logger.debug("Conditional scan: Connected device not in cache, scanning...")
        
        # 如果满足扫描条件且当前没在扫描，则执行扫描
        if should_scan and not self._scanning_in_progress:
            self._scan_devices()
        else:
            self.logger.debug(f"Conditional scan: Skip (should_scan={should_scan}, scanning={self._scanning_in_progress})")
    
    def _scan_devices(self):
        """扫描设备"""
        if self.scan_thread and self.scan_thread.isRunning():
            return
        
        self._scanning_in_progress = True
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("🔄 扫描中...")
        
        self.scan_thread = DeviceScanThread(self.adb_service)
        self.scan_thread.devices_found.connect(self._on_devices_found)
        self.scan_thread.finished.connect(self._on_scan_finished)
        self.scan_thread.start()
    
    def _on_scan_finished(self):
        """扫描完成后的清理工作"""
        import time
        self._scanning_in_progress = False
        self._last_scan_time = time.time()
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔄 刷新设备")
    
    def _on_devices_found(self, devices: List[Device]):
        """设备扫描完成"""
        self.devices = devices
        self._update_device_table()
        
        if not devices:
            self.device_info.setText(
                "未发现设备\n\n"
                "请检查:\n"
                "1. USB连接是否正常\n"
                "2. USB调试是否开启\n"
                "3. ADB驱动是否安装"
            )
    
    def _update_device_table(self):
        """更新设备表格"""
        self.device_table.setRowCount(len(self.devices))
        
        for i, device in enumerate(self.devices):
            # 设备ID
            self.device_table.setItem(i, 0, QTableWidgetItem(device.device_id))
            
            # 设备名
            self.device_table.setItem(i, 1, QTableWidgetItem(device.device_name or "未知设备"))
            
            # 状态
            status_item = QTableWidgetItem(device.status.value)
            if device.status == DeviceStatus.ONLINE:
                status_item.setForeground(Qt.GlobalColor.green)
            elif device.status == DeviceStatus.OFFLINE:
                status_item.setForeground(Qt.GlobalColor.red)
            else:
                status_item.setForeground(Qt.GlobalColor.yellow)
            self.device_table.setItem(i, 2, status_item)
        
        # 自动选中当前连接的设备
        if self.adb_service.current_device:
            for i, device in enumerate(self.devices):
                if device.device_id == self.adb_service.current_device.device_id:
                    self.device_table.selectRow(i)
                    self._update_connection_status(True, device.device_id)
                    break
    
    def _on_device_selected(self):
        """设备选中事件"""
        row = self.device_table.currentRow()
        if row >= 0 and row < len(self.devices):
            device = self.devices[row]
            self._show_device_info(device)
            
            # 根据设备状态启用/禁用连接按钮
            if device.status == DeviceStatus.ONLINE:
                is_connected = (self.adb_service.current_device and 
                              self.adb_service.current_device.device_id == device.device_id)
                self.connect_btn.setEnabled(not is_connected)
                self.disconnect_btn.setEnabled(is_connected)
            else:
                self.connect_btn.setEnabled(False)
                self.disconnect_btn.setEnabled(False)
    
    def _show_device_info(self, device: Device):
        """显示设备信息"""
        info_text = f"设备ID: {device.device_id}\n"
        info_text += f"设备名称: {device.device_name or '未知'}\n"
        info_text += f"连接状态: {device.status.value}\n"
        info_text += f"连接方式: {device.transport or 'USB'}\n"
        
        if device.status == DeviceStatus.ONLINE and self.adb_service.current_device == device:
            # 获取更多设备信息
            try:
                # Android版本
                android_version = self.adb_service.execute_shell_command(
                    "getprop ro.build.version.release"
                )
                if android_version:
                    info_text += f"\nAndroid版本: {android_version.strip()}"
                
                # 设备型号
                model = self.adb_service.execute_shell_command(
                    "getprop ro.product.model"
                )
                if model:
                    info_text += f"\n设备型号: {model.strip()}"
                
                # 屏幕分辨率
                resolution = self.adb_service.execute_shell_command(
                    "wm size"
                )
                if resolution and "Physical size:" in resolution:
                    size = resolution.split("Physical size:")[1].strip().split('\n')[0]
                    info_text += f"\n屏幕分辨率: {size}"
                
                # 电池状态
                battery = self.adb_service.execute_shell_command(
                    "dumpsys battery | grep level"
                )
                if battery:
                    info_text += f"\n{battery.strip()}"
            except Exception as e:
                self.logger.error(f"Failed to get device info: {e}")
        
        self.device_info.setText(info_text)
    
    def _connect_selected(self):
        """连接选中的设备"""
        row = self.device_table.currentRow()
        if row < 0 or row >= len(self.devices):
            QMessageBox.warning(self, "提示", "请先选择要连接的设备")
            return
        
        device = self.devices[row]
        
        if device.status != DeviceStatus.ONLINE:
            QMessageBox.warning(self, "警告", "设备不在线，无法连接")
            return
        
        if self.adb_service.connect_device(device.device_id):
            self._update_connection_status(True, device.device_id)
            QMessageBox.information(self, "成功", f"已连接到设备: {device.device_id}")
            self.logger.info(f"Connected to device: {device.device_id}")
            
            # 更新按钮状态
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            
            # 刷新设备信息
            self._show_device_info(device)
        else:
            QMessageBox.critical(self, "错误", "设备连接失败，请检查设备状态")
    
    def _disconnect_device(self):
        """断开连接"""
        if not self.adb_service.current_device:
            QMessageBox.warning(self, "提示", "当前没有连接的设备")
            return
        
        device_id = self.adb_service.current_device.device_id
        self.adb_service.disconnect_device()
        
        self._update_connection_status(False)
        QMessageBox.information(self, "成功", f"已断开设备: {device_id}")
        self.logger.info(f"Disconnected from device: {device_id}")
        
        # 更新按钮状态
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        
        # 清空设备信息
        self.device_info.setText("设备已断开连接")
    
    def _connect_wifi(self):
        """WiFi连接"""
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        
        if not ip:
            QMessageBox.warning(self, "提示", "请输入设备IP地址")
            return
        
        if not port:
            port = "5555"
        
        address = f"{ip}:{port}"
        
        # 尝试连接
        if self.adb_service.connect_wifi_device(address):
            self._update_connection_status(True, address)
            QMessageBox.information(self, "成功", f"已通过WiFi连接到: {address}")
            self.logger.info(f"Connected to WiFi device: {address}")
            
            # 刷新设备列表
            self._scan_devices()
        else:
            QMessageBox.critical(self, "错误", f"WiFi连接失败: {address}\n请确保设备和电脑在同一网络")
    
    def _update_connection_status(self, connected: bool, device_id: str = None):
        """更新连接状态显示"""
        if connected:
            self.connection_status.setText(f"✅ 已连接: {device_id}")
            self.connection_status.setStyleSheet("""
                QLabel {
                    padding: 10px;
                    background-color: #e8f5e9;
                    border: 2px solid #4caf50;
                    border-radius: 5px;
                    color: #2e7d32;
                    font-weight: bold;
                }
            """)
        else:
            self.connection_status.setText("❌ 未连接")
            self.connection_status.setStyleSheet("""
                QLabel {
                    padding: 10px;
                    background-color: #ffebee;
                    border: 2px solid #f44336;
                    border-radius: 5px;
                    color: #c62828;
                    font-weight: bold;
                }
            """)