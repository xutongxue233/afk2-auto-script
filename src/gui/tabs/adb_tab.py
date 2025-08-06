"""
ADB配置标签页
"""

from typing import Optional, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QTextEdit, QSplitter
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
    ADB配置标签页
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
        
        # 定时刷新
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._scan_devices)
        self.refresh_timer.start(5000)  # 每5秒刷新
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # 左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        splitter.addWidget(left_panel)
        
        # 设备列表组
        device_group = QGroupBox("设备列表")
        device_layout = QVBoxLayout()
        device_group.setLayout(device_layout)
        left_layout.addWidget(device_group)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        device_layout.addLayout(button_layout)
        
        self.scan_btn = QPushButton("扫描设备")
        self.scan_btn.clicked.connect(self._scan_devices)
        button_layout.addWidget(self.scan_btn)
        
        self.connect_btn = QPushButton("连接选中")
        self.connect_btn.clicked.connect(self._connect_selected)
        button_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("断开连接")
        self.disconnect_btn.clicked.connect(self._disconnect_device)
        button_layout.addWidget(self.disconnect_btn)
        
        button_layout.addStretch()
        
        # 设备表格
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(4)
        self.device_table.setHorizontalHeaderLabels(["设备ID", "设备名", "状态", "传输"])
        self.device_table.horizontalHeader().setStretchLastSection(True)
        self.device_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.device_table.itemSelectionChanged.connect(self._on_device_selected)
        device_layout.addWidget(self.device_table)
        
        # WiFi连接组
        wifi_group = QGroupBox("WiFi连接")
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
        
        # 右侧面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        splitter.addWidget(right_panel)
        
        # 设备信息组
        info_group = QGroupBox("设备信息")
        info_layout = QVBoxLayout()
        info_group.setLayout(info_layout)
        right_layout.addWidget(info_group)
        
        self.device_info = QTextEdit()
        self.device_info.setReadOnly(True)
        self.device_info.setFont(QFont("Consolas", 9))
        info_layout.addWidget(self.device_info)
        
        # ADB命令组
        cmd_group = QGroupBox("ADB命令")
        cmd_layout = QVBoxLayout()
        cmd_group.setLayout(cmd_layout)
        right_layout.addWidget(cmd_group)
        
        # 命令输入
        cmd_input_layout = QHBoxLayout()
        cmd_layout.addLayout(cmd_input_layout)
        
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("输入ADB命令（如: shell dumpsys battery）")
        self.cmd_input.returnPressed.connect(self._execute_command)
        cmd_input_layout.addWidget(self.cmd_input)
        
        self.execute_btn = QPushButton("执行")
        self.execute_btn.clicked.connect(self._execute_command)
        cmd_input_layout.addWidget(self.execute_btn)
        
        # 命令输出
        self.cmd_output = QTextEdit()
        self.cmd_output.setReadOnly(True)
        self.cmd_output.setFont(QFont("Consolas", 9))
        self.cmd_output.setMaximumHeight(200)
        cmd_layout.addWidget(self.cmd_output)
        
        # 快捷命令
        quick_cmd_layout = QHBoxLayout()
        cmd_layout.addLayout(quick_cmd_layout)
        
        quick_cmd_layout.addWidget(QLabel("快捷命令:"))
        
        self.quick_cmd = QComboBox()
        self.quick_cmd.addItems([
            "获取设备信息",
            "查看电池状态",
            "查看运行应用",
            "查看屏幕分辨率",
            "获取WiFi信息",
            "查看CPU信息"
        ])
        quick_cmd_layout.addWidget(self.quick_cmd)
        
        self.quick_execute_btn = QPushButton("执行快捷命令")
        self.quick_execute_btn.clicked.connect(self._execute_quick_command)
        quick_cmd_layout.addWidget(self.quick_execute_btn)
        
        quick_cmd_layout.addStretch()
        
        # 设置分割器比例
        splitter.setSizes([400, 600])
    
    def _scan_devices(self):
        """扫描设备"""
        if self.scan_thread and self.scan_thread.isRunning():
            return
        
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("扫描中...")
        
        self.scan_thread = DeviceScanThread(self.adb_service)
        self.scan_thread.devices_found.connect(self._on_devices_found)
        self.scan_thread.finished.connect(lambda: self.scan_btn.setEnabled(True))
        self.scan_thread.finished.connect(lambda: self.scan_btn.setText("扫描设备"))
        self.scan_thread.start()
    
    def _on_devices_found(self, devices: List[Device]):
        """设备扫描完成"""
        self.devices = devices
        self._update_device_table()
        
        if not devices:
            self.device_info.setText("未发现设备\n\n请检查:\n1. USB连接是否正常\n2. USB调试是否开启\n3. ADB驱动是否安装")
    
    def _update_device_table(self):
        """更新设备表格"""
        self.device_table.setRowCount(len(self.devices))
        
        for i, device in enumerate(self.devices):
            # 设备ID
            self.device_table.setItem(i, 0, QTableWidgetItem(device.device_id))
            
            # 设备名
            self.device_table.setItem(i, 1, QTableWidgetItem(device.device_name or "未知"))
            
            # 状态
            status_item = QTableWidgetItem(device.status.value)
            if device.status == DeviceStatus.ONLINE:
                status_item.setForeground(Qt.GlobalColor.green)
            elif device.status == DeviceStatus.OFFLINE:
                status_item.setForeground(Qt.GlobalColor.red)
            else:
                status_item.setForeground(Qt.GlobalColor.yellow)
            self.device_table.setItem(i, 2, status_item)
            
            # 传输模式
            self.device_table.setItem(i, 3, QTableWidgetItem(device.transport or "USB"))
        
        # 自动选中当前连接的设备
        if self.adb_service.current_device:
            for i, device in enumerate(self.devices):
                if device.device_id == self.adb_service.current_device.device_id:
                    self.device_table.selectRow(i)
                    break
    
    def _on_device_selected(self):
        """设备选中事件"""
        row = self.device_table.currentRow()
        if row >= 0 and row < len(self.devices):
            device = self.devices[row]
            self._show_device_info(device)
    
    def _show_device_info(self, device: Device):
        """显示设备信息"""
        info_text = f"设备ID: {device.device_id}\n"
        info_text += f"设备名: {device.device_name or '未知'}\n"
        info_text += f"状态: {device.status.value}\n"
        info_text += f"传输: {device.transport or 'USB'}\n"
        
        if device.status == DeviceStatus.ONLINE:
            # 获取更多设备信息
            try:
                # Android版本
                android_version = self.adb_service.execute_shell_command(
                    "getprop ro.build.version.release"
                )
                if android_version:
                    info_text += f"Android版本: {android_version.strip()}\n"
                
                # 设备型号
                model = self.adb_service.execute_shell_command(
                    "getprop ro.product.model"
                )
                if model:
                    info_text += f"设备型号: {model.strip()}\n"
                
                # 屏幕分辨率
                resolution = self.adb_service.execute_shell_command(
                    "wm size"
                )
                if resolution:
                    info_text += f"屏幕分辨率: {resolution.strip()}\n"
                
                # 电池状态
                battery = self.adb_service.execute_shell_command(
                    "dumpsys battery | grep level"
                )
                if battery:
                    info_text += f"电池: {battery.strip()}\n"
            except:
                pass
        
        self.device_info.setText(info_text)
    
    def _connect_selected(self):
        """连接选中的设备"""
        row = self.device_table.currentRow()
        if row < 0 or row >= len(self.devices):
            QMessageBox.warning(self, "警告", "请先选择设备")
            return
        
        device = self.devices[row]
        
        if device.status != DeviceStatus.ONLINE:
            QMessageBox.warning(self, "警告", "设备不在线")
            return
        
        if self.adb_service.connect_device(device.device_id):
            QMessageBox.information(self, "成功", f"已连接到设备: {device.device_id}")
            self.logger.info(f"Connected to device: {device.device_id}")
        else:
            QMessageBox.critical(self, "错误", "设备连接失败")
    
    def _disconnect_device(self):
        """断开连接"""
        if not self.adb_service.current_device:
            QMessageBox.warning(self, "警告", "当前没有连接的设备")
            return
        
        device_id = self.adb_service.current_device.device_id
        self.adb_service.disconnect_device()
        QMessageBox.information(self, "成功", f"已断开设备: {device_id}")
        self.logger.info(f"Disconnected from device: {device_id}")
        
        # 清空设备信息
        self.device_info.clear()
        self.device_table.clearSelection()
    
    def _connect_wifi(self):
        """WiFi连接"""
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        
        if not ip:
            QMessageBox.warning(self, "警告", "请输入IP地址")
            return
        
        if not port:
            port = "5555"
        
        address = f"{ip}:{port}"
        
        # 尝试连接
        if self.adb_service.connect_wifi_device(address):
            QMessageBox.information(self, "成功", f"已连接到: {address}")
            self.logger.info(f"Connected to WiFi device: {address}")
            
            # 刷新设备列表
            self._scan_devices()
        else:
            QMessageBox.critical(self, "错误", f"连接失败: {address}")
    
    def _execute_command(self):
        """执行ADB命令"""
        command = self.cmd_input.text().strip()
        if not command:
            return
        
        if not self.adb_service.current_device:
            QMessageBox.warning(self, "警告", "请先连接设备")
            return
        
        try:
            # 执行命令
            if command.startswith("shell "):
                result = self.adb_service.execute_shell_command(command[6:])
            else:
                result = self.adb_service.execute_adb_command(command.split())
            
            # 显示结果
            self.cmd_output.setText(result or "命令执行成功（无输出）")
            
            # 清空输入
            self.cmd_input.clear()
        except Exception as e:
            self.cmd_output.setText(f"执行失败: {e}")
    
    def _execute_quick_command(self):
        """执行快捷命令"""
        if not self.adb_service.current_device:
            QMessageBox.warning(self, "警告", "请先连接设备")
            return
        
        commands = {
            "获取设备信息": "shell getprop",
            "查看电池状态": "shell dumpsys battery",
            "查看运行应用": "shell dumpsys activity activities | grep mResumedActivity",
            "查看屏幕分辨率": "shell wm size",
            "获取WiFi信息": "shell dumpsys wifi | grep \"mWifiInfo\"",
            "查看CPU信息": "shell cat /proc/cpuinfo"
        }
        
        cmd_name = self.quick_cmd.currentText()
        command = commands.get(cmd_name)
        
        if command:
            self.cmd_input.setText(command)
            self._execute_command()