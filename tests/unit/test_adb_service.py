"""
ADB服务单元测试
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from PIL import Image
import io

from src.services.adb_service import ADBService
from src.models.device import Device, DeviceStatus, ConnectionType
from src.models.config import ADBConfig
from src.utils.exceptions import (
    ADBConnectionError, ADBCommandError, DeviceNotFoundError,
    DeviceUnauthorizedError, DeviceOfflineError
)


@pytest.fixture
def adb_config():
    """创建测试用的ADB配置"""
    return ADBConfig(
        adb_path="adb",
        screenshot_quality=90,
        command_timeout=30
    )


@pytest.fixture
def adb_service(adb_config):
    """创建ADB服务实例"""
    with patch.object(ADBService, '_check_adb_available', return_value=True):
        service = ADBService(adb_config)
        return service


@pytest.fixture
def mock_device():
    """创建模拟设备"""
    device = Device(
        device_id="emulator-5554",
        device_name="TestDevice",
        device_model="Pixel",
        android_version="11",
        screen_resolution=(1080, 1920),
        connection_type=ConnectionType.USB,
        status=DeviceStatus.CONNECTED
    )
    return device


class TestADBService:
    """ADB服务测试类"""
    
    def test_init(self, adb_config):
        """测试初始化"""
        with patch.object(ADBService, '_check_adb_available', return_value=True):
            service = ADBService(adb_config)
            assert service.config == adb_config
            assert service.current_device is None
    
    def test_find_adb_path(self, adb_service):
        """测试查找ADB路径"""
        # 测试配置中的路径
        with patch('os.path.exists', return_value=True):
            adb_service.config.adb_path = "/custom/path/adb"
            path = adb_service._find_adb_path()
            assert path == "/custom/path/adb"
        
        # 测试默认adb命令
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            adb_service.config.adb_path = ""
            path = adb_service._find_adb_path()
            assert path == "adb"
    
    def test_execute_command_success(self, adb_service, mock_device):
        """测试执行命令成功"""
        adb_service.current_device = mock_device
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Success"
            mock_run.return_value.stderr = ""
            
            result = adb_service.execute_command("devices")
            assert result == "Success"
            
            # 验证命令构建
            call_args = mock_run.call_args[0][0]
            assert "adb" in call_args[0]
            assert "-s" in call_args
            assert mock_device.device_id in call_args
    
    def test_execute_command_failure(self, adb_service):
        """测试执行命令失败"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "Error"
            
            with pytest.raises(ADBCommandError):
                adb_service.execute_command("invalid")
    
    def test_get_devices(self, adb_service):
        """测试获取设备列表"""
        mock_output = """List of devices attached
emulator-5554   device product:sdk_gphone_x86 model:Android_SDK_built device:generic_x86
192.168.1.100:5555  device
offline_device  offline
unauthorized_device unauthorized"""
        
        with patch.object(adb_service, 'execute_command', return_value=mock_output):
            with patch.object(adb_service, '_get_device_details'):
                devices = adb_service.get_devices()
                
                assert len(devices) == 4
                assert devices[0].device_id == "emulator-5554"
                assert devices[0].status == DeviceStatus.CONNECTED
                assert devices[0].connection_type == ConnectionType.USB
                
                assert devices[1].device_id == "192.168.1.100:5555"
                assert devices[1].connection_type == ConnectionType.WIFI
                
                assert devices[2].status == DeviceStatus.OFFLINE
                assert devices[3].status == DeviceStatus.UNAUTHORIZED
    
    def test_connect_device_by_id(self, adb_service, mock_device):
        """测试通过ID连接设备"""
        with patch.object(adb_service, 'get_devices', return_value=[mock_device]):
            result = adb_service.connect_device(mock_device.device_id)
            assert result is True
            assert adb_service.current_device == mock_device
    
    def test_connect_device_wireless(self, adb_service):
        """测试连接无线设备"""
        device_id = "192.168.1.100:5555"
        mock_device = Device(
            device_id=device_id,
            connection_type=ConnectionType.WIFI,
            status=DeviceStatus.CONNECTED
        )
        
        with patch.object(adb_service, 'execute_command', return_value="connected to 192.168.1.100:5555"):
            with patch.object(adb_service, 'get_devices', return_value=[mock_device]):
                result = adb_service.connect_device(device_id)
                assert result is True
                assert adb_service.current_device == mock_device
    
    def test_connect_device_not_found(self, adb_service):
        """测试连接不存在的设备"""
        with patch.object(adb_service, 'get_devices', return_value=[]):
            with pytest.raises(DeviceNotFoundError):
                adb_service.connect_device("nonexistent")
    
    def test_connect_device_unauthorized(self, adb_service):
        """测试连接未授权设备"""
        mock_device = Device(
            device_id="device1",
            status=DeviceStatus.UNAUTHORIZED
        )
        
        with patch.object(adb_service, 'get_devices', return_value=[mock_device]):
            with pytest.raises(DeviceUnauthorizedError):
                adb_service.connect_device("device1")
    
    def test_disconnect_device(self, adb_service, mock_device):
        """测试断开设备连接"""
        adb_service.current_device = mock_device
        adb_service.disconnect_device()
        assert adb_service.current_device is None
    
    def test_start_app(self, adb_service, mock_device):
        """测试启动应用"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command', return_value="Starting: Intent"):
            result = adb_service.start_app("com.example.app", ".MainActivity")
            assert result is True
    
    def test_start_app_with_monkey(self, adb_service, mock_device):
        """测试使用monkey启动应用"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command', return_value="Events injected: 1"):
            result = adb_service.start_app("com.example.app")
            assert result is True
    
    def test_stop_app(self, adb_service, mock_device):
        """测试停止应用"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command', return_value=""):
            result = adb_service.stop_app("com.example.app")
            assert result is True
    
    def test_is_app_running(self, adb_service, mock_device):
        """测试检查应用是否运行"""
        adb_service.current_device = mock_device
        
        # 测试应用正在运行
        with patch.object(adb_service, 'execute_command', 
                         return_value="mResumedActivity: com.example.app/.MainActivity"):
            assert adb_service.is_app_running("com.example.app") is True
        
        # 测试应用未运行
        with patch.object(adb_service, 'execute_command', return_value=""):
            assert adb_service.is_app_running("com.example.app") is False
    
    def test_tap(self, adb_service, mock_device):
        """测试点击操作"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command') as mock_exec:
            adb_service.tap(100, 200)
            mock_exec.assert_called_with("shell input tap 100 200")
    
    def test_swipe(self, adb_service, mock_device):
        """测试滑动操作"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command') as mock_exec:
            adb_service.swipe(100, 200, 300, 400, 500)
            mock_exec.assert_called_with("shell input swipe 100 200 300 400 500")
    
    def test_input_text(self, adb_service, mock_device):
        """测试输入文本"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command') as mock_exec:
            adb_service.input_text("Hello World")
            # 验证空格被转义
            assert mock_exec.called
            call_args = mock_exec.call_args[0][0]
            assert "Hello%sWorld" in call_args
    
    def test_press_key(self, adb_service, mock_device):
        """测试按键操作"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command') as mock_exec:
            # 测试带前缀的按键
            adb_service.press_key("KEYCODE_HOME")
            mock_exec.assert_called_with("shell input keyevent KEYCODE_HOME")
            
            # 测试不带前缀的按键
            adb_service.press_key("BACK")
            mock_exec.assert_called_with("shell input keyevent KEYCODE_BACK")
    
    def test_screenshot(self, adb_service, mock_device):
        """测试截图功能"""
        adb_service.current_device = mock_device
        
        # 创建模拟的图片数据
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = img_bytes.read()
            
            result = adb_service.screenshot()
            assert isinstance(result, Image.Image)
    
    def test_unlock_screen(self, adb_service, mock_device):
        """测试解锁屏幕"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command') as mock_exec:
            with patch.object(adb_service, 'press_key') as mock_press:
                with patch.object(adb_service, 'swipe') as mock_swipe:
                    # 模拟屏幕关闭状态
                    mock_exec.side_effect = [
                        "mWakefulness=Asleep",
                        "mDreamingLockscreen=true"
                    ]
                    
                    result = adb_service.unlock_screen()
                    assert result is True
                    mock_press.assert_called_with('KEYCODE_POWER')
                    mock_swipe.assert_called()
    
    def test_get_current_activity(self, adb_service, mock_device):
        """测试获取当前活动"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command',
                         return_value="mResumedActivity: com.example.app/.MainActivity"):
            activity = adb_service.get_current_activity()
            assert activity == "com.example.app/.MainActivity"
    
    def test_install_app(self, adb_service, mock_device):
        """测试安装应用"""
        adb_service.current_device = mock_device
        
        with patch('os.path.exists', return_value=True):
            with patch.object(adb_service, 'execute_command', return_value="Success"):
                result = adb_service.install_app("/path/to/app.apk")
                assert result is True
    
    def test_uninstall_app(self, adb_service, mock_device):
        """测试卸载应用"""
        adb_service.current_device = mock_device
        
        with patch.object(adb_service, 'execute_command', return_value="Success"):
            result = adb_service.uninstall_app("com.example.app")
            assert result is True
    
    def test_no_device_error(self, adb_service):
        """测试无设备时的错误"""
        adb_service.current_device = None
        
        with pytest.raises(DeviceNotFoundError):
            adb_service.tap(100, 200)
        
        with pytest.raises(DeviceNotFoundError):
            adb_service.screenshot()
        
        with pytest.raises(DeviceNotFoundError):
            adb_service.start_app("com.example.app")


class TestADBServiceIntegration:
    """ADB服务集成测试（需要真实设备）"""
    
    @pytest.mark.integration
    def test_real_device_connection(self):
        """测试真实设备连接"""
        service = ADBService()
        devices = service.get_devices()
        
        if devices:
            # 如果有设备，测试连接
            device = devices[0]
            if device.status == DeviceStatus.CONNECTED:
                result = service.connect_device(device.device_id)
                assert result is True
                assert service.current_device is not None
                
                # 测试截图
                screenshot = service.screenshot()
                assert screenshot is not None
                assert isinstance(screenshot, Image.Image)
                
                # 断开连接
                service.disconnect_device()
                assert service.current_device is None