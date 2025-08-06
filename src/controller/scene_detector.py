"""
场景检测器
用于识别和分析游戏场景
"""

import time
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from PIL import Image
import numpy as np

from src.services.log_service import LoggerMixin
from src.recognition.image_recognizer import ImageRecognizer
from src.recognition.ocr_engine import OCREngine
from src.utils.exceptions import SceneRecognitionError


@dataclass
class SceneFeature:
    """场景特征"""
    name: str  # 特征名称
    type: str  # 特征类型 ('image', 'text', 'color')
    value: Any  # 特征值
    region: Optional[Tuple[int, int, int, int]] = None  # 检测区域
    threshold: float = 0.8  # 匹配阈值
    weight: float = 1.0  # 特征权重


@dataclass
class SceneDetectionResult:
    """场景检测结果"""
    scene_name: str  # 场景名称
    confidence: float  # 置信度
    matched_features: List[str]  # 匹配的特征
    detection_time: float  # 检测耗时（秒）
    timestamp: float  # 时间戳


class SceneDetector(LoggerMixin):
    """
    场景检测器
    负责识别游戏当前所在的场景
    """
    
    def __init__(self,
                 image_recognizer: Optional[ImageRecognizer] = None,
                 ocr_engine: Optional[OCREngine] = None):
        """
        初始化场景检测器
        
        Args:
            image_recognizer: 图像识别器
            ocr_engine: OCR引擎
        """
        self.recognizer = image_recognizer or ImageRecognizer()
        self.ocr = ocr_engine or OCREngine()
        
        # 场景定义
        self._scenes: Dict[str, List[SceneFeature]] = {}
        
        # 检测缓存
        self._cache_enabled = True
        self._cache_timeout = 2.0  # 缓存超时时间（秒）
        self._last_result: Optional[SceneDetectionResult] = None
        
        # 初始化场景定义
        self._init_scenes()
        
        self.logger.info("SceneDetector initialized")
    
    def _init_scenes(self) -> None:
        """初始化场景定义"""
        # 这里可以加载预定义的场景特征
        # 子类可以覆盖此方法来定义具体游戏的场景
        pass
    
    def register_scene(self, scene_name: str, features: List[SceneFeature]) -> None:
        """
        注册场景
        
        Args:
            scene_name: 场景名称
            features: 场景特征列表
        """
        self._scenes[scene_name] = features
        self.logger.debug(f"Scene registered: {scene_name} with {len(features)} features")
    
    def detect_scene(self, screenshot: Image.Image,
                    use_cache: bool = True) -> Optional[SceneDetectionResult]:
        """
        检测当前场景
        
        Args:
            screenshot: 截图
            use_cache: 是否使用缓存
        
        Returns:
            场景检测结果
        """
        start_time = time.time()
        
        # 检查缓存
        if use_cache and self._cache_enabled and self._last_result:
            if time.time() - self._last_result.timestamp < self._cache_timeout:
                self.logger.debug(f"Using cached scene: {self._last_result.scene_name}")
                return self._last_result
        
        # 检测所有场景
        best_result = None
        best_confidence = 0.0
        
        for scene_name, features in self._scenes.items():
            confidence, matched = self._match_scene_features(screenshot, features)
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_result = SceneDetectionResult(
                    scene_name=scene_name,
                    confidence=confidence,
                    matched_features=matched,
                    detection_time=time.time() - start_time,
                    timestamp=time.time()
                )
        
        # 缓存结果
        if best_result and best_confidence > 0.5:
            self._last_result = best_result
            self.logger.info(f"Scene detected: {best_result.scene_name} (confidence: {best_confidence:.2f})")
            return best_result
        
        self.logger.warning("No scene detected")
        return None
    
    def _match_scene_features(self, screenshot: Image.Image,
                             features: List[SceneFeature]) -> Tuple[float, List[str]]:
        """
        匹配场景特征
        
        Args:
            screenshot: 截图
            features: 特征列表
        
        Returns:
            (置信度, 匹配的特征名称列表)
        """
        total_weight = sum(f.weight for f in features)
        matched_weight = 0.0
        matched_features = []
        
        for feature in features:
            if self._match_single_feature(screenshot, feature):
                matched_weight += feature.weight
                matched_features.append(feature.name)
                self.logger.debug(f"Feature matched: {feature.name}")
        
        confidence = matched_weight / total_weight if total_weight > 0 else 0.0
        return confidence, matched_features
    
    def _match_single_feature(self, screenshot: Image.Image,
                             feature: SceneFeature) -> bool:
        """
        匹配单个特征
        
        Args:
            screenshot: 截图
            feature: 特征
        
        Returns:
            是否匹配
        """
        try:
            # 裁剪区域
            if feature.region:
                x, y, w, h = feature.region
                region_img = screenshot.crop((x, y, x + w, y + h))
            else:
                region_img = screenshot
            
            # 根据特征类型进行匹配
            if feature.type == 'image':
                # 图像模板匹配
                result = self.recognizer.find_template(
                    region_img,
                    feature.value,
                    threshold=feature.threshold
                )
                return result is not None
                
            elif feature.type == 'text':
                # 文字识别
                result = self.ocr.find_text(
                    region_img,
                    feature.value,
                    exact_match=False
                )
                return result is not None
                
            elif feature.type == 'color':
                # 颜色检测
                return self._match_color(region_img, feature.value, feature.threshold)
                
            else:
                self.logger.warning(f"Unknown feature type: {feature.type}")
                return False
                
        except Exception as e:
            self.logger.error(f"Feature matching error: {e}")
            return False
    
    def _match_color(self, image: Image.Image,
                    target_color: Tuple[int, int, int],
                    threshold: float) -> bool:
        """
        匹配颜色
        
        Args:
            image: 图像
            target_color: 目标颜色 (R, G, B)
            threshold: 匹配阈值
        
        Returns:
            是否匹配
        """
        # 转换为numpy数组
        img_array = np.array(image)
        
        # 计算平均颜色
        avg_color = img_array.mean(axis=(0, 1))
        
        # 计算颜色距离
        distance = np.linalg.norm(avg_color - np.array(target_color))
        max_distance = np.linalg.norm([255, 255, 255])
        similarity = 1.0 - (distance / max_distance)
        
        return similarity >= threshold
    
    def wait_for_scene(self, scene_name: str,
                      screenshot_func: callable,
                      timeout: float = 10.0,
                      interval: float = 1.0) -> bool:
        """
        等待特定场景出现
        
        Args:
            scene_name: 场景名称
            screenshot_func: 截图函数
            timeout: 超时时间
            interval: 检查间隔
        
        Returns:
            是否成功等待到场景
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            screenshot = screenshot_func()
            result = self.detect_scene(screenshot, use_cache=False)
            
            if result and result.scene_name == scene_name:
                self.logger.info(f"Scene '{scene_name}' appeared after {time.time() - start_time:.2f}s")
                return True
            
            time.sleep(interval)
        
        self.logger.warning(f"Scene '{scene_name}' did not appear within {timeout}s")
        return False
    
    def wait_for_scene_change(self, screenshot_func: callable,
                             timeout: float = 10.0,
                             interval: float = 0.5) -> Optional[str]:
        """
        等待场景变化
        
        Args:
            screenshot_func: 截图函数
            timeout: 超时时间
            interval: 检查间隔
        
        Returns:
            新场景名称
        """
        # 获取初始场景
        initial_screenshot = screenshot_func()
        initial_result = self.detect_scene(initial_screenshot, use_cache=False)
        initial_scene = initial_result.scene_name if initial_result else None
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            screenshot = screenshot_func()
            result = self.detect_scene(screenshot, use_cache=False)
            current_scene = result.scene_name if result else None
            
            if current_scene != initial_scene:
                self.logger.info(f"Scene changed from '{initial_scene}' to '{current_scene}'")
                return current_scene
            
            time.sleep(interval)
        
        self.logger.warning(f"Scene did not change within {timeout}s")
        return None
    
    def get_scene_confidence(self, screenshot: Image.Image,
                            scene_name: str) -> float:
        """
        获取特定场景的置信度
        
        Args:
            screenshot: 截图
            scene_name: 场景名称
        
        Returns:
            置信度 (0-1)
        """
        if scene_name not in self._scenes:
            return 0.0
        
        features = self._scenes[scene_name]
        confidence, _ = self._match_scene_features(screenshot, features)
        return confidence
    
    def analyze_screenshot(self, screenshot: Image.Image) -> Dict[str, float]:
        """
        分析截图，返回所有场景的置信度
        
        Args:
            screenshot: 截图
        
        Returns:
            场景置信度字典
        """
        results = {}
        
        for scene_name in self._scenes:
            confidence = self.get_scene_confidence(screenshot, scene_name)
            if confidence > 0:
                results[scene_name] = confidence
        
        # 按置信度排序
        results = dict(sorted(results.items(), key=lambda x: x[1], reverse=True))
        
        self.logger.debug(f"Scene analysis: {results}")
        return results
    
    def clear_cache(self) -> None:
        """清除检测缓存"""
        self._last_result = None
        self.logger.debug("Scene detection cache cleared")
    
    def set_cache_timeout(self, timeout: float) -> None:
        """
        设置缓存超时时间
        
        Args:
            timeout: 超时时间（秒）
        """
        self._cache_timeout = timeout
        self.logger.debug(f"Cache timeout set to {timeout}s")
    
    def enable_cache(self, enabled: bool = True) -> None:
        """
        启用/禁用缓存
        
        Args:
            enabled: 是否启用
        """
        self._cache_enabled = enabled
        if not enabled:
            self.clear_cache()
        self.logger.debug(f"Cache {'enabled' if enabled else 'disabled'}")


class AFK2SceneDetector(SceneDetector):
    """
    AFK2游戏场景检测器
    """
    
    def _init_scenes(self) -> None:
        """初始化AFK2场景定义"""
        
        # 主界面场景
        self.register_scene("main", [
            SceneFeature("main_menu_icon", "image", "main_menu_icon", weight=2.0),
            SceneFeature("campaign_button", "text", "征战", region=(400, 1700, 280, 200)),
            SceneFeature("hero_button", "text", "英雄", region=(100, 1700, 200, 200)),
            SceneFeature("main_bg_color", "color", (45, 85, 120), region=(0, 0, 100, 100), threshold=0.7)
        ])
        
        # 战斗场景
        self.register_scene("battle", [
            SceneFeature("auto_button", "image", "auto_button", region=(900, 350, 180, 100), weight=2.0),
            SceneFeature("battle_ui", "image", "battle_ui"),
            SceneFeature("hp_bar", "color", (255, 50, 50), region=(100, 100, 200, 50), threshold=0.6)
        ])
        
        # 战斗结果场景
        self.register_scene("battle_result", [
            SceneFeature("victory_text", "text", "胜利", weight=2.0),
            SceneFeature("defeat_text", "text", "失败", weight=2.0),
            SceneFeature("reward_text", "text", "获得奖励"),
            SceneFeature("continue_button", "text", "点击继续")
        ])
        
        # 征战场景
        self.register_scene("campaign", [
            SceneFeature("campaign_title", "text", "征战", region=(400, 100, 280, 100), weight=2.0),
            SceneFeature("challenge_button", "text", "挑战", region=(400, 1500, 280, 200)),
            SceneFeature("stage_info", "image", "stage_info")
        ])
        
        # 英雄场景
        self.register_scene("hero", [
            SceneFeature("hero_title", "text", "英雄", region=(400, 100, 280, 100), weight=2.0),
            SceneFeature("upgrade_button", "text", "升级"),
            SceneFeature("hero_list", "image", "hero_list")
        ])
        
        # 背包场景
        self.register_scene("bag", [
            SceneFeature("bag_title", "text", "背包", region=(400, 100, 280, 100), weight=2.0),
            SceneFeature("item_grid", "image", "item_grid"),
            SceneFeature("sort_button", "text", "整理")
        ])
        
        # 加载场景
        self.register_scene("loading", [
            SceneFeature("loading_icon", "image", "loading_icon", weight=2.0),
            SceneFeature("loading_text", "text", "加载中"),
            SceneFeature("progress_bar", "color", (255, 200, 0), region=(300, 1000, 480, 50), threshold=0.6)
        ])