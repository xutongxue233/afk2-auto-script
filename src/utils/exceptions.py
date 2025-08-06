"""
自定义异常类
定义项目中使用的各种异常
"""

from typing import Optional, Any


class AFK2AutoException(Exception):
    """
    基础异常类
    所有自定义异常的父类
    """
    
    def __init__(self, message: str = "", code: Optional[int] = None, 
                 details: Optional[Any] = None):
        """
        初始化异常
        
        Args:
            message: 错误信息
            code: 错误代码
            details: 详细信息
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details
    
    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


# ==================== ADB相关异常 ====================

class ADBException(AFK2AutoException):
    """ADB相关异常的基类"""
    pass


class ADBConnectionError(ADBException):
    """ADB连接异常"""
    
    def __init__(self, device_id: Optional[str] = None, message: str = ""):
        if not message:
            if device_id:
                message = f"无法连接到设备 {device_id}"
            else:
                message = "无法连接到ADB设备"
        super().__init__(message, code=1001)
        self.device_id = device_id


class ADBCommandError(ADBException):
    """ADB命令执行异常"""
    
    def __init__(self, command: str, message: str = ""):
        if not message:
            message = f"ADB命令执行失败: {command}"
        super().__init__(message, code=1002)
        self.command = command


class DeviceNotFoundError(ADBException):
    """设备未找到异常"""
    
    def __init__(self, device_id: Optional[str] = None):
        message = f"未找到设备: {device_id}" if device_id else "未找到任何连接的设备"
        super().__init__(message, code=1003)
        self.device_id = device_id


class DeviceUnauthorizedError(ADBException):
    """设备未授权异常"""
    
    def __init__(self, device_id: str):
        message = f"设备 {device_id} 未授权，请在设备上确认调试授权"
        super().__init__(message, code=1004)
        self.device_id = device_id


class DeviceOfflineError(ADBException):
    """设备离线异常"""
    
    def __init__(self, device_id: str):
        message = f"设备 {device_id} 已离线"
        super().__init__(message, code=1005)
        self.device_id = device_id


# ==================== 游戏相关异常 ====================

class GameException(AFK2AutoException):
    """游戏相关异常的基类"""
    pass


class GameNotRunningError(GameException):
    """游戏未运行异常"""
    
    def __init__(self, package_name: Optional[str] = None):
        message = f"游戏 {package_name} 未运行" if package_name else "游戏未运行"
        super().__init__(message, code=2001)
        self.package_name = package_name


class GameStartupError(GameException):
    """游戏启动失败异常"""
    
    def __init__(self, package_name: str, reason: str = ""):
        message = f"游戏 {package_name} 启动失败"
        if reason:
            message += f": {reason}"
        super().__init__(message, code=2002)
        self.package_name = package_name


class GameLoadingTimeoutError(GameException):
    """游戏加载超时异常"""
    
    def __init__(self, timeout: int):
        message = f"游戏加载超时 ({timeout}秒)"
        super().__init__(message, code=2003)
        self.timeout = timeout


class GameControlError(GameException):
    """游戏控制异常"""
    
    def __init__(self, message: str):
        super().__init__(message, code=2004)


# ==================== 识别相关异常 ====================

class RecognitionException(AFK2AutoException):
    """识别相关异常的基类"""
    pass


class OCREngineNotFoundError(RecognitionException):
    """OCR引擎未找到异常"""
    
    def __init__(self, engine_name: str):
        message = f"OCR引擎未找到: {engine_name}"
        super().__init__(message, code=3007)
        self.engine_name = engine_name


class ImageNotFoundError(RecognitionException):
    """图像未找到异常"""
    
    def __init__(self, template_name: str, threshold: float = 0.0):
        message = f"未找到图像: {template_name}"
        if threshold > 0:
            message += f" (阈值: {threshold})"
        super().__init__(message, code=3001)
        self.template_name = template_name
        self.threshold = threshold


class ImageRecognitionError(RecognitionException):
    """图像识别异常"""
    
    def __init__(self, message: str = "图像识别失败"):
        super().__init__(message, code=3002)


class OCRRecognitionError(RecognitionException):
    """OCR识别异常"""
    
    def __init__(self, message: str = "OCR文字识别失败", text: Optional[str] = None):
        if text:
            message += f": 无法识别文字 '{text}'"
        super().__init__(message, code=3003)
        self.text = text


class TemplateLoadError(RecognitionException):
    """模板加载异常"""
    
    def __init__(self, template_path: str):
        message = f"无法加载模板图像: {template_path}"
        super().__init__(message, code=3004)
        self.template_path = template_path


class TemplateNotFoundError(RecognitionException):
    """模板未找到异常"""
    
    def __init__(self, template_name: str):
        message = f"模板未找到: {template_name}"
        super().__init__(message, code=3005)
        self.template_name = template_name


class InvalidImageFormatError(RecognitionException):
    """无效图像格式异常"""
    
    def __init__(self, format_info: str = ""):
        message = "无效的图像格式"
        if format_info:
            message += f": {format_info}"
        super().__init__(message, code=3006)
        self.format_info = format_info


class SceneRecognitionError(RecognitionException):
    """场景识别异常"""
    
    def __init__(self, expected_scene: Optional[str] = None, current_scene: Optional[str] = None):
        if expected_scene and current_scene:
            message = f"场景识别错误: 期望 '{expected_scene}'，当前 '{current_scene}'"
        elif expected_scene:
            message = f"未能识别到期望的场景: {expected_scene}"
        else:
            message = "场景识别失败"
        super().__init__(message, code=3008)
        self.expected_scene = expected_scene
        self.current_scene = current_scene


# ==================== 任务相关异常 ====================

class TaskException(AFK2AutoException):
    """任务相关异常的基类"""
    pass


class TaskError(TaskException):
    """通用任务异常"""
    
    def __init__(self, message: str):
        super().__init__(message, code=4000)


class TaskNotFoundError(TaskException):
    """任务未找到异常"""
    
    def __init__(self, task_id: str):
        message = f"任务未找到: {task_id}"
        super().__init__(message, code=4005)
        self.task_id = task_id


class TaskExecutionError(TaskException):
    """任务执行异常"""
    
    def __init__(self, task_name: str, reason: str = ""):
        message = f"任务 '{task_name}' 执行失败"
        if reason:
            message += f": {reason}"
        super().__init__(message, code=4001)
        self.task_name = task_name


class TaskTimeoutError(TaskException):
    """任务超时异常"""
    
    def __init__(self, task_name: str, timeout: int):
        message = f"任务 '{task_name}' 执行超时 ({timeout}秒)"
        super().__init__(message, code=4002)
        self.task_name = task_name
        self.timeout = timeout


class TaskCancelledError(TaskException):
    """任务取消异常"""
    
    def __init__(self, task_name: str):
        message = f"任务 '{task_name}' 已被取消"
        super().__init__(message, code=4003)
        self.task_name = task_name


class TaskDependencyError(TaskException):
    """任务依赖异常"""
    
    def __init__(self, task_name: str, dependency: str):
        message = f"任务 '{task_name}' 的依赖 '{dependency}' 未满足"
        super().__init__(message, code=4004)
        self.task_name = task_name
        self.dependency = dependency


# ==================== 配置相关异常 ====================

class ConfigException(AFK2AutoException):
    """配置相关异常的基类"""
    pass


class ConfigLoadError(ConfigException):
    """配置加载异常"""
    
    def __init__(self, config_path: str, reason: str = ""):
        message = f"无法加载配置文件: {config_path}"
        if reason:
            message += f": {reason}"
        super().__init__(message, code=5001)
        self.config_path = config_path


class ConfigSaveError(ConfigException):
    """配置保存异常"""
    
    def __init__(self, config_path: str, reason: str = ""):
        message = f"无法保存配置文件: {config_path}"
        if reason:
            message += f": {reason}"
        super().__init__(message, code=5002)
        self.config_path = config_path


class ConfigValidationError(ConfigException):
    """配置验证异常"""
    
    def __init__(self, field: str, value: Any, reason: str):
        message = f"配置验证失败 - {field}: {value} - {reason}"
        super().__init__(message, code=5003)
        self.field = field
        self.value = value


# ==================== 网络相关异常 ====================

class NetworkException(AFK2AutoException):
    """网络相关异常的基类"""
    pass


class NetworkConnectionError(NetworkException):
    """网络连接异常"""
    
    def __init__(self, host: str, port: int):
        message = f"无法连接到 {host}:{port}"
        super().__init__(message, code=6001)
        self.host = host
        self.port = port


class NetworkTimeoutError(NetworkException):
    """网络超时异常"""
    
    def __init__(self, operation: str, timeout: int):
        message = f"网络操作 '{operation}' 超时 ({timeout}秒)"
        super().__init__(message, code=6002)
        self.operation = operation
        self.timeout = timeout


# ==================== 错误处理工具函数 ====================

def get_user_friendly_message(exception: Exception) -> str:
    """
    获取用户友好的错误信息
    
    Args:
        exception: 异常对象
    
    Returns:
        用户友好的错误信息
    """
    ERROR_MESSAGES = {
        ADBConnectionError: "无法连接到设备，请检查ADB连接和设备授权",
        DeviceNotFoundError: "未找到设备，请确保设备已连接并开启USB调试",
        DeviceUnauthorizedError: "设备未授权，请在设备上确认调试授权",
        DeviceOfflineError: "设备已离线，请重新连接设备",
        GameNotRunningError: "游戏未运行，请先启动游戏",
        GameStartupError: "游戏启动失败，请检查游戏是否已安装",
        GameLoadingTimeoutError: "游戏加载超时，请检查网络连接",
        ImageNotFoundError: "未找到目标图像，可能游戏界面已变化",
        OCRRecognitionError: "文字识别失败，请检查截图质量",
        TaskExecutionError: "任务执行失败，请查看日志了解详情",
        TaskTimeoutError: "任务执行超时，请检查设备响应",
        ConfigLoadError: "配置文件加载失败，请检查文件格式",
        ConfigValidationError: "配置参数无效，请检查配置值",
        NetworkConnectionError: "网络连接失败，请检查网络设置",
        NetworkTimeoutError: "网络请求超时，请检查网络连接"
    }
    
    for exc_type, message in ERROR_MESSAGES.items():
        if isinstance(exception, exc_type):
            return message
    
    # 如果是自定义异常但没有特定消息，使用异常自身的消息
    if isinstance(exception, AFK2AutoException):
        return str(exception)
    
    # 对于其他异常，返回通用消息
    return f"发生未知错误：{str(exception)}"