"""
图像识别模块
提供模板匹配、特征点匹配等图像识别功能
"""

import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any, Union
from dataclasses import dataclass
import json
import hashlib

from src.services.log_service import LoggerMixin
from src.utils.exceptions import (
    ImageNotFoundError, ImageRecognitionError,
    TemplateNotFoundError, InvalidImageFormatError
)
from src.utils.retry import retry_on_recognition_error


@dataclass
class MatchResult:
    """
    匹配结果
    """
    confidence: float  # 置信度 (0-1)
    position: Tuple[int, int]  # 匹配位置 (x, y)
    size: Tuple[int, int]  # 匹配区域大小 (width, height)
    center: Tuple[int, int]  # 中心点坐标
    method: str  # 使用的匹配方法


@dataclass
class Template:
    """
    模板图像
    """
    name: str  # 模板名称
    path: Path  # 模板路径
    image: np.ndarray  # 图像数据
    mask: Optional[np.ndarray] = None  # 掩码（用于透明图像）
    threshold: float = 0.8  # 匹配阈值
    scale_range: Tuple[float, float] = (0.8, 1.2)  # 缩放范围
    rotation_range: Tuple[float, float] = (-10, 10)  # 旋转范围（度）
    method: str = 'TM_CCOEFF_NORMED'  # 匹配方法


