"""
游戏控制器模块
提供游戏自动化控制功能
"""

from .base_controller import BaseGameController
from .afk2_controller import AFK2Controller
from .scene_detector import SceneDetector

__all__ = ['BaseGameController', 'AFK2Controller', 'SceneDetector']