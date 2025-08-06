"""
识别模块
提供图像识别和OCR文字识别功能
"""

from .image_recognizer import ImageRecognizer
from .ocr_engine import OCREngine

__all__ = ['ImageRecognizer', 'OCREngine']