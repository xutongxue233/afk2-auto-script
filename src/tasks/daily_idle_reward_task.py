"""
领取每日挂机奖励任务
自动领取游戏中的挂机奖励
"""

import time
import os
from typing import Optional, Tuple
from src.services.log_service import LoggerMixin
from src.recognition.image_recognizer import ImageRecognizer
from src.recognition.ocr_engine import OCREngine
from src.services.adb_service import ADBService


class DailyIdleRewardTask(LoggerMixin):
    """
    每日挂机奖励领取任务
    
    任务流程：
    1. 检查是否在托管中状态，如果是则点击退出托管
    2. 寻找并点击"收获奖励"按钮
    3. 如果没有找到收获奖励，寻找沙漏图标并点击屏幕中间位置
    4. 再次尝试收获奖励
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
            'idle_mode': os.path.join(self.image_dir, 'idle_mode.png'),
            'collect_reward': os.path.join(self.image_dir, 'collect_reward.png'),
            'hourglass': os.path.join(self.image_dir, 'hourglass.png'),
            'current_progress': os.path.join(self.image_dir, 'current_progress.png')
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
        
        Args:
            device_id: 设备ID，如果为None则使用默认设备
        
        Returns:
            任务是否成功完成
        """
        try:
            self.logger.info("Starting daily idle reward collection task")
            
            # 确保设备连接
            if device_id:
                self.adb_service.select_device(device_id)
            
            if not self.adb_service.is_connected():
                self.logger.error("Device not connected")
                return False
            
            # 步骤1：检查是否在托管中
            if self._check_and_exit_idle_mode():
                self.logger.info("Exited idle mode")
                time.sleep(2)  # 等待界面切换
            
            # 步骤2：尝试直接收获奖励
            if self._try_collect_reward():
                self.logger.info("Successfully collected reward directly")
                return True
            
            # 步骤3：如果没有找到收获奖励，寻找沙漏
            if self._click_hourglass():
                self.logger.info("Clicked hourglass, attempting to collect reward")
                time.sleep(2)  # 等待界面更新
                
                # 步骤4：再次尝试收获奖励
                if self._try_collect_reward():
                    self.logger.info("Successfully collected reward after clicking hourglass")
                    return True
            
            # 如果所有步骤都失败
            self.logger.error("Failed to collect idle reward: no valid targets found")
            return False
            
        except Exception as e:
            self.logger.error(f"Task execution failed: {e}")
            return False
    
    def _check_and_exit_idle_mode(self) -> bool:
        """
        检查是否在托管模式并退出，或检查当前进度
        
        Returns:
            是否找到并点击了托管中/当前进度图标
        """
        try:
            # 截图
            screenshot = self.adb_service.take_screenshot()
            if screenshot is None:
                self.logger.error("Failed to take screenshot")
                return False
            
            
            # 裁剪底部30%区域进行识别
            width, height = screenshot.size
            bottom_region = (0, int(height * 0.7), width, height)  # 底部30%区域
            
            # 优先检查托管中图标
            result = self.image_recognizer.find_template(
                screenshot,
                'idle_mode',
                threshold=0.65,
                region=bottom_region,
                use_grayscale=True
            )
            
            if result:
                # result.center已经是绝对坐标（包含region偏移）
                x, y = result.center
                self.logger.info(f"Found idle mode icon at ({x}, {y}) with confidence {result.confidence:.2f}")
                
                # 验证位置是否合理（应该在屏幕左下角）
                screen_info = f"Screen size: {width}x{height}"
                position_info = f"Found position: x={x} (left={x < width//2}), y={y} (bottom={y > height//2})"
                region_info = f"Search region: {bottom_region} (bottom 30%)"
                relative_pos = f"Relative to region: x={x}, y={y - int(height * 0.7)} (within region)"
                
                self.logger.info(screen_info)
                self.logger.info(position_info)
                self.logger.info(region_info)
                self.logger.info(relative_pos)
                
                # 检查位置是否合理
                is_left_side = x < width // 2
                is_bottom_area = y > height * 0.7
                
                self.logger.info(f"Position analysis: left_side={is_left_side}, bottom_area={is_bottom_area}")
                
                if not is_left_side:
                    self.logger.warning(f"❌ Icon found on RIGHT side (x={x}/{width}), expected LEFT side")
                else:
                    self.logger.info(f"✅ Icon correctly found on LEFT side (x={x}/{width})")
                    
                if not is_bottom_area:
                    self.logger.warning(f"❌ Icon found in UPPER area (y={y}/{height}), expected BOTTOM area")
                else:
                    self.logger.info(f"✅ Icon correctly found in BOTTOM area (y={y}/{height})")
                
                # 如果位置不正确，可能是误识别
                if not is_left_side or not is_bottom_area:
                    self.logger.error(f"🚫 Recognition position seems incorrect! Expected: left-bottom, Found: {'right' if not is_left_side else 'left'}-{'top' if not is_bottom_area else 'bottom'}")
                    
                    # 尝试降低阈值或使用不同的识别策略
                    self.logger.info("Trying alternative recognition with lower threshold...")
                    alternative_result = self.image_recognizer.find_template(
                        screenshot,
                        'idle_mode',
                        threshold=0.4,  # 降低阈值
                        region=(0, int(height * 0.8), width // 2, height),  # 只在左下角区域搜索
                        use_grayscale=True
                    )
                    
                    if alternative_result:
                        alt_x, alt_y = alternative_result.center
                        self.logger.info(f"🔄 Alternative recognition found at ({alt_x}, {alt_y}) with confidence {alternative_result.confidence:.3f}")
                        
                        # 检查新位置是否更合理
                        alt_is_left = alt_x < width // 2
                        alt_is_bottom = alt_y > height * 0.8
                        
                        if alt_is_left and alt_is_bottom:
                            self.logger.info("✅ Alternative position is more reasonable, using it instead")
                            x, y = alt_x, alt_y
                            result = alternative_result
                        else:
                            self.logger.warning("❌ Alternative position is also not ideal")
                    else:
                        self.logger.warning("⚠️ No alternative recognition found in left-bottom area")
                
                
                # 尝试多种点击策略
                for attempt in range(3):
                    self.logger.info(f"Attempting to tap idle mode icon at ({x}, {y}) - attempt {attempt + 1}")
                    
                    # 尝试点击中心位置
                    self.adb_service.tap(x, y)
                    self.logger.info(f"Tap command executed at ({x}, {y})")
                    
                    # 等待响应
                    time.sleep(2)
                    
                    # 验证点击是否成功（检查图标是否还在）
                    verify_screenshot = self.adb_service.take_screenshot()
                    if verify_screenshot:
                        verify_result = self.image_recognizer.find_template(
                            verify_screenshot,
                            'idle_mode',
                            threshold=0.6,
                            region=bottom_region,
                            use_grayscale=True
                        )
                        
                        if not verify_result:
                            self.logger.info(f"Successfully tapped idle mode icon - icon disappeared after attempt {attempt + 1}")
                            return True
                        else:
                            self.logger.warning(f"Idle mode icon still present after attempt {attempt + 1}")
                    
                    # 如果第一次失败，尝试稍微偏移的位置
                    if attempt < 2:
                        # 尝试点击稍微上方的位置
                        offset_y = y - 10
                        self.logger.info(f"Trying offset position ({x}, {offset_y})")
                        self.adb_service.tap(x, offset_y)
                        time.sleep(1)
                
                self.logger.warning("Failed to tap idle mode icon after 3 attempts")
                return True  # 继续执行后续步骤
            
            # 如果没有找到"托管中"，检查"当前进度"
            result = self.image_recognizer.find_template(
                screenshot,
                'current_progress',
                threshold=0.6,
                region=bottom_region,
                use_grayscale=True
            )
            
            if result:
                x, y = result.center
                self.logger.info(f"Found current progress at ({x}, {y}) with confidence {result.confidence:.2f}")
                
                # 点击当前进度查看详情
                self.logger.info(f"Attempting to tap current progress at ({x}, {y})")
                self.adb_service.tap(x, y)
                self.logger.info(f"Tap command executed at ({x}, {y})")
                
                # 等待界面响应
                time.sleep(1)
                
                return True
            else:
                self.logger.info("Neither idle mode nor current progress found, continuing...")
                
        except Exception as e:
            self.logger.error(f"Error checking idle mode: {e}")
        
        return False
    
    def _try_collect_reward(self) -> bool:
        """
        尝试收获奖励
        
        Returns:
            是否成功找到并点击收获奖励
        """
        try:
            # 截图
            screenshot = self.adb_service.take_screenshot()
            if screenshot is None:
                self.logger.error("Failed to take screenshot for reward collection")
                return False
            
            
            # 裁剪底部30%区域进行识别
            width, height = screenshot.size
            bottom_region = (0, int(height * 0.7), width, height)  # 底部30%区域
            
            # 方法1：通过图片识别
            result = self.image_recognizer.find_template(
                screenshot,
                'collect_reward',
                threshold=0.6,
                region=bottom_region
            )
            
            if result:
                x, y = result.center
                self.logger.info(f"Found collect reward button (image) at ({x}, {y}) with confidence {result.confidence:.2f}")
                self.adb_service.tap(x, y)
                return True
            else:
                self.logger.info("Collect reward button not found with image recognition")
            
            # 方法2：通过文字识别（如果有OCR引擎）
            if self.ocr_engine:
                self.logger.info("Trying OCR text recognition for reward collection")
                text_results = self.ocr_engine.recognize_with_details(screenshot)
                self.logger.info(f"OCR found {len(text_results)} text regions")
                for text_item in text_results:
                    self.logger.debug(f"OCR text: '{text_item.text}' at {text_item.position}")
                    if '收获奖励' in text_item.text or '收集' in text_item.text or '领取' in text_item.text:
                        x, y = text_item.position
                        self.logger.info(f"Found collect reward text at ({x}, {y}): {text_item.text}")
                        self.adb_service.tap(x, y)
                        return True
            else:
                self.logger.info("No OCR engine available for text recognition")
            
        except Exception as e:
            self.logger.error(f"Error trying to collect reward: {e}")
        
        return False
    
    def _click_hourglass(self) -> bool:
        """
        寻找沙漏图标并点击屏幕中间位置
        
        Returns:
            是否成功找到沙漏并执行点击
        """
        try:
            # 截图
            screenshot = self.adb_service.take_screenshot()
            if screenshot is None:
                self.logger.error("Failed to take screenshot for hourglass detection")
                return False
            
            
            # 裁剪底部30%区域进行识别
            width, height = screenshot.size
            bottom_region = (0, int(height * 0.7), width, height)  # 底部30%区域
            
            # 识别沙漏图标
            result = self.image_recognizer.find_template(
                screenshot,
                'hourglass',
                threshold=0.6,
                region=bottom_region
            )
            
            if result:
                _, y = result.center
                
                # 获取屏幕尺寸
                screen_width, screen_height = self._get_screen_size()
                
                # 点击屏幕中间位置（x坐标），保持y坐标不变
                x = screen_width // 2
                self.logger.info(f"Found hourglass at confidence {result.confidence:.2f}, clicking at ({x}, {y})")
                self.adb_service.tap(x, y)
                return True
            else:
                self.logger.info("Hourglass icon not found")
                
        except Exception as e:
            self.logger.error(f"Error clicking hourglass: {e}")
        
        return False
    
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