class ImageRecognizer(LoggerMixin):
    """
    图像识别器
    提供各种图像识别功能
    """
    
    # 支持的匹配方法
    MATCH_METHODS = {
        'TM_SQDIFF': cv2.TM_SQDIFF,
        'TM_SQDIFF_NORMED': cv2.TM_SQDIFF_NORMED,
        'TM_CCORR': cv2.TM_CCORR,
        'TM_CCORR_NORMED': cv2.TM_CCORR_NORMED,
        'TM_CCOEFF': cv2.TM_CCOEFF,
        'TM_CCOEFF_NORMED': cv2.TM_CCOEFF_NORMED
    }
    
    # 支持的图像格式
    SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff'}
    
    def __init__(self, template_dir: Optional[Path] = None,
                 cache_templates: bool = True):
        """
        初始化图像识别器
        
        Args:
            template_dir: 模板图像目录
            cache_templates: 是否缓存模板
        """
        self.template_dir = template_dir or Path("templates")
        self.cache_templates = cache_templates
        self._template_cache: Dict[str, Template] = {}
        
        # 创建模板目录
        self.template_dir.mkdir(parents=True, exist_ok=True)
        
        # 特征检测器
        self._sift = None
        self._orb = None
        self._matcher = None
        
        self.logger.info(f"ImageRecognizer initialized with template dir: {self.template_dir}")
    
    def load_template(self, name: str, threshold: float = 0.8,
                     method: str = 'TM_CCOEFF_NORMED') -> Template:
        """
        加载模板图像
        
        Args:
            name: 模板名称（不含扩展名）
            threshold: 匹配阈值
            method: 匹配方法
        
        Returns:
            模板对象
        """
        # 检查缓存
        if self.cache_templates and name in self._template_cache:
            self.logger.debug(f"Using cached template: {name}")
            return self._template_cache[name]
        
        # 查找模板文件
        template_path = None
        for ext in self.SUPPORTED_FORMATS:
            path = self.template_dir / f"{name}{ext}"
            if path.exists():
                template_path = path
                break
        
        if not template_path:
            raise TemplateNotFoundError(name)
        
        try:
            # 加载图像
            image = cv2.imread(str(template_path), cv2.IMREAD_UNCHANGED)
            if image is None:
                raise InvalidImageFormatError(str(template_path))
            
            # 处理透明通道
            mask = None
            if image.shape[2] == 4:  # BGRA格式
                mask = image[:, :, 3]
                image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
            
            # 创建模板对象
            template = Template(
                name=name,
                path=template_path,
                image=image,
                mask=mask,
                threshold=threshold,
                method=method
            )
            
            # 缓存模板
            if self.cache_templates:
                self._template_cache[name] = template
            
            self.logger.info(f"Template loaded: {name} from {template_path}")
            return template
            
        except Exception as e:
            self.logger.error(f"Failed to load template '{name}': {e}")
            raise ImageRecognitionError(f"Failed to load template: {e}")
    
    def find_template(self, screenshot: Union[Image.Image, np.ndarray],
                     template: Union[str, Template],
                     threshold: Optional[float] = None,
                     method: Optional[str] = None,
                     region: Optional[Tuple[int, int, int, int]] = None,
                     use_grayscale: bool = True) -> Optional[MatchResult]:
        """
        在截图中查找模板
        
        Args:
            screenshot: 截图（PIL Image或numpy数组）
            template: 模板名称或模板对象
            threshold: 匹配阈值（覆盖模板默认值）
            method: 匹配方法（覆盖模板默认值）
            region: 搜索区域 (x, y, width, height)
            use_grayscale: 是否使用灰度处理
        
        Returns:
            匹配结果，未找到返回None
        """
        # 加载模板
        if isinstance(template, str):
            template = self.load_template(template)
        
        # 转换截图格式
        if isinstance(screenshot, Image.Image):
            screenshot = self._pil_to_cv2(screenshot)
        
        # 裁剪搜索区域
        if region:
            x, y, w, h = region
            screenshot = screenshot[y:y+h, x:x+w]
            region_offset = (x, y)
        else:
            region_offset = (0, 0)
        
        # 获取参数
        threshold = threshold or template.threshold
        method = method or template.method
        
        # 如果使用灰度处理
        if use_grayscale:
            # 转换为灰度图
            if len(screenshot.shape) == 3:
                screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            else:
                screenshot_gray = screenshot
            
            # 转换模板为灰度图
            if len(template.image.shape) == 3:
                template_gray = cv2.cvtColor(template.image, cv2.COLOR_BGR2GRAY)
            else:
                template_gray = template.image
            
            # 执行灰度模板匹配
            result = self._match_template_grayscale(
                screenshot_gray,
                template_gray,
                method
            )
        else:
            # 执行彩色模板匹配
            result = self._match_template(
                screenshot, 
                template.image,
                template.mask,
                method
            )
        
        if result and result['confidence'] >= threshold:
            # 计算实际坐标
            x = result['position'][0] + region_offset[0]
            y = result['position'][1] + region_offset[1]
            
            return MatchResult(
                confidence=result['confidence'],
                position=(x, y),
                size=(template.image.shape[1], template.image.shape[0]),
                center=(x + template.image.shape[1] // 2, 
                       y + template.image.shape[0] // 2),
                method=method
            )
        
        return None
    
    def find_all_templates(self, screenshot: Union[Image.Image, np.ndarray],
                          template: Union[str, Template],
                          threshold: Optional[float] = None,
                          max_count: int = 10,
                          min_distance: int = 20) -> List[MatchResult]:
        """
        查找所有匹配的模板
        
        Args:
            screenshot: 截图
            template: 模板
            threshold: 匹配阈值
            max_count: 最大匹配数量
            min_distance: 匹配点之间的最小距离
        
        Returns:
            匹配结果列表
        """
        # 加载模板
        if isinstance(template, str):
            template = self.load_template(template)
        
        # 转换截图格式
        if isinstance(screenshot, Image.Image):
            screenshot = self._pil_to_cv2(screenshot)
        
        threshold = threshold or template.threshold
        
        # 执行模板匹配
        result = cv2.matchTemplate(
            screenshot,
            template.image,
            self.MATCH_METHODS[template.method],
            mask=template.mask
        )
        
        # 查找所有匹配位置
        matches = []
        h, w = template.image.shape[:2]
        
        # 根据方法确定是否需要反转
        if template.method in ['TM_SQDIFF', 'TM_SQDIFF_NORMED']:
            locations = np.where(result <= 1 - threshold)
        else:
            locations = np.where(result >= threshold)
        
        # 转换为坐标列表
        points = list(zip(locations[1], locations[0]))
        
        # 非极大值抑制（去除重复）
        filtered_points = []
        for pt in points:
            too_close = False
            for existing in filtered_points:
                if abs(pt[0] - existing[0]) < min_distance and \
                   abs(pt[1] - existing[1]) < min_distance:
                    too_close = True
                    break
            
            if not too_close:
                filtered_points.append(pt)
                confidence = result[pt[1], pt[0]]
                
                matches.append(MatchResult(
                    confidence=float(confidence),
                    position=pt,
                    size=(w, h),
                    center=(pt[0] + w // 2, pt[1] + h // 2),
                    method=template.method
                ))
                
                if len(matches) >= max_count:
                    break
        
        # 按置信度排序
        matches.sort(key=lambda x: x.confidence, reverse=True)
        
        self.logger.debug(f"Found {len(matches)} matches for template '{template.name}'")
        return matches
    
    def find_by_feature(self, screenshot: Union[Image.Image, np.ndarray],
                       template: Union[str, Template, np.ndarray],
                       min_matches: int = 10,
                       detector: str = 'ORB') -> Optional[MatchResult]:
        """
        使用特征点匹配查找图像
        
        Args:
            screenshot: 截图
            template: 模板
            min_matches: 最小匹配点数
            detector: 特征检测器 ('SIFT' 或 'ORB')
        
        Returns:
            匹配结果
        """
        # 准备图像
        if isinstance(screenshot, Image.Image):
            screenshot = self._pil_to_cv2(screenshot)
        
        if isinstance(template, str):
            template = self.load_template(template).image
        elif isinstance(template, Template):
            template = template.image
        
        # 转换为灰度图
        gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        
        # 初始化特征检测器
        if detector == 'SIFT':
            detector_obj = self._get_sift()
        else:
            detector_obj = self._get_orb()
        
        # 检测特征点
        kp1, des1 = detector_obj.detectAndCompute(gray_template, None)
        kp2, des2 = detector_obj.detectAndCompute(gray_screen, None)
        
        if des1 is None or des2 is None:
            return None
        
        # 特征匹配
        matcher = self._get_matcher(detector)
        matches = matcher.knnMatch(des1, des2, k=2)
        
        # 筛选良好的匹配
        good_matches = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < 0.7 * n.distance:
                    good_matches.append(m)
        
        if len(good_matches) < min_matches:
            return None
        
        # 计算单应性矩阵
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        
        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        
        if M is None:
            return None
        
        # 计算模板在截图中的位置
        h, w = template.shape[:2]
        pts = np.float32([[0, 0], [0, h-1], [w-1, h-1], [w-1, 0]]).reshape(-1, 1, 2)
        dst = cv2.perspectiveTransform(pts, M)
        
        # 计算边界框
        x, y, w, h = cv2.boundingRect(dst)
        
        # 计算置信度（基于内点比例）
        matches_mask = mask.ravel().tolist()
        confidence = sum(matches_mask) / len(matches_mask)
        
        return MatchResult(
            confidence=confidence,
            position=(x, y),
            size=(w, h),
            center=(x + w // 2, y + h // 2),
            method=f'FEATURE_{detector}'
        )
    
    def wait_for_image(self, screenshot_func: callable,
                      template: Union[str, Template],
                      timeout: float = 10.0,
                      interval: float = 0.5,
                      threshold: Optional[float] = None) -> Optional[MatchResult]:
        """
        等待图像出现
        
        Args:
            screenshot_func: 截图函数
            template: 模板
            timeout: 超时时间（秒）
            interval: 检查间隔（秒）
            threshold: 匹配阈值
        
        Returns:
            匹配结果
        """
        import time
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            screenshot = screenshot_func()
            result = self.find_template(screenshot, template, threshold)
            
            if result:
                self.logger.info(f"Image found after {time.time() - start_time:.2f}s")
                return result
            
            time.sleep(interval)
        
        self.logger.warning(f"Image not found after {timeout}s timeout")
        return None
    
    def compare_images(self, image1: Union[Image.Image, np.ndarray],
                      image2: Union[Image.Image, np.ndarray],
                      method: str = 'MSE') -> float:
        """
        比较两张图像的相似度
        
        Args:
            image1: 第一张图像
            image2: 第二张图像
            method: 比较方法 ('MSE', 'SSIM', 'HIST')
        
        Returns:
            相似度分数 (0-1)
        """
        # 转换格式
        if isinstance(image1, Image.Image):
            image1 = self._pil_to_cv2(image1)
        if isinstance(image2, Image.Image):
            image2 = self._pil_to_cv2(image2)
        
        # 确保尺寸相同
        if image1.shape != image2.shape:
            h = min(image1.shape[0], image2.shape[0])
            w = min(image1.shape[1], image2.shape[1])
            image1 = cv2.resize(image1, (w, h))
            image2 = cv2.resize(image2, (w, h))
        
        if method == 'MSE':
            # 均方误差
            mse = np.mean((image1 - image2) ** 2)
            # 转换为相似度分数
            similarity = 1.0 / (1.0 + mse / 1000.0)
            
        elif method == 'SSIM':
            # 结构相似性
            from skimage.metrics import structural_similarity as ssim
            gray1 = cv2.cvtColor(image1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(image2, cv2.COLOR_BGR2GRAY)
            similarity = ssim(gray1, gray2)
            
        elif method == 'HIST':
            # 直方图比较
            hist1 = cv2.calcHist([image1], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            hist2 = cv2.calcHist([image2], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            hist1 = cv2.normalize(hist1, hist1).flatten()
            hist2 = cv2.normalize(hist2, hist2).flatten()
            similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            
        else:
            raise ValueError(f"Unknown comparison method: {method}")
        
        return float(similarity)
    
    def save_template(self, image: Union[Image.Image, np.ndarray],
                     name: str, metadata: Optional[Dict[str, Any]] = None) -> Path:
        """
        保存模板图像
        
        Args:
            image: 图像
            name: 模板名称
            metadata: 元数据
        
        Returns:
            保存路径
        """
        # 转换格式
        if isinstance(image, np.ndarray):
            image = self._cv2_to_pil(image)
        
        # 生成文件路径
        template_path = self.template_dir / f"{name}.png"
        
        # 保存图像
        image.save(template_path)
        
        # 保存元数据
        if metadata:
            metadata_path = self.template_dir / f"{name}.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # 清除缓存
        if name in self._template_cache:
            del self._template_cache[name]
        
        self.logger.info(f"Template saved: {template_path}")
        return template_path
    
    def clear_cache(self) -> None:
        """清除模板缓存"""
        self._template_cache.clear()
        self.logger.info("Template cache cleared")
    
    def _match_template(self, image: np.ndarray, template: np.ndarray,
                       mask: Optional[np.ndarray], method: str) -> Optional[Dict[str, Any]]:
        """
        执行模板匹配
        
        Args:
            image: 搜索图像
            template: 模板图像
            mask: 掩码
            method: 匹配方法
        
        Returns:
            匹配结果字典
        """
        try:
            # 执行匹配
            result = cv2.matchTemplate(
                image,
                template,
                self.MATCH_METHODS[method],
                mask=mask
            )
            
            # 查找最佳匹配
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # 根据方法选择位置和置信度
            if method in ['TM_SQDIFF', 'TM_SQDIFF_NORMED']:
                position = min_loc
                confidence = 1 - min_val if method == 'TM_SQDIFF_NORMED' else 1.0 / (1.0 + min_val)
            else:
                position = max_loc
                confidence = max_val
            
            return {
                'position': position,
                'confidence': confidence
            }
            
        except Exception as e:
            self.logger.error(f"Template matching error: {e}")
            return None
    
    def _match_template_grayscale(self, image: np.ndarray, template: np.ndarray,
                                 method: str) -> Optional[Dict[str, Any]]:
        """
        执行灰度模板匹配
        
        Args:
            image: 搜索图像（灰度）
            template: 模板图像（灰度）
            method: 匹配方法
        
        Returns:
            匹配结果字典
        """
        try:
            # 执行灰度匹配
            result = cv2.matchTemplate(
                image,
                template,
                self.MATCH_METHODS[method]
            )
            
            # 查找最佳匹配
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # 根据方法选择位置和置信度
            if method in ['TM_SQDIFF', 'TM_SQDIFF_NORMED']:
                position = min_loc
                confidence = 1 - min_val if method == 'TM_SQDIFF_NORMED' else 1.0 / (1.0 + min_val)
            else:
                position = max_loc
                confidence = max_val
            
            return {
                'position': position,
                'confidence': confidence
            }
            
        except Exception as e:
            self.logger.error(f"Grayscale template matching error: {e}")
            return None
    
    def _pil_to_cv2(self, image: Image.Image) -> np.ndarray:
        """PIL Image转OpenCV格式"""
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    
    def _cv2_to_pil(self, image: np.ndarray) -> Image.Image:
        """OpenCV格式转PIL Image"""
        return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    
    def _get_sift(self):
        """获取SIFT检测器"""
        if self._sift is None:
            self._sift = cv2.SIFT_create()
        return self._sift
    
    def _get_orb(self):
        """获取ORB检测器"""
        if self._orb is None:
            self._orb = cv2.ORB_create()
        return self._orb
    
    def _get_matcher(self, detector: str):
        """获取特征匹配器"""
        if self._matcher is None:
            if detector == 'SIFT':
                self._matcher = cv2.BFMatcher(cv2.NORM_L2)
            else:
                self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        return self._matcher