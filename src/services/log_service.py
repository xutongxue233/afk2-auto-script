"""
日志服务模块
提供统一的日志配置和管理
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler


def setup_logger(
    name: str = 'AFK2Auto',
    log_level: str = 'INFO',
    log_dir: Optional[str] = None,
    console_output: bool = True,
    file_output: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    配置并返回日志记录器
    
    Args:
        name: 日志记录器名称
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 日志文件目录，默认为项目根目录下的logs文件夹
        console_output: 是否输出到控制台
        file_output: 是否输出到文件
        max_bytes: 日志文件最大大小（字节）
        backup_count: 日志文件备份数量
    
    Returns:
        配置好的日志记录器
    """
    # 获取或创建日志记录器
    logger = logging.getLogger(name)
    
    # 如果已经配置过，直接返回
    if logger.handlers:
        return logger
    
    # 设置日志级别
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)
    
    # 创建日志格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 简化的控制台格式
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 添加控制台处理器
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # 添加文件处理器
    if file_output:
        # 确定日志目录
        if log_dir is None:
            # 获取项目根目录
            project_root = Path(__file__).parent.parent.parent
            log_dir = project_root / 'logs'
        else:
            log_dir = Path(log_dir)
        
        # 创建日志目录
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建日志文件名（包含日期）
        log_filename = f"afk2_auto_{datetime.now().strftime('%Y%m%d')}.log"
        log_path = log_dir / log_filename
        
        # 使用RotatingFileHandler实现日志轮转
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 添加错误日志文件（只记录ERROR及以上级别）
        error_log_filename = f"afk2_auto_error_{datetime.now().strftime('%Y%m%d')}.log"
        error_log_path = log_dir / error_log_filename
        
        error_handler = RotatingFileHandler(
            error_log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)
    
    # 防止日志传播到父记录器
    logger.propagate = False
    
    return logger


def get_logger(name: str = 'AFK2Auto') -> logging.Logger:
    """
    获取已配置的日志记录器
    
    Args:
        name: 日志记录器名称
    
    Returns:
        日志记录器实例
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        # 如果还没有配置，使用默认配置
        return setup_logger(name)
    return logger


def setup_logging(level: int = logging.INFO) -> None:
    """
    配置全局日志设置（用于主程序）
    
    Args:
        level: 日志级别
    """
    # 将整数级别转换为字符串
    level_name = logging.getLevelName(level)
    
    # 设置默认日志记录器
    setup_logger('AFK2Auto', log_level=level_name)


class LoggerMixin:
    """
    日志混入类，为其他类提供日志功能
    """
    
    @property
    def logger(self) -> logging.Logger:
        """获取类专用的日志记录器"""
        if not hasattr(self, '_logger'):
            # 使用类的完整名称作为日志记录器名称
            logger_name = f"AFK2Auto.{self.__class__.__module__}.{self.__class__.__name__}"
            self._logger = logging.getLogger(logger_name)
            
            # 如果父记录器已配置，子记录器会继承配置
            if not self._logger.handlers and not logging.getLogger('AFK2Auto').handlers:
                # 如果都没有配置，设置默认配置
                setup_logger('AFK2Auto')
                
        return self._logger


def log_function_call(func):
    """
    装饰器：记录函数调用
    """
    logger = get_logger()
    
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        logger.debug(f"Calling function: {func_name}")
        
        try:
            result = func(*args, **kwargs)
            logger.debug(f"Function {func_name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"Function {func_name} failed with error: {str(e)}", exc_info=True)
            raise
    
    return wrapper


# 模块初始化时设置默认日志记录器
default_logger = setup_logger()

# 导出常用的日志方法
debug = default_logger.debug
info = default_logger.info
warning = default_logger.warning
error = default_logger.error
critical = default_logger.critical