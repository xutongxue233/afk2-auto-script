"""
OCR引擎单元测试
"""

import pytest
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from unittest.mock import Mock, MagicMock, patch
import cv2

from src.recognition.ocr_engine import (
    OCREngine, OCRResult, OCRConfig
)
from src.utils.exceptions import (
    OCRRecognitionError, OCREngineNotFoundError
)


@pytest.fixture
def ocr_config():
    """创建OCR配置"""
    return OCRConfig(
        lang='ch',
        preprocess=True
    )


@pytest.fixture
def ocr_engine(ocr_config):
    """创建OCR引擎实例"""
    with patch.object(OCREngine, '_init_paddleocr'):
        engine = OCREngine(ocr_config)
        engine._engine_initialized = True
        return engine


@pytest.fixture
def text_image():
    """创建包含文字的测试图像"""
    image = Image.new('RGB', (200, 50), color='white')
    draw = ImageDraw.Draw(image)
    
    # 尝试使用默认字体，如果失败则使用None
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = None
    
    draw.text((10, 10), "Test Text 123", fill='black', font=font)
    return image


@pytest.fixture
def mock_paddleocr():
    """模拟PaddleOCR"""
    mock = MagicMock()
    
    # 模拟新版本PaddleOCR的返回格式
    ocr_result = MagicMock()
    ocr_result.__getitem__ = lambda self, key: {
        'rec_texts': ['Test', 'Text', '123'],
        'rec_scores': [0.95, 0.92, 0.88],
        'rec_polys': [
            [[10, 10], [40, 10], [40, 30], [10, 30]],
            [[50, 10], [80, 10], [80, 30], [50, 30]],
            [[100, 10], [125, 10], [125, 30], [100, 30]]
        ]
    }.get(key, [])
    ocr_result.get = lambda key, default=None: {
        'rec_texts': ['Test', 'Text', '123'],
        'rec_scores': [0.95, 0.92, 0.88],
        'rec_polys': [
            [[10, 10], [40, 10], [40, 30], [10, 30]],
            [[50, 10], [80, 10], [80, 30], [50, 30]],
            [[100, 10], [125, 10], [125, 30], [100, 30]]
        ]
    }.get(key, default)
    ocr_result.__contains__ = lambda self, key: key in ['rec_texts', 'rec_scores', 'rec_polys']
    
    # predict方法返回格式
    mock.predict.return_value = [ocr_result]
    
    # ocr方法返回格式（兼容旧版本）
    mock.ocr.return_value = [ocr_result]
    
    return mock


