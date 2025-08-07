"""
领取每日挂机奖励任务
自动领取游戏中的挂机奖励
"""

import time
import os
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from src.services.log_service import LoggerMixin
from src.recognition.image_recognizer import ImageRecognizer
from src.recognition.ocr_engine import OCREngine
from src.services.adb_service import ADBService


class DailyIdleRewardTask(LoggerMixin):
    """
    每日挂机奖励领取任务

    任务流程逻辑：
        1.找到 托管中/当前进度/托管完成 三个其中一个的坐标中心点，点击
        2.判断是否弹出 收获奖励 按钮，如果有则点击，任务完成
        3.如果没有弹出 收获奖励 按钮，点击屏幕50%，80%的位置，然后识别 收获奖励 按钮点击，任务完成

    """
    
    def __init__(self, adb_service: ADBService, image_recognizer: ImageRecognizer, ocr_engine: Optional[OCREngine] = None):
        """
        初始化任务
        
        Args:
            adb_service: ADB服务实例
            image_recognizer: 图像识别器实例
            ocr_engine: OCR引擎实例（可选，用于文字识别）
        """
        super().__init__()
        self.adb_service = adb_service
        self.image_recognizer = image_recognizer
        self.ocr_engine = ocr_engine
        
        # 图片资源路径
        self.image_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'resources', 'images'
        )
        
        # 定义图片路径
        self.images = {
            'idle_mode': os.path.join(self.image_dir, 'idle_mode.png'),  # 托管中
            'collect_reward': os.path.join(self.image_dir, 'collect_reward.png'),
            'hourglass': os.path.join(self.image_dir, 'hourglass.png'),
            'current_progress': os.path.join(self.image_dir, 'current_progress.png'),  # 当前进度
            'idle_completed': os.path.join(self.image_dir, 'idle_completed.png')  # 托管完成
        }
        
        # 验证图片文件是否存在
        self._validate_images()
    
    def _validate_images(self) -> None:
        """验证所需图片文件是否存在"""
        for name, path in self.images.items():
            if not os.path.exists(path):
                self.logger.error(f"Required image not found: {name} at {path}")
                raise FileNotFoundError(f"Image file not found: {path}")
    
    def execute(self, device_id: Optional[str] = None) -> bool:
        """
        执行领取挂机奖励任务
        
        根据任务流程逻辑：
        1. 找到 托管中/当前进度/托管完成 三个其中一个的坐标中心点，点击
        2. 判断是否弹出 收获奖励 按钮，如果有则点击，任务完成
        3. 如果没有弹出 收获奖励 按钮，点击屏幕50%，80%的位置，然后识别 收获奖励 按钮点击
        
        Args:
            device_id: 设备ID，如果为None则使用默认设备
        
        Returns:
            任务是否成功完成
        """
        try:
            self.logger.info("开始执行每日挂机奖励领取任务")
            
            # 确保设备连接
            if device_id:
                self.adb_service.select_device(device_id)
            
            if not self.adb_service.is_connected():
                self.logger.error("设备未连接")
                return False
            
            # 步骤1：找到并点击 托管中/当前进度/托管完成 图标
            clicked_icon = self._find_and_click_idle_icon()
            if not clicked_icon:
                self.logger.warning("未找到任何挂机相关图标")
                return False
            
            self.logger.info(f"已点击 {clicked_icon} 图标")
            
            # 等待界面响应
            time.sleep(2)
            
            # 步骤2：尝试查找并点击 收获奖励 按钮
            if self._find_and_click_collect_reward():
                self.logger.info("成功点击收获奖励按钮，任务完成")
                return True
            
            # 步骤3：如果没有找到收获奖励按钮，点击屏幕中间位置后再次尝试
            self.logger.info("未找到收获奖励按钮，尝试点击屏幕中间位置")
            self._click_screen_center()
            
            # 等待界面响应
            time.sleep(2)
            
            # 再次尝试查找并点击收获奖励按钮
            if self._find_and_click_collect_reward():
                self.logger.info("成功点击收获奖励按钮，任务完成")
                return True
            
            self.logger.warning("未能成功领取挂机奖励")
            return False
            
        except Exception as e:
            self.logger.error(f"任务执行失败: {e}")
            return False
    
    def _find_and_click_idle_icon(self) -> Optional[str]:
        """
        查找并点击挂机相关图标（托管中/当前进度/托管完成）
        
        Returns:
            点击的图标名称，如果没有找到则返回 None
        """
        try:
            # 截图
            screenshot = self.adb_service.take_screenshot()
            if screenshot is None:
                self.logger.error("Failed to take screenshot")
                return None
            
            # 裁剪底部30%区域进行识别
            width, height = screenshot.size
            bottom_region = (0, int(height * 0.7), width, height)  # 底部30%区域
            
            # 定义要查找的图标列表（优先级顺序）
            icons_to_check = [
                ('idle_completed', '托管完成'),
                ('idle_mode', '托管中'),
                ('current_progress', '当前进度')
            ]
            
            # 依次查找图标
            for icon_key, icon_name in icons_to_check:
                result = self.image_recognizer.find_template(
                    screenshot,
                    icon_key,
                    threshold=0.7,
                    region=bottom_region,
                    use_grayscale=True
                )
                
                if result:
                    x, y = result.center
                    self.logger.info(f"找到 {icon_name} 图标，位置: ({x}, {y})，置信度: {result.confidence:.2f}")
                    
                    # 点击图标
                    self.adb_service.tap(x, y)
                    self.logger.info(f"已点击 {icon_name} 图标")
                    
                    return icon_name
            
            self.logger.info("未找到任何挂机相关图标")
            return None
                
        except Exception as e:
            self.logger.error(f"Error checking idle mode: {e}")
            return None
    
    def _save_click_screenshot(self, screenshot: Image.Image, click_x: int, click_y: int, label: str = "click") -> None:
        """
        保存带点击位置标记的截图
        
        Args:
            screenshot: 原始截图
            click_x: 点击X坐标
            click_y: 点击Y坐标
            label: 标签说明
        """
        try:
            # 创建截图副本用于标记
            marked_image = screenshot.copy()
            draw = ImageDraw.Draw(marked_image)
            
            # 画十字准星标记点击位置
            cross_size = 50
            line_width = 3
            # 水平线
            draw.line([(click_x - cross_size, click_y), (click_x + cross_size, click_y)], 
                     fill='red', width=line_width)
            # 垂直线
            draw.line([(click_x, click_y - cross_size), (click_x, click_y + cross_size)], 
                     fill='red', width=line_width)
            
            # 画圆圈
            circle_radius = 30
            draw.ellipse([(click_x - circle_radius, click_y - circle_radius),
                         (click_x + circle_radius, click_y + circle_radius)],
                        outline='red', width=line_width)
            
            # 添加文字标注
            text = f"{label}: ({click_x}, {click_y})"
            # 计算文字位置（在点击位置上方）
            text_y = click_y - circle_radius - 40 if click_y > 100 else click_y + circle_radius + 10
            
            # 绘制文字背景
            bbox = [click_x - 100, text_y - 5, click_x + 100, text_y + 25]
            draw.rectangle(bbox, fill='white', outline='red', width=2)
            
            # 绘制文字（简单文字，不使用字体）
            draw.text((click_x - 95, text_y), text, fill='red')
            
            # 创建debug目录
            debug_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'debug', 'clicks'
            )
            os.makedirs(debug_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{label}_{timestamp}_{click_x}_{click_y}.png"
            filepath = os.path.join(debug_dir, filename)
            
            # 保存图片
            marked_image.save(filepath)
            self.logger.info(f"Saved click screenshot to: {filepath}")
            
        except Exception as e:
            self.logger.error(f"Failed to save click screenshot: {e}")
    
    def _find_and_click_collect_reward(self) -> bool:
        """
        查找并点击收获奖励按钮
        
        Returns:
            是否成功找到并点击收获奖励按钮
        """
        try:
            # 截图
            screenshot = self.adb_service.take_screenshot()
            if screenshot is None:
                self.logger.error("截图失败")
                return False
            
            # 裁剪底部30%区域进行识别
            width, height = screenshot.size
            bottom_region = (0, int(height * 0.7), width, height)  # 底部30%区域
            
            # 通过图片模板匹配查找收获奖励按钮
            result = self.image_recognizer.find_template(
                screenshot,
                'collect_reward',
                threshold=0.6,
                region=bottom_region
            )
            
            if result:
                x, y = result.center
                self.logger.info(f"找到收获奖励按钮，位置: ({x}, {y})，置信度: {result.confidence:.2f}")
                self.adb_service.tap(x, y)
                return True
            
            # 如果有OCR引擎，尝试通过文字识别
            if self.ocr_engine:
                self.logger.info("尝试通过OCR识别收获奖励按钮")
                ocr_results = self.ocr_engine.recognize(screenshot)
                for text, bbox in ocr_results:
                    if "收获" in text or "奖励" in text or "领取" in text:
                        # 计算文字中心点
                        center_x = (bbox[0] + bbox[2]) // 2
                        center_y = (bbox[1] + bbox[3]) // 2
                        self.logger.info(f"通过OCR找到相关文字 '{text}'，位置: ({center_x}, {center_y})")
                        self.adb_service.tap(center_x, center_y)
                        return True
            
            self.logger.info("未找到收获奖励按钮")
            return False
            
        except Exception as e:
            self.logger.error(f"查找收获奖励按钮时出错: {e}")
            return False
    
    def _click_screen_center(self) -> None:
        """
        点击屏幕中间偏下位置（50%, 80%）
        """
        try:
            # 获取屏幕尺寸
            screen_width, screen_height = self._get_screen_size()
            
            # 计算点击位置（水平50%，垂直80%）
            click_x = screen_width // 2
            click_y = int(screen_height * 0.8)
            
            self.logger.info(f"点击屏幕中间位置: ({click_x}, {click_y})")
            self.adb_service.tap(click_x, click_y)
            
        except Exception as e:
            self.logger.error(f"点击屏幕中间位置时出错: {e}")
    
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """
        获取屏幕尺寸
        
        Returns:
            (宽度, 高度)
        """
        try:
            size_str = self.adb_service.execute_command("shell wm size")
            if size_str and 'Physical size:' in size_str:
                # 解析格式: Physical size: 1080x2400
                size_part = size_str.split('Physical size:')[1].strip()
                width, height = map(int, size_part.split('x'))
                return width, height
        except Exception as e:
            self.logger.error(f"Failed to get screen size: {e}")
        
        # 返回默认值
        return 1080, 2400


def create_daily_idle_reward_task(adb_service: ADBService, image_recognizer: ImageRecognizer, ocr_engine: Optional[OCREngine] = None) -> DailyIdleRewardTask:
    """
    创建每日挂机奖励任务实例
    
    Args:
        adb_service: ADB服务实例
        image_recognizer: 图像识别器实例
        ocr_engine: OCR引擎实例（可选）
    
    Returns:
        任务实例
    """
    return DailyIdleRewardTask(adb_service, image_recognizer, ocr_engine)
