"""
ADB配置标签页 - 紧凑版
"""

from typing import Optional, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox
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




class DeviceConnectThread(QThread):
    """设备连接线程"""
    connection_finished = pyqtSignal(bool, str, object)  # (success, message, device)
    
    def __init__(self, adb_service: ADBService, device_id: str, device: Device):
        super().__init__()
        self.adb_service = adb_service
        self.device_id = device_id
        self.device = device
    
    def run(self):
        """执行连接"""
        try:
            success = self.adb_service.connect_device(self.device_id)
            if success:
                self.connection_finished.emit(True, f"已连接到设备: {self.device_id}", self.device)
            else:
                self.connection_finished.emit(False, "设备连接失败，请检查设备状态", None)
        except Exception as e:
            self.connection_finished.emit(False, f"连接失败: {str(e)}", None)


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
        self._is_scanning = False  # 添加扫描标志
        
        self._init_ui()
        
        # 延迟初始扫描，避免初始化时的问题
        QTimer.singleShot(500, self._scan_devices)
        
        # 移除自动刷新定时器，避免频繁扫描导致的问题
        # 用户可以手动点击刷新按钮来扫描设备
    
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
        
        # 内容区域 - 使用垂直布局
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(5)
        main_layout.addWidget(content_widget)
        
        # 设备列表
        device_group = QGroupBox("设备列表")
        device_layout = QVBoxLayout()
        device_layout.setSpacing(3)
        device_group.setLayout(device_layout)
        content_layout.addWidget(device_group)
        
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
        self.device_table.setMaximumHeight(150)  # 增加高度
        self.device_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 设置紧凑的行高
        self.device_table.verticalHeader().setDefaultSectionSize(25)
        self.device_table.verticalHeader().setVisible(False)
        
        device_layout.addWidget(self.device_table)
        
        # WiFi连接
        wifi_group = QGroupBox("WiFi连接")
        wifi_layout = QHBoxLayout()
        wifi_layout.setSpacing(5)
        wifi_group.setLayout(wifi_layout)
        content_layout.addWidget(wifi_group)
        
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
        
        # 添加一个提示标签
        tip_label = QLabel("提示: 确保设备已开启USB调试，首次连接需在设备上授权")
        tip_label.setStyleSheet("QLabel { color: #666; font-size: 11px; padding: 5px; }")
        main_layout.addWidget(tip_label)
        
        # 添加弹性空间
        main_layout.addStretch()
    
    def _scan_devices(self):
        """扫描设备"""
        # 检查是否已有线程在运行
        if self.scan_thread and self.scan_thread.isRunning():
            self.logger.debug("Scan thread already running, skipping")
            return
        
        # 清理旧线程
        if self.scan_thread:
            try:
                # 断开所有信号连接
                self.scan_thread.devices_found.disconnect()
                self.scan_thread.error_occurred.disconnect()
                self.scan_thread.finished.disconnect()
            except TypeError:
                # 信号未连接时会抛出TypeError，忽略
                pass
            
            # 如果线程还在运行，等待它结束
            if self.scan_thread.isRunning():
                self.scan_thread.quit()
                if not self.scan_thread.wait(1000):  # 等待1秒
                    self.scan_thread.terminate()
                    self.scan_thread.wait()
            
            # 删除旧线程对象
            self.scan_thread.deleteLater()
            self.scan_thread = None
        
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("扫描中...")
        
        # 创建新线程
        self.scan_thread = DeviceScanThread(self.adb_service)
        self.scan_thread.devices_found.connect(self._on_devices_found)
        self.scan_thread.error_occurred.connect(self._on_scan_error)
        # 使用单个连接处理完成事件
        self.scan_thread.finished.connect(self._on_scan_complete)
        self.scan_thread.start()
    
    def _on_devices_found(self, devices: List[Device]):
        """设备扫描完成"""
        self.devices = devices
        self._update_device_table()
    
    def _on_scan_error(self, error_msg: str):
        """扫描错误处理"""
        self.logger.warning(f"Device scan error: {error_msg}")
    
    def _on_scan_complete(self):
        """扫描完成处理"""
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("刷新")
        self._is_scanning = False
    
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
        
        # 检查是否已有连接线程在运行
        if hasattr(self, 'connect_thread') and self.connect_thread and self.connect_thread.isRunning():
            QMessageBox.warning(self, "提示", "正在连接中，请稍候")
            return
        
        # 清理旧的连接线程
        if hasattr(self, 'connect_thread') and self.connect_thread:
            try:
                self.connect_thread.connection_finished.disconnect()
            except TypeError:
                pass
            self.connect_thread.deleteLater()
            self.connect_thread = None
        
        # 禁用连接按钮，防止重复点击
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("连接中...")
        
        # 创建并启动连接线程
        self.connect_thread = DeviceConnectThread(self.adb_service, device.device_id, device)
        self.connect_thread.connection_finished.connect(self._on_connection_finished)
        self.connect_thread.start()
    
    def _on_connection_finished(self, success: bool, message: str, device: Optional[Device]):
        """设备连接完成处理"""
        # 恢复连接按钮
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("连接")
        
        if success:
            # 连接成功
            self._update_connection_status(True, device.device_id if device else "")
            self.logger.info(message)
            
            # 更新按钮状态
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            
        else:
            # 连接失败
            QMessageBox.critical(self, "错误", message)
            
        # 清理连接线程
        if hasattr(self, 'connect_thread'):
            self.connect_thread.deleteLater()
            self.connect_thread = None
    
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
    
    
    def cleanup(self):
        """清理资源"""
        # 清理连接线程
        if hasattr(self, 'connect_thread') and self.connect_thread:
            try:
                self.connect_thread.connection_finished.disconnect()
            except TypeError:
                pass
            
            if self.connect_thread.isRunning():
                self.connect_thread.quit()
                if not self.connect_thread.wait(1000):
                    self.connect_thread.terminate()
                    self.connect_thread.wait()
            
            self.connect_thread.deleteLater()
            self.connect_thread = None
        
        # 清理扫描线程
        if self.scan_thread:
            try:
                self.scan_thread.devices_found.disconnect()
                self.scan_thread.error_occurred.disconnect()
                self.scan_thread.finished.disconnect()
            except TypeError:
                pass
            
            if self.scan_thread.isRunning():
                self.scan_thread.quit()
                if not self.scan_thread.wait(1000):
                    self.scan_thread.terminate()
                    self.scan_thread.wait()
            
            self.scan_thread.deleteLater()
            self.scan_thread = None
        
        
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        self.cleanup()
        super().closeEvent(event)