class TestOCREngine:
    """OCR引擎测试类"""
    
    def test_init_with_paddleocr(self):
        """测试PaddleOCR初始化"""
        config = OCRConfig(lang='ch')
        
        with patch('src.recognition.ocr_engine.PaddleOCR') as mock_paddle:
            engine = OCREngine(config)
            engine._ensure_engine_initialized()
            assert engine._paddleocr is not None
            mock_paddle.assert_called_once()
    
    def test_recognize_text_paddleocr(self, ocr_engine, text_image, mock_paddleocr):
        """测试PaddleOCR文字识别"""
        ocr_engine._paddleocr = mock_paddleocr
        
        with patch.object(ocr_engine, '_prepare_image', return_value=text_image):
            text = ocr_engine.recognize_text(text_image)
            assert "Test" in text
            assert "Text" in text
            assert "123" in text
    
    def test_recognize_with_details_paddleocr(self, ocr_engine, text_image, mock_paddleocr):
        """测试PaddleOCR详细识别"""
        ocr_engine._paddleocr = mock_paddleocr
        
        with patch.object(ocr_engine, '_prepare_image', return_value=text_image):
            results = ocr_engine.recognize_with_details(text_image)
            
            assert len(results) == 3
            assert results[0].text == 'Test'
            assert results[0].confidence == 0.95
    
    def test_find_text(self, ocr_engine, text_image):
        """测试查找文本"""
        mock_results = [
            OCRResult('Hello', 0.9, (10, 10, 30, 20), (10, 10)),
            OCRResult('World', 0.85, (50, 10, 30, 20), (50, 10)),
            OCRResult('123', 0.88, (100, 10, 25, 20), (100, 10))
        ]
        
        with patch.object(ocr_engine, 'recognize_with_details', return_value=mock_results):
            # 精确匹配
            result = ocr_engine.find_text(text_image, 'Hello', exact_match=True)
            assert result is not None
            assert result.text == 'Hello'
            
            # 部分匹配
            result = ocr_engine.find_text(text_image, 'orl', exact_match=False)
            assert result is not None
            assert result.text == 'World'
            
            # 大小写不敏感
            result = ocr_engine.find_text(text_image, 'HELLO', case_sensitive=False)
            assert result is not None
            assert result.text == 'Hello'
            
            # 未找到
            result = ocr_engine.find_text(text_image, 'NotFound')
            assert result is None
    
    def test_find_all_text(self, ocr_engine, text_image):
        """测试查找所有匹配文本"""
        mock_results = [
            OCRResult('Test1', 0.9, (10, 10, 30, 20), (10, 10)),
            OCRResult('Test2', 0.85, (50, 10, 30, 20), (50, 10)),
            OCRResult('Other', 0.88, (100, 10, 25, 20), (100, 10))
        ]
        
        with patch.object(ocr_engine, 'recognize_with_details', return_value=mock_results):
            # 字符串匹配
            results = ocr_engine.find_all_text(text_image, 'Test')
            assert len(results) == 2
            
            # 正则表达式匹配
            results = ocr_engine.find_all_text(text_image, r'Test\d', use_regex=True)
            assert len(results) == 2
    
    def test_extract_numbers(self, ocr_engine, text_image):
        """测试提取数字"""
        with patch.object(ocr_engine, 'recognize_text', return_value="Price: $123.45, Quantity: 10"):
            numbers = ocr_engine.extract_numbers(text_image)
            assert len(numbers) == 2
            assert 123.45 in numbers
            assert 10.0 in numbers
    
    def test_preprocess_image(self, ocr_engine):
        """测试图像预处理"""
        # 创建带噪声的图像
        image = Image.new('RGB', (100, 50), color='white')
        draw = ImageDraw.Draw(image)
        draw.text((10, 10), "Test", fill='black')
        
        # 添加噪声
        pixels = image.load()
        for i in range(0, 100, 10):
            for j in range(0, 50, 10):
                if i % 20 == 0:
                    pixels[i, j] = (200, 200, 200)
        
        processed = ocr_engine._preprocess_image(image)
        assert isinstance(processed, Image.Image)
        # 预处理后应该是灰度图
        assert len(np.array(processed).shape) == 2 or np.array(processed).shape[2] == 1
    
    def test_prepare_image_with_region(self, ocr_engine, text_image):
        """测试图像准备（带区域）"""
        region = (10, 5, 50, 30)
        
        with patch.object(ocr_engine, '_preprocess_image', return_value=text_image) as mock_preprocess:
            ocr_engine.config.preprocess = False  # 关闭预处理
            prepared = ocr_engine._prepare_image(text_image, region)
            
            # 验证裁剪
            assert prepared.size == (50, 30)
    
    def test_set_language(self, ocr_engine):
        """测试设置语言"""
        ocr_engine.set_language('eng')
        assert ocr_engine.config.lang == 'eng'
        # 应该标记需要重新初始化
        assert ocr_engine._engine_initialized == False
    
    def test_clean_text(self, ocr_engine):
        """测试文本清理"""
        # 测试多余空格
        text = "  Hello   World  \n\t123  "
        cleaned = ocr_engine._clean_text(text)
        assert cleaned == "Hello World 123"
        
        # 测试空文本
        assert ocr_engine._clean_text("") == ""
        assert ocr_engine._clean_text("   ") == ""
    
    def test_error_handling(self, ocr_engine, text_image):
        """测试错误处理"""
        # PaddleOCR错误
        ocr_engine._paddleocr = Mock()
        ocr_engine._paddleocr.predict.side_effect = Exception("PaddleOCR error")
        ocr_engine._paddleocr.ocr.side_effect = Exception("PaddleOCR error")
        
        with patch.object(ocr_engine, '_prepare_image', return_value=text_image):
            with pytest.raises(OCRRecognitionError):
                ocr_engine.recognize_text(text_image)
    
    def test_is_engine_available(self, ocr_engine):
        """测试引擎可用性检查"""
        # 模拟引擎可用
        with patch.object(ocr_engine, '_ensure_engine_initialized'):
            assert ocr_engine.is_engine_available() == True
        
        # 模拟引擎不可用
        with patch.object(ocr_engine, '_ensure_engine_initialized', side_effect=Exception("Not available")):
            assert ocr_engine.is_engine_available() == False
    
    def test_get_engine_status(self, ocr_engine):
        """测试获取引擎状态"""
        with patch.object(ocr_engine, '_ensure_engine_initialized'):
            status = ocr_engine.get_engine_status()
            assert status['engine'] == 'PaddleOCR'
            assert status['available'] == True
            assert status['error'] is None
        
        # 模拟引擎错误
        with patch.object(ocr_engine, '_ensure_engine_initialized', side_effect=Exception("Test error")):
            status = ocr_engine.get_engine_status()
            assert status['available'] == False
            assert 'Test error' in status['error']
    
    def test_recognize_with_old_format(self, ocr_engine, text_image):
        """测试兼容旧版本PaddleOCR格式"""
        # 模拟旧版本格式
        mock_paddle = MagicMock()
        mock_paddle.predict.side_effect = AttributeError("No predict method")
        mock_paddle.ocr.return_value = [[
            [[[10, 10], [40, 10], [40, 30], [10, 30]], ('Test', 0.95)],
            [[[50, 10], [80, 10], [80, 30], [50, 30]], ('Text', 0.92)],
            [[[100, 10], [125, 10], [125, 30], [100, 30]], ('123', 0.88)]
        ]]
        
        ocr_engine._paddleocr = mock_paddle
        
        with patch.object(ocr_engine, '_prepare_image', return_value=text_image):
            text = ocr_engine.recognize_text(text_image)
            assert "Test" in text
            assert "Text" in text
            assert "123" in text