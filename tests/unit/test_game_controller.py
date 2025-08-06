"""
游戏控制器单元测试
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from PIL import Image
import time

from src.controller.base_controller import (
    BaseGameController, GameState, GameScene, ClickPoint
)
from src.controller.afk2_controller import AFK2Controller, AFK2Scene
from src.controller.scene_detector import (
    SceneDetector, SceneFeature, SceneDetectionResult
)
from src.services.adb_service import ADBService
from src.models.config import GameConfig
from src.recognition.image_recognizer import ImageRecognizer
from src.recognition.ocr_engine import OCREngine
from src.utils.exceptions import (
    GameNotRunningError, GameStartupError, GameLoadingTimeoutError
)


@pytest.fixture
def mock_adb():
    """创建模拟ADB服务"""
    mock = MagicMock(spec=ADBService)
    mock.current_device = MagicMock()
    mock.current_device.screen_resolution = (1080, 1920)
    return mock


@pytest.fixture
def mock_recognizer():
    """创建模拟图像识别器"""
    return MagicMock(spec=ImageRecognizer)


@pytest.fixture
def mock_ocr():
    """创建模拟OCR引擎"""
    return MagicMock(spec=OCREngine)


@pytest.fixture
def game_config():
    """创建游戏配置"""
    config = GameConfig()
    config.package_name = "com.test.game"
    config.main_activity = ".MainActivity"
    return config


@pytest.fixture
def sample_screenshot():
    """创建示例截图"""
    return Image.new('RGB', (1080, 1920), color='white')


class TestGameController(BaseGameController):
    """测试用游戏控制器"""
    
    def _init_scenes(self):
        self.add_scene(GameScene(
            name="main",
            identifiers=["main_icon"],
            click_points={"start": ClickPoint("start", 540, 1000)}
        ))
    
    def _navigate_step(self, from_scene: str, to_scene: str) -> bool:
        return True
    
    def perform_daily_tasks(self):
        return {"test": True}
    
    def collect_rewards(self):
        return True


class TestBaseGameController:
    """基础游戏控制器测试"""
    
    def test_init(self, mock_adb, game_config, mock_recognizer, mock_ocr):
        """测试初始化"""
        controller = TestGameController(mock_adb, game_config, mock_recognizer, mock_ocr)
        assert controller.adb == mock_adb
        assert controller.config == game_config
        assert controller.state == GameState.STOPPED
        assert controller.current_scene is None
    
    def test_state_change(self, mock_adb):
        """测试状态变更"""
        controller = TestGameController(mock_adb)
        
        # 添加状态监听器
        state_changes = []
        controller.add_state_listener(lambda old, new: state_changes.append((old, new)))
        
        # 改变状态
        controller.state = GameState.STARTING
        assert controller.state == GameState.STARTING
        assert len(state_changes) == 1
        assert state_changes[0] == (GameState.STOPPED, GameState.STARTING)
    
    def test_add_scene(self, mock_adb):
        """测试添加场景"""
        controller = TestGameController(mock_adb)
        
        scene = GameScene(
            name="test_scene",
            identifiers=["test"],
            click_points={}
        )
        
        controller.add_scene(scene)
        assert "test_scene" in controller._scenes
        assert controller._scenes["test_scene"] == scene
    
    def test_start_game(self, mock_adb):
        """测试启动游戏"""
        controller = TestGameController(mock_adb)
        
        mock_adb.is_app_running.return_value = False
        mock_adb.start_app.return_value = True
        
        with patch.object(controller, 'wait_for_scene', return_value=True):
            result = controller.start_game()
            assert result is True
            assert controller.state == GameState.IN_GAME
            mock_adb.start_app.assert_called_once()
    
    def test_start_game_already_running(self, mock_adb):
        """测试游戏已运行时启动"""
        controller = TestGameController(mock_adb)
        
        mock_adb.is_app_running.return_value = True
        
        result = controller.start_game()
        assert result is True
        assert controller.state == GameState.IN_GAME
        mock_adb.start_app.assert_not_called()
    
    def test_stop_game(self, mock_adb):
        """测试停止游戏"""
        controller = TestGameController(mock_adb)
        controller.state = GameState.IN_GAME
        
        mock_adb.stop_app.return_value = True
        
        result = controller.stop_game()
        assert result is True
        assert controller.state == GameState.STOPPED
        mock_adb.stop_app.assert_called_once()
    
    def test_screenshot(self, mock_adb, sample_screenshot):
        """测试截图"""
        controller = TestGameController(mock_adb)
        
        mock_adb.is_app_running.return_value = True
        mock_adb.screenshot.return_value = sample_screenshot
        
        screenshot = controller.screenshot()
        assert screenshot == sample_screenshot
        mock_adb.screenshot.assert_called_once()
    
    def test_screenshot_game_not_running(self, mock_adb):
        """测试游戏未运行时截图"""
        controller = TestGameController(mock_adb)
        
        mock_adb.is_app_running.return_value = False
        
        with pytest.raises(GameNotRunningError):
            controller.screenshot()
    
    def test_detect_scene(self, mock_adb, mock_recognizer, mock_ocr, sample_screenshot):
        """测试场景检测"""
        controller = TestGameController(mock_adb)
        controller.recognizer = mock_recognizer
        controller.ocr = mock_ocr
        
        # 模拟图像识别成功
        mock_recognizer.find_template.return_value = MagicMock()
        
        scene = controller.detect_scene(sample_screenshot)
        assert scene == "main"
        assert controller.current_scene == "main"
    
    def test_wait_for_scene(self, mock_adb):
        """测试等待场景"""
        controller = TestGameController(mock_adb)
        
        # 模拟场景检测
        with patch.object(controller, 'detect_scene', side_effect=[None, None, "target"]):
            result = controller.wait_for_scene("target", timeout=5.0, interval=0.1)
            assert result is True
    
    def test_click_point(self, mock_adb):
        """测试点击点"""
        controller = TestGameController(mock_adb)
        
        # 点击ClickPoint对象
        point = ClickPoint("test", 100, 200, wait_after=0.5)
        with patch('time.sleep'):
            controller.click_point(point)
            mock_adb.tap.assert_called_with(100, 200)
        
        # 点击坐标元组
        controller.click_point((300, 400), wait_after=0)
        mock_adb.tap.assert_called_with(300, 400)
    
    def test_click_template(self, mock_adb, mock_recognizer, sample_screenshot):
        """测试点击模板"""
        controller = TestGameController(mock_adb)
        controller.recognizer = mock_recognizer
        
        # 模拟模板匹配
        mock_result = MagicMock()
        mock_result.center = (500, 1000)
        mock_recognizer.find_template.return_value = mock_result
        
        with patch('time.sleep'):
            result = controller.click_template("template", sample_screenshot)
            assert result is True
            mock_adb.tap.assert_called_with(500, 1000)
    
    def test_click_text(self, mock_adb, mock_ocr, sample_screenshot):
        """测试点击文字"""
        controller = TestGameController(mock_adb)
        controller.ocr = mock_ocr
        
        # 模拟文字识别
        mock_result = MagicMock()
        mock_result.bbox = (100, 200, 100, 50)  # x, y, width, height
        mock_ocr.find_text.return_value = mock_result
        
        with patch('time.sleep'):
            result = controller.click_text("text", sample_screenshot)
            assert result is True
            mock_adb.tap.assert_called_with(150, 225)  # 中心点
    
    def test_swipe_direction(self, mock_adb):
        """测试方向滑动"""
        controller = TestGameController(mock_adb)
        
        # 测试向上滑动
        controller.swipe_direction("up", distance=500)
        call_args = mock_adb.swipe.call_args[0]
        assert call_args[1] > call_args[3]  # y1 > y2
        
        # 测试向下滑动
        controller.swipe_direction("down", distance=500)
        call_args = mock_adb.swipe.call_args[0]
        assert call_args[1] < call_args[3]  # y1 < y2


class TestAFK2Controller:
    """AFK2控制器测试"""
    
    def test_init(self, mock_adb):
        """测试初始化"""
        controller = AFK2Controller(mock_adb)
        assert controller.config.package_name == "com.lilith.odyssey.cn"
        assert controller.auto_battle_enabled is True
        assert len(controller._scenes) > 0
    
    def test_navigate_step(self, mock_adb):
        """测试导航步骤"""
        controller = AFK2Controller(mock_adb)
        
        # 从主界面到征战
        with patch.object(controller, 'click_point'):
            with patch.object(controller, 'wait_for_scene', return_value=True):
                result = controller._navigate_step(
                    AFK2Scene.MAIN.value,
                    AFK2Scene.CAMPAIGN.value
                )
                assert result is True
    
    def test_collect_idle_rewards(self, mock_adb, mock_recognizer):
        """测试领取挂机奖励"""
        controller = AFK2Controller(mock_adb)
        controller.recognizer = mock_recognizer
        
        # 模拟有奖励可领取
        mock_recognizer.find_template.return_value = MagicMock()
        
        with patch.object(controller, 'navigate_to_scene', return_value=True):
            with patch.object(controller, 'screenshot', return_value=MagicMock()):
                with patch.object(controller, 'click_point'):
                    with patch('time.sleep'):
                        result = controller.collect_idle_rewards()
                        assert result is True
    
    def test_auto_campaign(self, mock_adb, mock_recognizer):
        """测试自动征战"""
        controller = AFK2Controller(mock_adb)
        controller.recognizer = mock_recognizer
        
        # 模拟战斗流程
        with patch.object(controller, 'navigate_to_scene', return_value=True):
            with patch.object(controller, 'click_point'):
                with patch.object(controller, 'wait_for_scene', side_effect=[True, True]):
                    with patch.object(controller, 'screenshot', return_value=MagicMock()):
                        # 模拟胜利
                        mock_recognizer.find_template.return_value = MagicMock()
                        
                        with patch('time.sleep'):
                            result = controller.auto_campaign(max_battles=1)
                            assert result is True
    
    def test_perform_daily_tasks(self, mock_adb):
        """测试执行日常任务"""
        controller = AFK2Controller(mock_adb)
        
        with patch.object(controller, 'navigate_to_scene', return_value=True):
            with patch.object(controller, 'collect_idle_rewards', return_value=True):
                with patch.object(controller, 'collect_mail', return_value=True):
                    with patch.object(controller, 'complete_daily_quests', return_value=True):
                        with patch.object(controller, 'auto_campaign', return_value=True):
                            with patch.object(controller, 'guild_checkin', return_value=True):
                                with patch.object(controller, 'shop_free_draw', return_value=True):
                                    results = controller.perform_daily_tasks()
                                    
                                    assert 'idle_rewards' in results
                                    assert 'mail' in results
                                    assert 'daily_quests' in results
                                    assert 'campaign' in results


class TestSceneDetector:
    """场景检测器测试"""
    
    def test_init(self):
        """测试初始化"""
        detector = SceneDetector()
        assert detector._scenes == {}
        assert detector._cache_enabled is True
    
    def test_register_scene(self):
        """测试注册场景"""
        detector = SceneDetector()
        
        features = [
            SceneFeature("feature1", "image", "template1"),
            SceneFeature("feature2", "text", "text1")
        ]
        
        detector.register_scene("test_scene", features)
        assert "test_scene" in detector._scenes
        assert len(detector._scenes["test_scene"]) == 2
    
    def test_detect_scene(self, sample_screenshot):
        """测试场景检测"""
        detector = SceneDetector()
        
        # 注册场景
        features = [SceneFeature("test", "image", "test_template")]
        detector.register_scene("test_scene", features)
        
        # 模拟特征匹配
        with patch.object(detector, '_match_single_feature', return_value=True):
            result = detector.detect_scene(sample_screenshot, use_cache=False)
            
            assert result is not None
            assert result.scene_name == "test_scene"
            assert result.confidence == 1.0
    
    def test_cache(self, sample_screenshot):
        """测试缓存机制"""
        detector = SceneDetector()
        
        # 注册场景
        features = [SceneFeature("test", "image", "test")]
        detector.register_scene("cached_scene", features)
        
        # 第一次检测
        with patch.object(detector, '_match_single_feature', return_value=True):
            result1 = detector.detect_scene(sample_screenshot)
            
            # 第二次检测（应使用缓存）
            with patch.object(detector, '_match_scene_features') as mock_match:
                result2 = detector.detect_scene(sample_screenshot)
                mock_match.assert_not_called()  # 不应调用匹配函数
                
                assert result2.scene_name == result1.scene_name