"""
重试装饰器
提供可配置的重试机制
"""

import time
import functools
import random
from typing import Tuple, Type, Callable, Optional, Any, Union
from src.services.log_service import get_logger
from src.utils.exceptions import AFK2AutoException


logger = get_logger()


class RetryDecorator:
    """
    重试装饰器类
    支持多种重试策略
    """
    
    @staticmethod
    def retry(
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff: float = 1.0,
        max_delay: float = 60.0,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        jitter: bool = False,
        on_retry: Optional[Callable[[Exception, int], None]] = None
    ):
        """
        重试装饰器
        
        Args:
            max_attempts: 最大重试次数
            delay: 初始延迟时间（秒）
            backoff: 退避因子（每次重试延迟时间的倍数）
            max_delay: 最大延迟时间（秒）
            exceptions: 需要重试的异常类型元组
            jitter: 是否添加随机抖动（避免惊群效应）
            on_retry: 重试时的回调函数，接收异常和当前重试次数
        
        Returns:
            装饰器函数
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                current_delay = delay
                last_exception = None
                
                for attempt in range(max_attempts):
                    try:
                        # 尝试执行函数
                        result = func(*args, **kwargs)
                        
                        # 成功执行，记录日志（如果不是第一次尝试）
                        if attempt > 0:
                            logger.info(
                                f"Function '{func.__name__}' succeeded after {attempt} retry(ies)"
                            )
                        
                        return result
                    
                    except exceptions as e:
                        last_exception = e
                        
                        # 如果是最后一次尝试，直接抛出异常
                        if attempt == max_attempts - 1:
                            logger.error(
                                f"Function '{func.__name__}' failed after {max_attempts} attempts: {str(e)}"
                            )
                            raise
                        
                        # 记录重试日志
                        logger.warning(
                            f"Function '{func.__name__}' failed (attempt {attempt + 1}/{max_attempts}): {str(e)}"
                        )
                        
                        # 执行重试回调
                        if on_retry:
                            try:
                                on_retry(e, attempt + 1)
                            except Exception as callback_error:
                                logger.error(f"Retry callback error: {callback_error}")
                        
                        # 计算延迟时间
                        actual_delay = current_delay
                        
                        # 添加随机抖动
                        if jitter:
                            actual_delay *= (0.5 + random.random())
                        
                        # 等待
                        logger.debug(f"Waiting {actual_delay:.2f} seconds before retry...")
                        time.sleep(actual_delay)
                        
                        # 更新下次延迟时间（指数退避）
                        current_delay = min(current_delay * backoff, max_delay)
                
                # 理论上不应该到达这里
                if last_exception:
                    raise last_exception
            
            return wrapper
        return decorator
    
    @staticmethod
    def retry_on_condition(
        condition: Callable[[Any], bool],
        max_attempts: int = 3,
        delay: float = 1.0,
        on_retry: Optional[Callable[[int], None]] = None
    ):
        """
        基于条件的重试装饰器
        当返回值满足特定条件时进行重试
        
        Args:
            condition: 判断是否需要重试的条件函数
            max_attempts: 最大重试次数
            delay: 重试延迟时间（秒）
            on_retry: 重试时的回调函数
        
        Returns:
            装饰器函数
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                for attempt in range(max_attempts):
                    result = func(*args, **kwargs)
                    
                    # 检查条件
                    if not condition(result):
                        # 条件不满足，返回结果
                        if attempt > 0:
                            logger.info(
                                f"Function '{func.__name__}' succeeded after {attempt} retry(ies)"
                            )
                        return result
                    
                    # 条件满足，需要重试
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Function '{func.__name__}' result requires retry "
                            f"(attempt {attempt + 1}/{max_attempts})"
                        )
                        
                        if on_retry:
                            try:
                                on_retry(attempt + 1)
                            except Exception as e:
                                logger.error(f"Retry callback error: {e}")
                        
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Function '{func.__name__}' condition not met after {max_attempts} attempts"
                        )
                
                return result
            
            return wrapper
        return decorator


# 便捷函数
def retry_on_adb_error(max_attempts: int = 3, delay: float = 2.0):
    """
    ADB错误重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        delay: 重试延迟时间（秒）
    """
    from src.utils.exceptions import (
        ADBConnectionError, ADBCommandError, 
        DeviceNotFoundError, DeviceOfflineError
    )
    
    return RetryDecorator.retry(
        max_attempts=max_attempts,
        delay=delay,
        backoff=2.0,
        exceptions=(
            ADBConnectionError,
            ADBCommandError,
            DeviceNotFoundError,
            DeviceOfflineError
        ),
        jitter=True
    )


def retry_on_recognition_error(max_attempts: int = 5, delay: float = 1.0):
    """
    识别错误重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        delay: 重试延迟时间（秒）
    """
    from src.utils.exceptions import (
        ImageNotFoundError, ImageRecognitionError,
        OCRRecognitionError
    )
    
    return RetryDecorator.retry(
        max_attempts=max_attempts,
        delay=delay,
        backoff=1.5,
        exceptions=(
            ImageNotFoundError,
            ImageRecognitionError,
            OCRRecognitionError
        ),
        jitter=False
    )


def retry_on_game_error(max_attempts: int = 3, delay: float = 5.0):
    """
    游戏错误重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        delay: 重试延迟时间（秒）
    """
    from src.utils.exceptions import (
        GameNotRunningError, GameStartupError,
        GameLoadingTimeoutError
    )
    
    return RetryDecorator.retry(
        max_attempts=max_attempts,
        delay=delay,
        backoff=2.0,
        max_delay=30.0,
        exceptions=(
            GameNotRunningError,
            GameStartupError,
            GameLoadingTimeoutError
        )
    )


class RetryManager:
    """
    重试管理器
    提供更复杂的重试逻辑管理
    """
    
    def __init__(self, 
                 max_attempts: int = 3,
                 delay: float = 1.0,
                 backoff: float = 2.0):
        """
        初始化重试管理器
        
        Args:
            max_attempts: 最大重试次数
            delay: 初始延迟时间
            backoff: 退避因子
        """
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff = backoff
        self.attempt = 0
        self.current_delay = delay
    
    def should_retry(self) -> bool:
        """判断是否应该重试"""
        return self.attempt < self.max_attempts
    
    def wait(self) -> None:
        """执行等待"""
        time.sleep(self.current_delay)
        self.current_delay *= self.backoff
        self.attempt += 1
    
    def reset(self) -> None:
        """重置重试状态"""
        self.attempt = 0
        self.current_delay = self.delay
    
    def execute_with_retry(self, 
                          func: Callable,
                          *args,
                          exceptions: Tuple[Type[Exception], ...] = (Exception,),
                          **kwargs) -> Any:
        """
        执行函数并自动重试
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            exceptions: 需要重试的异常类型
            **kwargs: 函数关键字参数
        
        Returns:
            函数执行结果
        """
        self.reset()
        last_exception = None
        
        while self.should_retry():
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                last_exception = e
                logger.warning(
                    f"Attempt {self.attempt + 1}/{self.max_attempts} failed: {str(e)}"
                )
                
                if self.attempt + 1 < self.max_attempts:
                    self.wait()
                else:
                    logger.error(f"All {self.max_attempts} attempts failed")
                    raise
        
        if last_exception:
            raise last_exception