"""
ADB服务模块
封装所有ADB操作
"""

import subprocess
import re
import time
import os
import struct
import gzip
import socket
import threading
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image
import numpy as np
import cv2
import io
import tempfile

from src.models.device import Device, DeviceStatus, ConnectionType
from src.models.config import ADBConfig
from src.services.log_service import LoggerMixin
from src.utils.exceptions import (
    ADBConnectionError, ADBCommandError, DeviceNotFoundError,
    DeviceUnauthorizedError, DeviceOfflineError
)
from src.utils.retry import retry_on_adb_error


class ADBService(LoggerMixin):
    """
    ADB服务类
    提供与Android设备通信的所有功能
    """

    def __init__(self, config: Optional[ADBConfig] = None):
        """
        初始化ADB服务

        Args:
            config: ADB配置对象
        """
        self.config = config or ADBConfig()
        self.current_device: Optional[Device] = None
        self._adb_path = None
        self._adb_checked = False
        self._adb_available = False
        self._screenshot_cache: Optional[Image.Image] = None
        self._screenshot_cache_time: float = 0
        self._numpy_cache: Optional[np.ndarray] = None
        self._numpy_cache_time: float = 0
        # 截图方法自动选择
        self._screencap_method: Optional[str] = None  # 'raw_netcat', 'raw_gzip', 'encode'
        self._screencap_tested: bool = False
        # netcat 相关状态
        self._netcat_address: Optional[str] = None
        self._netcat_server: Optional[socket.socket] = None
        self._netcat_port: int = 0
    
    def _find_adb_path(self) -> str:
        """
        查找ADB可执行文件路径
        
        Returns:
            ADB路径
        """
        # 如果配置中指定了路径
        if self.config.adb_path and os.path.exists(self.config.adb_path):
            return self.config.adb_path
        
        # 优先使用项目目录下的adb
        project_root = Path(__file__).parent.parent.parent  # src/services/adb_service.py -> 项目根目录
        if os.name == 'nt':
            # Windows系统
            project_adb = project_root / "adb" / "adb.exe"
            if project_adb.exists():
                self.logger.info(f"Using project ADB: {project_adb}")
                return str(project_adb)
        else:
            # Linux/Mac系统
            project_adb = project_root / "adb" / "adb"
            if project_adb.exists():
                self.logger.info(f"Using project ADB: {project_adb}")
                return str(project_adb)
        
        # 尝试直接使用adb命令
        try:
            result = subprocess.run(
                ["adb", "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return "adb"
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # Windows系统尝试常见路径
        if os.name == 'nt':
            common_paths = [
                r"C:\platform-tools\adb.exe",
                r"C:\Android\platform-tools\adb.exe",
                r"C:\Users\%USERNAME%\AppData\Local\Android\Sdk\platform-tools\adb.exe"
            ]
            for path in common_paths:
                expanded_path = os.path.expandvars(path)
                if os.path.exists(expanded_path):
                    return expanded_path
        
        # 默认返回adb，让系统去找
        return "adb"
    
    def ensure_adb_available(self) -> bool:
        """
        确保ADB可用（延迟检查）
        
        Returns:
            是否可用
        """
        if self._adb_checked:
            return self._adb_available
        
        # 第一次检查时查找ADB路径
        if not self._adb_path:
            self._adb_path = self._find_adb_path()
        
        try:
            # 尝试执行version命令检查ADB
            cmd_parts = [self._adb_path, "version"]
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=5,
                shell=False
            )
            
            if result.returncode == 0:
                self.logger.info(f"ADB is available: {result.stdout.split(chr(10))[0]}")
                self._adb_available = True
            else:
                self.logger.error(f"ADB not available: {result.stderr or result.stdout}")
                self._adb_available = False
        except Exception as e:
            self.logger.error(f"ADB not available: {e}")
            self._adb_available = False
        
        self._adb_checked = True
        
        if not self._adb_available:
            raise ADBConnectionError("ADB未安装或不在系统PATH中，请先安装ADB工具")
        
        return self._adb_available
    
    def is_adb_available(self) -> bool:
        """
        检查ADB是否可用（不抛出异常）
        
        Returns:
            是否可用
        """
        try:
            return self.ensure_adb_available()
        except:
            return False
    
    def get_adb_status(self) -> dict:
        """
        获取ADB状态信息
        
        Returns:
            状态信息字典
        """
        status = {
            "available": False,
            "path": self._adb_path or "未找到",
            "checked": self._adb_checked,
            "error": None
        }
        
        try:
            status["available"] = self.ensure_adb_available()
            status["path"] = self._adb_path
        except Exception as e:
            status["error"] = str(e)
        
        return status
    
    def execute_command(self, command: str, use_device: bool = True, 
                       timeout: Optional[int] = None) -> str:
        """
        执行ADB命令
        
        Args:
            command: ADB命令（不包含adb前缀）
            use_device: 是否使用当前设备
            timeout: 命令超时时间
        
        Returns:
            命令输出
        """
        # 确保ADB可用
        self.ensure_adb_available()
        
        # 构建完整命令
        cmd_parts = [self._adb_path]
        
        # 如果需要指定设备
        if use_device and self.current_device:
            cmd_parts.extend(["-s", self.current_device.device_id])
        
        # 添加实际命令
        if isinstance(command, str):
            cmd_parts.extend(command.split())
        else:
            cmd_parts.extend(command)
        
        # 设置超时
        if timeout is None:
            timeout = self.config.command_timeout
        
        self.logger.debug(f"Executing ADB command: {' '.join(cmd_parts)}")
        
        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                self.logger.error(f"ADB command failed: {error_msg}")
                raise ADBCommandError(' '.join(cmd_parts), error_msg)
            
            return result.stdout.strip()
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"ADB command timeout: {' '.join(cmd_parts)}")
            raise ADBCommandError(' '.join(cmd_parts), "Command timeout")
        except Exception as e:
            self.logger.error(f"ADB command error: {e}")
            raise ADBCommandError(' '.join(cmd_parts), str(e))
    
    @retry_on_adb_error(max_attempts=3)
    def get_devices(self) -> List[Device]:
        """
        获取已连接的设备列表
        
        Returns:
            设备列表
        """
        try:
            output = self.execute_command("devices -l", use_device=False)
            devices = []
            
            for line in output.split('\n'):
                if not line or line.startswith('List of devices'):
                    continue
                
                parts = line.split()
                if len(parts) < 2:
                    continue
                
                device_id = parts[0]
                status = parts[1]
                
                # 创建设备对象
                device = Device(device_id=device_id)
                
                # 设置状态
                if status == 'device':
                    device.status = DeviceStatus.ONLINE
                elif status == 'offline':
                    device.status = DeviceStatus.OFFLINE
                elif status == 'unauthorized':
                    device.status = DeviceStatus.UNAUTHORIZED
                else:
                    device.status = DeviceStatus.UNKNOWN
                
                self.logger.debug(f"Device {device_id} status: {status} -> {device.status}")
                
                # 判断连接类型
                if ':' in device_id:
                    device.connection_type = ConnectionType.WIFI
                else:
                    device.connection_type = ConnectionType.USB
                
                self.logger.debug(f"Device {device_id} connection type: {device.connection_type}")
                
                # 解析额外信息
                for part in parts[2:]:
                    if part.startswith('model:'):
                        device.device_model = part.split(':')[1]
                    elif part.startswith('device:'):
                        device.device_name = part.split(':')[1]
                
                # 如果设备已连接，获取更多信息
                if device.status == DeviceStatus.ONLINE:
                    self._get_device_details(device)
                
                devices.append(device)
            
            self.logger.info(f"Found {len(devices)} device(s)")
            return devices
            
        except Exception as e:
            self.logger.error(f"Failed to get devices: {e}")
            return []
    
    def _get_device_details(self, device: Device) -> None:
        """
        获取设备详细信息（简化版，只获取基本信息）
        
        Args:
            device: 设备对象
        """
        try:
            # 获取屏幕分辨率
            cmd = f"-s {device.device_id} shell wm size"
            output = self.execute_command(cmd, use_device=False, timeout=2)
            if output:
                # 解析输出，格式通常是 "Physical size: 1080x1920"
                import re
                match = re.search(r'(\d+)x(\d+)', output)
                if match:
                    width = int(match.group(1))
                    height = int(match.group(2))
                    device.set_resolution(width, height)
                    self.logger.debug(f"Device {device.device_id} resolution: {width}x{height}")
        except Exception as e:
            self.logger.debug(f"Failed to get device details: {e}")
            # 不影响主流程，忽略错误
    
    def connect_device(self, device_id: Optional[str] = None) -> bool:
        """
        连接到设备
        
        Args:
            device_id: 设备ID，如果为None则连接第一个可用设备
        
        Returns:
            是否连接成功
        """
        try:
            # 如果指定了设备ID
            if device_id:
                # 如果是无线连接地址
                if ':' in device_id:
                    self.logger.info(f"Connecting to wireless device: {device_id}")
                    output = self.execute_command(f"connect {device_id}", use_device=False)
                    if "connected" not in output.lower() and "already" not in output.lower():
                        raise ADBConnectionError(device_id, f"Failed to connect: {output}")

                # 获取设备列表并查找指定设备
                devices = self.get_devices()
                for device in devices:
                    if device.device_id == device_id:
                        if device.status in (DeviceStatus.CONNECTED, DeviceStatus.ONLINE):
                            self.current_device = device
                            self._screencap_tested = False  # 新设备需重新测速
                            self._cleanup_netcat_server()
                            self.logger.info(f"Connected to device: {device}")
                            return True
                        elif device.status == DeviceStatus.UNAUTHORIZED:
                            raise DeviceUnauthorizedError(device_id)
                        elif device.status == DeviceStatus.OFFLINE:
                            raise DeviceOfflineError(device_id)
                        else:
                            raise ADBConnectionError(device_id, f"Device status: {device.status}")
                
                raise DeviceNotFoundError(device_id)
            
            else:
                # 连接第一个可用设备
                devices = self.get_devices()
                for device in devices:
                    if device.status in (DeviceStatus.CONNECTED, DeviceStatus.ONLINE):
                        self.current_device = device
                        self.logger.info(f"Connected to first available device: {device}")
                        self._screencap_tested = False  # 新设备需重新测速
                        self._cleanup_netcat_server()
                        return True
                
                if not devices:
                    raise DeviceNotFoundError()
                else:
                    raise ADBConnectionError(message="No connected devices available")
                    
        except Exception as e:
            self.logger.error(f"Failed to connect device: {e}")
            raise
    
    def connect_wifi_device(self, address: str) -> bool:
        """
        连接WiFi设备
        
        Args:
            address: 设备地址 (IP:端口)
        
        Returns:
            是否连接成功
        """
        try:
            self.logger.info(f"Connecting to WiFi device: {address}")
            output = self.execute_command(f"connect {address}", use_device=False)
            
            if "connected" in output.lower() or "already" in output.lower():
                self.logger.info(f"WiFi device connected: {address}")
                return True
            else:
                self.logger.error(f"Failed to connect WiFi device: {output}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to connect WiFi device: {e}")
            return False
    
    def disconnect_device(self) -> None:
        """断开设备连接"""
        if self.current_device:
            # 如果是无线连接，执行disconnect命令
            if self.current_device.is_wireless:
                try:
                    self.execute_command(f"disconnect {self.current_device.device_id}", 
                                       use_device=False)
                    self.logger.info(f"Disconnected from wireless device: {self.current_device}")
                except Exception as e:
                    self.logger.warning(f"Failed to disconnect: {e}")
            
            self.current_device = None
            self.logger.info("Device disconnected")
    
    def bring_app_to_foreground(self, package_name: str) -> bool:
        """
        将应用切换到前台
        
        Args:
            package_name: 应用包名
        
        Returns:
            是否切换成功
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        try:
            # 方法1：先尝试使用am start-activity命令（更可靠）
            # 获取当前运行的activity
            cmd = f"shell dumpsys activity activities | grep -E 'mFocusedActivity|mResumedActivity'"
            current_activity = self.execute_command(cmd)
            
            # 尝试启动应用的主activity
            cmd = f"shell am start -n {package_name}/.MainActivity"
            output = self.execute_command(cmd)
            
            if "Error" not in output:
                self.logger.info(f"App brought to foreground using am start: {package_name}")
                return True
            
            # 方法2：使用monkey命令作为备选
            cmd = f"shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1"
            output = self.execute_command(cmd)
            
            if "Events injected: 1" in output:
                self.logger.info(f"App brought to foreground using monkey: {package_name}")
                return True
            
            # 方法3：尝试使用am命令切换到应用最近的任务
            cmd = f"shell am start --activity-brought-to-front -n {package_name}/."
            output = self.execute_command(cmd)
            
            if "Error" not in output:
                self.logger.info(f"App brought to foreground using am start --activity-brought-to-front: {package_name}")
                return True
            
            # 方法4：最后尝试使用input keyevent切换应用
            # 先按HOME键，再启动应用
            self.execute_command("shell input keyevent KEYCODE_HOME")
            time.sleep(0.5)
            cmd = f"shell monkey -p {package_name} 1"
            output = self.execute_command(cmd)
            
            if output and "Error" not in output:
                self.logger.info(f"App brought to foreground using HOME+monkey: {package_name}")
                return True
            
            self.logger.warning(f"All methods failed to bring app to foreground: {package_name}")
            return False
                
        except Exception as e:
            self.logger.error(f"Failed to bring app to foreground: {e}")
            return False
    
    def start_app(self, package_name: str, activity_name: Optional[str] = None) -> bool:
        """
        启动应用（如果应用已运行则切换到前台）
        
        Args:
            package_name: 应用包名
            activity_name: 活动名称
        
        Returns:
            是否启动成功
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        try:
            # 先检查应用是否已经在运行
            if self.is_app_running(package_name):
                self.logger.info(f"App {package_name} is already running, bringing to foreground...")
                return self.bring_app_to_foreground(package_name)
            
            # 构建启动命令
            if activity_name:
                if not activity_name.startswith('.'):
                    component = f"{package_name}/{activity_name}"
                else:
                    component = f"{package_name}/{package_name}{activity_name}"
            else:
                # 使用monkey命令启动
                cmd = f"shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1"
                output = self.execute_command(cmd)
                return "Events injected: 1" in output
            
            # 使用am start命令启动
            cmd = f"shell am start -n {component}"
            output = self.execute_command(cmd)
            
            # 检查是否启动成功
            if "Error" in output or "Exception" in output:
                self.logger.error(f"Failed to start app: {output}")
                return False
            
            self.logger.info(f"App started: {package_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start app: {e}")
            return False
    
    def stop_app(self, package_name: str) -> bool:
        """
        停止应用
        
        Args:
            package_name: 应用包名
        
        Returns:
            是否停止成功
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        try:
            cmd = f"shell am force-stop {package_name}"
            self.execute_command(cmd)
            self.logger.info(f"App stopped: {package_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop app: {e}")
            return False
    
    def is_app_running(self, package_name: str) -> bool:
        """
        检查应用是否在运行（检查进程是否存在）
        
        Args:
            package_name: 应用包名
        
        Returns:
            是否在运行
        """
        if not self.current_device:
            return False
        
        # 使用缓存机制，避免频繁调用
        cache_key = f"app_running_{package_name}"
        cache_time = 5  # 缓存5秒
        
        # 检查缓存
        if hasattr(self, '_app_status_cache'):
            cached = self._app_status_cache.get(cache_key)
            if cached and (time.time() - cached['time']) < cache_time:
                return cached['status']
        else:
            self._app_status_cache = {}
        
        # 默认返回False
        result = False
        
        try:
            # 方法1：检查进程是否存在（更可靠）
            cmd = f"shell ps | grep {package_name}"
            output = self.execute_command(cmd, timeout=3)
            
            # 如果输出中包含包名，说明进程存在
            if package_name in output:
                self.logger.debug(f"Found {package_name} process running")
                result = True
            else:
                # 方法2：通过dumpsys检查应用状态
                cmd = f"shell dumpsys activity activities | grep {package_name}"
                output = self.execute_command(cmd, timeout=3)
                
                if package_name in output:
                    self.logger.debug(f"Found {package_name} in activity stack")
                    result = True
                else:
                    # 方法3：检查运行的包列表
                    cmd = "shell pm list packages -3"  # 列出第三方应用
                    output = self.execute_command(cmd, timeout=3)
                    
                    # 检查包是否安装
                    if f"package:{package_name}" in output:
                        # 包已安装，再检查是否有活动的任务
                        cmd = f"shell dumpsys activity recents | grep {package_name}"
                        output = self.execute_command(cmd, timeout=3)
                        if package_name in output:
                            self.logger.debug(f"Found {package_name} in recent tasks")
                            result = True
                    
        except Exception as e:
            # 忽略错误，使用缓存或返回False
            self.logger.debug(f"Check app status failed (will use cache or False): {e}")
            if cache_key in self._app_status_cache:
                return self._app_status_cache[cache_key]['status']
        
        # 更新缓存
        self._app_status_cache[cache_key] = {
            'status': result,
            'time': time.time()
        }
        
        return result
    
    def tap(self, x: int, y: int) -> None:
        """
        点击坐标
        
        Args:
            x: X坐标
            y: Y坐标
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        cmd = f"shell input tap {x} {y}"
        self.execute_command(cmd)
        self.logger.debug(f"Tapped at ({x}, {y})")
    
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 500) -> None:
        """
        滑动操作
        
        Args:
            x1: 起始X坐标
            y1: 起始Y坐标
            x2: 结束X坐标
            y2: 结束Y坐标
            duration: 滑动持续时间（毫秒）
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        cmd = f"shell input swipe {x1} {y1} {x2} {y2} {duration}"
        self.execute_command(cmd)
        self.logger.debug(f"Swiped from ({x1}, {y1}) to ({x2}, {y2})")
    
    def input_text(self, text: str) -> None:
        """
        输入文本
        
        Args:
            text: 要输入的文本
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        # 转义特殊字符
        text = text.replace(' ', '%s')
        text = text.replace('&', '\\&')
        text = text.replace('<', '\\<')
        text = text.replace('>', '\\>')
        text = text.replace('|', '\\|')
        text = text.replace(';', '\\;')
        text = text.replace('*', '\\*')
        text = text.replace('~', '\\~')
        text = text.replace('"', '\\"')
        text = text.replace("'", "\\'")
        
        cmd = f'shell input text "{text}"'
        self.execute_command(cmd)
        self.logger.debug(f"Input text: {text[:20]}...")
    
    def press_key(self, key_code: str) -> None:
        """
        按键操作
        
        Args:
            key_code: 按键代码（如：KEYCODE_HOME, KEYCODE_BACK）
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        # 如果没有KEYCODE_前缀，添加它
        if not key_code.startswith('KEYCODE_'):
            key_code = f'KEYCODE_{key_code.upper()}'
        
        cmd = f"shell input keyevent {key_code}"
        self.execute_command(cmd)
        self.logger.debug(f"Pressed key: {key_code}")
    
    def screenshot(self, cache_ms: int = 0) -> Image.Image:
        """
        截取屏幕，自动选择最快的截图方式

        Args:
            cache_ms: 缓存有效期（毫秒），在此时间内返回缓存截图，0表示不缓存

        Returns:
            PIL Image对象
        """
        if not self.current_device:
            raise DeviceNotFoundError()

        # 检查PIL缓存
        if cache_ms > 0 and self._screenshot_cache is not None:
            elapsed_ms = (time.time() - self._screenshot_cache_time) * 1000
            if elapsed_ms < cache_ms:
                return self._screenshot_cache

        # 检查numpy缓存是否可以复用
        if cache_ms > 0 and self._numpy_cache is not None:
            elapsed_ms = (time.time() - self._numpy_cache_time) * 1000
            if elapsed_ms < cache_ms:
                rgb = cv2.cvtColor(self._numpy_cache, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(rgb, 'RGB')
                self._screenshot_cache = image
                self._screenshot_cache_time = time.time()
                return image

        try:
            # 使用numpy路径截图，然后转PIL
            bgr = self.screenshot_numpy(cache_ms=0)

            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb, 'RGB')

            # 当 quality < 100 时做 JPEG 压缩
            if self.config.screenshot_quality < 100:
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=self.config.screenshot_quality)
                output.seek(0)
                image = Image.open(output)

            # 更新PIL缓存
            self._screenshot_cache = image
            self._screenshot_cache_time = time.time()

            return image

        except Exception as e:
            self.logger.error(f"Failed to capture screenshot: {e}")
            raise ADBCommandError("screenshot", str(e))

    def _adb_exec_binary(self, cmd: str, timeout: int = 10) -> bytes:
        """
        执行ADB命令并返回二进制输出

        Args:
            cmd: ADB命令
            timeout: 超时时间

        Returns:
            二进制输出
        """
        cmd_parts = [self._adb_path]
        if self.current_device:
            cmd_parts.extend(["-s", self.current_device.device_id])
        cmd_parts.extend(cmd.split())

        result = subprocess.run(
            cmd_parts,
            capture_output=True,
            timeout=timeout
        )

        if result.returncode != 0:
            raise ADBCommandError(cmd, "Command failed")

        return result.stdout

    def screenshot_numpy(self, cache_ms: int = 0) -> np.ndarray:
        """
        截取屏幕，返回numpy BGR数组，供高帧率显示使用

        Args:
            cache_ms: 缓存有效期（毫秒），0表示不缓存

        Returns:
            numpy BGR ndarray (H, W, 3)
        """
        if not self.current_device:
            raise DeviceNotFoundError()

        # 检查numpy缓存
        if cache_ms > 0 and self._numpy_cache is not None:
            elapsed_ms = (time.time() - self._numpy_cache_time) * 1000
            if elapsed_ms < cache_ms:
                return self._numpy_cache

        # 首次调用时执行速度测试
        if not self._screencap_tested:
            self._screencap_speed_test()

        try:
            arr = self._screencap_to_numpy()

            # 更新numpy缓存
            self._numpy_cache = arr
            self._numpy_cache_time = time.time()
            # 同步清除PIL缓存（过期）
            self._screenshot_cache = None

            return arr

        except Exception as e:
            self.logger.error(f"Failed to capture screenshot (numpy): {e}")
            raise ADBCommandError("screenshot_numpy", str(e))

    def _screencap_to_numpy(self) -> np.ndarray:
        """
        使用当前最快方法截图并返回numpy BGR数组
        """
        if self._screencap_method == 'raw_netcat':
            try:
                return self._screenshot_raw_netcat_numpy()
            except Exception:
                self.logger.warning("raw_netcat failed at runtime, falling back to raw_gzip")
                self._screencap_method = 'raw_gzip'

        if self._screencap_method == 'raw_gzip':
            try:
                return self._screenshot_raw_gzip_numpy()
            except Exception:
                self.logger.warning("raw_gzip failed at runtime, falling back to encode")
                self._screencap_method = 'encode'

        return self._screenshot_encode_numpy()

    def _screenshot_encode_numpy(self) -> np.ndarray:
        """PNG截图直接返回numpy BGR"""
        data = self._adb_exec_binary("exec-out screencap -p")
        arr = np.frombuffer(data, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            raise ADBCommandError("screencap -p", "Failed to decode PNG")
        return bgr

    def _screenshot_raw_gzip_numpy(self) -> np.ndarray:
        """raw+gzip截图直接返回numpy BGR"""
        cmd_parts = [self._adb_path]
        if self.current_device:
            cmd_parts.extend(["-s", self.current_device.device_id])
        cmd_parts.extend(["exec-out", "sh", "-c", "screencap | gzip -1"])

        result = subprocess.run(cmd_parts, capture_output=True, timeout=10)

        if result.returncode != 0:
            raise ADBCommandError("screencap|gzip", "Command failed")

        data = result.stdout
        if len(data) < 2:
            raise ADBCommandError("screencap|gzip", "Empty response")

        if data[:2] == b'\x1f\x8b':
            data = gzip.decompress(data)

        return self._parse_raw_screencap_numpy(data)

    def _screenshot_raw_netcat_numpy(self) -> np.ndarray:
        """
        RawByNetcat截图，参考MaaFramework的RawByNetcat策略。
        设备端执行 screencap | nc HOST PORT，本机通过TCP socket接收原始帧数据。
        避免gzip压缩开销和exec-out协议开销。
        """
        if not self._netcat_server:
            self._init_netcat_server()

        port = self._netcat_port
        address = self._netcat_address

        # 在设备上执行 screencap | nc
        cmd_parts = [self._adb_path]
        if self.current_device:
            cmd_parts.extend(["-s", self.current_device.device_id])
        cmd_parts.extend([
            "exec-out", "sh", "-c",
            f"screencap | nc -w 3 {address} {port}"
        ])

        # 启动设备端命令（不阻塞等待）
        proc = subprocess.Popen(
            cmd_parts,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        try:
            # 接受来自设备的TCP连接
            self._netcat_server.settimeout(3.0)
            conn, _ = self._netcat_server.accept()
            try:
                conn.settimeout(2.0)
                chunks = []
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                data = b''.join(chunks)
            finally:
                conn.close()
        except socket.timeout:
            proc.kill()
            raise ADBCommandError("screencap|nc", "Netcat accept/read timeout")
        finally:
            proc.wait(timeout=3)

        if len(data) < 16:
            raise ADBCommandError("screencap|nc", "Data too short")

        return self._parse_raw_screencap_numpy(data)

    def _init_netcat_server(self) -> None:
        """初始化本地TCP服务端用于netcat接收"""
        # 获取本机对设备可见的IP地址
        self._netcat_address = self._get_host_address_for_device()

        # 绑定随机端口
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('0.0.0.0', 0))
        srv.listen(1)
        self._netcat_port = srv.getsockname()[1]
        self._netcat_server = srv
        self.logger.info(f"Netcat server listening on 0.0.0.0:{self._netcat_port}")

    def _get_host_address_for_device(self) -> str:
        """
        获取本机对ADB设备可见的IP地址。
        参考MaaFramework: cat /proc/net/arp | grep : 获取ARP表中的网关IP
        """
        try:
            cmd_parts = [self._adb_path]
            if self.current_device:
                cmd_parts.extend(["-s", self.current_device.device_id])
            cmd_parts.extend(["shell", "cat", "/proc/net/arp"])

            result = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if ':' in line:
                        parts = line.split()
                        if parts:
                            ip = parts[0]
                            if re.match(r'\d+\.\d+\.\d+\.\d+', ip):
                                self.logger.info(f"Host address from ARP: {ip}")
                                return ip
        except Exception as e:
            self.logger.debug(f"Failed to get address from ARP: {e}")

        # USB连接时使用 adb forward 方案作为回退
        return "127.0.0.1"

    def _cleanup_netcat_server(self):
        """关闭netcat服务端"""
        if self._netcat_server:
            try:
                self._netcat_server.close()
            except Exception:
                pass
            self._netcat_server = None
            self._netcat_port = 0

    def _parse_raw_screencap_numpy(self, data: bytes) -> np.ndarray:
        """
        解析原始screencap帧缓冲区数据，返回numpy BGR数组。
        参考MaaFramework ScreencapHelper::decode_raw
        """
        if len(data) < 12:
            raise ADBCommandError("screencap", "Raw data too short")

        width = struct.unpack_from('<I', data, 0)[0]
        height = struct.unpack_from('<I', data, 4)[0]

        if width == 0 or height == 0 or width > 8192 or height > 8192:
            raise ADBCommandError("screencap", f"Invalid dimensions: {width}x{height}")

        expected_pixels = width * height * 4
        # 参考MaaFramework: header_size = len(data) - expected_pixels
        header_size = len(data) - expected_pixels

        if header_size < 8 or header_size > 16:
            raise ADBCommandError("screencap",
                f"Invalid data size: {len(data)} for {width}x{height}, header={header_size}")

        pixel_data = data[header_size:]

        # 直接从bytes创建RGBA数组，然后转BGR
        arr = np.frombuffer(pixel_data, dtype=np.uint8).reshape(height, width, 4)

        # 检查alpha通道是否有效（参考MaaFramework检查最后一个像素的alpha）
        if arr[-1, -1, 3] != 255:
            raise ADBCommandError("screencap", "Invalid alpha channel")

        # RGBA -> BGR (OpenCV格式)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        return bgr

    def _screencap_speed_test(self) -> None:
        """
        测试各截图方法的速度，自动选择最快的方法。
        参考MaaFramework ScreencapAgent::speed_test
        """
        self._screencap_tested = True
        methods = {}

        # 测试 raw_netcat
        try:
            # netcat需要先warmup（第一次建连慢），丢弃第一次结果
            self._screenshot_raw_netcat_numpy()
            start = time.perf_counter()
            self._screenshot_raw_netcat_numpy()
            elapsed = time.perf_counter() - start
            methods['raw_netcat'] = elapsed
            self.logger.info(f"Screencap speed test - raw_netcat: {elapsed*1000:.0f}ms")
        except Exception as e:
            self.logger.debug(f"Screencap speed test - raw_netcat failed: {e}")
            self._cleanup_netcat_server()

        # 测试 raw_gzip
        try:
            start = time.perf_counter()
            self._screenshot_raw_gzip_numpy()
            elapsed = time.perf_counter() - start
            methods['raw_gzip'] = elapsed
            self.logger.info(f"Screencap speed test - raw_gzip: {elapsed*1000:.0f}ms")
        except Exception as e:
            self.logger.debug(f"Screencap speed test - raw_gzip failed: {e}")

        # 测试 encode (PNG)
        try:
            start = time.perf_counter()
            self._screenshot_encode_numpy()
            elapsed = time.perf_counter() - start
            methods['encode'] = elapsed
            self.logger.info(f"Screencap speed test - encode: {elapsed*1000:.0f}ms")
        except Exception as e:
            self.logger.debug(f"Screencap speed test - encode failed: {e}")

        if not methods:
            self.logger.error("All screencap methods failed")
            self._screencap_method = 'encode'
            return

        # 选择最快的方法
        best = min(methods, key=methods.get)
        self._screencap_method = best
        self.logger.info(f"Screencap method selected: {best} ({methods[best]*1000:.0f}ms)")
    
    def unlock_screen(self) -> bool:
        """
        解锁屏幕
        
        Returns:
            是否解锁成功
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        try:
            # 检查屏幕状态（不使用grep）
            cmd = "shell dumpsys power"
            output = self.execute_command(cmd)
            
            # 在Python中查找mWakefulness
            is_asleep = False
            for line in output.split('\n'):
                if 'mWakefulness' in line:
                    if 'Asleep' in line or 'Dozing' in line:
                        is_asleep = True
                        break
            
            # 如果屏幕关闭，先唤醒
            if is_asleep:
                self.press_key('KEYCODE_POWER')
                time.sleep(1)
            
            # 检查是否有锁屏（不使用grep）
            cmd = "shell dumpsys window"
            output = self.execute_command(cmd)
            
            # 在Python中查找mDreamingLockscreen
            has_lockscreen = False
            for line in output.split('\n'):
                if 'mDreamingLockscreen=true' in line:
                    has_lockscreen = True
                    break
            
            if has_lockscreen:
                # 尝试滑动解锁
                width, height = self.current_device.screen_resolution
                if width > 0 and height > 0:
                    # 从下往上滑动
                    self.swipe(width // 2, height * 3 // 4, 
                             width // 2, height // 4, 300)
                else:
                    # 使用默认分辨率
                    self.swipe(540, 1600, 540, 800, 300)
                
                time.sleep(1)
                self.logger.info("Screen unlocked")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to unlock screen: {e}")
            return False
    
    def get_current_activity(self) -> Optional[str]:
        """
        获取当前活动
        
        Returns:
            当前活动名称
        """
        if not self.current_device:
            return None
        
        try:
            # 获取所有活动信息（不使用grep）
            cmd = "shell dumpsys activity activities"
            output = self.execute_command(cmd)
            
            # 在Python中查找mResumedActivity
            for line in output.split('\n'):
                if 'mResumedActivity' in line:
                    # 解析活动名称
                    match = re.search(r'([a-zA-Z0-9_.]+)/([a-zA-Z0-9_.]+)', line)
                    if match:
                        return f"{match.group(1)}/{match.group(2)}"
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get current activity: {e}")
            return None
    
    def install_app(self, apk_path: str) -> bool:
        """
        安装应用
        
        Args:
            apk_path: APK文件路径
        
        Returns:
            是否安装成功
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        if not os.path.exists(apk_path):
            self.logger.error(f"APK file not found: {apk_path}")
            return False
        
        try:
            cmd = f"install -r \"{apk_path}\""
            output = self.execute_command(cmd, timeout=120)
            
            if "Success" in output:
                self.logger.info(f"App installed: {apk_path}")
                return True
            else:
                self.logger.error(f"Failed to install app: {output}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to install app: {e}")
            return False
    
    def uninstall_app(self, package_name: str) -> bool:
        """
        卸载应用
        
        Args:
            package_name: 应用包名
        
        Returns:
            是否卸载成功
        """
        if not self.current_device:
            raise DeviceNotFoundError()
        
        try:
            cmd = f"uninstall {package_name}"
            output = self.execute_command(cmd)
            
            if "Success" in output:
                self.logger.info(f"App uninstalled: {package_name}")
                return True
            else:
                self.logger.error(f"Failed to uninstall app: {output}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to uninstall app: {e}")
            return False
    
    def is_connected(self) -> bool:
        """
        检查是否有设备连接
        
        Returns:
            是否有设备连接
        """
        return self.current_device is not None and self.current_device.status == DeviceStatus.ONLINE
    
    def select_device(self, device_id: str) -> bool:
        """
        选择设备
        
        Args:
            device_id: 设备ID
        
        Returns:
            是否选择成功
        """
        try:
            devices = self.get_devices()
            for device in devices:
                if device.device_id == device_id and device.status == DeviceStatus.ONLINE:
                    self.current_device = device
                    self._screencap_tested = False  # 新设备需重新测速
                    self._cleanup_netcat_server()
                    self.logger.info(f"Selected device: {device_id}")
                    return True
            
            self.logger.error(f"Device not found or not online: {device_id}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to select device {device_id}: {e}")
            return False
    
    def take_screenshot(self) -> Optional[Image.Image]:
        """
        截取屏幕截图
        
        Returns:
            PIL Image对象，失败时返回None
        """
        try:
            return self.screenshot()
        except Exception as e:
            self.logger.error(f"Failed to take screenshot: {e}")
            return None
    
    def wake_and_start_game(self, package_name: str = "com.lilithgame.igame.android.cn") -> bool:
        """
        唤醒设备并启动游戏
        
        Args:
            package_name: 游戏包名，默认为剑与远征启程
        
        Returns:
            是否成功启动游戏
        """
        if not self.current_device:
            self.logger.error("No device connected")
            return False
        
        try:
            self.logger.info("Starting wake and launch game process...")
            
            # 1. 唤醒设备屏幕
            self.logger.info("Waking up device...")
            if not self.unlock_screen():
                self.logger.warning("Failed to unlock screen, but continuing...")
            
            # 2. 等待一下确保屏幕完全唤醒
            time.sleep(2)
            
            # 3. 返回主屏幕
            self.logger.info("Going to home screen...")
            self.press_key('KEYCODE_HOME')
            time.sleep(1)
            
            # 4. 检查游戏是否已经在运行
            if self.is_app_running(package_name):
                self.logger.info(f"Game {package_name} is already running")
                # 如果游戏已经在运行，切换到前台
                current_activity = self.get_current_activity()
                if current_activity and package_name not in current_activity:
                    # 游戏在后台，需要切换到前台
                    self.logger.info("Bringing game to foreground...")
                    return self.start_app(package_name)
                return True
            
            # 5. 启动游戏
            self.logger.info(f"Starting game: {package_name}")
            if self.start_app(package_name):
                self.logger.info("Game started successfully")
                # 等待游戏启动
                time.sleep(5)
                return True
            else:
                self.logger.error("Failed to start game")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to wake and start game: {e}")
            return False
    
    def get_device_id(self) -> Optional[str]:
        """
        获取当前设备ID
        
        Returns:
            设备ID，无设备时返回None
        """
        return self.current_device.device_id if self.current_device else None