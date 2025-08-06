"""
任务状态模型
定义任务管理相关的数据结构
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from enum import Enum
import uuid


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"        # 待执行
    RUNNING = "running"        # 执行中
    PAUSED = "paused"         # 已暂停
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"    # 已取消
    RETRYING = "retrying"     # 重试中
    SKIPPED = "skipped"       # 已跳过


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


class TaskType(Enum):
    """任务类型"""
    WAKE_UP_GAME = "wake_up_game"           # 唤醒游戏
    DAILY_TASK = "daily_task"               # 日常任务
    BATTLE = "battle"                        # 战斗
    COLLECT_REWARD = "collect_reward"       # 收集奖励
    UPGRADE = "upgrade"                     # 升级
    CUSTOM = "custom"                        # 自定义


@dataclass
class TaskInfo:
    """
    任务信息数据类
    
    Attributes:
        task_id: 任务唯一标识
        task_name: 任务名称
        task_type: 任务类型
        status: 任务状态
        priority: 任务优先级
        start_time: 开始时间
        end_time: 结束时间
        retry_count: 重试次数
        max_retries: 最大重试次数
        error_message: 错误信息
        progress: 任务进度 (0-100)
        result: 任务结果
        metadata: 额外的元数据
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_name: str = "未命名任务"
    task_type: TaskType = TaskType.CUSTOM
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    progress: int = 0
    result: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 任务依赖
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务ID列表
    parent_task_id: Optional[str] = None  # 父任务ID
    sub_tasks: List[str] = field(default_factory=list)  # 子任务ID列表
    
    def __str__(self) -> str:
        """返回任务的字符串表示"""
        return f"{self.task_name} ({self.task_id[:8]}...)"
    
    def __repr__(self) -> str:
        """返回任务的详细表示"""
        return (f"TaskInfo(id={self.task_id[:8]}..., name={self.task_name}, "
                f"type={self.task_type.value}, status={self.status.value})")
    
    @property
    def is_running(self) -> bool:
        """检查任务是否正在运行"""
        return self.status in [TaskStatus.RUNNING, TaskStatus.RETRYING]
    
    @property
    def is_finished(self) -> bool:
        """检查任务是否已结束"""
        return self.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, 
                               TaskStatus.CANCELLED, TaskStatus.SKIPPED]
    
    @property
    def can_retry(self) -> bool:
        """检查任务是否可以重试"""
        return (self.status == TaskStatus.FAILED and 
                self.retry_count < self.max_retries)
    
    @property
    def duration(self) -> Optional[float]:
        """获取任务执行时长（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        elif self.start_time:
            return (datetime.now() - self.start_time).total_seconds()
        return None
    
    def start(self) -> None:
        """开始任务"""
        self.status = TaskStatus.RUNNING
        self.start_time = datetime.now()
        self.progress = 0
        self.error_message = None
    
    def pause(self) -> None:
        """暂停任务"""
        if self.status == TaskStatus.RUNNING:
            self.status = TaskStatus.PAUSED
    
    def resume(self) -> None:
        """恢复任务"""
        if self.status == TaskStatus.PAUSED:
            self.status = TaskStatus.RUNNING
    
    def complete(self, result: Any = None) -> None:
        """完成任务"""
        self.status = TaskStatus.COMPLETED
        self.end_time = datetime.now()
        self.progress = 100
        self.result = result
    
    def fail(self, error: str) -> None:
        """标记任务失败"""
        self.status = TaskStatus.FAILED
        self.end_time = datetime.now()
        self.error_message = error
    
    def cancel(self) -> None:
        """取消任务"""
        self.status = TaskStatus.CANCELLED
        self.end_time = datetime.now()
    
    def retry(self) -> None:
        """重试任务"""
        if self.can_retry:
            self.retry_count += 1
            self.status = TaskStatus.RETRYING
            self.error_message = None
            self.progress = 0
    
    def update_progress(self, progress: int) -> None:
        """更新任务进度"""
        self.progress = max(0, min(100, progress))
    
    def add_metadata(self, key: str, value: Any) -> None:
        """添加元数据"""
        self.metadata[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'task_id': self.task_id,
            'task_name': self.task_name,
            'task_type': self.task_type.value,
            'status': self.status.value,
            'priority': self.priority.value,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'error_message': self.error_message,
            'progress': self.progress,
            'result': self.result,
            'metadata': self.metadata,
            'dependencies': self.dependencies,
            'parent_task_id': self.parent_task_id,
            'sub_tasks': self.sub_tasks
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskInfo':
        """从字典创建TaskInfo实例"""
        # 处理枚举类型
        if 'task_type' in data:
            data['task_type'] = TaskType(data['task_type'])
        if 'status' in data:
            data['status'] = TaskStatus(data['status'])
        if 'priority' in data:
            data['priority'] = TaskPriority(data['priority'])
        
        # 处理日期时间类型
        if 'start_time' in data and data['start_time']:
            data['start_time'] = datetime.fromisoformat(data['start_time'])
        if 'end_time' in data and data['end_time']:
            data['end_time'] = datetime.fromisoformat(data['end_time'])
        
        return cls(**data)


@dataclass
class TaskGroup:
    """
    任务组
    用于管理一组相关的任务
    """
    group_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    group_name: str = "未命名任务组"
    tasks: List[TaskInfo] = field(default_factory=list)
    execution_mode: str = "serial"  # serial（串行）或 parallel（并行）
    status: TaskStatus = TaskStatus.PENDING
    created_time: datetime = field(default_factory=datetime.now)
    
    def add_task(self, task: TaskInfo) -> None:
        """添加任务到任务组"""
        self.tasks.append(task)
    
    def remove_task(self, task_id: str) -> bool:
        """从任务组移除任务"""
        for i, task in enumerate(self.tasks):
            if task.task_id == task_id:
                self.tasks.pop(i)
                return True
        return False
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """根据ID获取任务"""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None
    
    @property
    def pending_tasks(self) -> List[TaskInfo]:
        """获取待执行的任务"""
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]
    
    @property
    def running_tasks(self) -> List[TaskInfo]:
        """获取正在执行的任务"""
        return [t for t in self.tasks if t.is_running]
    
    @property
    def completed_tasks(self) -> List[TaskInfo]:
        """获取已完成的任务"""
        return [t for t in self.tasks if t.status == TaskStatus.COMPLETED]
    
    @property
    def failed_tasks(self) -> List[TaskInfo]:
        """获取失败的任务"""
        return [t for t in self.tasks if t.status == TaskStatus.FAILED]
    
    @property
    def progress(self) -> int:
        """计算任务组的总体进度"""
        if not self.tasks:
            return 0
        total_progress = sum(task.progress for task in self.tasks)
        return int(total_progress / len(self.tasks))
    
    def update_status(self) -> None:
        """根据子任务状态更新任务组状态"""
        if all(task.status == TaskStatus.COMPLETED for task in self.tasks):
            self.status = TaskStatus.COMPLETED
        elif any(task.is_running for task in self.tasks):
            self.status = TaskStatus.RUNNING
        elif any(task.status == TaskStatus.FAILED for task in self.tasks):
            self.status = TaskStatus.FAILED
        elif all(task.status == TaskStatus.CANCELLED for task in self.tasks):
            self.status = TaskStatus.CANCELLED
        else:
            self.status = TaskStatus.PENDING