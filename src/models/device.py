"""
设备信息模型
定义Android设备相关的数据结构
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple
from enum import Enum


class ConnectionType(Enum):
    """设备连接类型"""
    USB = "usb"
    WIFI = "wifi"
    UNKNOWN = "unknown"


class DeviceStatus(Enum):
    """设备状态"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    UNKNOWN = "unknown"


@dataclass
class Device:
    """
    设备信息数据类
    
    Attributes:
        device_id: 设备唯一标识符 (如: emulator-5554, 192.168.1.100:5555)
        device_name: 设备名称
        device_model: 设备型号
        android_version: Android系统版本
        screen_resolution: 屏幕分辨率 (宽, 高)
        connection_type: 连接类型
        status: 设备状态
        adb_path: ADB可执行文件路径
    """
    device_id: str
    device_name: str = "Unknown Device"
    device_model: str = "Unknown Model"
    android_version: str = "Unknown"
    screen_resolution: Tuple[int, int] = (0, 0)
    connection_type: ConnectionType = ConnectionType.UNKNOWN
    status: DeviceStatus = DeviceStatus.UNKNOWN
    adb_path: Optional[str] = None
    
    # 额外的设备信息
    manufacturer: str = field(default="Unknown")
    sdk_version: int = field(default=0)
    cpu_arch: str = field(default="Unknown")
    battery_level: int = field(default=-1)
    
    def __str__(self) -> str:
        """返回设备的字符串表示"""
        return f"{self.device_name} ({self.device_id})"
    
    def __repr__(self) -> str:
        """返回设备的详细表示"""
        return (f"Device(id={self.device_id}, name={self.device_name}, "
                f"model={self.device_model}, status={self.status.value})")
    
    @property
    def is_connected(self) -> bool:
        """检查设备是否已连接"""
        return self.status == DeviceStatus.CONNECTED
    
    @property
    def is_wireless(self) -> bool:
        """检查是否为无线连接"""
        return self.connection_type == ConnectionType.WIFI
    
    @property
    def resolution_string(self) -> str:
        """获取分辨率字符串表示"""
        if self.screen_resolution == (0, 0):
            return "Unknown"
        return f"{self.screen_resolution[0]}x{self.screen_resolution[1]}"
    
    def to_dict(self) -> dict:
        """转换为字典格式，便于序列化"""
        return {
            'device_id': self.device_id,
            'device_name': self.device_name,
            'device_model': self.device_model,
            'android_version': self.android_version,
            'screen_resolution': list(self.screen_resolution),
            'connection_type': self.connection_type.value,
            'status': self.status.value,
            'adb_path': self.adb_path,
            'manufacturer': self.manufacturer,
            'sdk_version': self.sdk_version,
            'cpu_arch': self.cpu_arch,
            'battery_level': self.battery_level
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Device':
        """从字典创建Device实例"""
        # 处理枚举类型
        if 'connection_type' in data:
            data['connection_type'] = ConnectionType(data['connection_type'])
        if 'status' in data:
            data['status'] = DeviceStatus(data['status'])
        
        # 处理元组类型
        if 'screen_resolution' in data:
            data['screen_resolution'] = tuple(data['screen_resolution'])
        
        return cls(**data)
    
    def update_status(self, status: DeviceStatus) -> None:
        """更新设备状态"""
        self.status = status
    
    def update_resolution(self, width: int, height: int) -> None:
        """更新屏幕分辨率"""
        self.screen_resolution = (width, height)