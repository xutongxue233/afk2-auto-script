"""
退出弹窗处理器
专门处理游戏退出确认弹窗
"""

from typing import Tuple, Optional
from PIL import Image
import numpy as np
import cv2

class ExitDialogHandler:
    """退出弹窗处理器"""
    
    @staticmethod
    def detect_exit_dialog(screenshot: Image.Image) -> Tuple[bool, Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
        """
        检测退出游戏弹窗
        
        Args:
            screenshot: 当前截图
            
        Returns:
            (是否检测到弹窗, 取消按钮坐标, 确认按钮坐标)
        """
        width, height = screenshot.size
        
        # 基于截图观察的按钮位置
        # X按钮（取消）: 约35%, 62%
        # ✓按钮（确认）: 约65%, 62%
        cancel_pos = (int(width * 0.35), int(height * 0.62))
        confirm_pos = (int(width * 0.65), int(height * 0.62))
        
        # 方法1: 检测弹窗的白色背景区域
        # 弹窗通常有一个白色或浅色的矩形区域
        try:
            # 转换为numpy数组
            img_array = np.array(screenshot)
            
            # 检查弹窗区域（大约在屏幕中央）
            dialog_region = img_array[
                int(height * 0.35):int(height * 0.70),  # 垂直35%-70%
                int(width * 0.15):int(width * 0.85)     # 水平15%-85%
            ]
            
            # 计算区域的平均亮度
            if len(dialog_region.shape) == 3:
                # RGB图像，转换为灰度
                gray_region = cv2.cvtColor(dialog_region, cv2.COLOR_RGB2GRAY)
            else:
                gray_region = dialog_region
            
            mean_brightness = np.mean(gray_region)
            
            # 如果区域很亮（白色弹窗），且有一定的对比度
            if mean_brightness > 200:  # 白色背景
                # 进一步检查是否有按钮
                # 检查按钮区域的颜色特征
                button_y = int(height * 0.62)
                button_size = int(width * 0.08)  # 按钮大小约8%屏幕宽度
                
                # 检查左侧按钮区域（X按钮）
                left_button_region = img_array[
                    button_y - button_size:button_y + button_size,
                    cancel_pos[0] - button_size:cancel_pos[0] + button_size
                ]
                
                # 检查右侧按钮区域（✓按钮）
                right_button_region = img_array[
                    button_y - button_size:button_y + button_size,
                    confirm_pos[0] - button_size:confirm_pos[0] + button_size
                ]
                
                # 如果两个按钮区域都有内容（不是纯白）
                left_std = np.std(left_button_region)
                right_std = np.std(right_button_region)
                
                if left_std > 30 and right_std > 30:
                    # 两个按钮都存在，很可能是退出弹窗
                    return True, cancel_pos, confirm_pos
                    
        except Exception:
            pass
        
        # 方法2: 检测特定的UI模式
        # 退出弹窗有固定的布局：顶部文字、底部两个按钮
        try:
            # 检查是否有半透明黑色遮罩（背景变暗）
            # 边缘区域应该比正常情况暗
            top_edge = img_array[0:int(height * 0.1), :]
            bottom_edge = img_array[int(height * 0.9):, :]
            
            edge_brightness = (np.mean(top_edge) + np.mean(bottom_edge)) / 2
            
            # 如果边缘很暗（有遮罩）且中央很亮（有弹窗）
            if edge_brightness < 100 and mean_brightness > 200:
                return True, cancel_pos, confirm_pos
                
        except Exception:
            pass
        
        return False, None, None
    
    @staticmethod
    def get_button_positions(screen_width: int, screen_height: int) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        获取退出弹窗按钮的位置
        
        Args:
            screen_width: 屏幕宽度
            screen_height: 屏幕高度
            
        Returns:
            (取消按钮坐标, 确认按钮坐标)
        """
        # 基于百分比计算按钮位置
        cancel_x = int(screen_width * 0.35)   # X按钮在左侧35%
        cancel_y = int(screen_height * 0.62)  # 垂直位置62%
        
        confirm_x = int(screen_width * 0.65)  # ✓按钮在右侧65%
        confirm_y = int(screen_height * 0.62) # 垂直位置62%
        
        return (cancel_x, cancel_y), (confirm_x, confirm_y)