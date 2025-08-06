"""
配置服务模块
提供配置的加载、保存、验证和管理功能
"""

import os
import json
import yaml
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Union
from datetime import datetime
import threading

from src.models.config import AppConfig, ADBConfig, GameConfig, RecognitionConfig, UIConfig
from src.services.log_service import LoggerMixin
from src.utils.exceptions import ConfigLoadError, ConfigSaveError, ConfigValidationError


class ConfigService(LoggerMixin):
    """
    配置服务类
    管理应用程序配置的加载、保存和验证
    """
    
    # 默认配置文件名
    DEFAULT_CONFIG_NAME = "config.yaml"
    DEFAULT_BACKUP_DIR = "config_backups"
    MAX_BACKUP_COUNT = 5
    
    # 单例模式
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """实现单例模式"""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化配置服务
        
        Args:
            config_dir: 配置文件目录，默认为项目根目录
        """
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        
        # 设置配置目录
        if config_dir is None:
            # 获取项目根目录
            self.config_dir = Path(__file__).parent.parent.parent
        else:
            self.config_dir = Path(config_dir)
        
        # 确保目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 备份目录
        self.backup_dir = self.config_dir / self.DEFAULT_BACKUP_DIR
        self.backup_dir.mkdir(exist_ok=True)
        
        # 配置文件路径
        self.config_file = self.config_dir / self.DEFAULT_CONFIG_NAME
        
        # 当前配置
        self._config: Optional[AppConfig] = None
        
        # 配置变更监听器
        self._listeners = []
        
        # 自动保存标志
        self._auto_save_enabled = True
        
        self.logger.info(f"ConfigService initialized with config dir: {self.config_dir}")
    
    @property
    def config(self) -> AppConfig:
        """
        获取当前配置
        
        Returns:
            当前配置对象
        """
        if self._config is None:
            self._config = self.load_config()
        return self._config
    
    @config.setter
    def config(self, value: AppConfig) -> None:
        """
        设置当前配置
        
        Args:
            value: 新的配置对象
        """
        old_config = self._config
        self._config = value
        
        # 触发配置变更事件
        self._notify_listeners(old_config, value)
        
        # 自动保存
        if self._auto_save_enabled and value.auto_save:
            self.save_config(value)
    
    def load_config(self, config_file: Optional[Path] = None) -> AppConfig:
        """
        加载配置文件
        
        Args:
            config_file: 配置文件路径，默认使用默认路径
        
        Returns:
            配置对象
        """
        if config_file is None:
            config_file = self.config_file
        else:
            config_file = Path(config_file)
        
        # 如果配置文件不存在，创建默认配置
        if not config_file.exists():
            self.logger.info(f"Config file not found, creating default config: {config_file}")
            default_config = AppConfig.get_default()
            self.save_config(default_config, config_file)
            return default_config
        
        try:
            # 根据文件扩展名选择加载方式
            if config_file.suffix in ['.yaml', '.yml']:
                config = self._load_yaml_config(config_file)
            elif config_file.suffix == '.json':
                config = self._load_json_config(config_file)
            else:
                raise ConfigLoadError(
                    str(config_file),
                    f"Unsupported config file format: {config_file.suffix}"
                )
            
            # 验证配置
            if not self.validate_config(config):
                raise ConfigLoadError(str(config_file), "Config validation failed")
            
            self.logger.info(f"Config loaded successfully from: {config_file}")
            self._config = config
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            if isinstance(e, ConfigLoadError):
                raise
            raise ConfigLoadError(str(config_file), str(e))
    
    def _load_yaml_config(self, config_file: Path) -> AppConfig:
        """
        加载YAML配置文件
        
        Args:
            config_file: YAML文件路径
        
        Returns:
            配置对象
        """
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data:
                return AppConfig.get_default()
            
            return AppConfig.from_dict(data)
            
        except yaml.YAMLError as e:
            raise ConfigLoadError(str(config_file), f"YAML parse error: {e}")
        except Exception as e:
            raise ConfigLoadError(str(config_file), f"Failed to load YAML: {e}")
    
    def _load_json_config(self, config_file: Path) -> AppConfig:
        """
        加载JSON配置文件
        
        Args:
            config_file: JSON文件路径
        
        Returns:
            配置对象
        """
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not data:
                return AppConfig.get_default()
            
            return AppConfig.from_dict(data)
            
        except json.JSONDecodeError as e:
            raise ConfigLoadError(str(config_file), f"JSON parse error: {e}")
        except Exception as e:
            raise ConfigLoadError(str(config_file), f"Failed to load JSON: {e}")
    
    def save_config(self, config: Optional[AppConfig] = None, 
                   config_file: Optional[Path] = None,
                   create_backup: bool = True) -> None:
        """
        保存配置到文件
        
        Args:
            config: 要保存的配置对象，默认使用当前配置
            config_file: 配置文件路径，默认使用默认路径
            create_backup: 是否创建备份
        """
        if config is None:
            config = self._config
            if config is None:
                config = AppConfig.get_default()
        
        if config_file is None:
            config_file = self.config_file
        else:
            config_file = Path(config_file)
        
        # 验证配置
        if not self.validate_config(config):
            raise ConfigSaveError(str(config_file), "Config validation failed")
        
        # 创建备份
        if create_backup and config_file.exists():
            self._create_backup(config_file)
        
        try:
            # 确保目录存在
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 根据文件扩展名选择保存方式
            if config_file.suffix in ['.yaml', '.yml']:
                self._save_yaml_config(config, config_file)
            elif config_file.suffix == '.json':
                self._save_json_config(config, config_file)
            else:
                # 默认使用YAML格式
                config_file = config_file.with_suffix('.yaml')
                self._save_yaml_config(config, config_file)
            
            self.logger.info(f"Config saved successfully to: {config_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            if isinstance(e, ConfigSaveError):
                raise
            raise ConfigSaveError(str(config_file), str(e))
    
    def _save_yaml_config(self, config: AppConfig, config_file: Path) -> None:
        """
        保存配置为YAML格式
        
        Args:
            config: 配置对象
            config_file: YAML文件路径
        """
        try:
            data = config.to_dict()
            
            # 添加元信息
            data['_metadata'] = {
                'version': config.config_version,
                'saved_at': datetime.now().isoformat(),
                'saved_by': 'AFK2AutoScript'
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, 
                         allow_unicode=True, sort_keys=False)
                
        except Exception as e:
            raise ConfigSaveError(str(config_file), f"Failed to save YAML: {e}")
    
    def _save_json_config(self, config: AppConfig, config_file: Path) -> None:
        """
        保存配置为JSON格式
        
        Args:
            config: 配置对象
            config_file: JSON文件路径
        """
        try:
            data = config.to_dict()
            
            # 添加元信息
            data['_metadata'] = {
                'version': config.config_version,
                'saved_at': datetime.now().isoformat(),
                'saved_by': 'AFK2AutoScript'
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            raise ConfigSaveError(str(config_file), f"Failed to save JSON: {e}")
    
    def validate_config(self, config: AppConfig) -> bool:
        """
        验证配置的有效性
        
        Args:
            config: 要验证的配置对象
        
        Returns:
            是否有效
        """
        try:
            # 调用配置对象的验证方法
            return config.validate()
        except ValueError as e:
            self.logger.error(f"Config validation error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected validation error: {e}")
            return False
    
    def _create_backup(self, config_file: Path) -> None:
        """
        创建配置文件备份
        
        Args:
            config_file: 要备份的配置文件
        """
        try:
            # 生成备份文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{config_file.stem}_{timestamp}{config_file.suffix}"
            backup_file = self.backup_dir / backup_name
            
            # 复制文件
            shutil.copy2(config_file, backup_file)
            self.logger.info(f"Config backup created: {backup_file}")
            
            # 清理旧备份
            self._cleanup_old_backups()
            
        except Exception as e:
            self.logger.warning(f"Failed to create backup: {e}")
    
    def _cleanup_old_backups(self) -> None:
        """清理旧的备份文件"""
        try:
            # 获取所有备份文件
            backup_files = sorted(
                self.backup_dir.glob(f"*{self.DEFAULT_CONFIG_NAME.split('.')[0]}*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            # 删除超出数量限制的备份
            for backup_file in backup_files[self.MAX_BACKUP_COUNT:]:
                backup_file.unlink()
                self.logger.debug(f"Deleted old backup: {backup_file}")
                
        except Exception as e:
            self.logger.warning(f"Failed to cleanup old backups: {e}")
    
    def restore_from_backup(self, backup_file: Optional[Path] = None) -> AppConfig:
        """
        从备份恢复配置
        
        Args:
            backup_file: 备份文件路径，默认使用最新备份
        
        Returns:
            恢复的配置对象
        """
        try:
            if backup_file is None:
                # 获取最新的备份文件
                backup_files = sorted(
                    self.backup_dir.glob(f"*{self.DEFAULT_CONFIG_NAME.split('.')[0]}*"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )
                
                if not backup_files:
                    raise ConfigLoadError("", "No backup files found")
                
                backup_file = backup_files[0]
            
            self.logger.info(f"Restoring config from backup: {backup_file}")
            
            # 加载备份配置
            config = self.load_config(backup_file)
            
            # 保存到主配置文件
            self.save_config(config, create_backup=False)
            
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to restore from backup: {e}")
            raise ConfigLoadError(str(backup_file), f"Restore failed: {e}")
    
    def get_config_value(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值（支持点分路径）
        
        Args:
            key_path: 配置键路径，如 "adb.screenshot_quality"
            default: 默认值
        
        Returns:
            配置值
        """
        try:
            config = self.config
            value = config
            
            for key in key_path.split('.'):
                if hasattr(value, key):
                    value = getattr(value, key)
                else:
                    return default
            
            return value
            
        except Exception as e:
            self.logger.warning(f"Failed to get config value '{key_path}': {e}")
            return default
    
    def set_config_value(self, key_path: str, value: Any) -> bool:
        """
        设置配置值（支持点分路径）
        
        Args:
            key_path: 配置键路径，如 "adb.screenshot_quality"
            value: 配置值
        
        Returns:
            是否设置成功
        """
        try:
            config = self.config
            keys = key_path.split('.')
            
            # 导航到父对象
            obj = config
            for key in keys[:-1]:
                if hasattr(obj, key):
                    obj = getattr(obj, key)
                else:
                    self.logger.error(f"Config path not found: {key_path}")
                    return False
            
            # 设置值
            last_key = keys[-1]
            if hasattr(obj, last_key):
                setattr(obj, last_key, value)
                
                # 触发配置变更
                self._notify_listeners(None, config)
                
                # 自动保存
                if self._auto_save_enabled and config.auto_save:
                    self.save_config(config)
                
                return True
            else:
                self.logger.error(f"Config key not found: {last_key}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to set config value '{key_path}': {e}")
            return False
    
    def reset_to_default(self) -> AppConfig:
        """
        重置为默认配置
        
        Returns:
            默认配置对象
        """
        self.logger.info("Resetting config to default")
        default_config = AppConfig.get_default()
        self.config = default_config
        return default_config
    
    def export_config(self, export_file: Path) -> None:
        """
        导出配置到指定文件
        
        Args:
            export_file: 导出文件路径
        """
        self.save_config(self.config, export_file, create_backup=False)
        self.logger.info(f"Config exported to: {export_file}")
    
    def import_config(self, import_file: Path) -> AppConfig:
        """
        从指定文件导入配置
        
        Args:
            import_file: 导入文件路径
        
        Returns:
            导入的配置对象
        """
        config = self.load_config(import_file)
        self.config = config
        self.logger.info(f"Config imported from: {import_file}")
        return config
    
    def add_listener(self, listener: callable) -> None:
        """
        添加配置变更监听器
        
        Args:
            listener: 监听器函数，接收(old_config, new_config)参数
        """
        if listener not in self._listeners:
            self._listeners.append(listener)
    
    def remove_listener(self, listener: callable) -> None:
        """
        移除配置变更监听器
        
        Args:
            listener: 监听器函数
        """
        if listener in self._listeners:
            self._listeners.remove(listener)
    
    def _notify_listeners(self, old_config: Optional[AppConfig], 
                         new_config: AppConfig) -> None:
        """
        通知所有监听器配置已变更
        
        Args:
            old_config: 旧配置
            new_config: 新配置
        """
        for listener in self._listeners:
            try:
                listener(old_config, new_config)
            except Exception as e:
                self.logger.error(f"Error in config listener: {e}")
    
    def enable_auto_save(self, enabled: bool = True) -> None:
        """
        启用/禁用自动保存
        
        Args:
            enabled: 是否启用
        """
        self._auto_save_enabled = enabled
        self.logger.info(f"Auto-save {'enabled' if enabled else 'disabled'}")


# 全局配置服务实例
config_service = ConfigService()