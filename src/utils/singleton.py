"""
单例模式实现
提供单例模式的装饰器和元类
"""

from typing import Any, Dict, Type
import threading


class SingletonMeta(type):
    """
    单例元类
    确保一个类只有一个实例
    """
    
    _instances: Dict[Type, Any] = {}
    _lock: threading.Lock = threading.Lock()
    
    def __call__(cls, *args, **kwargs):
        """
        控制类的实例化过程
        
        Returns:
            类的唯一实例
        """
        # 双重检查锁定模式
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]


def singleton(cls: Type) -> Type:
    """
    单例装饰器
    将类转换为单例模式
    
    Args:
        cls: 要转换的类
    
    Returns:
        单例类
    
    Example:
        @singleton
        class MyClass:
            pass
    """
    instances = {}
    lock = threading.Lock()
    
    def get_instance(*args, **kwargs):
        """获取单例实例"""
        if cls not in instances:
            with lock:
                if cls not in instances:
                    instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance


class Singleton:
    """
    单例基类
    继承此类的子类将自动成为单例
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """
        创建或返回唯一实例
        
        Returns:
            类的唯一实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance