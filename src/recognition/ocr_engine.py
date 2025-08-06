"""
OCR引擎模块
提供文字识别功能，使用PaddleOCR
"""

import re
from PIL import Image
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any, Union
from dataclasses import dataclass
import cv2

from src.services.log_service import LoggerMixin
from src.utils.exceptions import (
    OCRRecognitionError, OCREngineNotFoundError,
    InvalidImageFormatError
)
from src.utils.retry import retry_on_recognition_error


@dataclass
class OCRResult:
    """
    OCR识别结果
    """
    text: str  # 识别的文本
    confidence: float  # 置信度 (0-1)
    bbox: Tuple[int, int, int, int]  # 边界框 (x, y, width, height)
    position: Tuple[int, int]  # 文本位置 (x, y)


@dataclass
class OCRConfig:
    """
    OCR配置 - 使用PaddleOCR
    """
    lang: str = 'ch'  # 识别语言 (PaddleOCR使用'ch'表示中文)
    use_angle_cls: bool = True  # 是否使用角度分类
    det_db_thresh: float = 0.3  # 文本检测阈值
    rec_thresh: float = 0.5  # 文本识别阈值
    preprocess: bool = False  # 是否预处理图像（默认关闭，避免过度处理）


class OCREngine(LoggerMixin):
    """
    OCR引擎类 - 基于PaddleOCR
    提供文字识别功能
    """
    
    def __init__(self, config: Optional[OCRConfig] = None):
        """
        初始化OCR引擎
        
        Args:
            config: OCR配置
        """
        self.config = config or OCRConfig()
        self._paddleocr = None
        self._engine_initialized = False
        
        self.logger.info(f"OCREngine created with PaddleOCR, lang: {self.config.lang}")
    
    def _ensure_engine_initialized(self) -> None:
        """确保OCR引擎已初始化（延迟初始化）"""
        if self._engine_initialized:
            return
        
        try:
            self._init_paddleocr()
            self._engine_initialized = True
            self.logger.info("PaddleOCR引擎初始化完成")
        except Exception as e:
            self.logger.error(f"PaddleOCR引擎初始化失败: {e}")
            raise
    
    def is_engine_available(self) -> bool:
        """
        检查OCR引擎是否可用（不抛出异常）
        
        Returns:
            是否可用
        """
        try:
            self._ensure_engine_initialized()
            return True
        except:
            return False
    
    def get_engine_status(self) -> dict:
        """
        获取OCR引擎状态信息
        
        Returns:
            状态信息字典
        """
        status = {
            "engine": "PaddleOCR",
            "available": False,
            "initialized": self._engine_initialized,
            "error": None
        }
        
        try:
            self._ensure_engine_initialized()
            status["available"] = True
        except Exception as e:
            status["error"] = str(e)
        
        return status
    
    def _init_paddleocr(self) -> None:
        """初始化PaddleOCR引擎"""
        try:
            from paddleocr import PaddleOCR
            
            # PaddleOCR配置，使用最小参数避免兼容性问题
            try:
                # 尝试只指定语言参数
                self._paddleocr = PaddleOCR(lang=self.config.lang)
                self.logger.info("PaddleOCR initialized successfully")
                
            except Exception as e:
                # 如果失败，尝试完全默认配置
                self.logger.warning(f"PaddleOCR init with lang failed: {e}, trying default config")
                try:
                    self._paddleocr = PaddleOCR()
                    self.logger.info("PaddleOCR initialized with default config")
                except Exception as e2:
                    self.logger.error(f"PaddleOCR init completely failed: {e2}")
                    raise OCREngineNotFoundError(f"PaddleOCR初始化失败: {e2}. 请运行: pip install paddlepaddle paddleocr")
            
        except ImportError:
            raise OCREngineNotFoundError("PaddleOCR未安装. 请运行: pip install paddlepaddle paddleocr")
    
    @retry_on_recognition_error(max_attempts=3)
    def recognize_text(self, image: Union[Image.Image, np.ndarray, str, Path],
                      region: Optional[Tuple[int, int, int, int]] = None,
                      lang: Optional[str] = None) -> str:
        """
        识别图像中的文字
        
        Args:
            image: 输入图像（PIL Image、numpy数组、文件路径）
            region: 识别区域 (x, y, width, height)
            lang: 识别语言（覆盖默认设置，暂不支持）
        
        Returns:
            识别的文本
        """
        # 确保引擎已初始化
        self._ensure_engine_initialized()
        
        # 准备图像
        image = self._prepare_image(image, region)
        
        # 执行识别
        text = self._recognize_with_paddleocr(image)
        
        # 清理文本
        text = self._clean_text(text)
        
        self.logger.debug(f"Recognized text: {text[:50] if text else 'No text'}...")
        return text
    
    def recognize_with_details(self, image: Union[Image.Image, np.ndarray, str, Path],
                              region: Optional[Tuple[int, int, int, int]] = None,
                              lang: Optional[str] = None) -> List[OCRResult]:
        """
        识别图像中的文字（带详细信息）
        
        Args:
            image: 输入图像
            region: 识别区域
            lang: 识别语言（暂不支持）
        
        Returns:
            OCR结果列表
        """
        # 确保引擎已初始化
        self._ensure_engine_initialized()
        
        # 准备图像
        image = self._prepare_image(image, region)
        region_offset = region[:2] if region else (0, 0)
        
        results = []
        
        # 使用PaddleOCR获取详细信息
        try:
            # 使用predict方法（新版本推荐）
            ocr_results = self._paddleocr.predict(np.array(image))
        except AttributeError:
            # 如果predict方法不存在，使用ocr方法
            ocr_results = self._paddleocr.ocr(np.array(image))
        
        if ocr_results and len(ocr_results) > 0:
            result = ocr_results[0]
            
            # 处理新版本PaddleOCR的返回格式
            if hasattr(result, '__getitem__') and 'rec_texts' in result:
                # 新格式：result是一个OCRResult对象，包含rec_texts和rec_scores
                texts = result.get('rec_texts', [])
                scores = result.get('rec_scores', [])
                boxes = result.get('rec_boxes', [])
                polys = result.get('rec_polys', result.get('dt_polys', []))
                
                for i in range(len(texts)):
                    text = texts[i] if i < len(texts) else ''
                    confidence = float(scores[i]) if i < len(scores) else 0.0
                    
                    # 获取边界框
                    if i < len(polys) and len(polys[i]) >= 4:
                        poly = polys[i]
                        x_coords = [p[0] for p in poly]
                        y_coords = [p[1] for p in poly]
                        x = int(min(x_coords)) + region_offset[0]
                        y = int(min(y_coords)) + region_offset[1]
                        w = int(max(x_coords) - min(x_coords))
                        h = int(max(y_coords) - min(y_coords))
                    elif i < len(boxes) and len(boxes[i]) >= 4:
                        # 使用rec_boxes作为备选
                        box = boxes[i]
                        x = int(box[0]) + region_offset[0]
                        y = int(box[1]) + region_offset[1]
                        w = int(box[2] - box[0])
                        h = int(box[3] - box[1])
                    else:
                        x, y, w, h = 0, 0, 0, 0
                    
                    if confidence >= self.config.rec_thresh:
                        results.append(OCRResult(
                            text=text,
                            confidence=confidence,
                            bbox=(x, y, w, h),
                            position=(x, y)
                        ))
            else:
                # 旧格式：result是一个列表，每个元素包含[bbox, (text, score)]
                try:
                    for line in result:
                        if isinstance(line, (list, tuple)) and len(line) >= 2:
                            bbox = line[0]
                            text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                            confidence = line[1][1] if isinstance(line[1], (list, tuple)) and len(line[1]) > 1 else 1.0
                            
                            # 计算边界框
                            if bbox and len(bbox) >= 4:
                                x_coords = [p[0] for p in bbox]
                                y_coords = [p[1] for p in bbox]
                                x = int(min(x_coords)) + region_offset[0]
                                y = int(min(y_coords)) + region_offset[1]
                                w = int(max(x_coords) - min(x_coords))
                                h = int(max(y_coords) - min(y_coords))
                            else:
                                x, y, w, h = 0, 0, 0, 0
                            
                            if confidence >= self.config.rec_thresh:
                                results.append(OCRResult(
                                    text=text,
                                    confidence=float(confidence),
                                    bbox=(x, y, w, h),
                                    position=(x, y)
                                ))
                except (IndexError, TypeError, KeyError) as e:
                    self.logger.warning(f"Failed to parse OCR result: {e}")
        
        self.logger.debug(f"Recognized {len(results)} text regions")
        return results
    
    def find_text(self, image: Union[Image.Image, np.ndarray],
                 target_text: str,
                 exact_match: bool = False,
                 case_sensitive: bool = False) -> Optional[OCRResult]:
        """
        在图像中查找特定文本
        
        Args:
            image: 输入图像
            target_text: 要查找的文本
            exact_match: 是否精确匹配
            case_sensitive: 是否区分大小写
        
        Returns:
            找到的OCR结果，未找到返回None
        """
        # 获取所有文本
        results = self.recognize_with_details(image)
        
        # 准备目标文本
        if not case_sensitive:
            target_text = target_text.lower()
        
        # 查找匹配
        for result in results:
            text = result.text
            if not case_sensitive:
                text = text.lower()
            
            if exact_match:
                if text == target_text:
                    return result
            else:
                if target_text in text:
                    return result
        
        return None
    
    def find_all_text(self, image: Union[Image.Image, np.ndarray],
                     pattern: str,
                     use_regex: bool = False) -> List[OCRResult]:
        """
        查找所有匹配的文本
        
        Args:
            image: 输入图像
            pattern: 匹配模式（字符串或正则表达式）
            use_regex: 是否使用正则表达式
        
        Returns:
            匹配的OCR结果列表
        """
        # 获取所有文本
        results = self.recognize_with_details(image)
        
        matches = []
        
        if use_regex:
            regex = re.compile(pattern)
            for result in results:
                if regex.search(result.text):
                    matches.append(result)
        else:
            pattern_lower = pattern.lower()
            for result in results:
                if pattern_lower in result.text.lower():
                    matches.append(result)
        
        self.logger.debug(f"Found {len(matches)} text matches for pattern: {pattern}")
        return matches
    
    def extract_numbers(self, image: Union[Image.Image, np.ndarray],
                       region: Optional[Tuple[int, int, int, int]] = None) -> List[float]:
        """
        从图像中提取数字
        
        Args:
            image: 输入图像
            region: 识别区域
        
        Returns:
            提取的数字列表
        """
        # 识别文本
        text = self.recognize_text(image, region)
        
        # 提取数字
        numbers = []
        pattern = r'[-+]?\d*\.?\d+'
        matches = re.findall(pattern, text)
        
        for match in matches:
            try:
                if '.' in match:
                    numbers.append(float(match))
                else:
                    numbers.append(float(match))
            except ValueError:
                continue
        
        self.logger.debug(f"Extracted {len(numbers)} numbers: {numbers}")
        return numbers
    
    def _prepare_image(self, image: Union[Image.Image, np.ndarray, str, Path],
                      region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """
        准备图像用于OCR
        
        Args:
            image: 输入图像
            region: 裁剪区域
        
        Returns:
            处理后的PIL Image
        """
        # 加载图像
        if isinstance(image, (str, Path)):
            image = Image.open(image)
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        
        # 裁剪区域
        if region:
            x, y, w, h = region
            image = image.crop((x, y, x + w, y + h))
        
        # 预处理
        if self.config.preprocess:
            image = self._preprocess_image(image)
        
        return image
    
    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        预处理图像以提高OCR准确率
        
        Args:
            image: 输入图像
        
        Returns:
            处理后的图像
        """
        # 转换为numpy数组
        img_array = np.array(image)
        
        # 转换为灰度图
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # 去噪
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # 二值化
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 形态学操作（去除小噪点）
        kernel = np.ones((2, 2), np.uint8)
        processed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # 转换回PIL Image
        return Image.fromarray(processed)
    
    def _recognize_with_paddleocr(self, image: Image.Image) -> str:
        """
        使用PaddleOCR识别文字
        
        Args:
            image: 输入图像
        
        Returns:
            识别的文本
        """
        if not self._paddleocr:
            raise OCREngineNotFoundError("PaddleOCR not initialized")
        
        try:
            # 转换为numpy数组
            img_array = np.array(image)
            
            # 执行OCR
            try:
                # 使用predict方法（新版本推荐）
                result = self._paddleocr.predict(img_array)
            except AttributeError:
                # 如果predict方法不存在，使用ocr方法
                result = self._paddleocr.ocr(img_array)
            
            # 提取文本
            texts = []
            if result and len(result) > 0:
                ocr_result = result[0]
                
                # 处理新版本PaddleOCR的返回格式
                if hasattr(ocr_result, '__getitem__') and 'rec_texts' in ocr_result:
                    # 新格式：result是一个OCRResult对象
                    rec_texts = ocr_result.get('rec_texts', [])
                    rec_scores = ocr_result.get('rec_scores', [])
                    
                    for i, text in enumerate(rec_texts):
                        confidence = float(rec_scores[i]) if i < len(rec_scores) else 0.0
                        if confidence >= self.config.rec_thresh:
                            texts.append(text)
                else:
                    # 旧格式：result是一个列表
                    try:
                        for line in ocr_result:
                            if isinstance(line, (list, tuple)) and len(line) >= 2:
                                text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                                confidence = line[1][1] if isinstance(line[1], (list, tuple)) and len(line[1]) > 1 else 1.0
                                if float(confidence) >= self.config.rec_thresh:
                                    texts.append(text)
                    except (IndexError, TypeError, KeyError) as e:
                        self.logger.warning(f"Failed to parse OCR result: {e}")
            
            return ' '.join(texts)
            
        except Exception as e:
            self.logger.error(f"PaddleOCR recognition error: {e}")
            raise OCRRecognitionError(f"PaddleOCR error: {e}")
    
    def _clean_text(self, text: str) -> str:
        """
        清理识别的文本
        
        Args:
            text: 原始文本
        
        Returns:
            清理后的文本
        """
        # 去除多余的空白字符
        text = ' '.join(text.split())
        
        # 去除特殊字符（可选）
        # text = re.sub(r'[^\w\s\u4e00-\u9fa5]', '', text)
        
        return text.strip()
    
    def set_language(self, lang: str) -> None:
        """
        设置识别语言
        
        Args:
            lang: 语言代码
        """
        self.config.lang = lang
        # PaddleOCR需要重新初始化
        self._engine_initialized = False
        self._paddleocr = None
        self.logger.info(f"OCR language set to: {lang}, will reinitialize on next use")