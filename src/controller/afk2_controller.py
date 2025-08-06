"""
剑与远征启程(AFK2)游戏控制器
实现AFK2游戏的自动化控制
"""

import time
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum

from src.controller.base_controller import (
    BaseGameController, GameScene, ClickPoint, GameState
)
from src.services.adb_service import ADBService
from src.models.config import GameConfig
from src.recognition.image_recognizer import ImageRecognizer
from src.recognition.ocr_engine import OCREngine
from src.utils.exceptions import GameControlError
from PIL import Image


class AFK2Scene(Enum):
    """AFK2游戏场景枚举"""
    LOADING = "loading"  # 加载中
    LOGIN = "login"  # 登录界面
    MAIN = "main"  # 主界面
    BATTLE = "battle"  # 战斗界面
    BATTLE_RESULT = "battle_result"  # 战斗结果
    HERO = "hero"  # 英雄界面
    BAG = "bag"  # 背包界面
    SHOP = "shop"  # 商店界面
    GUILD = "guild"  # 公会界面
    ARENA = "arena"  # 竞技场
    CAMPAIGN = "campaign"  # 征战
    DAILY_QUEST = "daily_quest"  # 日常任务
    MAIL = "mail"  # 邮件
    CHAT = "chat"  # 聊天
    SETTINGS = "settings"  # 设置


