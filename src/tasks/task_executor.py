"""
任务执行器
负责具体任务的执行
"""

import time
import threading
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import traceback

from src.services.log_service import LoggerMixin
from src.models.task import TaskInfo, TaskStatus
from src.controller.afk2_controller import AFK2Controller
from src.utils.exceptions import TaskError, TaskExecutionError

# 避免循环导入
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.services.adb_service import ADBService


class TaskExecutor(LoggerMixin):
    """
    任务执行器
    负责执行具体的任务逻辑
    """
    
    def __init__(self, game_controller: Optional[AFK2Controller] = None, adb_service: Optional['ADBService'] = None, ocr_engine: Optional['OCREngine'] = None):
        """
        初始化任务执行器
        
        Args:
            game_controller: 游戏控制器
            adb_service: ADB服务实例
            ocr_engine: OCR引擎实例（可选）
        """
        self.game_controller = game_controller
        self.adb_service = adb_service
        self.ocr_engine = ocr_engine
        
        # 任务执行函数注册表
        self._executors: Dict[str, Callable] = {}
        
        # 执行上下文
        self._context: Dict[str, Any] = {}
        
        # 执行统计
        self._execution_stats: Dict[str, Dict[str, Any]] = {}
        
        # 注册内置执行器
        self._register_builtin_executors()
        
        self.logger.info("TaskExecutor initialized")
    
    def execute(self, task: TaskInfo) -> Any:
        """
        执行任务
        
        Args:
            task: 任务信息
        
        Returns:
            执行结果
        """
        start_time = time.time()
        
        try:
            # 获取执行器
            task_type = task.metadata.get('task_type') if hasattr(task, 'metadata') else task.task_type
            executor = self._executors.get(task_type)
            if not executor:
                raise TaskExecutionError(f"No executor for task type: {task_type}")
            
            self.logger.info(f"Executing task: {task.task_name} ({task.task_id})")
            
            # 检查是否需要唤醒游戏（排除系统任务和唤醒游戏任务本身）
            if task_type not in ['system', 'wake_game'] and hasattr(task, 'metadata'):
                should_wake = task.metadata.get('wake_game', True)  # 默认为True
                if should_wake:
                    self._ensure_game_running()
            
            # 设置超时
            timeout = task.metadata.get('timeout') if hasattr(task, 'metadata') else None
            if timeout:
                result = self._execute_with_timeout(executor, task, timeout)
            else:
                result = executor(task, self._context)
            
            # 更新统计
            self._update_stats(task_type, True, time.time() - start_time)
            
            # 任务执行成功后返回首页（排除系统任务）
            if task_type not in ['system', 'wake_game'] and self.game_controller:
                try:
                    # 先检查是否已经在首页
                    self.logger.info("Checking if already at home screen...")
                    if self._is_at_home_screen():
                        self.logger.info("Already at home screen, no need to return")
                    else:
                        self.logger.info("Not at home screen, returning to home...")
                        if self.game_controller.return_to_home():
                            self.logger.info("Successfully returned to home screen")
                        else:
                            self.logger.warning("Failed to return to home screen")
                except Exception as e:
                    self.logger.warning(f"Error during home screen check/return: {e}")
            
            self.logger.info(f"Task executed successfully: {task.task_name}")
            return result
            
        except Exception as e:
            # 更新统计
            self._update_stats(task_type, False, time.time() - start_time)
            
            self.logger.error(f"Task execution failed: {task.task_name} - {e}")
            self.logger.debug(traceback.format_exc())
            raise TaskExecutionError(f"Task execution failed: {e}")
    
    def register_executor(self, task_type: str, executor: Callable) -> None:
        """
        注册任务执行器
        
        Args:
            task_type: 任务类型
            executor: 执行函数
        """
        self._executors[task_type] = executor
        self.logger.info(f"Executor registered for type: {task_type}")
    
    def set_context(self, key: str, value: Any) -> None:
        """
        设置执行上下文
        
        Args:
            key: 键
            value: 值
        """
        self._context[key] = value
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """
        获取执行上下文
        
        Args:
            key: 键
            default: 默认值
        
        Returns:
            上下文值
        """
        return self._context.get(key, default)
    
    def get_statistics(self) -> Dict[str, Dict[str, Any]]:
        """
        获取执行统计
        
        Returns:
            统计信息
        """
        return self._execution_stats.copy()
    
    def _register_builtin_executors(self) -> None:
        """注册内置执行器"""
        
        # 唤醒游戏任务执行器
        self.register_executor('wake_game', self._execute_wake_game)
        self.register_executor('system', self._execute_wake_game)  # 系统任务也使用同样的执行器
        
        # 每日挂机奖励执行器
        self.register_executor('daily_idle_reward', self._execute_daily_idle_reward)
    
    def _execute_with_timeout(self, executor: Callable, task: TaskInfo, 
                            timeout: int) -> Any:
        """
        带超时的任务执行
        
        Args:
            executor: 执行函数
            task: 任务信息
            timeout: 超时时间（秒）
        
        Returns:
            执行结果
        """
        result = [None]
        exception = [None]
        
        def run():
            try:
                result[0] = executor(task, self._context)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            # 超时
            raise TaskExecutionError(f"Task timeout after {timeout} seconds")
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    def _update_stats(self, task_type: str, success: bool, duration: float) -> None:
        """
        更新执行统计
        
        Args:
            task_type: 任务类型
            success: 是否成功
            duration: 执行时长
        """
        if task_type not in self._execution_stats:
            self._execution_stats[task_type] = {
                'total': 0,
                'success': 0,
                'failed': 0,
                'total_duration': 0.0,
                'avg_duration': 0.0
            }
        
        stats = self._execution_stats[task_type]
        stats['total'] += 1
        
        if success:
            stats['success'] += 1
        else:
            stats['failed'] += 1
        
        stats['total_duration'] += duration
        stats['avg_duration'] = stats['total_duration'] / stats['total']
    
    # ========== 内置执行器实现 ==========
    
    def _execute_daily_idle_reward(self, task: TaskInfo, context: Dict[str, Any]) -> bool:
        """
        执行每日挂机奖励任务
        
        Args:
            task: 任务信息
            context: 执行上下文
        
        Returns:
            是否成功
        """
        if not self.game_controller:
            raise TaskExecutionError("Game controller not available")
        
        # 导入任务类
        from src.tasks.daily_idle_reward_task import DailyIdleRewardTask
        from src.services.adb_service import ADBService
        from src.recognition.image_recognizer import ImageRecognizer
        from src.recognition.ocr_engine import OCREngine
        from pathlib import Path
        
        # 获取参数
        params = task.metadata.get('params', {}) if hasattr(task, 'metadata') else {}
        check_idle_mode = params.get('check_idle_mode', True)
        use_hourglass = params.get('use_hourglass', True)
        
        try:
            # 使用传入的ADB服务或创建新的
            if self.adb_service:
                adb_service = self.adb_service
                self.logger.info("Using provided ADB service")
            else:
                # 创建新的ADB服务实例
                adb_service = ADBService()
                
                # 尝试连接设备（如果没有已连接的设备）
                if not adb_service.current_device:
                    devices = adb_service.get_devices()
                    online_devices = [d for d in devices if d.status.value == 'device']
                    
                    if online_devices:
                        # 连接第一个在线设备
                        if adb_service.connect_device(online_devices[0].device_id):
                            self.logger.info(f"Connected to device: {online_devices[0].device_id}")
                        else:
                            raise TaskExecutionError("Failed to connect to device")
                    else:
                        raise TaskExecutionError("No online devices found")
            
            # 检查设备连接
            if not adb_service.current_device:
                raise TaskExecutionError("No device connected")
            
            # 设置图像识别器的模板目录
            images_dir = Path(__file__).parent.parent / 'resources' / 'images'
            image_recognizer = ImageRecognizer(template_dir=images_dir)
            
            # 使用传入的OCR引擎实例，如果没有则尝试创建新的
            ocr_engine = self.ocr_engine
            if not ocr_engine:
                try:
                    self.logger.info("Creating new OCR engine instance for task")
                    ocr_engine = OCREngine()
                except Exception as e:
                    self.logger.warning(f"OCR engine not available: {e}")
                    ocr_engine = None
            else:
                self.logger.info("Using existing OCR engine instance")
            
            # 创建任务实例
            idle_reward_task = DailyIdleRewardTask(adb_service, image_recognizer, ocr_engine)
            
            # 执行任务
            result = idle_reward_task.execute()
            
            if result:
                self.logger.info("Daily idle reward task completed successfully")
            else:
                self.logger.warning("Daily idle reward task completed with warnings")
            
            return result
        except Exception as e:
            self.logger.error(f"Daily idle reward task failed: {e}")
            raise TaskExecutionError(f"Daily idle reward task execution failed: {e}")
    
    def _execute_wake_game(self, task: TaskInfo, context: Dict[str, Any]) -> bool:
        """
        执行唤醒游戏任务
        
        Args:
            task: 任务信息
            context: 执行上下文
        
        Returns:
            是否成功
        """
        if not self.game_controller:
            raise TaskExecutionError("Game controller not available")
        
        # 导入唤醒游戏任务
        from src.tasks.wake_game_task import WakeGameTask
        
        # 获取参数
        params = task.metadata.get('params', {}) if hasattr(task, 'metadata') else {}
        wait_for_main = params.get('wait_for_main', True)
        startup_timeout = params.get('startup_timeout', 30.0)
        
        # 创建唤醒任务实例
        wake_task = WakeGameTask(
            wait_for_main=wait_for_main,
            startup_timeout=startup_timeout
        )
        
        # 执行唤醒任务
        result = wake_task.execute(self.game_controller)
        
        if result:
            self.logger.info("Game wake task completed successfully")
        else:
            self.logger.warning("Game wake task failed")
        
        return result
    
    def execute_task(self, task) -> bool:
        """
        执行任务对象（兼容旧接口）
        
        Args:
            task: 任务对象（具有execute方法）
        
        Returns:
            是否成功
        """
        if hasattr(task, 'execute'):
            # 如果任务有execute方法，直接调用
            if self.game_controller:
                return task.execute(self.game_controller)
            else:
                raise TaskExecutionError("Game controller not available")
        else:
            # 否则使用原有的execute方法
            return self.execute(task)
    
    def _ensure_game_running(self) -> bool:
        """
        确保游戏正在运行
        
        Returns:
            游戏是否成功运行
        """
        if not self.game_controller:
            raise TaskExecutionError("Game controller not available")
        
        try:
            # 检查游戏是否已运行
            if self.game_controller.is_game_running():
                self.logger.info("Game is already running")
                return True
            
            self.logger.info("Game is not running, starting game...")
            
            # 导入唤醒游戏任务
            from src.tasks.wake_game_task import WakeGameTask
            
            # 创建唤醒任务
            wake_task = WakeGameTask(
                name="Auto wake game",
                wait_for_main=True,
                startup_timeout=30.0
            )
            
            # 执行唤醒任务
            result = wake_task.execute(self.game_controller)
            
            if result:
                self.logger.info("Game started successfully")
            else:
                self.logger.error("Failed to start game")
                raise TaskExecutionError("Failed to start game")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error ensuring game is running: {e}")
            raise TaskExecutionError(f"Failed to ensure game is running: {e}")
    
    def _is_at_home_screen(self) -> bool:
        """
        检查是否已经在游戏首页
        
        Returns:
            是否在首页
        """
        if not self.game_controller:
            return False
        
        try:
            from pathlib import Path
            
            # 截取当前画面
            screenshot = self.game_controller.screenshot()
            
            # 检查首页标志
            home_indicator_path = Path(__file__).parent.parent / 'resources' / 'images' / 'home_indicator.png'
            
            # 尝试识别首页标志
            if self.game_controller.recognizer and home_indicator_path.exists():
                try:
                    # 扩大搜索区域到右下角（水平60-100%，垂直70-100%）
                    # 更大的区域提供更多上下文，提高匹配准确性
                    width, height = screenshot.size
                    search_region = (
                        int(width * 0.6),   # x: 从60%开始
                        int(height * 0.7),  # y: 从70%开始
                        int(width * 0.4),   # width: 右侧40%
                        int(height * 0.3)   # height: 底部30%
                    )
                    # 优先使用灰度匹配，对罗盘图标这种有内部细节的图标更准确
                    result = self.game_controller.recognizer.find_template(
                        screenshot,
                        'home_indicator',
                        threshold=0.7,  # 灰度匹配使用更高的阈值
                        preprocessing='grayscale',  # 使用灰度匹配
                        region=search_region  # 限定搜索区域
                    )
                    
                    # 如果灰度匹配失败，尝试轮廓匹配
                    if not result:
                        result = self.game_controller.recognizer.find_template(
                            screenshot,
                            'home_indicator',
                            threshold=0.35,
                            use_contour=True,  # 使用轮廓匹配作为备选
                            region=search_region
                        )
                    if result:
                        self.logger.debug("Home indicator found")
                        return True
                except:
                    pass
            
            # 尝试识别神秘屋图标（备用方案）
            try:
                mystery_result = self.game_controller.recognizer.find_template(
                    screenshot,
                    'mystery_house',
                    threshold=0.6,  # 降低阈值
                    preprocessing='auto'  # 自动选择最佳预处理方式
                )
                if mystery_result:
                    self.logger.debug("Mystery house icon found, at home screen")
                    return True
            except:
                pass
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error checking home screen: {e}")
            return False