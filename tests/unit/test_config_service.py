"""
配置服务单元测试
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import yaml
import json

from src.services.config_service import ConfigService
from src.models.config import AppConfig, ADBConfig, GameConfig
from src.utils.exceptions import ConfigLoadError, ConfigSaveError


@pytest.fixture
def temp_config_dir():
    """创建临时配置目录"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def config_service(temp_config_dir):
    """创建配置服务实例"""
    # 重置单例
    ConfigService._instance = None
    service = ConfigService(temp_config_dir)
    return service


@pytest.fixture
def sample_config():
    """创建示例配置"""
    config = AppConfig()
    config.adb.screenshot_quality = 95
    config.game.package_name = "com.test.app"
    config.log_level = "DEBUG"
    return config


class TestConfigService:
    """配置服务测试类"""
    
    def test_singleton(self, temp_config_dir):
        """测试单例模式"""
        ConfigService._instance = None
        service1 = ConfigService(temp_config_dir)
        service2 = ConfigService(temp_config_dir)
        assert service1 is service2
    
    def test_init(self, config_service, temp_config_dir):
        """测试初始化"""
        assert config_service.config_dir == temp_config_dir
        assert config_service.backup_dir.exists()
        assert config_service.config_file.name == "config.yaml"
    
    def test_load_default_config(self, config_service):
        """测试加载默认配置"""
        # 配置文件不存在时应创建默认配置
        config = config_service.load_config()
        assert isinstance(config, AppConfig)
        assert config_service.config_file.exists()
    
    def test_save_yaml_config(self, config_service, sample_config, temp_config_dir):
        """测试保存YAML配置"""
        yaml_file = temp_config_dir / "test_config.yaml"
        config_service.save_config(sample_config, yaml_file, create_backup=False)
        
        assert yaml_file.exists()
        
        # 验证内容
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        assert data['adb']['screenshot_quality'] == 95
        assert data['game']['package_name'] == "com.test.app"
        assert data['log_level'] == "DEBUG"
        assert '_metadata' in data
    
    def test_save_json_config(self, config_service, sample_config, temp_config_dir):
        """测试保存JSON配置"""
        json_file = temp_config_dir / "test_config.json"
        config_service.save_config(sample_config, json_file, create_backup=False)
        
        assert json_file.exists()
        
        # 验证内容
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data['adb']['screenshot_quality'] == 95
        assert data['game']['package_name'] == "com.test.app"
        assert data['log_level'] == "DEBUG"
    
    def test_load_yaml_config(self, config_service, temp_config_dir):
        """测试加载YAML配置"""
        # 创建测试配置文件
        yaml_file = temp_config_dir / "test_config.yaml"
        test_data = {
            'adb': {'screenshot_quality': 85},
            'game': {'package_name': 'com.yaml.test'},
            'log_level': 'INFO'
        }
        
        with open(yaml_file, 'w', encoding='utf-8') as f:
            yaml.dump(test_data, f)
        
        # 加载配置
        config = config_service.load_config(yaml_file)
        assert config.adb.screenshot_quality == 85
        assert config.game.package_name == 'com.yaml.test'
        assert config.log_level == 'INFO'
    
    def test_load_json_config(self, config_service, temp_config_dir):
        """测试加载JSON配置"""
        # 创建测试配置文件
        json_file = temp_config_dir / "test_config.json"
        test_data = {
            'adb': {'screenshot_quality': 75},
            'game': {'package_name': 'com.json.test'},
            'log_level': 'WARNING'
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f)
        
        # 加载配置
        config = config_service.load_config(json_file)
        assert config.adb.screenshot_quality == 75
        assert config.game.package_name == 'com.json.test'
        assert config.log_level == 'WARNING'
    
    def test_load_invalid_format(self, config_service, temp_config_dir):
        """测试加载不支持的格式"""
        invalid_file = temp_config_dir / "test_config.txt"
        invalid_file.write_text("invalid content")
        
        with pytest.raises(ConfigLoadError):
            config_service.load_config(invalid_file)
    
    def test_validate_config(self, config_service):
        """测试配置验证"""
        # 有效配置
        valid_config = AppConfig()
        assert config_service.validate_config(valid_config) is True
        
        # 无效配置
        invalid_config = AppConfig()
        invalid_config.adb.screenshot_quality = 150  # 超出范围
        assert config_service.validate_config(invalid_config) is False
    
    def test_create_backup(self, config_service, sample_config):
        """测试创建备份"""
        # 保存配置
        config_service.save_config(sample_config)
        
        # 修改并再次保存（应创建备份）
        sample_config.log_level = "ERROR"
        config_service.save_config(sample_config)
        
        # 检查备份文件
        backup_files = list(config_service.backup_dir.glob("*.yaml"))
        assert len(backup_files) > 0
    
    def test_cleanup_old_backups(self, config_service, sample_config):
        """测试清理旧备份"""
        # 创建多个备份
        for i in range(10):
            backup_file = config_service.backup_dir / f"config_{i}.yaml"
            config_service.save_config(sample_config, backup_file, create_backup=False)
        
        # 触发清理
        config_service._cleanup_old_backups()
        
        # 检查备份数量
        backup_files = list(config_service.backup_dir.glob("*.yaml"))
        assert len(backup_files) <= ConfigService.MAX_BACKUP_COUNT
    
    def test_restore_from_backup(self, config_service, sample_config, temp_config_dir):
        """测试从备份恢复"""
        # 创建备份
        backup_file = config_service.backup_dir / "backup_config.yaml"
        config_service.save_config(sample_config, backup_file, create_backup=False)
        
        # 修改当前配置
        new_config = AppConfig()
        new_config.log_level = "CRITICAL"
        config_service.save_config(new_config)
        
        # 从备份恢复
        restored_config = config_service.restore_from_backup(backup_file)
        assert restored_config.adb.screenshot_quality == sample_config.adb.screenshot_quality
        assert restored_config.game.package_name == sample_config.game.package_name
    
    def test_get_config_value(self, config_service, sample_config):
        """测试获取配置值"""
        config_service._config = sample_config
        
        # 测试获取嵌套值
        value = config_service.get_config_value("adb.screenshot_quality")
        assert value == 95
        
        value = config_service.get_config_value("game.package_name")
        assert value == "com.test.app"
        
        # 测试默认值
        value = config_service.get_config_value("nonexistent.key", "default")
        assert value == "default"
    
    def test_set_config_value(self, config_service, sample_config):
        """测试设置配置值"""
        config_service._config = sample_config
        config_service._auto_save_enabled = False  # 禁用自动保存
        
        # 设置嵌套值
        success = config_service.set_config_value("adb.screenshot_quality", 80)
        assert success is True
        assert config_service.config.adb.screenshot_quality == 80
        
        # 设置不存在的键
        success = config_service.set_config_value("nonexistent.key", "value")
        assert success is False
    
    def test_reset_to_default(self, config_service, sample_config):
        """测试重置为默认配置"""
        config_service._config = sample_config
        config_service._auto_save_enabled = False
        
        default_config = config_service.reset_to_default()
        assert isinstance(default_config, AppConfig)
        assert config_service.config == default_config
        assert config_service.config.game.package_name == "com.lilith.odyssey.cn"  # 默认值
    
    def test_export_import_config(self, config_service, sample_config, temp_config_dir):
        """测试导出和导入配置"""
        config_service._config = sample_config
        
        # 导出配置
        export_file = temp_config_dir / "exported_config.yaml"
        config_service.export_config(export_file)
        assert export_file.exists()
        
        # 修改当前配置
        config_service.config.log_level = "ERROR"
        
        # 导入配置
        imported_config = config_service.import_config(export_file)
        assert imported_config.log_level == "DEBUG"  # 恢复到导出时的值
    
    def test_config_listeners(self, config_service):
        """测试配置监听器"""
        listener_called = False
        old_config_ref = None
        new_config_ref = None
        
        def test_listener(old_config, new_config):
            nonlocal listener_called, old_config_ref, new_config_ref
            listener_called = True
            old_config_ref = old_config
            new_config_ref = new_config
        
        # 添加监听器
        config_service.add_listener(test_listener)
        
        # 修改配置
        old = config_service.config
        new = AppConfig()
        config_service._auto_save_enabled = False
        config_service.config = new
        
        assert listener_called is True
        assert old_config_ref == old
        assert new_config_ref == new
        
        # 移除监听器
        config_service.remove_listener(test_listener)
        listener_called = False
        config_service.config = AppConfig()
        assert listener_called is False
    
    def test_auto_save(self, config_service, sample_config):
        """测试自动保存"""
        config_service._auto_save_enabled = True
        sample_config.auto_save = True
        
        # 设置配置（应触发自动保存）
        config_service.config = sample_config
        
        # 验证文件已保存
        assert config_service.config_file.exists()
        
        # 加载并验证
        loaded_config = config_service.load_config()
        assert loaded_config.adb.screenshot_quality == sample_config.adb.screenshot_quality
    
    def test_enable_disable_auto_save(self, config_service):
        """测试启用/禁用自动保存"""
        config_service.enable_auto_save(False)
        assert config_service._auto_save_enabled is False
        
        config_service.enable_auto_save(True)
        assert config_service._auto_save_enabled is True
    
    def test_config_property(self, config_service):
        """测试config属性"""
        # 第一次访问应加载或创建默认配置
        config = config_service.config
        assert isinstance(config, AppConfig)
        assert config_service._config is not None
        
        # 再次访问应返回相同实例
        config2 = config_service.config
        assert config2 is config
    
    def test_error_handling(self, config_service, temp_config_dir):
        """测试错误处理"""
        # 测试加载损坏的YAML文件
        bad_yaml = temp_config_dir / "bad.yaml"
        bad_yaml.write_text("invalid: yaml: content:")
        
        with pytest.raises(ConfigLoadError):
            config_service.load_config(bad_yaml)
        
        # 测试加载损坏的JSON文件
        bad_json = temp_config_dir / "bad.json"
        bad_json.write_text("{invalid json}")
        
        with pytest.raises(ConfigLoadError):
            config_service.load_config(bad_json)
        
        # 测试保存到只读目录（模拟）
        with patch('builtins.open', side_effect=PermissionError):
            with pytest.raises(ConfigSaveError):
                config_service.save_config(AppConfig(), temp_config_dir / "readonly.yaml")