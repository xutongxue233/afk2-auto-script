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
from src.controller.exit_dialog_handler import ExitDialogHandler


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
    
    def return_to_home(self, max_attempts: int = 10, debug_output: bool = False) -> bool:
        """
        返回到游戏首页
        
        策略：
        1. 查找返回按钮（两种样式）
        2. 如果找到返回按钮，点击它
        3. 如果没找到返回按钮，认为已经在首页
        
        Args:
            max_attempts: 最大尝试次数
            debug_output: 是否输出调试图片
            
        Returns:
            是否成功返回首页
        """
        from pathlib import Path
        import os
        from datetime import datetime
        from PIL import Image, ImageDraw
        import cv2
        import numpy as np
        
        # 返回按钮模板路径
        back_button_1_path = Path(__file__).parent.parent / 'resources' / 'images' / 'back_button_1.png'
        back_button_2_path = Path(__file__).parent.parent / 'resources' / 'images' / 'back_button_2.png'
        
        consecutive_no_button_count = 0  # 连续没找到返回按钮的次数
        
        for attempt in range(max_attempts):
            try:
                # 截取当前画面
                screenshot = self.screenshot()
                
                # 保存调试图片（如果启用）
                if debug_output:
                    width, height = screenshot.size
                    search_region = (0, 0, width, height)  # 全屏搜索返回按钮
                    self._save_debug_images(screenshot, search_region, 'return_attempt', attempt + 1)
                
                # 先检查是否有退出游戏弹窗
                is_exit_dialog, cancel_pos, _ = ExitDialogHandler.detect_exit_dialog(screenshot)
                if is_exit_dialog:
                    self.logger.info("Exit dialog detected, clicking cancel to close it")
                    if cancel_pos:
                        self.adb.tap(cancel_pos[0], cancel_pos[1])
                        time.sleep(0.5)
                        # 关闭弹窗后继续检查是否还有返回按钮
                        continue
                
                # 查找返回按钮（两种样式）
                back_button_found = False
                back_button_position = None
                
                # 尝试查找第一种返回按钮样式
                if self.recognizer and back_button_1_path.exists():
                    try:
                        result = self.recognizer.find_template(
                            screenshot,
                            'back_button_1',
                            threshold=0.7,
                            preprocessing='grayscale'  # 使用灰度匹配
                        )
                        if result:
                            back_button_found = True
                            back_button_position = result.center
                            self.logger.info(f"Found back button style 1 at {back_button_position}")
                    except Exception as e:
                        self.logger.debug(f"Failed to find back button 1: {e}")
                
                # 如果没找到，尝试第二种返回按钮样式
                if not back_button_found and self.recognizer and back_button_2_path.exists():
                    try:
                        result = self.recognizer.find_template(
                            screenshot,
                            'back_button_2',
                            threshold=0.7,
                            preprocessing='grayscale'  # 使用灰度匹配
                        )
                        if result:
                            back_button_found = True
                            back_button_position = result.center
                            self.logger.info(f"Found back button style 2 at {back_button_position}")
                    except Exception as e:
                        self.logger.debug(f"Failed to find back button 2: {e}")
                
                # 如果找到返回按钮，点击它
                if back_button_found and back_button_position:
                    self.logger.info(f"Clicking back button at {back_button_position} (attempt {attempt + 1}/{max_attempts})")
                    self.adb.tap(back_button_position[0], back_button_position[1])
                    time.sleep(1.5)  # 等待界面响应
                    consecutive_no_button_count = 0  # 重置计数器
                    # 继续循环，检查是否还有更多返回按钮
                    continue
                else:
                    # 没有找到返回按钮
                    consecutive_no_button_count += 1
                    self.logger.info(f"No back button found (consecutive count: {consecutive_no_button_count})")
                    
                    # 如果连续2次没找到返回按钮，认为已经在首页
                    if consecutive_no_button_count >= 2:
                        self.logger.info("No back button found for 2 consecutive attempts, assuming we are at home screen")
                        
                        # 最后再检查一次是否有退出游戏弹窗需要处理
                        screenshot = self.screenshot()
                        is_exit_dialog, cancel_pos, _ = ExitDialogHandler.detect_exit_dialog(screenshot)
                        if is_exit_dialog:
                            self.logger.info("Final check: Exit dialog detected, closing it")
                            if cancel_pos:
                                self.adb.tap(cancel_pos[0], cancel_pos[1])
                                time.sleep(0.5)
                        
                        # 额外验证：尝试识别主界面元素（如神秘屋）
                        try:
                            mystery_result = self.recognizer.find_template(
                                screenshot,
                                'mystery_house',
                                threshold=0.6,
                                preprocessing='grayscale'
                            )
                            if mystery_result:
                                self.logger.info("Mystery house icon found, confirming home screen")
                        except:
                            pass
                        
                        return True
                    
                    # 等待一下再重试
                    time.sleep(1.0)
                
            except Exception as e:
                self.logger.error(f"Error returning to home: {e}")
        
        self.logger.warning(f"Failed to return to home after {max_attempts} attempts")
        return False
    
    def _save_debug_images(self, screenshot: Image.Image, search_region: Tuple[int, int, int, int], 
                          stage: str, attempt: int) -> None:
        """
        保存调试图片：识别区域、滤镜处理后的区域和模板
        
        Args:
            screenshot: 全屏截图
            search_region: 搜索区域 (x, y, width, height)
            stage: 阶段标识
            attempt: 尝试次数
        """
        try:
            # 在保存调试图片后，立即尝试识别并记录结果
            self._test_recognition_methods(screenshot, search_region, stage, attempt)
            from datetime import datetime
            from PIL import Image, ImageDraw
            import cv2
            import numpy as np
            import os
            from pathlib import Path
            
            # 创建调试目录
            debug_dir = Path(__file__).parent.parent / 'debug' / 'home_detection'
            debug_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prefix = f"{stage}_attempt{attempt}_{timestamp}"
            
            # 1. 保存带识别区域标记的全屏截图
            marked_screenshot = screenshot.copy()
            draw = ImageDraw.Draw(marked_screenshot)
            x, y, w, h = search_region
            # 绘制红色矩形框标记识别区域
            draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=3)
            # 添加文字标注
            draw.text((x, y - 20), f"Search Region ({w}x{h})", fill=(255, 0, 0))
            marked_screenshot.save(debug_dir / f"{prefix}_1_marked_region.png")
            self.logger.debug(f"Saved marked region: {prefix}_1_marked_region.png")
            
            # 2. 保存裁剪的识别区域（高质量）
            region_image = screenshot.crop((x, y, x + w, y + h))
            region_image.save(debug_dir / f"{prefix}_2_region_original.png", quality=100, optimize=False)
            
            # 3. 保存不同滤镜处理后的区域图片
            # 转换为OpenCV格式，保持原始分辨率
            region_cv = cv2.cvtColor(np.array(region_image), cv2.COLOR_RGB2BGR)
            
            # 灰度处理（保持高质量）
            gray = cv2.cvtColor(region_cv, cv2.COLOR_BGR2GRAY)
            cv2.imwrite(str(debug_dir / f"{prefix}_3_region_grayscale.png"), gray, 
                       [cv2.IMWRITE_PNG_COMPRESSION, 0])  # 无损压缩
            
            # 二值化处理（高质量保存）
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            cv2.imwrite(str(debug_dir / f"{prefix}_4_region_binary.png"), binary,
                       [cv2.IMWRITE_PNG_COMPRESSION, 0])  # 无损压缩
            
            # 自适应阈值
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                            cv2.THRESH_BINARY, 11, 2)
            cv2.imwrite(str(debug_dir / f"{prefix}_5_region_adaptive.png"), adaptive)
            
            # Canny边缘检测
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            cv2.imwrite(str(debug_dir / f"{prefix}_6_region_canny.png"), edges)
            
            # 4. 保存模板图片的不同滤镜处理
            try:
                # 加载模板
                template_path = Path(__file__).parent.parent / 'resources' / 'images' / 'home_indicator.png'
                if template_path.exists():
                    template = cv2.imread(str(template_path))
                    if template is not None:
                        # 原始模板
                        cv2.imwrite(str(debug_dir / f"{prefix}_7_template_original.png"), template)
                        
                        # 灰度模板
                        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
                        cv2.imwrite(str(debug_dir / f"{prefix}_8_template_grayscale.png"), template_gray)
                        
                        # 二值化模板
                        _, template_binary = cv2.threshold(template_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                        cv2.imwrite(str(debug_dir / f"{prefix}_9_template_binary.png"), template_binary)
                        
                        # 模板的Canny边缘检测（用于轮廓匹配）
                        template_edges = cv2.Canny(template_gray, 50, 150)
                        cv2.imwrite(str(debug_dir / f"{prefix}_10_template_canny.png"), template_edges)
                        
                        # 对比显示：将区域和模板的边缘图放在一起
                        comparison = np.zeros((max(edges.shape[0], template_edges.shape[0]), 
                                              edges.shape[1] + template_edges.shape[1] + 20), dtype=np.uint8)
                        comparison[:edges.shape[0], :edges.shape[1]] = edges
                        comparison[:template_edges.shape[0], edges.shape[1]+20:] = template_edges
                        cv2.imwrite(str(debug_dir / f"{prefix}_11_edge_comparison.png"), comparison)
                        
                        self.logger.info(f"Debug images saved to: {debug_dir}/{prefix}_*.png")
            except Exception as e:
                self.logger.warning(f"Failed to process template: {e}")
                
        except Exception as e:
            self.logger.error(f"Failed to save debug images: {e}")
    
    def _test_recognition_methods(self, screenshot: Image.Image, search_region: Tuple[int, int, int, int],
                                 stage: str, attempt: int) -> None:
        """
        测试不同的识别方法并记录结果
        """
        try:
            self.logger.info(f"\n===== Recognition Test for {stage} attempt {attempt} =====")
            
            # 测试所有预处理方法，包括轮廓匹配
            # 先测试轮廓匹配
            self.logger.info("Testing contour matching...")
            for threshold in [0.3, 0.35, 0.4, 0.45, 0.5]:
                try:
                    result = self.recognizer.find_template(
                        screenshot,
                        'home_indicator',
                        threshold=threshold,
                        use_contour=True,
                        region=search_region
                    )
                    
                    if result:
                        self.logger.info(f"  ✓ CONTOUR SUCCESS @ {threshold:.2f} -> confidence={result.confidence:.3f}, pos={result.position}")
                    else:
                        self.logger.debug(f"  ✗ CONTOUR FAILED @ {threshold:.2f}")
                except Exception as e:
                    self.logger.debug(f"  ✗ CONTOUR ERROR @ {threshold:.2f} - {e}")
            
            # 测试其他预处理方法
            methods = ['canny', 'grayscale', 'binary', 'adaptive', 'none']
            thresholds = [0.3, 0.4, 0.5, 0.6]
            
            for method in methods:
                for threshold in thresholds:
                    try:
                        result = self.recognizer.find_template(
                            screenshot,
                            'home_indicator',
                            threshold=threshold,
                            preprocessing=method,
                            region=search_region,
                            method='TM_CCOEFF_NORMED'
                        )
                        
                        if result:
                            self.logger.info(f"  ✓ SUCCESS: {method} @ {threshold:.1f} -> confidence={result.confidence:.3f}, pos={result.position}")
                        else:
                            self.logger.debug(f"  ✗ FAILED: {method} @ {threshold:.1f}")
                    except Exception as e:
                        self.logger.debug(f"  ✗ ERROR: {method} @ {threshold:.1f} - {e}")
            
            self.logger.info("===== End of Recognition Test =====")
            
        except Exception as e:
            self.logger.error(f"Recognition test failed: {e}")
    
    def _check_and_handle_exit_dialog(self, screenshot: Image.Image) -> bool:
        """
        检查并处理退出游戏弹窗
        
        Args:
            screenshot: 当前截图
            
        Returns:
            是否检测到并处理了退出弹窗
        """
        try:
            width, height = screenshot.size
            
            # 方法1：通过按钮位置和颜色特征检测
            # 根据截图，X按钮在左侧，✓按钮在右侧，都是圆形按钮
            # 按钮区域大约在屏幕60-65%高度位置
            try:
                # 定义按钮位置（基于截图观察）
                cancel_button_region = (
                    int(width * 0.25),   # x: 25%位置
                    int(height * 0.58),  # y: 58%位置
                    int(width * 0.20),   # width: 20%宽度
                    int(height * 0.10)   # height: 10%高度
                )
                
                confirm_button_region = (
                    int(width * 0.55),   # x: 55%位置
                    int(height * 0.58),  # y: 58%位置
                    int(width * 0.20),   # width: 20%宽度
                    int(height * 0.10)   # height: 10%高度
                )
                
                # 尝试识别取消按钮（X图标）
                cancel_result = self.recognizer.find_template(
                    screenshot,
                    'cancel_button',  # X按钮模板
                    threshold=0.6,
                    preprocessing='auto',
                    region=cancel_button_region
                )
                
                if cancel_result:
                    # 验证确认按钮也存在
                    confirm_result = self.recognizer.find_template(
                        screenshot,
                        'confirm_button',  # ✓按钮模板
                        threshold=0.6,
                        preprocessing='auto',
                        region=confirm_button_region
                    )
                    
                    if confirm_result:
                        # 两个按钮都存在，确认是退出弹窗
                        self.logger.info("Exit dialog detected via button icons")
                        # 点击取消按钮（X按钮）
                        self.adb.tap(cancel_result.center[0], cancel_result.center[1])
                        time.sleep(0.5)
                        return True
            except:
                pass
            
            # 方法2：通过OCR检测文字
            if self.ocr:
                try:
                    # 只检测弹窗区域的文字（中央40-50%高度）
                    dialog_region = (
                        int(width * 0.2),   # x: 20%
                        int(height * 0.4),  # y: 40%
                        int(width * 0.6),   # width: 60%
                        int(height * 0.15)  # height: 15%
                    )
                    
                    # 裁剪弹窗区域进行OCR
                    dialog_image = screenshot.crop((
                        dialog_region[0], 
                        dialog_region[1],
                        dialog_region[0] + dialog_region[2],
                        dialog_region[1] + dialog_region[3]
                    ))
                    
                    text_results = self.ocr.recognize(dialog_image)
                    exit_keywords = ['退出游戏', '确定要退出', '确定退出', '是否退出', '退出']
                    
                    if any(keyword in text_results for keyword in exit_keywords):
                        self.logger.info(f"Exit dialog detected via OCR: {text_results}")
                        
                        # 根据截图精确计算取消按钮位置
                        # X按钮在左侧，大约在35%水平，62%垂直位置
                        cancel_x = int(width * 0.35)  # 左侧X按钮
                        cancel_y = int(height * 0.62)  # 按钮垂直位置
                        
                        self.logger.info(f"Clicking X button at ({cancel_x}, {cancel_y})")
                        self.adb.tap(cancel_x, cancel_y)
                        time.sleep(0.5)
                        return True
                except Exception as e:
                    self.logger.debug(f"OCR check failed: {e}")
            
            # 方法3：通过固定位置点击（备用方案）
            # 如果检测到类似弹窗的模糊背景特征，直接点击取消位置
            try:
                # 检测中央是否有弹窗（通过检测模糊背景或半透明遮罩）
                # 这里可以通过检测屏幕中央区域的亮度变化来判断
                import cv2
                import numpy as np
                
                # 转换为OpenCV格式
                screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(screenshot_cv, cv2.COLOR_BGR2GRAY)
                
                # 检查中央区域亮度
                center_region = gray[
                    int(height * 0.4):int(height * 0.6),
                    int(width * 0.3):int(width * 0.7)
                ]
                mean_brightness = np.mean(center_region)
                
                # 检查边缘区域亮度（作为对比）
                edge_region = gray[
                    int(height * 0.1):int(height * 0.2),
                    int(width * 0.1):int(width * 0.9)
                ]
                edge_brightness = np.mean(edge_region)
                
                # 如果中央明显比边缘亮，可能有弹窗
                if mean_brightness > edge_brightness + 30:
                    self.logger.debug(f"Possible dialog detected by brightness: center={mean_brightness:.1f}, edge={edge_brightness:.1f}")
                    # 可以尝试点击取消位置，但这个方法不够可靠，所以只记录不执行
            except:
                pass
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Exit dialog check failed: {e}")
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