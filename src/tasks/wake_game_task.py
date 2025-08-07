"""
唤醒游戏任务
用于确保游戏处于运行状态并进入主界面
"""

import os
import time
from typing import Optional, Dict, Any
from datetime import datetime
from PIL import Image

from src.models.task import TaskInfo, TaskStatus, TaskType
from src.controller.base_controller import BaseGameController, GameState
from src.services.log_service import LoggerMixin
from src.recognition.image_recognizer import ImageRecognizer, Template
from src.services.adb_service import ADBService
import cv2
import numpy as np


class WakeGameTask(LoggerMixin):
    """
    唤醒游戏任务
    
    功能流程：
    1. 根据包名唤醒游戏（启动或切换到前台）
    2. 识别是否出现"点击开始游戏"按钮，如果出现则点击
    3. 等待并识别"神秘屋"图标，确认进入游戏主界面
    4. 识别到神秘屋后，任务完成
    """
    
    def __init__(self,
                 task_id: Optional[str] = None,
                 name: str = "唤醒游戏",
                 startup_timeout: float = 60.0,
                 **kwargs):
        """
        初始化唤醒游戏任务
        
        Args:
            task_id: 任务ID
            name: 任务名称
            startup_timeout: 启动超时时间（秒）
            **kwargs: 其他参数
        """
        super().__init__()
        
        self.task_id = task_id
        self.name = name
        self.startup_timeout = startup_timeout
        
        # 任务状态
        self.status = TaskStatus.PENDING
        self.started_at = None
        self.completed_at = None
        self.result = None
        
        # 任务结果
        self.was_already_running = False
        self.startup_time = 0.0
        
        # 图片资源路径
        self.image_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'resources', 'images', 'wake'
        )
        
        # 定义图片路径
        self.images = {
            'tap_to_start': os.path.join(self.image_dir, 'tap_to_start.png'),  # 点击开始游戏
            'mystery_house': os.path.join(self.image_dir, 'mystery_house.png')  # 神秘屋
        }
        
        # 验证图片文件是否存在
        self._validate_images()
        
        # 预加载模板
        self._templates = {}
        
        self.logger.info(f"WakeGameTask initialized: {self.name}")
    
    def _validate_images(self) -> None:
        """验证所需图片文件是否存在"""
        for name, path in self.images.items():
            if not os.path.exists(path):
                self.logger.warning(f"Image not found: {name} at {path}")
    
    def execute(self, controller: BaseGameController) -> bool:
        """
        执行唤醒游戏任务
        
        Args:
            controller: 游戏控制器
        
        Returns:
            是否执行成功
        """
        try:
            self.status = TaskStatus.RUNNING
            self.started_at = datetime.now()
            
            self.logger.info("开始执行唤醒游戏任务")
            
            # 记录开始时间
            start_time = time.time()
            
            # 步骤1：根据包名唤醒游戏
            if not self._wake_game_by_package(controller):
                self.logger.error("无法唤醒游戏")
                self.status = TaskStatus.FAILED
                self.result = {
                    "success": False,
                    "reason": "无法唤醒游戏"
                }
                return False
            
            # 等待游戏加载
            time.sleep(3)
            
            # 步骤2：检查并点击"点击开始游戏"按钮
            if not self._check_and_tap_start(controller):
                self.logger.warning("未能处理开始游戏界面")
            
            # 步骤3：等待并识别神秘屋，确认进入主界面
            if self._wait_for_mystery_house(controller):
                # 计算启动时间
                self.startup_time = time.time() - start_time
                
                self.logger.info(f"游戏唤醒成功，耗时: {self.startup_time:.1f}秒")
                
                self.result = {
                    "success": True,
                    "was_running": self.was_already_running,
                    "startup_time": self.startup_time
                }
                self.status = TaskStatus.COMPLETED
                self.completed_at = datetime.now()
                return True
            else:
                self.logger.error("超时：未能识别到神秘屋图标")
                self.result = {
                    "success": False,
                    "reason": "未能进入游戏主界面"
                }
                self.status = TaskStatus.FAILED
                self.completed_at = datetime.now()
                return False
                
        except Exception as e:
            self.logger.error(f"唤醒游戏任务执行异常: {e}")
            self.result = {
                "success": False,
                "reason": str(e),
                "was_running": self.was_already_running
            }
            self.status = TaskStatus.FAILED
            self.completed_at = datetime.now()
            return False
    
    def _wake_game_by_package(self, controller: BaseGameController) -> bool:
        """
        根据包名唤醒游戏
        
        Args:
            controller: 游戏控制器
        
        Returns:
            是否成功唤醒
        """
        try:
            # 获取游戏包名
            package_name = controller.config.package_name
            
            # 检查游戏是否已运行
            if controller.is_game_running():
                self.was_already_running = True
                self.logger.info(f"游戏 {package_name} 已在运行，尝试切换到前台...")
                
                # 将游戏切换到前台
                if controller.adb.bring_app_to_foreground(package_name):
                    self.logger.info("成功将游戏切换到前台")
                    return True
                else:
                    # 如果切换失败，尝试重新启动
                    self.logger.warning("切换前台失败，尝试重新启动游戏...")
            else:
                self.logger.info(f"游戏 {package_name} 未运行，开始启动...")
            
            # 启动游戏
            activity = getattr(controller.config, 'main_activity', None)
            if controller.adb.start_app(package_name, activity):
                self.logger.info("游戏启动成功")
                return True
            else:
                self.logger.error("游戏启动失败")
                return False
                
        except Exception as e:
            self.logger.error(f"唤醒游戏时出错: {e}")
            return False
    
    def _check_and_tap_start(self, controller: BaseGameController, 
                            max_attempts: int = 5) -> bool:
        """
        检查并点击"点击开始游戏"按钮
        
        Args:
            controller: 游戏控制器
            max_attempts: 最大尝试次数
        
        Returns:
            是否成功处理
        """
        try:
            # 加载模板图片
            tap_to_start_img = self._load_template_image('tap_to_start')
            if tap_to_start_img is None:
                self.logger.warning("无法加载'点击开始游戏'模板图片")
                return True  # 继续执行
            
            for attempt in range(max_attempts):
                # 截图
                screenshot = controller.adb.take_screenshot()
                if screenshot is None:
                    self.logger.error("无法获取截图")
                    time.sleep(2)
                    continue
                
                # 使用自定义方法识别模板
                result = self._find_template_in_image(screenshot, tap_to_start_img, threshold=0.7)
                
                if result:
                    x, y = result
                    self.logger.info(f"发现'点击开始游戏'按钮，位置: ({x}, {y})")
                    
                    # 点击按钮
                    controller.adb.tap(x, y)
                    self.logger.info("已点击开始游戏按钮")
                    
                    # 等待游戏加载
                    time.sleep(5)
                    return True
                else:
                    self.logger.debug(f"未发现开始游戏按钮 (尝试 {attempt + 1}/{max_attempts})")
                    
                    # 如果已经在游戏中（没有开始按钮），直接返回成功
                    if attempt > 1:
                        # 检查是否已经在游戏主界面
                        mystery_house_img = self._load_template_image('mystery_house')
                        if mystery_house_img is not None:
                            mystery_result = self._find_template_in_image(screenshot, mystery_house_img, threshold=0.7)
                            if mystery_result:
                                self.logger.info("已在游戏主界面，无需点击开始按钮")
                                return True
                    
                    time.sleep(2)
            
            # 没有找到开始按钮，可能已经在游戏中
            self.logger.info("未找到开始游戏按钮，可能已在游戏中")
            return True
            
        except Exception as e:
            self.logger.error(f"检查开始游戏按钮时出错: {e}")
            return False
    
    def _wait_for_mystery_house(self, controller: BaseGameController,
                               timeout: float = None) -> bool:
        """
        等待并识别神秘屋图标，确认进入游戏主界面
        
        Args:
            controller: 游戏控制器
            timeout: 超时时间，默认使用startup_timeout
        
        Returns:
            是否成功识别到神秘屋
        """
        if timeout is None:
            timeout = self.startup_timeout
        
        # 加载神秘屋模板图片
        mystery_house_img = self._load_template_image('mystery_house')
        if mystery_house_img is None:
            self.logger.error("无法加载'神秘屋'模板图片")
            return False
        
        start_time = time.time()
        check_interval = 2.0  # 检查间隔
        
        self.logger.info("等待识别神秘屋图标...")
        
        while time.time() - start_time < timeout:
            try:
                # 截图
                screenshot = controller.adb.take_screenshot()
                if screenshot is None:
                    self.logger.warning("无法获取截图")
                    time.sleep(check_interval)
                    continue
                
                # 使用自定义方法识别神秘屋图标
                result = self._find_template_in_image(screenshot, mystery_house_img, threshold=0.7)
                
                if result:
                    x, y = result
                    self.logger.info(f"成功识别到神秘屋图标，位置: ({x}, {y})")
                    self.logger.info("游戏已成功进入主界面")
                    return True
                else:
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    self.logger.debug(f"未识别到神秘屋，继续等待... (剩余 {remaining:.1f}秒)")
                
                time.sleep(check_interval)
                
            except Exception as e:
                self.logger.error(f"识别神秘屋时出错: {e}")
                time.sleep(check_interval)
        
        self.logger.warning(f"超时：{timeout}秒内未能识别到神秘屋图标")
        return False
    
    def get_info(self) -> Dict[str, Any]:
        """
        获取任务信息
        
        Returns:
            任务信息字典
        """
        info = {
            "task_id": self.task_id,
            "name": self.name,
            "status": self.status.value if self.status else None,
            "startup_timeout": self.startup_timeout,
            "was_already_running": self.was_already_running,
            "startup_time": self.startup_time,
            "result": self.result
        }
        return info
    
    def validate(self) -> bool:
        """
        验证任务参数
        
        Returns:
            是否有效
        """
        if self.startup_timeout <= 0:
            self.logger.error("启动超时时间必须大于0")
            return False
        
        # 验证图片文件
        for name, path in self.images.items():
            if not os.path.exists(path):
                self.logger.error(f"必需的图片文件不存在: {path}")
                return False
        
        return True
    
    def _load_template_image(self, name: str) -> Optional[np.ndarray]:
        """
        加载模板图片
        
        Args:
            name: 图片名称键
        
        Returns:
            OpenCV图像数组，加载失败返回None
        """
        if name in self._templates:
            return self._templates[name]
        
        if name not in self.images:
            self.logger.error(f"未定义图片: {name}")
            return None
        
        image_path = self.images[name]
        if not os.path.exists(image_path):
            self.logger.error(f"图片文件不存在: {image_path}")
            return None
        
        try:
            # 加载图片
            template = cv2.imread(image_path)
            if template is None:
                self.logger.error(f"无法加载图片: {image_path}")
                return None
            
            # 缓存模板
            self._templates[name] = template
            self.logger.debug(f"加载模板图片: {name}")
            return template
            
        except Exception as e:
            self.logger.error(f"加载图片时出错 {image_path}: {e}")
            return None
    
    def _find_template_in_image(self, screenshot: Image.Image, 
                                template: np.ndarray, 
                                threshold: float = 0.8) -> Optional[Tuple[int, int]]:
        """
        在截图中查找模板
        
        Args:
            screenshot: PIL截图
            template: OpenCV模板图像
            threshold: 匹配阈值
        
        Returns:
            匹配中心坐标(x, y)，未找到返回None
        """
        try:
            # 将PIL图像转换为OpenCV格式
            screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # 模板匹配
            result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
            
            # 找到最佳匹配位置
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= threshold:
                # 计算中心点
                template_height, template_width = template.shape[:2]
                center_x = max_loc[0] + template_width // 2
                center_y = max_loc[1] + template_height // 2
                
                self.logger.debug(f"找到模板匹配: 置信度={max_val:.2f}, 位置=({center_x}, {center_y})")
                return (center_x, center_y)
            else:
                self.logger.debug(f"模板匹配度不足: {max_val:.2f} < {threshold}")
                return None
                
        except Exception as e:
            self.logger.error(f"模板匹配时出错: {e}")
            return None


class QuickWakeTask(WakeGameTask):
    """
    快速唤醒任务
    跳过某些等待步骤，快速进入游戏
    """
    
    def __init__(self, **kwargs):
        super().__init__(
            name="快速唤醒游戏",
            startup_timeout=30.0,  # 更短的超时时间
            **kwargs
        )