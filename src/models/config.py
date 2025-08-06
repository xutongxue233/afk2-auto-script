"""
配置数据模型
定义应用配置相关的数据结构
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
import json
import yaml
from pathlib import Path


@dataclass
class ADBConfig:
    """
    ADB配置
    
    Attributes:
        adb_path: ADB可执行文件路径
        device_id: 默认设备ID
        wireless_address: 无线连接地址 (IP:端口)
        screenshot_quality: 截图质量 (1-100)
        command_timeout: 命令超时时间（秒）
        auto_connect: 启动时自动连接设备
        reconnect_attempts: 重连尝试次数
    """
    adb_path: str = "adb"
    device_id: Optional[str] = None
    wireless_address: Optional[str] = None
    screenshot_quality: int = 90
    command_timeout: int = 30
    auto_connect: bool = True
    reconnect_attempts: int = 3
    
    def validate(self) -> bool:
        """验证配置的有效性"""
        if self.screenshot_quality < 1 or self.screenshot_quality > 100:
            raise ValueError("截图质量必须在1-100之间")
        if self.command_timeout < 1:
            raise ValueError("命令超时时间必须大于0")
        if self.reconnect_attempts < 0:
            raise ValueError("重连尝试次数不能为负数")
        return True


@dataclass
class GameConfig:
    """
    游戏配置
    
    Attributes:
        package_name: 游戏包名
        activity_name: 主活动名
        startup_wait_time: 启动等待时间（秒）
        operation_delay: 操作延迟（秒）
        loading_timeout: 加载超时时间（秒）
        retry_on_failure: 失败时是否重试
        max_retry_count: 最大重试次数
    """
    package_name: str = "com.lilith.odyssey.cn"
    activity_name: str = ".MainActivity"
    startup_wait_time: int = 10
    operation_delay: float = 0.5
    loading_timeout: int = 30
    retry_on_failure: bool = True
    max_retry_count: int = 3
    
    @property
    def full_activity_name(self) -> str:
        """获取完整的活动名称"""
        if self.activity_name.startswith('.'):
            return f"{self.package_name}{self.activity_name}"
        return self.activity_name
    
    def validate(self) -> bool:
        """验证配置的有效性"""
        if not self.package_name:
            raise ValueError("游戏包名不能为空")
        if self.startup_wait_time < 0:
            raise ValueError("启动等待时间不能为负数")
        if self.operation_delay < 0:
            raise ValueError("操作延迟不能为负数")
        if self.loading_timeout < 1:
            raise ValueError("加载超时时间必须大于0")
        if self.max_retry_count < 0:
            raise ValueError("最大重试次数不能为负数")
        return True


@dataclass
class RecognitionConfig:
    """
    识别配置
    
    Attributes:
        image_threshold: 图像匹配阈值 (0-1)
        ocr_language: OCR识别语言
        ocr_engine: OCR引擎 (tesseract/paddleocr)
        template_matching_method: 模板匹配方法
        enable_debug_output: 启用调试输出
    """
    image_threshold: float = 0.8
    ocr_language: str = "chi_sim"
    ocr_engine: str = "paddleocr"
    template_matching_method: str = "TM_CCOEFF_NORMED"
    enable_debug_output: bool = False
    
    def validate(self) -> bool:
        """验证配置的有效性"""
        if self.image_threshold < 0 or self.image_threshold > 1:
            raise ValueError("图像匹配阈值必须在0-1之间")
        if self.ocr_engine not in ["tesseract", "paddleocr"]:
            raise ValueError("OCR引擎必须是tesseract或paddleocr")
        return True


@dataclass
class UIConfig:
    """
    界面配置
    
    Attributes:
        theme: 界面主题
        language: 界面语言
        window_size: 窗口大小 (宽, 高)
        show_console_log: 显示控制台日志
        auto_save_config: 自动保存配置
        confirm_on_exit: 退出时确认
    """
    theme: str = "default"
    language: str = "zh_CN"
    window_size: tuple = (1200, 800)
    show_console_log: bool = True
    auto_save_config: bool = True
    confirm_on_exit: bool = True
    
    def validate(self) -> bool:
        """验证配置的有效性"""
        if len(self.window_size) != 2:
            raise ValueError("窗口大小必须是(宽, 高)元组")
        if self.window_size[0] < 800 or self.window_size[1] < 600:
            raise ValueError("窗口大小不能小于800x600")
        return True


@dataclass
class AppConfig:
    """
    应用配置主类
    
    Attributes:
        adb: ADB配置
        game: 游戏配置
        recognition: 识别配置
        ui: 界面配置
        log_level: 日志级别
        auto_save: 自动保存
        config_version: 配置版本
    """
    adb: ADBConfig = field(default_factory=ADBConfig)
    game: GameConfig = field(default_factory=GameConfig)
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    log_level: str = "INFO"
    auto_save: bool = True
    config_version: str = "1.0.0"
    
    def validate(self) -> bool:
        """验证所有配置的有效性"""
        self.adb.validate()
        self.game.validate()
        self.recognition.validate()
        self.ui.validate()
        
        if self.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError("日志级别必须是DEBUG/INFO/WARNING/ERROR/CRITICAL之一")
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        # 特殊处理元组类型
        data['ui']['window_size'] = list(data['ui']['window_size'])
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """从字典创建配置实例"""
        # 复制数据以避免修改原始数据
        data = data.copy()
        
        # 移除元数据字段（不是配置的一部分）
        data.pop('_metadata', None)
        
        # 特殊处理元组类型
        if 'ui' in data and 'window_size' in data['ui']:
            data['ui']['window_size'] = tuple(data['ui']['window_size'])
        
        # 创建子配置对象
        if 'adb' in data:
            data['adb'] = ADBConfig(**data['adb'])
        if 'game' in data:
            data['game'] = GameConfig(**data['game'])
        if 'recognition' in data:
            data['recognition'] = RecognitionConfig(**data['recognition'])
        if 'ui' in data:
            data['ui'] = UIConfig(**data['ui'])
        
        return cls(**data)
    
    def save_to_file(self, file_path: Path, format: str = 'yaml') -> None:
        """
        保存配置到文件
        
        Args:
            file_path: 文件路径
            format: 文件格式 (yaml/json)
        """
        data = self.to_dict()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            if format == 'yaml':
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            elif format == 'json':
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"不支持的格式: {format}")
    
    @classmethod
    def load_from_file(cls, file_path: Path) -> 'AppConfig':
        """
        从文件加载配置
        
        Args:
            file_path: 文件路径
        
        Returns:
            AppConfig实例
        """
        if not file_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            if file_path.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif file_path.suffix == '.json':
                data = json.load(f)
            else:
                raise ValueError(f"不支持的文件格式: {file_path.suffix}")
        
        return cls.from_dict(data)
    
    @classmethod
    def get_default(cls) -> 'AppConfig':
        """获取默认配置"""
        return cls()