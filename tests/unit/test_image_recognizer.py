"""
图像识别器单元测试
"""

import pytest
import numpy as np
from PIL import Image
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch
import cv2

from src.recognition.image_recognizer import (
    ImageRecognizer, MatchResult, Template
)
from src.utils.exceptions import (
    TemplateNotFoundError, InvalidImageFormatError,
    ImageRecognitionError
)


@pytest.fixture
def temp_template_dir():
    """创建临时模板目录"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def image_recognizer(temp_template_dir):
    """创建图像识别器实例"""
    return ImageRecognizer(template_dir=temp_template_dir)


@pytest.fixture
def sample_image():
    """创建示例图像"""
    # 创建一个简单的测试图像
    image = Image.new('RGB', (100, 100), color='white')
    # 在中间画一个红色方块
    pixels = image.load()
    for i in range(40, 60):
        for j in range(40, 60):
            pixels[i, j] = (255, 0, 0)
    return image


@pytest.fixture
def sample_template():
    """创建示例模板"""
    # 创建一个小的红色方块作为模板
    template = Image.new('RGB', (20, 20), color=(255, 0, 0))
    return template


class TestImageRecognizer:
    """图像识别器测试类"""
    
    def test_init(self, temp_template_dir):
        """测试初始化"""
        recognizer = ImageRecognizer(template_dir=temp_template_dir)
        assert recognizer.template_dir == temp_template_dir
        assert recognizer.cache_templates is True
        assert len(recognizer._template_cache) == 0
    
    def test_load_template(self, image_recognizer, temp_template_dir, sample_template):
        """测试加载模板"""
        # 保存模板文件
        template_path = temp_template_dir / "test_template.png"
        sample_template.save(template_path)
        
        # 加载模板
        template = image_recognizer.load_template("test_template")
        assert isinstance(template, Template)
        assert template.name == "test_template"
        assert template.path == template_path
        assert template.threshold == 0.8
        
        # 测试缓存
        cached_template = image_recognizer.load_template("test_template")
        assert cached_template is template
    
    def test_load_template_not_found(self, image_recognizer):
        """测试加载不存在的模板"""
        with pytest.raises(TemplateNotFoundError):
            image_recognizer.load_template("nonexistent")
    
    def test_find_template(self, image_recognizer, sample_image, sample_template, temp_template_dir):
        """测试查找模板"""
        # 保存模板
        template_path = temp_template_dir / "red_square.png"
        sample_template.save(template_path)
        
        # 模拟模板匹配
        with patch.object(image_recognizer, '_match_template') as mock_match:
            mock_match.return_value = {
                'position': (40, 40),
                'confidence': 0.9
            }
            
            result = image_recognizer.find_template(sample_image, "red_square")
            assert isinstance(result, MatchResult)
            assert result.confidence == 0.9
            assert result.position == (40, 40)
    
    def test_find_template_with_region(self, image_recognizer, sample_image, sample_template, temp_template_dir):
        """测试在指定区域查找模板"""
        # 保存模板
        template_path = temp_template_dir / "red_square.png"
        sample_template.save(template_path)
        
        with patch.object(image_recognizer, '_match_template') as mock_match:
            mock_match.return_value = {
                'position': (10, 10),
                'confidence': 0.85
            }
            
            # 指定搜索区域
            result = image_recognizer.find_template(
                sample_image, 
                "red_square",
                region=(30, 30, 40, 40)
            )
            
            # 验证位置偏移
            assert result.position == (40, 40)  # 10 + 30 offset
    
    def test_find_all_templates(self, image_recognizer, sample_image, sample_template, temp_template_dir):
        """测试查找所有模板"""
        # 保存模板
        template_path = temp_template_dir / "pattern.png"
        sample_template.save(template_path)
        
        # 创建模拟的匹配结果
        mock_result = np.zeros((80, 80), dtype=np.float32)
        mock_result[20, 20] = 0.9
        mock_result[50, 50] = 0.85
        mock_result[20, 50] = 0.8
        
        with patch('cv2.matchTemplate', return_value=mock_result):
            results = image_recognizer.find_all_templates(
                sample_image,
                "pattern",
                threshold=0.75
            )
            
            assert len(results) <= 3
            assert all(isinstance(r, MatchResult) for r in results)
    
    def test_find_by_feature(self, image_recognizer, sample_image, sample_template):
        """测试特征点匹配"""
        # 模拟特征检测器
        mock_detector = MagicMock()
        mock_detector.detectAndCompute.return_value = (
            [cv2.KeyPoint(10, 10, 1) for _ in range(20)],
            np.random.rand(20, 32).astype(np.uint8)
        )
        
        with patch.object(image_recognizer, '_get_orb', return_value=mock_detector):
            with patch.object(image_recognizer, '_get_matcher') as mock_matcher:
                # 模拟匹配结果
                mock_matches = [[MagicMock(distance=0.1), MagicMock(distance=0.3)] for _ in range(15)]
                mock_matcher.return_value.knnMatch.return_value = mock_matches
                
                with patch('cv2.findHomography') as mock_homography:
                    mock_homography.return_value = (np.eye(3), np.ones(15))
                    
                    with patch('cv2.perspectiveTransform'):
                        with patch('cv2.boundingRect', return_value=(10, 10, 50, 50)):
                            result = image_recognizer.find_by_feature(
                                sample_image,
                                sample_template
                            )
                            
                            assert result is not None
                            assert isinstance(result, MatchResult)
    
    def test_wait_for_image(self, image_recognizer, sample_template, temp_template_dir):
        """测试等待图像出现"""
        # 保存模板
        template_path = temp_template_dir / "wait_template.png"
        sample_template.save(template_path)
        
        # 模拟截图函数
        call_count = [0]
        def mock_screenshot():
            call_count[0] += 1
            if call_count[0] >= 3:
                # 第3次返回匹配的图像
                return sample_template
            return Image.new('RGB', (100, 100), color='black')
        
        with patch.object(image_recognizer, 'find_template') as mock_find:
            # 前两次返回None，第三次返回结果
            mock_find.side_effect = [None, None, MatchResult(
                confidence=0.9,
                position=(10, 10),
                size=(20, 20),
                center=(20, 20),
                method='TM_CCOEFF_NORMED'
            )]
            
            result = image_recognizer.wait_for_image(
                mock_screenshot,
                "wait_template",
                timeout=5.0,
                interval=0.1
            )
            
            assert result is not None
            assert mock_find.call_count == 3
    
    def test_compare_images_mse(self, image_recognizer):
        """测试MSE图像比较"""
        image1 = np.zeros((100, 100, 3), dtype=np.uint8)
        image2 = np.zeros((100, 100, 3), dtype=np.uint8)
        
        # 相同图像
        similarity = image_recognizer.compare_images(image1, image2, method='MSE')
        assert similarity > 0.99
        
        # 不同图像
        image2[:50, :50] = 255
        similarity = image_recognizer.compare_images(image1, image2, method='MSE')
        assert similarity < 0.99
    
    def test_compare_images_hist(self, image_recognizer):
        """测试直方图比较"""
        image1 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        image2 = image1.copy()
        
        similarity = image_recognizer.compare_images(image1, image2, method='HIST')
        assert similarity > 0.9
    
    def test_save_template(self, image_recognizer, sample_image, temp_template_dir):
        """测试保存模板"""
        # 保存模板
        template_path = image_recognizer.save_template(
            sample_image,
            "saved_template",
            metadata={'description': 'Test template'}
        )
        
        assert template_path.exists()
        assert template_path.name == "saved_template.png"
        
        # 检查元数据文件
        metadata_path = temp_template_dir / "saved_template.json"
        assert metadata_path.exists()
    
    def test_clear_cache(self, image_recognizer, sample_template, temp_template_dir):
        """测试清除缓存"""
        # 添加模板到缓存
        template_path = temp_template_dir / "cached.png"
        sample_template.save(template_path)
        image_recognizer.load_template("cached")
        
        assert len(image_recognizer._template_cache) == 1
        
        # 清除缓存
        image_recognizer.clear_cache()
        assert len(image_recognizer._template_cache) == 0
    
    def test_pil_cv2_conversion(self, image_recognizer):
        """测试图像格式转换"""
        # PIL to CV2
        pil_image = Image.new('RGB', (50, 50), color=(255, 0, 0))
        cv2_image = image_recognizer._pil_to_cv2(pil_image)
        assert cv2_image.shape == (50, 50, 3)
        assert cv2_image[0, 0, 2] == 255  # Red channel in BGR
        
        # CV2 to PIL
        pil_converted = image_recognizer._cv2_to_pil(cv2_image)
        assert pil_converted.size == (50, 50)
        assert pil_converted.getpixel((0, 0)) == (255, 0, 0)
    
    def test_match_methods(self, image_recognizer):
        """测试不同的匹配方法"""
        for method_name in ImageRecognizer.MATCH_METHODS.keys():
            assert method_name in ImageRecognizer.MATCH_METHODS
            assert ImageRecognizer.MATCH_METHODS[method_name] is not None