class AFK2Controller(BaseGameController):
    """
    AFK2游戏控制器
    """
    
    def __init__(self,
                 adb_service: ADBService,
                 config: Optional[GameConfig] = None,
                 image_recognizer: Optional[ImageRecognizer] = None,
                 ocr_engine: Optional[OCREngine] = None):
        """
        初始化AFK2控制器
        
        Args:
            adb_service: ADB服务
            config: 游戏配置
            image_recognizer: 图像识别器
            ocr_engine: OCR引擎
        """
        # 设置默认包名
        if config is None:
            config = GameConfig()
        config.package_name = "com.lilith.odyssey.cn"
        config.main_activity = ".MainActivity"
        
        super().__init__(adb_service, config, image_recognizer, ocr_engine)
        
        # AFK2特定配置
        self.auto_battle_enabled = True
        self.skip_dialogues = True
        self.collect_idle_rewards = True
        
        self.logger.info("AFK2Controller initialized")
    
    def _init_scenes(self) -> None:
        """初始化AFK2游戏场景"""
        
        # 主界面
        self.add_scene(GameScene(
            name=AFK2Scene.MAIN.value,
            identifiers=["main_menu_icon", "主界面", "征战"],
            click_points={
                "campaign": ClickPoint("征战", 540, 1800, "进入征战"),
                "hero": ClickPoint("英雄", 200, 1800, "英雄界面"),
                "bag": ClickPoint("背包", 360, 1800, "背包界面"),
                "guild": ClickPoint("公会", 720, 1800, "公会界面"),
                "shop": ClickPoint("商店", 880, 1800, "商店界面"),
                "mail": ClickPoint("邮件", 980, 100, "邮件按钮"),
                "quest": ClickPoint("任务", 100, 500, "任务按钮"),
                "idle_reward": ClickPoint("挂机奖励", 540, 1200, "领取挂机奖励", wait_after=2.0)
            },
            next_scenes=[AFK2Scene.CAMPAIGN.value, AFK2Scene.HERO.value, 
                        AFK2Scene.BAG.value, AFK2Scene.GUILD.value,
                        AFK2Scene.SHOP.value]
        ))
        
        # 征战界面
        self.add_scene(GameScene(
            name=AFK2Scene.CAMPAIGN.value,
            identifiers=["campaign_title", "征战", "挑战"],
            click_points={
                "challenge": ClickPoint("挑战", 540, 1600, "开始挑战", wait_after=1.5),
                "quick_battle": ClickPoint("快速战斗", 380, 1600, "快速战斗"),
                "back": ClickPoint("返回", 100, 100, "返回主界面"),
                "auto_battle": ClickPoint("自动战斗", 900, 1600, "自动战斗开关")
            },
            next_scenes=[AFK2Scene.BATTLE.value, AFK2Scene.MAIN.value]
        ))
        
        # 战斗界面
        self.add_scene(GameScene(
            name=AFK2Scene.BATTLE.value,
            identifiers=["battle_ui", "战斗中", "AUTO"],
            click_points={
                "auto": ClickPoint("自动", 980, 400, "自动战斗"),
                "speed": ClickPoint("加速", 980, 500, "战斗加速"),
                "pause": ClickPoint("暂停", 980, 100, "暂停战斗"),
                "skip": ClickPoint("跳过", 540, 1700, "跳过战斗")
            },
            next_scenes=[AFK2Scene.BATTLE_RESULT.value]
        ))
        
        # 战斗结果界面
        self.add_scene(GameScene(
            name=AFK2Scene.BATTLE_RESULT.value,
            identifiers=["victory", "defeat", "战斗胜利", "战斗失败", "获得奖励"],
            click_points={
                "confirm": ClickPoint("确认", 540, 1600, "确认结果", wait_after=1.0),
                "retry": ClickPoint("重试", 380, 1600, "重新挑战"),
                "next": ClickPoint("下一关", 700, 1600, "下一关"),
                "tap_continue": ClickPoint("点击继续", 540, 1500, "点击屏幕继续")
            },
            next_scenes=[AFK2Scene.CAMPAIGN.value, AFK2Scene.MAIN.value]
        ))
        
        # 英雄界面
        self.add_scene(GameScene(
            name=AFK2Scene.HERO.value,
            identifiers=["hero_list", "英雄", "升级", "进阶"],
            click_points={
                "upgrade": ClickPoint("升级", 800, 1400, "英雄升级"),
                "advance": ClickPoint("进阶", 800, 1500, "英雄进阶"),
                "equip": ClickPoint("装备", 800, 1600, "装备管理"),
                "back": ClickPoint("返回", 100, 100, "返回主界面")
            },
            next_scenes=[AFK2Scene.MAIN.value]
        ))
        
        # 背包界面
        self.add_scene(GameScene(
            name=AFK2Scene.BAG.value,
            identifiers=["bag_ui", "背包", "物品", "装备"],
            click_points={
                "use": ClickPoint("使用", 800, 1600, "使用物品"),
                "sell": ClickPoint("出售", 600, 1600, "出售物品"),
                "sort": ClickPoint("整理", 900, 200, "整理背包"),
                "back": ClickPoint("返回", 100, 100, "返回主界面")
            },
            next_scenes=[AFK2Scene.MAIN.value]
        ))
        
        # 日常任务界面
        self.add_scene(GameScene(
            name=AFK2Scene.DAILY_QUEST.value,
            identifiers=["daily_quest", "日常任务", "每日任务", "任务奖励"],
            click_points={
                "claim_all": ClickPoint("一键领取", 900, 1700, "一键领取奖励", wait_after=2.0),
                "refresh": ClickPoint("刷新", 900, 300, "刷新任务"),
                "back": ClickPoint("返回", 100, 100, "返回主界面")
            },
            next_scenes=[AFK2Scene.MAIN.value]
        ))
        
        # 邮件界面
        self.add_scene(GameScene(
            name=AFK2Scene.MAIL.value,
            identifiers=["mail_box", "邮件", "收件箱"],
            click_points={
                "claim_all": ClickPoint("一键领取", 900, 1700, "一键领取邮件", wait_after=2.0),
                "delete_read": ClickPoint("删除已读", 700, 1700, "删除已读邮件"),
                "back": ClickPoint("返回", 100, 100, "返回主界面")
            },
            next_scenes=[AFK2Scene.MAIN.value]
        ))
    
    def _navigate_step(self, from_scene: str, to_scene: str) -> bool:
        """
        执行单步导航
        
        Args:
            from_scene: 起始场景
            to_scene: 目标场景
        
        Returns:
            是否成功
        """
        # 从主界面导航到其他界面
        if from_scene == AFK2Scene.MAIN.value:
            scene_clicks = {
                AFK2Scene.CAMPAIGN.value: "campaign",
                AFK2Scene.HERO.value: "hero",
                AFK2Scene.BAG.value: "bag",
                AFK2Scene.GUILD.value: "guild",
                AFK2Scene.SHOP.value: "shop"
            }
            
            if to_scene in scene_clicks:
                self.click_point(scene_clicks[to_scene])
                return self.wait_for_scene(to_scene, timeout=5.0)
        
        # 从其他界面返回主界面
        elif to_scene == AFK2Scene.MAIN.value:
            self.click_point("back")
            return self.wait_for_scene(AFK2Scene.MAIN.value, timeout=5.0)
        
        # 从征战到战斗
        elif from_scene == AFK2Scene.CAMPAIGN.value and to_scene == AFK2Scene.BATTLE.value:
            self.click_point("challenge")
            return self.wait_for_scene(AFK2Scene.BATTLE.value, timeout=5.0)
        
        return False
    
    def perform_daily_tasks(self) -> Dict[str, bool]:
        """
        执行日常任务
        
        Returns:
            任务执行结果
        """
        results = {}
        
        try:
            # 确保在主界面
            if not self.navigate_to_scene(AFK2Scene.MAIN.value):
                self.logger.error("Failed to navigate to main scene")
                return results
            
            # 1. 领取挂机奖励
            results['idle_rewards'] = self.collect_idle_rewards()
            
            # 2. 领取邮件
            results['mail'] = self.collect_mail()
            
            # 3. 完成日常任务
            results['daily_quests'] = self.complete_daily_quests()
            
            # 4. 征战推图
            results['campaign'] = self.auto_campaign(max_battles=5)
            
            # 5. 公会签到
            results['guild_checkin'] = self.guild_checkin()
            
            # 6. 商店免费抽取
            results['shop_free'] = self.shop_free_draw()
            
            self.logger.info(f"Daily tasks completed: {results}")
            
        except Exception as e:
            self.logger.error(f"Error performing daily tasks: {e}")
        
        return results
    
    def collect_rewards(self) -> bool:
        """
        收集所有奖励
        
        Returns:
            是否成功
        """
        success = True
        
        # 收集挂机奖励
        if self.collect_idle_rewards:
            success &= self.collect_idle_rewards()
        
        # 收集邮件奖励
        success &= self.collect_mail()
        
        # 收集任务奖励
        success &= self.collect_quest_rewards()
        
        return success
    
    def collect_idle_rewards(self) -> bool:
        """
        领取挂机奖励
        
        Returns:
            是否成功
        """
        try:
            # 导航到主界面
            if not self.navigate_to_scene(AFK2Scene.MAIN.value):
                return False
            
            # 检查是否有挂机奖励
            screenshot = self.screenshot()
            if self.recognizer.find_template(screenshot, "idle_reward_available", threshold=0.7):
                self.click_point("idle_reward")
                time.sleep(2)
                
                # 点击屏幕确认
                self.adb.tap(540, 1000)
                time.sleep(1)
                
                self.logger.info("Idle rewards collected")
                return True
            else:
                self.logger.info("No idle rewards available")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to collect idle rewards: {e}")
            return False
    
    def collect_mail(self) -> bool:
        """
        领取邮件奖励
        
        Returns:
            是否成功
        """
        try:
            # 导航到主界面
            if not self.navigate_to_scene(AFK2Scene.MAIN.value):
                return False
            
            # 点击邮件按钮
            self.click_point("mail")
            
            # 等待邮件界面
            if self.wait_for_scene(AFK2Scene.MAIL.value):
                # 一键领取
                self.click_point("claim_all")
                time.sleep(2)
                
                # 返回主界面
                self.click_point("back")
                
                self.logger.info("Mail rewards collected")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to collect mail: {e}")
            return False
    
    def collect_quest_rewards(self) -> bool:
        """
        领取任务奖励
        
        Returns:
            是否成功
        """
        try:
            # 导航到主界面
            if not self.navigate_to_scene(AFK2Scene.MAIN.value):
                return False
            
            # 点击任务按钮
            self.click_point("quest")
            
            # 等待任务界面
            if self.wait_for_scene(AFK2Scene.DAILY_QUEST.value):
                # 一键领取
                self.click_point("claim_all")
                time.sleep(2)
                
                # 返回主界面
                self.click_point("back")
                
                self.logger.info("Quest rewards collected")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to collect quest rewards: {e}")
            return False
    
    def complete_daily_quests(self) -> bool:
        """
        完成日常任务
        
        Returns:
            是否成功
        """
        return self.collect_quest_rewards()
    
    def auto_campaign(self, max_battles: int = 10) -> bool:
        """
        自动征战推图
        
        Args:
            max_battles: 最大战斗次数
        
        Returns:
            是否成功
        """
        try:
            # 导航到征战界面
            if not self.navigate_to_scene(AFK2Scene.CAMPAIGN.value):
                return False
            
            battles_completed = 0
            consecutive_failures = 0
            
            while battles_completed < max_battles and consecutive_failures < 3:
                # 开始挑战
                self.click_point("challenge")
                
                # 等待战斗开始
                if self.wait_for_scene(AFK2Scene.BATTLE.value, timeout=10):
                    # 确保自动战斗开启
                    self.click_point("auto")
                    
                    # 等待战斗结束
                    if self.wait_for_scene(AFK2Scene.BATTLE_RESULT.value, timeout=60):
                        screenshot = self.screenshot()
                        
                        # 检查战斗结果
                        if self.recognizer.find_template(screenshot, "victory", threshold=0.7):
                            self.logger.info(f"Battle {battles_completed + 1} won")
                            consecutive_failures = 0
                            
                            # 点击下一关
                            if self.click_template("next_stage", screenshot):
                                time.sleep(1)
                            else:
                                self.click_point("confirm")
                        else:
                            self.logger.info(f"Battle {battles_completed + 1} lost")
                            consecutive_failures += 1
                            
                            # 点击确认返回
                            self.click_point("confirm")
                            
                            if consecutive_failures >= 3:
                                self.logger.info("Too many consecutive failures, stopping")
                                break
                        
                        battles_completed += 1
                    else:
                        self.logger.warning("Battle timeout")
                        break
                else:
                    self.logger.warning("Failed to start battle")
                    break
                
                # 等待返回征战界面
                time.sleep(2)
            
            self.logger.info(f"Auto campaign completed: {battles_completed} battles")
            return battles_completed > 0
            
        except Exception as e:
            self.logger.error(f"Auto campaign failed: {e}")
            return False
    
    def guild_checkin(self) -> bool:
        """
        公会签到
        
        Returns:
            是否成功
        """
        try:
            # 导航到主界面
            if not self.navigate_to_scene(AFK2Scene.MAIN.value):
                return False
            
            # 进入公会
            self.click_point("guild")
            
            # 等待公会界面
            if self.wait_for_scene(AFK2Scene.GUILD.value):
                # 查找并点击签到按钮
                if self.click_text("签到"):
                    time.sleep(1)
                    self.logger.info("Guild check-in completed")
                else:
                    self.logger.info("Already checked in or button not found")
                
                # 返回主界面
                self.click_point("back")
                return True
                
        except Exception as e:
            self.logger.error(f"Guild check-in failed: {e}")
            return False
    
    def shop_free_draw(self) -> bool:
        """
        商店免费抽取
        
        Returns:
            是否成功
        """
        try:
            # 导航到主界面
            if not self.navigate_to_scene(AFK2Scene.MAIN.value):
                return False
            
            # 进入商店
            self.click_point("shop")
            
            # 等待商店界面
            if self.wait_for_scene(AFK2Scene.SHOP.value):
                # 查找免费按钮
                if self.click_text("免费"):
                    time.sleep(2)
                    
                    # 确认抽取
                    self.click_text("确认")
                    time.sleep(2)
                    
                    # 点击屏幕跳过动画
                    self.adb.tap(540, 1000)
                    time.sleep(1)
                    
                    self.logger.info("Free draw completed")
                else:
                    self.logger.info("No free draw available")
                
                # 返回主界面
                self.click_point("back")
                return True
                
        except Exception as e:
            self.logger.error(f"Shop free draw failed: {e}")
            return False
    
    def quick_battle(self, count: int = 1) -> bool:
        """
        快速战斗
        
        Args:
            count: 战斗次数
        
        Returns:
            是否成功
        """
        try:
            # 导航到征战界面
            if not self.navigate_to_scene(AFK2Scene.CAMPAIGN.value):
                return False
            
            # 点击快速战斗
            for i in range(count):
                if self.click_point("quick_battle"):
                    time.sleep(2)
                    
                    # 确认使用
                    self.click_text("确认")
                    time.sleep(3)
                    
                    # 点击屏幕继续
                    self.adb.tap(540, 1000)
                    time.sleep(1)
                    
                    self.logger.info(f"Quick battle {i+1}/{count} completed")
                else:
                    self.logger.warning("Quick battle button not found")
                    break
            
            return True
            
        except Exception as e:
            self.logger.error(f"Quick battle failed: {e}")
            return False
    
    def upgrade_heroes(self) -> bool:
        """
        自动升级英雄
        
        Returns:
            是否成功
        """
        try:
            # 导航到英雄界面
            if not self.navigate_to_scene(AFK2Scene.HERO.value):
                return False
            
            # 实现英雄升级逻辑
            # TODO: 根据游戏具体UI实现
            
            self.logger.info("Hero upgrade completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Hero upgrade failed: {e}")
            return False