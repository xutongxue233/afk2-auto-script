"""
内置任务定义
提供常用的预定义任务
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.models.task import TaskInfo, TaskPriority, TaskGroup
from src.tasks.task_manager import TaskManager
from src.services.log_service import LoggerMixin


@dataclass
class TaskTemplate:
    """任务模板"""
    name: str
    task_type: str
    description: str
    default_params: Dict[str, Any]
    priority: TaskPriority = TaskPriority.NORMAL
    group: Optional[TaskGroup] = None
    timeout: Optional[int] = None
    max_retries: int = 3


class DailyTask(LoggerMixin):
    """
    日常任务
    包含所有日常任务的集合
    """
    
    def __init__(self, task_manager: TaskManager):
        """
        初始化日常任务
        
        Args:
            task_manager: 任务管理器
        """
        self.task_manager = task_manager
        self.task_ids: List[str] = []
    
    def create(self, scheduled_time: Optional[datetime] = None) -> str:
        """
        创建日常任务
        
        Args:
            scheduled_time: 计划执行时间
        
        Returns:
            主任务ID
        """
        # 创建主任务
        main_task_id = self.task_manager.create_task(
            name="每日任务合集",
            task_type="daily_tasks",
            params={
                'include_campaign': True,
                'include_rewards': True,
                'include_guild': True,
                'include_shop': True
            },
            priority=TaskPriority.HIGH,
            group=TaskGroup.DAILY,
            scheduled_time=scheduled_time,
            timeout=1800,  # 30分钟
            max_retries=2
        )
        
        self.task_ids = [main_task_id]
        self.logger.info(f"Daily task created: {main_task_id}")
        
        return main_task_id
    
    def create_subtasks(self, scheduled_time: Optional[datetime] = None) -> List[str]:
        """
        创建日常子任务（分别执行）
        
        Args:
            scheduled_time: 计划执行时间
        
        Returns:
            任务ID列表
        """
        task_ids = []
        
        # 1. 收集奖励
        reward_task = self.task_manager.create_task(
            name="收集奖励",
            task_type="collect_rewards",
            priority=TaskPriority.HIGH,
            group=TaskGroup.DAILY,
            scheduled_time=scheduled_time
        )
        task_ids.append(reward_task)
        
        # 2. 征战推图
        campaign_task = self.task_manager.create_task(
            name="自动征战",
            task_type="campaign",
            params={'max_battles': 5},
            priority=TaskPriority.NORMAL,
            group=TaskGroup.DAILY,
            dependencies=[reward_task]  # 依赖收集奖励完成
        )
        task_ids.append(campaign_task)
        
        # 3. 公会任务
        guild_task = self.task_manager.create_task(
            name="公会任务",
            task_type="guild_tasks",
            priority=TaskPriority.NORMAL,
            group=TaskGroup.DAILY
        )
        task_ids.append(guild_task)
        
        # 4. 英雄升级
        hero_task = self.task_manager.create_task(
            name="英雄升级",
            task_type="hero_upgrade",
            priority=TaskPriority.LOW,
            group=TaskGroup.DAILY,
            dependencies=[campaign_task]  # 征战后升级
        )
        task_ids.append(hero_task)
        
        self.task_ids = task_ids
        self.logger.info(f"Daily subtasks created: {len(task_ids)} tasks")
        
        return task_ids


class CampaignTask(LoggerMixin):
    """
    征战任务
    自动推图任务
    """
    
    def __init__(self, task_manager: TaskManager):
        """
        初始化征战任务
        
        Args:
            task_manager: 任务管理器
        """
        self.task_manager = task_manager
    
    def create(self, max_battles: int = 10,
              use_quick_battle: bool = False,
              priority: TaskPriority = TaskPriority.NORMAL) -> str:
        """
        创建征战任务
        
        Args:
            max_battles: 最大战斗次数
            use_quick_battle: 是否使用快速战斗
            priority: 优先级
        
        Returns:
            任务ID
        """
        task_id = self.task_manager.create_task(
            name=f"征战推图 x{max_battles}",
            task_type="campaign",
            params={
                'max_battles': max_battles,
                'use_quick_battle': use_quick_battle
            },
            priority=priority,
            group=TaskGroup.BATTLE,
            timeout=600,  # 10分钟
            max_retries=2
        )
        
        self.logger.info(f"Campaign task created: {task_id}")
        return task_id


class CollectRewardTask(LoggerMixin):
    """
    收集奖励任务
    """
    
    def __init__(self, task_manager: TaskManager):
        """
        初始化收集奖励任务
        
        Args:
            task_manager: 任务管理器
        """
        self.task_manager = task_manager
    
    def create(self, reward_types: Optional[List[str]] = None,
              priority: TaskPriority = TaskPriority.HIGH) -> str:
        """
        创建收集奖励任务
        
        Args:
            reward_types: 奖励类型列表 ['idle', 'mail', 'quest']
            priority: 优先级
        
        Returns:
            任务ID
        """
        if reward_types is None:
            reward_types = ['idle', 'mail', 'quest']
        
        task_id = self.task_manager.create_task(
            name="收集奖励",
            task_type="collect_rewards",
            params={'reward_types': reward_types},
            priority=priority,
            group=TaskGroup.DAILY,
            timeout=300,  # 5分钟
            max_retries=3
        )
        
        self.logger.info(f"Collect reward task created: {task_id}")
        return task_id


class CustomScriptTask(LoggerMixin):
    """
    自定义脚本任务
    """
    
    def __init__(self, task_manager: TaskManager):
        """
        初始化自定义脚本任务
        
        Args:
            task_manager: 任务管理器
        """
        self.task_manager = task_manager
    
    def create(self, script_name: str,
              script_path: Optional[str] = None,
              script_code: Optional[str] = None,
              params: Optional[Dict[str, Any]] = None,
              priority: TaskPriority = TaskPriority.NORMAL) -> str:
        """
        创建自定义脚本任务
        
        Args:
            script_name: 脚本名称
            script_path: 脚本文件路径
            script_code: 脚本代码
            params: 脚本参数
            priority: 优先级
        
        Returns:
            任务ID
        """
        task_params = params or {}
        
        if script_path:
            task_params['script_path'] = script_path
        elif script_code:
            task_params['script_code'] = script_code
        else:
            raise ValueError("Must provide either script_path or script_code")
        
        task_id = self.task_manager.create_task(
            name=f"自定义脚本: {script_name}",
            task_type="custom_script",
            params=task_params,
            priority=priority,
            group=TaskGroup.MANUAL,
            timeout=600,  # 10分钟
            max_retries=1
        )
        
        self.logger.info(f"Custom script task created: {task_id}")
        return task_id


class TaskTemplateManager:
    """
    任务模板管理器
    管理预定义的任务模板
    """
    
    def __init__(self):
        """初始化任务模板管理器"""
        self.templates: Dict[str, TaskTemplate] = {}
        self._init_builtin_templates()
    
    def _init_builtin_templates(self) -> None:
        """初始化内置模板"""
        
        # 日常任务模板
        self.register_template(TaskTemplate(
            name="daily_full",
            task_type="daily_tasks",
            description="完整的日常任务",
            default_params={
                'include_campaign': True,
                'include_rewards': True,
                'include_guild': True,
                'include_shop': True
            },
            priority=TaskPriority.HIGH,
            group=TaskGroup.DAILY,
            timeout=1800
        ))
        
        # 快速日常模板
        self.register_template(TaskTemplate(
            name="daily_quick",
            task_type="daily_tasks",
            description="快速日常任务（仅收集奖励）",
            default_params={
                'include_campaign': False,
                'include_rewards': True,
                'include_guild': False,
                'include_shop': False
            },
            priority=TaskPriority.HIGH,
            group=TaskGroup.DAILY,
            timeout=600
        ))
        
        # 征战模板
        self.register_template(TaskTemplate(
            name="campaign_normal",
            task_type="campaign",
            description="普通征战推图",
            default_params={
                'max_battles': 10,
                'use_quick_battle': False
            },
            priority=TaskPriority.NORMAL,
            group=TaskGroup.BATTLE,
            timeout=600
        ))
        
        # 快速征战模板
        self.register_template(TaskTemplate(
            name="campaign_quick",
            task_type="campaign",
            description="快速征战（使用扫荡）",
            default_params={
                'max_battles': 5,
                'use_quick_battle': True
            },
            priority=TaskPriority.NORMAL,
            group=TaskGroup.BATTLE,
            timeout=300
        ))
        
        # 收集奖励模板
        self.register_template(TaskTemplate(
            name="collect_all",
            task_type="collect_rewards",
            description="收集所有奖励",
            default_params={
                'reward_types': ['idle', 'mail', 'quest', 'achievement']
            },
            priority=TaskPriority.HIGH,
            group=TaskGroup.DAILY,
            timeout=300
        ))
    
    def register_template(self, template: TaskTemplate) -> None:
        """
        注册任务模板
        
        Args:
            template: 任务模板
        """
        self.templates[template.name] = template
    
    def get_template(self, name: str) -> Optional[TaskTemplate]:
        """
        获取任务模板
        
        Args:
            name: 模板名称
        
        Returns:
            任务模板
        """
        return self.templates.get(name)
    
    def list_templates(self) -> List[TaskTemplate]:
        """
        列出所有模板
        
        Returns:
            模板列表
        """
        return list(self.templates.values())
    
    def create_task_from_template(self, task_manager: TaskManager,
                                 template_name: str,
                                 override_params: Optional[Dict[str, Any]] = None) -> str:
        """
        从模板创建任务
        
        Args:
            task_manager: 任务管理器
            template_name: 模板名称
            override_params: 覆盖参数
        
        Returns:
            任务ID
        """
        template = self.get_template(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")
        
        # 合并参数
        params = template.default_params.copy()
        if override_params:
            params.update(override_params)
        
        # 创建任务
        task_id = task_manager.create_task(
            name=template.description,
            task_type=template.task_type,
            params=params,
            priority=template.priority,
            group=template.group,
            timeout=template.timeout,
            max_retries=template.max_retries
        )
        
        return task_id