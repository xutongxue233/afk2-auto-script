"""
OCR引擎模块
提供文字识别功能，支持pytesseract和PaddleOCR
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
    OCR配置
    """
    engine: str = 'pytesseract'  # OCR引擎 ('pytesseract' 或 'paddleocr')
    lang: str = 'chi_sim'  # 识别语言
    use_angle_cls: bool = True  # 是否使用角度分类（PaddleOCR）
    use_gpu: bool = False  # 是否使用GPU
    det_db_thresh: float = 0.3  # 文本检测阈值
    rec_thresh: float = 0.5  # 文本识别阈值
    tesseract_config: str = '--psm 3'  # Tesseract配置
    preprocess: bool = True  # 是否预处理图像


class OCREngine(LoggerMixin):
    """
    OCR引擎类
    提供文字识别功能
    """
    
    def __init__(self, config: Optional[OCRConfig] = None):
        """
        初始化OCR引擎
        
        Args:
            config: OCR配置
        """
        self.config = config or OCRConfig()
        self._tesseract = None
        self._paddleocr = None
        self._engine_initialized = False
        
        self.logger.info(f"OCREngine created with engine: {self.config.engine}")
    
    def _ensure_engine_initialized(self) -> None:
        """确保OCR引擎已初始化（延迟初始化）"""
        if self._engine_initialized:
            return
        
        try:
            if self.config.engine == 'pytesseract':
                self._init_tesseract()
            elif self.config.engine == 'paddleocr':
                self._init_paddleocr()
            else:
                raise OCREngineNotFoundError(self.config.engine)
            
            self._engine_initialized = True
            self.logger.info(f"OCR引擎初始化完成: {self.config.engine}")
        except Exception as e:
            self.logger.error(f"OCR引擎初始化失败: {e}")
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
            "engine": self.config.engine,
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
    
    def _init_engine(self) -> None:
        """初始化OCR引擎（兼容旧代码）"""
        self._ensure_engine_initialized()
    
    def _init_tesseract(self) -> None:
        """初始化Tesseract引擎"""
        try:
            import pytesseract
            
            # 检查Tesseract是否可用
            try:
                pytesseract.get_tesseract_version()
                self._tesseract = pytesseract
                self.logger.info("Tesseract OCR initialized successfully")
            except pytesseract.TesseractNotFoundError:
                raise OCREngineNotFoundError("Tesseract not installed or not in PATH")
                
        except ImportError:
            raise OCREngineNotFoundError("pytesseract not installed")
    
    def _init_paddleocr(self) -> None:
        """初始化PaddleOCR引擎"""
        try:
            from paddleocr import PaddleOCR
            
            self._paddleocr = PaddleOCR(
                use_angle_cls=self.config.use_angle_cls,
                lang=self.config.lang if self.config.lang != 'chi_sim' else 'ch',
                use_gpu=self.config.use_gpu,
                det_db_thresh=self.config.det_db_thresh,
                show_log=False
            )
            self.logger.info("PaddleOCR initialized successfully")
            
        except ImportError:
            raise OCREngineNotFoundError("paddleocr not installed")
    
    @retry_on_recognition_error(max_attempts=3)
    def recognize_text(self, image: Union[Image.Image, np.ndarray, str, Path],
                      region: Optional[Tuple[int, int, int, int]] = None,
                      lang: Optional[str] = None) -> str:
        """
        识别图像中的文字
        
        Args:
            image: 输入图像（PIL Image、numpy数组、文件路径）
            region: 识别区域 (x, y, width, height)
            lang: 识别语言（覆盖默认设置）
        
        Returns:
            识别的文本
        """
        # 确保引擎已初始化
        self._ensure_engine_initialized()
        
        # 准备图像
        image = self._prepare_image(image, region)
        
        # 执行识别
        if self.config.engine == 'pytesseract':
            text = self._recognize_with_tesseract(image, lang)
        else:
            text = self._recognize_with_paddleocr(image)
        
        # 清理文本
        text = self._clean_text(text)
        
        self.logger.debug(f"Recognized text: {text[:50]}...")
        return text
    
    def recognize_with_details(self, image: Union[Image.Image, np.ndarray, str, Path],
                              region: Optional[Tuple[int, int, int, int]] = None,
                              lang: Optional[str] = None) -> List[OCRResult]:
        """
        识别图像中的文字（带详细信息）
        
        Args:
            image: 输入图像
            region: 识别区域
            lang: 识别语言
        
        Returns:
            OCR结果列表
        """
        # 确保引擎已初始化
        self._ensure_engine_initialized()
        
        # 准备图像
        image = self._prepare_image(image, region)
        region_offset = region[:2] if region else (0, 0)
        
        results = []
        
        if self.config.engine == 'pytesseract':
            # 使用Tesseract获取详细信息
            data = self._tesseract.image_to_data(
                image,
                lang=lang or self.config.lang,
                config=self.config.tesseract_config,
                output_type=self._tesseract.Output.DICT
            )
            
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                if int(data['conf'][i]) > 0:
                    text = data['text'][i].strip()
                    if text:
                        x = data['left'][i] + region_offset[0]
                        y = data['top'][i] + region_offset[1]
                        w = data['width'][i]
                        h = data['height'][i]
                        
                        results.append(OCRResult(
                            text=text,
                            confidence=int(data['conf'][i]) / 100.0,
                            bbox=(x, y, w, h),
                            position=(x, y)
                        ))
        
        else:
            # 使用PaddleOCR获取详细信息
            ocr_results = self._paddleocr.ocr(np.array(image), cls=self.config.use_angle_cls)
            
            if ocr_results and ocr_results[0]:
                for line in ocr_results[0]:
                    bbox = line[0]
                    text = line[1][0]
                    confidence = line[1][1]
                    
                    # 计算边界框
                    x_coords = [p[0] for p in bbox]
                    y_coords = [p[1] for p in bbox]
                    x = int(min(x_coords)) + region_offset[0]
                    y = int(min(y_coords)) + region_offset[1]
                    w = int(max(x_coords) - min(x_coords))
                    h = int(max(y_coords) - min(y_coords))
                    
                    if confidence >= self.config.rec_thresh:
                        results.append(OCRResult(
                            text=text,
                            confidence=confidence,
                            bbox=(x, y, w, h),
                            position=(x, y)
                        ))
        
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
    
    def _recognize_with_tesseract(self, image: Image.Image, lang: Optional[str] = None) -> str:
        """
        使用Tesseract识别文字
        
        Args:
            image: 输入图像
            lang: 识别语言
        
        Returns:
            识别的文本
        """
        if not self._tesseract:
            raise OCREngineNotFoundError("Tesseract not initialized")
        
        try:
            text = self._tesseract.image_to_string(
                image,
                lang=lang or self.config.lang,
                config=self.config.tesseract_config
            )
            return text
            
        except Exception as e:
            self.logger.error(f"Tesseract recognition error: {e}")
            raise OCRRecognitionError(f"Tesseract error: {e}")
    
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
            result = self._paddleocr.ocr(img_array, cls=self.config.use_angle_cls)
            
            # 提取文本
            texts = []
            if result and result[0]:
                for line in result[0]:
                    text = line[1][0]
                    confidence = line[1][1]
                    if confidence >= self.config.rec_thresh:
                        texts.append(text)
            
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
    
    def switch_engine(self, engine: str) -> None:
        """
        切换OCR引擎
        
        Args:
            engine: 引擎名称 ('pytesseract' 或 'paddleocr')
        """
        if engine == self.config.engine:
            return
        
        self.config.engine = engine
        self._init_engine()
        self.logger.info(f"Switched OCR engine to: {engine}")
    
    def set_language(self, lang: str) -> None:
        """
        设置识别语言
        
        Args:
            lang: 语言代码
        """
        self.config.lang = lang
        
        # 如果使用PaddleOCR，需要重新初始化
        if self.config.engine == 'paddleocr':
            self._init_paddleocr()
        
        self.logger.info(f"OCR language set to: {lang}")
    
    def benchmark(self, image: Union[Image.Image, np.ndarray]) -> Dict[str, Any]:
        """
        对比不同引擎的性能
        
        Args:
            image: 测试图像
        
        Returns:
            性能测试结果
        """
        import time
        
        results = {}
        
        # 测试Tesseract
        try:
            self.switch_engine('pytesseract')
            start = time.time()
            text_tesseract = self.recognize_text(image)
            time_tesseract = time.time() - start
            
            results['tesseract'] = {
                'text': text_tesseract,
                'time': time_tesseract,
                'success': True
            }
        except Exception as e:
            results['tesseract'] = {
                'error': str(e),
                'success': False
            }
        
        # 测试PaddleOCR
        try:
            self.switch_engine('paddleocr')
            start = time.time()
            text_paddle = self.recognize_text(image)
            time_paddle = time.time() - start
            
            results['paddleocr'] = {
                'text': text_paddle,
                'time': time_paddle,
                'success': True
            }
        except Exception as e:
            results['paddleocr'] = {
                'error': str(e),
                'success': False
            }
        
        return results