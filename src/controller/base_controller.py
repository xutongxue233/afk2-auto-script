"""
游戏控制器基类
提供游戏控制的基础功能
"""

import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List, Dict, Any, Callable, Union
from dataclasses import dataclass
from enum import Enum
from PIL import Image

from src.services.adb_service import ADBService
from src.services.config_service import ConfigService
from src.services.log_service import LoggerMixin
from src.recognition.image_recognizer import ImageRecognizer
from src.recognition.ocr_engine import OCREngine
from src.models.config import GameConfig
from src.utils.exceptions import (
    GameNotRunningError, GameStartupError,
    GameLoadingTimeoutError, SceneRecognitionError
)
from src.utils.retry import retry_on_game_error


class GameState(Enum):
    """游戏状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    LOADING = "loading"
    MAIN_MENU = "main_menu"
    IN_GAME = "in_game"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class ClickPoint:
    """点击点信息"""
    name: str  # 点击点名称
    x: int  # X坐标
    y: int  # Y坐标
    description: str = ""  # 描述
    wait_after: float = 1.0  # 点击后等待时间
    
    def to_tuple(self) -> Tuple[int, int]:
        """转换为坐标元组"""
        return (self.x, self.y)


@dataclass
class GameScene:
    """游戏场景信息"""
    name: str  # 场景名称
    identifiers: List[str]  # 识别标识（模板名称或文本）
    click_points: Dict[str, ClickPoint]  # 点击点集合
    next_scenes: List[str] = None  # 可能的下一个场景
    
    def __post_init__(self):
        if self.next_scenes is None:
            self.next_scenes = []


class BaseGameController(LoggerMixin, ABC):
    """
    游戏控制器基类
    提供游戏控制的通用功能
    """
    
    def __init__(self, 
                 adb_service: ADBService,
                 config: Optional[GameConfig] = None,
                 image_recognizer: Optional[ImageRecognizer] = None,
                 ocr_engine: Optional[OCREngine] = None):
        """
        初始化游戏控制器
        
        Args:
            adb_service: ADB服务
            config: 游戏配置
            image_recognizer: 图像识别器
            ocr_engine: OCR引擎
        """
        self.adb = adb_service
        self.config = config or GameConfig()
        self.recognizer = image_recognizer or ImageRecognizer()
        self.ocr = ocr_engine or OCREngine()
        
        self._state = GameState.STOPPED
        self._current_scene: Optional[str] = None
        self._scenes: Dict[str, GameScene] = {}
        self._state_listeners: List[Callable] = []
        
        # 初始化场景
        self._init_scenes()
        
        self.logger.info(f"GameController initialized for {self.config.package_name}")
    
    @property
    def state(self) -> GameState:
        """获取当前游戏状态"""
        return self._state
    
    @state.setter
    def state(self, value: GameState) -> None:
        """设置游戏状态"""
        if value != self._state:
            old_state = self._state
            self._state = value
            self._notify_state_change(old_state, value)
            self.logger.info(f"Game state changed: {old_state.value} -> {value.value}")
    
    @property
    def current_scene(self) -> Optional[str]:
        """获取当前场景"""
        return self._current_scene
    
    @abstractmethod
    def _init_scenes(self) -> None:
        """初始化游戏场景（子类实现）"""
        pass
    
    def add_scene(self, scene: GameScene) -> None:
        """
        添加游戏场景
        
        Args:
            scene: 场景对象
        """
        self._scenes[scene.name] = scene
        self.logger.debug(f"Scene added: {scene.name}")
    
    @retry_on_game_error(max_attempts=3)
    def start_game(self, wait_for_main: bool = True, timeout: float = 30.0) -> bool:
        """
        启动游戏
        
        Args:
            wait_for_main: 是否等待进入主界面
            timeout: 超时时间
        
        Returns:
            是否启动成功
        """
        try:
            self.state = GameState.STARTING
            
            # 检查游戏是否已运行
            if self.is_game_running():
                self.logger.info("Game is already running, bringing to foreground...")
                # 将游戏切换到前台
                if self.adb.bring_app_to_foreground(self.config.package_name):
                    self.logger.info("Game brought to foreground successfully")
                    self.state = GameState.IN_GAME
                    return True
                else:
                    self.logger.warning("Failed to bring game to foreground, trying to restart...")
                    # 如果切换失败，继续尝试重新启动
            
            # 启动应用
            # 如果有 main_activity 则传递，否则只传包名让 ADB 自动启动
            activity = getattr(self.config, 'main_activity', None)
            if not self.adb.start_app(self.config.package_name, activity):
                raise GameStartupError("Failed to start game app")
            
            self.state = GameState.LOADING
            
            # 等待进入主界面
            if wait_for_main:
                if not self.wait_for_scene("main_menu", timeout):
                    raise GameLoadingTimeoutError(f"Game loading timeout after {timeout}s")
            
            self.state = GameState.IN_GAME
            self.logger.info("Game started successfully")
            return True
            
        except Exception as e:
            self.state = GameState.ERROR
            self.logger.error(f"Failed to start game: {e}")
            raise
    
    def stop_game(self) -> bool:
        """
        停止游戏
        
        Returns:
            是否停止成功
        """
        try:
            if self.adb.stop_app(self.config.package_name):
                self.state = GameState.STOPPED
                self._current_scene = None
                self.logger.info("Game stopped")
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to stop game: {e}")
            return False
    
    def is_game_running(self) -> bool:
        """
        检查游戏是否在运行
        
        Returns:
            是否在运行
        """
        return self.adb.is_app_running(self.config.package_name)
    
    def screenshot(self) -> Image.Image:
        """
        截取游戏画面
        
        Returns:
            截图图像
        """
        if not self.is_game_running():
            raise GameNotRunningError()
        
        return self.adb.screenshot()
    
    def detect_scene(self, screenshot: Optional[Image.Image] = None) -> Optional[str]:
        """
        检测当前场景
        
        Args:
            screenshot: 截图，如果为None则自动截图
        
        Returns:
            场景名称
        """
        if screenshot is None:
            screenshot = self.screenshot()
        
        for scene_name, scene in self._scenes.items():
            # 尝试通过标识符识别场景
            for identifier in scene.identifiers:
                # 尝试图像识别
                if self.recognizer.find_template(screenshot, identifier, threshold=0.8):
                    self._current_scene = scene_name
                    self.logger.debug(f"Scene detected by image: {scene_name}")
                    return scene_name
                
                # 尝试文字识别
                if self.ocr.find_text(screenshot, identifier):
                    self._current_scene = scene_name
                    self.logger.debug(f"Scene detected by text: {scene_name}")
                    return scene_name
        
        self._current_scene = None
        return None
    
    def wait_for_scene(self, scene_name: str, timeout: float = 10.0, interval: float = 1.0) -> bool:
        """
        等待特定场景出现
        
        Args:
            scene_name: 场景名称
            timeout: 超时时间
            interval: 检查间隔
        
        Returns:
            是否成功等待到场景
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            current_scene = self.detect_scene()
            if current_scene == scene_name:
                self.logger.info(f"Scene '{scene_name}' detected after {time.time() - start_time:.2f}s")
                return True
            
            time.sleep(interval)
        
        self.logger.warning(f"Scene '{scene_name}' not found after {timeout}s")
        return False
    
    def click_point(self, point: Union[ClickPoint, str, Tuple[int, int]], 
                   wait_after: Optional[float] = None) -> None:
        """
        点击指定位置
        
        Args:
            point: 点击点（ClickPoint对象、点击点名称或坐标）
            wait_after: 点击后等待时间
        """
        # 解析点击点
        if isinstance(point, str):
            # 从当前场景获取点击点
            if self._current_scene and self._current_scene in self._scenes:
                scene = self._scenes[self._current_scene]
                if point in scene.click_points:
                    point = scene.click_points[point]
                else:
                    raise ValueError(f"Click point '{point}' not found in scene '{self._current_scene}'")
            else:
                raise ValueError("Current scene not detected")
        
        # 执行点击
        if isinstance(point, ClickPoint):
            self.adb.tap(point.x, point.y)
            wait_time = wait_after or point.wait_after
            self.logger.debug(f"Clicked {point.name} at ({point.x}, {point.y})")
        elif isinstance(point, tuple) and len(point) == 2:
            self.adb.tap(point[0], point[1])
            wait_time = wait_after or 1.0
            self.logger.debug(f"Clicked at ({point[0]}, {point[1]})")
        else:
            raise ValueError(f"Invalid click point: {point}")
        
        # 等待
        if wait_time > 0:
            time.sleep(wait_time)
    
    def click_template(self, template_name: str, 
                      screenshot: Optional[Image.Image] = None,
                      threshold: float = 0.8,
                      wait_after: float = 1.0) -> bool:
        """
        点击模板匹配的位置
        
        Args:
            template_name: 模板名称
            screenshot: 截图
            threshold: 匹配阈值
            wait_after: 点击后等待时间
        
        Returns:
            是否成功点击
        """
        if screenshot is None:
            screenshot = self.screenshot()
        
        result = self.recognizer.find_template(screenshot, template_name, threshold)
        if result:
            self.adb.tap(result.center[0], result.center[1])
            self.logger.debug(f"Clicked template '{template_name}' at {result.center}")
            
            if wait_after > 0:
                time.sleep(wait_after)
            return True
        
        return False
    
    def click_text(self, text: str,
                  screenshot: Optional[Image.Image] = None,
                  exact_match: bool = False,
                  wait_after: float = 1.0) -> bool:
        """
        点击文字位置
        
        Args:
            text: 要点击的文字
            screenshot: 截图
            exact_match: 是否精确匹配
            wait_after: 点击后等待时间
        
        Returns:
            是否成功点击
        """
        if screenshot is None:
            screenshot = self.screenshot()
        
        result = self.ocr.find_text(screenshot, text, exact_match)
        if result:
            center_x = result.bbox[0] + result.bbox[2] // 2
            center_y = result.bbox[1] + result.bbox[3] // 2
            self.adb.tap(center_x, center_y)
            self.logger.debug(f"Clicked text '{text}' at ({center_x}, {center_y})")
            
            if wait_after > 0:
                time.sleep(wait_after)
            return True
        
        return False
    
    def swipe_direction(self, direction: str, distance: int = 500, duration: int = 500) -> None:
        """
        按方向滑动
        
        Args:
            direction: 方向 ('up', 'down', 'left', 'right')
            distance: 滑动距离
            duration: 滑动持续时间（毫秒）
        """
        # 获取屏幕中心
        if self.adb.current_device:
            width, height = self.adb.current_device.screen_resolution
        else:
            width, height = 1080, 1920  # 默认分辨率
        
        center_x = width // 2
        center_y = height // 2
        
        # 计算滑动坐标
        if direction == 'up':
            start = (center_x, center_y + distance // 2)
            end = (center_x, center_y - distance // 2)
        elif direction == 'down':
            start = (center_x, center_y - distance // 2)
            end = (center_x, center_y + distance // 2)
        elif direction == 'left':
            start = (center_x + distance // 2, center_y)
            end = (center_x - distance // 2, center_y)
        elif direction == 'right':
            start = (center_x - distance // 2, center_y)
            end = (center_x + distance // 2, center_y)
        else:
            raise ValueError(f"Invalid direction: {direction}")
        
        self.adb.swipe(start[0], start[1], end[0], end[1], duration)
        self.logger.debug(f"Swiped {direction} for {distance}px")
    
    def navigate_to_scene(self, target_scene: str, max_steps: int = 10) -> bool:
        """
        导航到指定场景
        
        Args:
            target_scene: 目标场景
            max_steps: 最大步数
        
        Returns:
            是否成功导航
        """
        steps = 0
        visited = set()
        
        while steps < max_steps:
            current = self.detect_scene()
            
            if current == target_scene:
                self.logger.info(f"Navigated to scene '{target_scene}' in {steps} steps")
                return True
            
            if current in visited:
                self.logger.warning(f"Scene loop detected at '{current}'")
                return False
            
            visited.add(current)
            
            # 查找导航路径
            if current and current in self._scenes:
                scene = self._scenes[current]
                if target_scene in scene.next_scenes:
                    # 直接导航
                    if self._navigate_step(current, target_scene):
                        steps += 1
                        continue
            
            # 无法继续导航
            self.logger.warning(f"Cannot navigate from '{current}' to '{target_scene}'")
            return False
        
        self.logger.warning(f"Max steps ({max_steps}) reached while navigating")
        return False
    
    @abstractmethod
    def _navigate_step(self, from_scene: str, to_scene: str) -> bool:
        """
        执行单步导航（子类实现）
        
        Args:
            from_scene: 起始场景
            to_scene: 目标场景
        
        Returns:
            是否成功
        """
        pass
    
    def wait_and_click(self, identifier: str, 
                      timeout: float = 10.0,
                      threshold: float = 0.8) -> bool:
        """
        等待并点击元素
        
        Args:
            identifier: 标识符（模板名称或文本）
            timeout: 超时时间
            threshold: 匹配阈值
        
        Returns:
            是否成功点击
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            screenshot = self.screenshot()
            
            # 尝试模板点击
            if self.click_template(identifier, screenshot, threshold):
                return True
            
            # 尝试文字点击
            if self.click_text(identifier, screenshot):
                return True
            
            time.sleep(0.5)
        
        return False
    
    def add_state_listener(self, listener: Callable[[GameState, GameState], None]) -> None:
        """
        添加状态监听器
        
        Args:
            listener: 监听器函数，接收(old_state, new_state)
        """
        if listener not in self._state_listeners:
            self._state_listeners.append(listener)
    
    def remove_state_listener(self, listener: Callable) -> None:
        """
        移除状态监听器
        
        Args:
            listener: 监听器函数
        """
        if listener in self._state_listeners:
            self._state_listeners.remove(listener)
    
    def _notify_state_change(self, old_state: GameState, new_state: GameState) -> None:
        """
        通知状态变化
        
        Args:
            old_state: 旧状态
            new_state: 新状态
        """
        for listener in self._state_listeners:
            try:
                listener(old_state, new_state)
            except Exception as e:
                self.logger.error(f"Error in state listener: {e}")
    
    @abstractmethod
    def perform_daily_tasks(self) -> Dict[str, bool]:
        """
        执行日常任务（子类实现）
        
        Returns:
            任务执行结果
        """
        pass
    
    @abstractmethod
    def collect_rewards(self) -> bool:
        """
        收集奖励（子类实现）
        
        Returns:
            是否成功
        """
        pass