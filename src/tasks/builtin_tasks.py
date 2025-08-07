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
from src.tasks.daily_idle_reward_task import DailyIdleRewardTask


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


class DailyIdleRewardTaskBuilder(LoggerMixin):
    """
    每日挂机奖励任务构建器
    """
    
    def __init__(self, task_manager: TaskManager):
        """
        初始化任务构建器
        
        Args:
            task_manager: 任务管理器
        """
        self.task_manager = task_manager
    
    def create(self, scheduled_time: Optional[datetime] = None,
              priority: TaskPriority = TaskPriority.HIGH) -> str:
        """
        创建每日挂机奖励领取任务
        
        Args:
            scheduled_time: 计划执行时间
            priority: 优先级
        
        Returns:
            任务ID
        """
        task_id = self.task_manager.create_task(
            name="领取每日挂机奖励",
            task_type="daily_idle_reward",
            params={
                'check_idle_mode': True,
                'use_hourglass': False  # 已移除hourglass功能
            },
            priority=priority,
            group=None,
            scheduled_time=scheduled_time,
            timeout=180,  # 3分钟
            max_retries=2,
            metadata={'wake_game': True}  # 添加唤醒游戏标志
        )
        
        self.logger.info(f"Daily idle reward task created: {task_id}")
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
        
        # 每日挂机奖励模板
        self.register_template(TaskTemplate(
            name="daily_idle_reward",
            task_type="daily_idle_reward",
            description="领取每日挂机奖励",
            default_params={
                'check_idle_mode': True,
                'use_hourglass': False  # 已移除hourglass功能
            },
            priority=TaskPriority.HIGH,
            group=None,
            timeout=180,  # 3分钟
            max_retries=2
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