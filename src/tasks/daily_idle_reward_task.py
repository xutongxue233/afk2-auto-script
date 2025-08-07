"""
领取每日挂机奖励任务
自动领取游戏中的挂机奖励
"""

import time
import os
from typing import Optional, Tuple
import time
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import cv2
import numpy as np
from src.services.log_service import LoggerMixin
from src.recognition.image_recognizer import ImageRecognizer
from src.recognition.ocr_engine import OCREngine
from src.services.adb_service import ADBService


class DailyIdleRewardTask(LoggerMixin):
    """
    每日挂机奖励领取任务

    优化后的任务流程逻辑：
        1. 识别神秘屋图标，确认在游戏主界面
        2. 点击左下角固定位置（8%, 99%）打开挂机界面
        3. 判断是否弹出 收获奖励 按钮，如果有则点击，任务完成
        4. 如果没有弹出 收获奖励 按钮，点击屏幕50%，80%的位置，然后识别 收获奖励 按钮点击，任务完成

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
            'mystery_house': os.path.join(self.image_dir, 'wake', 'mystery_house.png'),  # 神秘屋图标
            'collect_reward': os.path.join(self.image_dir, 'collect_reward.png'),  # 收获奖励按钮
            'back_button_1': os.path.join(self.image_dir, 'back_button_1.png'),  # 返回按钮样式1
            'back_button_2': os.path.join(self.image_dir, 'back_button_2.png'),  # 返回按钮样式2
        }
        
        # 预加载模板
        self._templates = {}
        
        # 验证图片文件是否存在（仅验证必需的图片）
        self._validate_required_images()
    
    def _validate_required_images(self) -> None:
        """验证必需的图片文件是否存在"""
        # 只验证必需的图片
        required_images = ['mystery_house', 'collect_reward']
        for name in required_images:
            path = self.images.get(name)
            if path and not os.path.exists(path):
                self.logger.warning(f"Image not found: {name} at {path}")
                # 不再抛出异常，允许任务继续执行
    
    def execute(self, device_id: Optional[str] = None) -> bool:
        """
        执行领取挂机奖励任务
        
        优化后的流程：
        1. 识别神秘屋图标，确认在游戏主界面
        2. 点击左下角固定位置（8%, 99%）打开挂机界面
        3. 判断是否弹出 收获奖励 按钮，如果有则点击，任务完成
        4. 如果没有弹出 收获奖励 按钮，点击屏幕50%，80%的位置，然后再次识别收获奖励按钮
        
        Args:
            device_id: 设备ID，如果为None则使用默认设备
        
        Returns:
            任务是否成功完成
        """
        try:
            # 确保设备连接
            if device_id:
                self.adb_service.select_device(device_id)
            
            if not self.adb_service.is_connected():
                self.logger.error("设备未连接")
                return False
            
            # 步骤1：识别神秘屋图标，确认在游戏主界面
            if not self._check_mystery_house():
                self.logger.warning("未识别到神秘屋图标，可能不在游戏主界面")
                # 即使没有识别到，也尝试继续执行
            else:
                self.logger.info("已确认在游戏主界面")
            
            # 步骤2：点击左下角固定位置打开挂机界面
            self._click_idle_button()
            
            # 等待界面响应
            time.sleep(2)
            
            # 步骤3：尝试查找并点击 收获奖励 按钮
            reward_collected = False
            if self._find_and_click_collect_reward():
                self.logger.info("成功点击收获奖励按钮")
                reward_collected = True
                # 等待奖励收集动画
                time.sleep(2)
            else:
                # 步骤4：如果没有找到收获奖励按钮，点击屏幕中间位置后再次尝试
                self.logger.info("未找到收获奖励按钮，尝试点击屏幕中间位置")
                self._click_screen_center()
                
                # 等待界面响应
                time.sleep(2)
                
                # 再次尝试查找并点击收获奖励按钮
                if self._find_and_click_collect_reward():
                    self.logger.info("成功点击收获奖励按钮")
                    reward_collected = True
                    # 等待奖励收集动画
                    time.sleep(2)
            
            # 步骤5：如果成功收获奖励，点击返回按钮返回主界面
            if reward_collected:
                self.logger.info("奖励已收集，点击返回按钮")
                self._click_back_button()
                time.sleep(1)
                self.logger.info("任务完成")
                return True
            
            self.logger.warning("未能成功领取挂机奖励")
            return False
            
        except Exception as e:
            self.logger.error(f"任务执行失败: {e}")
            return False
    
    def _check_mystery_house(self) -> bool:
        """
        检查是否在游戏主界面（通过识别神秘屋图标）
        
        Returns:
            是否在游戏主界面
        """
        try:
            # 加载神秘屋模板图片
            mystery_house_img = self._load_template_image('mystery_house')
            if mystery_house_img is None:
                self.logger.warning("无法加载神秘屋模板图片")
                return False
            
            # 截图
            screenshot = self.adb_service.take_screenshot()
            if screenshot is None:
                self.logger.error("无法获取截图")
                return False
            
            # 使用自定义方法识别神秘屋图标
            result = self._find_template_in_image(screenshot, mystery_house_img, threshold=0.7)
            
            if result:
                x, y = result
                self.logger.info(f"识别到神秘屋图标，位置: ({x}, {y})")
                return True
            else:
                self.logger.debug("未识别到神秘屋图标")
                return False
                
        except Exception as e:
            self.logger.error(f"检查神秘屋时出错: {e}")
            return False
    
    def _click_idle_button(self) -> None:
        """
        点击左下角挂机按钮（当前进度标志位置）
        根据不同分辨率自适应调整位置
        """
        try:
            # 获取屏幕尺寸
            screen_width, screen_height = self._get_screen_size()
            
            # 根据屏幕比例判断设备类型并调整点击位置
            aspect_ratio = screen_height / screen_width
            
            # 左下角"当前进度"按钮的位置
            # 基于用户反馈：按钮在左下角，位置是8%水平，99%垂直
            if aspect_ratio > 2.0:
                # 全面屏手机（如3200x1440）
                click_x = int(screen_width * 0.08)  # 水平8%位置
                click_y = int(screen_height * 0.99)  # 垂直99%位置（接近底部）
            elif aspect_ratio > 1.8:
                # 普通全面屏（如2340x1080）
                click_x = int(screen_width * 0.08)  # 水平8%位置
                click_y = int(screen_height * 0.99)  # 垂直99%位置
            else:
                # 16:9或更宽的屏幕
                click_x = int(screen_width * 0.08)  # 水平8%位置
                click_y = int(screen_height * 0.99)  # 垂直99%位置
            
            # 根据分辨率微调（更精确的位置）
            # 用户明确要求：8%水平，99%垂直
            if screen_width == 1080 and screen_height == 2400:
                # 您的设备的实际截图尺寸
                click_x = int(screen_width * 0.08)  # 8%水平 = 86像素
                click_y = int(screen_height * 0.99)  # 99%垂直 = 2376像素
            elif screen_width >= 1440:
                # 2K或更高分辨率
                click_x = int(screen_width * 0.08)  # 8%水平
                click_y = int(screen_height * 0.99)  # 99%垂直
            elif screen_width == 1080:
                # 其他1080p屏幕
                click_x = int(screen_width * 0.08)  # 8%水平
                click_y = int(screen_height * 0.99)  # 99%垂直
            elif screen_width <= 720:
                # 低分辨率屏幕
                click_x = int(screen_width * 0.08)  # 8%水平
                click_y = int(screen_height * 0.99)  # 99%垂直
            
            self.logger.info(f"点击左下角挂机按钮位置: ({click_x}, {click_y})")
            
            # 执行点击
            self.adb_service.tap(click_x, click_y)
            
        except Exception as e:
            self.logger.error(f"点击挂机按钮时出错: {e}")
            # 使用备用固定坐标
            try:
                self.logger.info("尝试使用备用坐标点击")
                # 根据常见分辨率使用固定坐标（调整到更高位置）
                screen_width, screen_height = self._get_screen_size()
                if screen_width == 1080:
                    # 1080p屏幕的固定坐标
                    self.adb_service.tap(119, int(screen_height * 0.835))
                elif screen_width == 1440:
                    # 2K屏幕的固定坐标
                    self.adb_service.tap(int(screen_width * 0.08), int(screen_height * 0.99))
                else:
                    # 默认坐标
                    self.adb_service.tap(int(screen_width * 0.08), int(screen_height * 0.99))
            except Exception as backup_error:
                self.logger.error(f"备用坐标点击也失败: {backup_error}")
    
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
            self.logger.info(f"准备保存点击截图 - 图像大小: {screenshot.size}, 点击坐标: ({click_x}, {click_y})")
            
            # 验证坐标是否在图像范围内
            img_width, img_height = screenshot.size
            if click_x < 0 or click_x >= img_width or click_y < 0 or click_y >= img_height:
                self.logger.warning(f"点击坐标({click_x}, {click_y})超出图像范围({img_width}x{img_height})")
                # 调整坐标到图像范围内
                click_x = max(0, min(click_x, img_width - 1))
                click_y = max(0, min(click_y, img_height - 1))
                self.logger.info(f"调整后的坐标: ({click_x}, {click_y})")
            
            # 确保图像是RGB模式
            if screenshot.mode != 'RGB':
                self.logger.info(f"转换图像模式从 {screenshot.mode} 到 RGB")
                screenshot = screenshot.convert('RGB')
            
            # 创建截图副本用于标记
            marked_image = screenshot.copy()
            self.logger.info(f"创建图像副本成功")
            draw = ImageDraw.Draw(marked_image)
            self.logger.info(f"ImageDraw对象创建成功")
            
            # 定义颜色（确保在RGB模式下正确显示）
            RED = (255, 0, 0)
            GREEN = (0, 255, 0)
            BLUE = (0, 0, 255)
            YELLOW = (255, 255, 0)
            WHITE = (255, 255, 255)
            BLACK = (0, 0, 0)
            
            # 首先画一个简单的大方框测试是否能正常绘制
            test_size = 200
            test_x = min(click_x, img_width - test_size - 10)
            test_y = min(click_y, img_height - test_size - 10)
            draw.rectangle([test_x, test_y, test_x + test_size, test_y + test_size], 
                          outline=RED, width=10)
            self.logger.info(f"测试方框绘制完成: ({test_x}, {test_y}, {test_x + test_size}, {test_y + test_size})")
            
            # 1. 画大十字准星（最明显的标记）  
            cross_size = 100
            line_width = 8
            self.logger.info(f"准备绘制十字准星，大小: {cross_size}, 线宽: {line_width}")
            # 先画黑色边框（增强对比度）
            h_start = max(0, click_x - cross_size)
            h_end = min(img_width - 1, click_x + cross_size)
            v_start = max(0, click_y - cross_size)
            v_end = min(img_height - 1, click_y + cross_size)
            
            draw.line([(h_start, click_y), (h_end, click_y)], 
                     fill=BLACK, width=line_width + 4)
            draw.line([(click_x, v_start), (click_x, v_end)], 
                     fill=BLACK, width=line_width + 4)
            # 再画红色十字
            draw.line([(h_start, click_y), (h_end, click_y)], 
                     fill=RED, width=line_width)
            draw.line([(click_x, v_start), (click_x, v_end)], 
                     fill=RED, width=line_width)
            self.logger.info(f"十字准星绘制完成: 水平线({h_start},{click_y})-({h_end},{click_y}), 垂直线({click_x},{v_start})-({click_x},{v_end})")
            
            # 2. 画多个同心圆（确保不超出边界）
            for radius, color, width in [(80, BLUE, 4), (60, GREEN, 4), (40, YELLOW, 4), (20, RED, 4)]:
                # 检查圆是否会超出边界
                if (click_x - radius - 2 >= 0 and click_x + radius + 2 < img_width and
                    click_y - radius - 2 >= 0 and click_y + radius + 2 < img_height):
                    # 黑色边框
                    draw.ellipse([(click_x - radius - 2, click_y - radius - 2),
                                 (click_x + radius + 2, click_y + radius + 2)],
                                outline=BLACK, width=width + 2)
                    # 彩色圆圈
                    draw.ellipse([(click_x - radius, click_y - radius),
                                 (click_x + radius, click_y + radius)],
                                outline=color, width=width)
                    self.logger.debug(f"绘制圆圈: 半径={radius}, 颜色={color}")
            
            # 3. 画中心实心圆点
            center_size = 10
            draw.ellipse([(click_x - center_size - 2, click_y - center_size - 2),
                         (click_x + center_size + 2, click_y + center_size + 2)],
                        fill=BLACK)  # 黑色边框
            draw.ellipse([(click_x - center_size, click_y - center_size),
                         (click_x + center_size, click_y + center_size)],
                        fill=RED)  # 红色中心
            
            # 4. 只在左上角添加一个大的文字标注
            text = f"CLICK HERE: ({click_x}, {click_y})"
            text_pos = (50, 50)
            # 文字背景（黑色）
            text_width = len(text) * 12
            draw.rectangle([text_pos[0] - 10, text_pos[1] - 10, 
                          text_pos[0] + text_width + 10, text_pos[1] + 40], 
                          fill=BLACK)
            # 白色文字
            try:
                # 尝试使用更大的字体
                from PIL import ImageFont
                try:
                    font = ImageFont.truetype("arial.ttf", 30)
                except:
                    font = ImageFont.load_default()
                draw.text(text_pos, text, fill=WHITE, font=font)
            except:
                # 如果字体加载失败，使用默认字体
                draw.text(text_pos, text, fill=WHITE)
            
            # 5. 不画箭头，避免复杂化
            self.logger.info(f"所有标记绘制完成")
            
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
            self.logger.info(f"准备保存图片到: {filepath}")
            marked_image.save(filepath)
            self.logger.info(f"图片保存成功: {filepath}")
            
            # 同时保存一个未标记的原始截图用于对比
            original_filepath = os.path.join(debug_dir, f"original_{timestamp}.png")
            screenshot.save(original_filepath)
            self.logger.info(f"原始截图保存成功: {original_filepath}")
            
        except Exception as e:
            self.logger.error(f"Failed to save click screenshot: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
    
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
                try:
                    # 使用recognize_with_details获取详细信息
                    ocr_results = self.ocr_engine.recognize_with_details(screenshot)
                    for result in ocr_results:
                        if "收获" in result.text or "奖励" in result.text or "领取" in result.text or "收穫" in result.text:
                            # bbox格式是 (x, y, width, height)，计算中心点
                            center_x = result.bbox[0] + result.bbox[2] // 2
                            center_y = result.bbox[1] + result.bbox[3] // 2
                            self.logger.info(f"通过OCR找到相关文字 '{result.text}'，位置: ({center_x}, {center_y})，置信度: {result.confidence:.2f}")
                            self.adb_service.tap(center_x, center_y)
                            return True
                except Exception as e:
                    self.logger.warning(f"OCR识别出错: {e}")
            
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
    
    def _click_back_button(self) -> None:
        """
        点击返回按钮
        通过图片识别查找并点击返回按钮，支持两种样式的返回按钮
        如果都找不到，则使用Android系统返回键作为后备方案
        """
        try:
            # 截图
            screenshot = self.adb_service.take_screenshot()
            if screenshot is None:
                self.logger.error("无法获取截图")
                # 尝试使用系统返回键
                self._use_system_back_key()
                return
            
            # 方法1：尝试识别第一种返回按钮样式
            self.logger.info("尝试识别返回按钮样式1")
            back_button_1 = self._load_template_image('back_button_1')
            if back_button_1 is not None:
                result = self._find_template_in_image(screenshot, back_button_1, threshold=0.7)
                if result:
                    x, y = result
                    self.logger.info(f"找到返回按钮样式1，位置: ({x}, {y})")
                    self.adb_service.tap(x, y)
                    return
            
            # 方法2：尝试识别第二种返回按钮样式
            self.logger.info("尝试识别返回按钮样式2")
            back_button_2 = self._load_template_image('back_button_2')
            if back_button_2 is not None:
                result = self._find_template_in_image(screenshot, back_button_2, threshold=0.7)
                if result:
                    x, y = result
                    self.logger.info(f"找到返回按钮样式2，位置: ({x}, {y})")
                    self.adb_service.tap(x, y)
                    return
            
            # 方法3：如果都没找到，使用Android系统返回键作为后备方案
            self.logger.warning("未找到游戏内返回按钮，使用系统返回键")
            self._use_system_back_key()
            
        except Exception as e:
            self.logger.error(f"点击返回按钮时出错: {e}")
            # 出错时尝试使用系统返回键
            self._use_system_back_key()
    
    def _use_system_back_key(self) -> None:
        """
        使用Android系统返回键
        """
        try:
            self.logger.info("使用Android系统返回键")
            result = self.adb_service.execute_command("shell input keyevent 4")  # KEYCODE_BACK = 4
            
            if result:
                self.logger.debug("成功发送返回键命令")
            else:
                self.logger.warning("发送返回键命令失败")
                
        except Exception as e:
            self.logger.error(f"使用系统返回键时出错: {e}")
    
    
    def _load_template_image(self, name: str) -> Optional[np.ndarray]:
        """
        加载模板图片
        
        Args:
            name: 图片名称键
        
        Returns:
            OpenCV图像数组，加载失败返回None
        """
        if name in self._templates:
            return self._templates[name]
        
        if name not in self.images:
            self.logger.error(f"未定义图片: {name}")
            return None
        
        image_path = self.images[name]
        if not os.path.exists(image_path):
            self.logger.error(f"图片文件不存在: {image_path}")
            return None
        
        try:
            # 加载图片
            template = cv2.imread(image_path)
            if template is None:
                self.logger.error(f"无法加载图片: {image_path}")
                return None
            
            # 缓存模板
            self._templates[name] = template
            self.logger.debug(f"加载模板图片: {name}")
            return template
            
        except Exception as e:
            self.logger.error(f"加载图片时出错 {image_path}: {e}")
            return None
    
    def _find_template_in_image(self, screenshot: Image.Image, 
                                template: np.ndarray, 
                                threshold: float = 0.8,
                                use_grayscale: bool = True) -> Optional[Tuple[int, int]]:
        """
        在截图中查找模板
        
        Args:
            screenshot: PIL截图
            template: OpenCV模板图像
            threshold: 匹配阈值
            use_grayscale: 是否使用灰度图进行匹配（提高准确率）
        
        Returns:
            匹配中心坐标(x, y)，未找到返回None
        """
        try:
            # 将PIL图像转换为OpenCV格式
            screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # 如果使用灰度图匹配
            if use_grayscale:
                # 转换截图为灰度图
                screenshot_gray = cv2.cvtColor(screenshot_cv, cv2.COLOR_BGR2GRAY)
                # 转换模板为灰度图（如果不是的话）
                if len(template.shape) == 3:
                    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
                else:
                    template_gray = template
                
                # 在灰度图上进行模板匹配
                result = cv2.matchTemplate(screenshot_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            else:
                # 彩色图匹配
                result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
            
            # 找到最佳匹配位置
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= threshold:
                # 计算中心点
                if use_grayscale:
                    template_height, template_width = template_gray.shape[:2] if use_grayscale else template.shape[:2]
                else:
                    template_height, template_width = template.shape[:2]
                center_x = max_loc[0] + template_width // 2
                center_y = max_loc[1] + template_height // 2
                
                self.logger.debug(f"找到模板匹配: 置信度={max_val:.2f}, 位置=({center_x}, {center_y}), 灰度模式={use_grayscale}")
                return (center_x, center_y)
            else:
                self.logger.debug(f"模板匹配度不足: {max_val:.2f} < {threshold}")
                return None
                
        except Exception as e:
            self.logger.error(f"模板匹配时出错: {e}")
            return None
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """
        获取屏幕尺寸（始终从截图获取）
        
        Returns:
            (宽度, 高度)
        """
        try:
            # 直接从截图获取屏幕尺寸，这是最准确的
            screenshot = self.adb_service.take_screenshot()
            if screenshot:
                width, height = screenshot.size
                return width, height
        except Exception as e:
            self.logger.error(f"Failed to get screen size from screenshot: {e}")
        
        # 使用默认值
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
