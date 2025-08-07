"""
任务管理器
负责任务的创建、管理和监控
"""

import time
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
from pathlib import Path
import uuid

from src.services.log_service import LoggerMixin
from src.models.task import TaskInfo, TaskStatus, TaskPriority, TaskGroup
from src.utils.exceptions import TaskError, TaskNotFoundError


@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    status: TaskStatus
    start_time: datetime
    end_time: Optional[datetime]
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    
    @property
    def duration(self) -> Optional[timedelta]:
        """执行时长"""
        if self.end_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def is_success(self) -> bool:
        """是否成功"""
        return self.status == TaskStatus.COMPLETED


class TaskManager(LoggerMixin):
    """
    任务管理器
    负责所有任务的生命周期管理
    """
    
    def __init__(self, max_concurrent_tasks: int = 5,
                 task_history_dir: Optional[Path] = None):
        """
        初始化任务管理器
        
        Args:
            max_concurrent_tasks: 最大并发任务数
            task_history_dir: 任务历史记录目录
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.task_history_dir = task_history_dir or Path("task_history")
        
        # 任务存储
        self._tasks: Dict[str, TaskInfo] = {}
        self._task_results: Dict[str, TaskResult] = {}
        self._task_queue: List[str] = []
        self._running_tasks: Dict[str, threading.Thread] = {}
        
        # 任务执行器注册
        self._executors: Dict[str, Callable] = {}
        
        # 任务监听器
        self._task_listeners: List[Callable] = []
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 创建历史目录
        self.task_history_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"TaskManager initialized with max {max_concurrent_tasks} concurrent tasks")
    
    def create_task(self, name: str, task_type: str,
                   params: Optional[Dict[str, Any]] = None,
                   priority: TaskPriority = TaskPriority.NORMAL,
                   group: Optional[TaskGroup] = None,
                   scheduled_time: Optional[datetime] = None,
                   timeout: Optional[int] = None,
                   max_retries: int = 3,
                   dependencies: Optional[List[str]] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        创建新任务
        
        Args:
            name: 任务名称
            task_type: 任务类型
            params: 任务参数
            priority: 优先级
            group: 任务组
            scheduled_time: 计划执行时间
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
            dependencies: 依赖任务ID列表
            metadata: 额外的元数据
        
        Returns:
            任务ID
        """
        with self._lock:
            # 首先尝试从字符串创建 TaskType
            from src.models.task import TaskType
            try:
                # 尝试从枚举中找到对应的类型
                task_type_enum = next((t for t in TaskType if t.value == task_type), TaskType.CUSTOM)
            except:
                task_type_enum = TaskType.CUSTOM
            
            # 创建任务
            task = TaskInfo(
                task_id=str(uuid.uuid4()),
                task_name=name,
                task_type=task_type_enum,
                priority=priority,
                status=TaskStatus.PENDING,
                max_retries=max_retries,
                dependencies=dependencies or []
            )
            
            # 设置额外的属性到metadata
            task.metadata['task_type'] = task_type  # 保留字符串版本用于执行器
            task.metadata['params'] = params or {}
            task.metadata['group'] = group
            task.metadata['scheduled_time'] = scheduled_time
            task.metadata['timeout'] = timeout
            
            # 合并传入的metadata
            if metadata:
                task.metadata.update(metadata)
            
            # 存储任务
            self._tasks[task.task_id] = task
            
            # 创建结果记录
            self._task_results[task.task_id] = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.PENDING,
                start_time=datetime.now(),
                end_time=None
            )
            
            # 加入队列
            self._add_to_queue(task.task_id)
            
            self.logger.info(f"Task created: {task.task_id} - {name}")
            
            # 通知监听器
            self._notify_listeners('task_created', task)
            
            return task.task_id
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """
        获取任务信息
        
        Args:
            task_id: 任务ID
        
        Returns:
            任务信息
        """
        return self._tasks.get(task_id)
    
    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """
        获取任务结果
        
        Args:
            task_id: 任务ID
        
        Returns:
            任务结果
        """
        return self._task_results.get(task_id)
    
    def list_tasks(self, status: Optional[TaskStatus] = None,
                  group: Optional[TaskGroup] = None) -> List[TaskInfo]:
        """
        列出任务
        
        Args:
            status: 筛选状态
            group: 筛选任务组
        
        Returns:
            任务列表
        """
        tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        if group:
            tasks = [t for t in tasks if t.metadata.get('group') == group]
        
        return tasks
    
    def update_task_status(self, task_id: str, status: TaskStatus,
                          result: Any = None, error: Optional[str] = None) -> None:
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            result: 执行结果
            error: 错误信息
        """
        with self._lock:
            if task_id not in self._tasks:
                raise TaskNotFoundError(task_id)
            
            task = self._tasks[task_id]
            old_status = task.status
            task.status = status
            
            # 更新结果
            if task_id in self._task_results:
                task_result = self._task_results[task_id]
                task_result.status = status
                task_result.result = result
                task_result.error = error
                
                if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    task_result.end_time = datetime.now()
            
            self.logger.info(f"Task {task_id} status updated: {old_status} -> {status}")
            
            # 通知监听器
            self._notify_listeners('task_status_changed', task, old_status, status)
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            是否成功取消
        """
        with self._lock:
            if task_id not in self._tasks:
                raise TaskNotFoundError(task_id)
            
            task = self._tasks[task_id]
            
            # 只能取消待执行或运行中的任务
            if task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                self.logger.warning(f"Cannot cancel task {task_id} with status {task.status}")
                return False
            
            # 从队列中移除
            if task_id in self._task_queue:
                self._task_queue.remove(task_id)
            
            # 停止运行中的任务
            if task_id in self._running_tasks:
                # TODO: 实现任务中断机制
                pass
            
            # 更新状态
            self.update_task_status(task_id, TaskStatus.CANCELLED)
            
            self.logger.info(f"Task cancelled: {task_id}")
            return True
    
    def retry_task(self, task_id: str) -> bool:
        """
        重试任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            是否成功重试
        """
        with self._lock:
            if task_id not in self._tasks:
                raise TaskNotFoundError(task_id)
            
            task = self._tasks[task_id]
            
            # 只能重试失败的任务
            if task.status != TaskStatus.FAILED:
                self.logger.warning(f"Cannot retry task {task_id} with status {task.status}")
                return False
            
            # 检查重试次数
            if task.retry_count >= task.max_retries:
                self.logger.warning(f"Task {task_id} has reached max retries ({task.max_retries})")
                return False
            
            # 增加重试计数
            task.retry_count += 1
            
            # 重置状态
            task.status = TaskStatus.PENDING
            
            # 重新加入队列
            self._add_to_queue(task_id)
            
            self.logger.info(f"Task retry scheduled: {task_id} (attempt {task.retry_count})")
            return True
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            是否成功删除
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
            
            task = self._tasks[task_id]
            
            # 不能删除运行中的任务
            if task.status == TaskStatus.RUNNING:
                self.logger.warning(f"Cannot delete running task {task_id}")
                return False
            
            # 从队列中移除
            if task_id in self._task_queue:
                self._task_queue.remove(task_id)
            
            # 删除任务
            del self._tasks[task_id]
            
            # 删除结果
            if task_id in self._task_results:
                del self._task_results[task_id]
            
            self.logger.info(f"Task deleted: {task_id}")
            return True
    
    def register_executor(self, task_type: str, executor: Callable) -> None:
        """
        注册任务执行器
        
        Args:
            task_type: 任务类型
            executor: 执行器函数
        """
        self._executors[task_type] = executor
        self.logger.info(f"Executor registered for task type: {task_type}")
    
    def get_executor(self, task_type: str) -> Optional[Callable]:
        """
        获取任务执行器
        
        Args:
            task_type: 任务类型
        
        Returns:
            执行器函数
        """
        return self._executors.get(task_type)
    
    def add_task_listener(self, listener: Callable) -> None:
        """
        添加任务监听器
        
        Args:
            listener: 监听器函数
        """
        if listener not in self._task_listeners:
            self._task_listeners.append(listener)
    
    def remove_task_listener(self, listener: Callable) -> None:
        """
        移除任务监听器
        
        Args:
            listener: 监听器函数
        """
        if listener in self._task_listeners:
            self._task_listeners.remove(listener)
    
    def save_task_history(self, task_id: str) -> None:
        """
        保存任务历史记录
        
        Args:
            task_id: 任务ID
        """
        if task_id not in self._tasks:
            return
        
        task = self._tasks[task_id]
        result = self._task_results.get(task_id)
        
        # 构建历史记录
        history = {
            'task': task.to_dict() if hasattr(task, 'to_dict') else {
                'task_id': task.task_id,
                'task_name': task.task_name,
                'task_type': task.metadata.get('task_type'),
                'status': task.status.value,
                'priority': task.priority.value,
                'created_time': task.start_time.isoformat() if task.start_time else None
            },
            'result': {
                'status': result.status.value if result else None,
                'start_time': result.start_time.isoformat() if result else None,
                'end_time': result.end_time.isoformat() if result and result.end_time else None,
                'duration': str(result.duration) if result and result.duration else None,
                'error': result.error if result else None
            } if result else None
        }
        
        # 保存到文件
        history_file = self.task_history_dir / f"{task_id}.json"
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        self.logger.debug(f"Task history saved: {history_file}")
    
    def load_task_history(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        加载任务历史记录
        
        Args:
            task_id: 任务ID
        
        Returns:
            历史记录
        """
        history_file = self.task_history_dir / f"{task_id}.json"
        
        if not history_file.exists():
            return None
        
        with open(history_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Returns:
            统计信息
        """
        stats = {
            'total': len(self._tasks),
            'pending': len([t for t in self._tasks.values() if t.status == TaskStatus.PENDING]),
            'queued': len([t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]),
            'running': len([t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]),
            'completed': len([t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]),
            'failed': len([t for t in self._tasks.values() if t.status == TaskStatus.FAILED]),
            'cancelled': len([t for t in self._tasks.values() if t.status == TaskStatus.CANCELLED]),
            'queue_length': len(self._task_queue),
            'running_threads': len(self._running_tasks)
        }
        
        return stats
    
    def clear_completed_tasks(self) -> int:
        """
        清理已完成的任务
        
        Returns:
            清理的任务数量
        """
        with self._lock:
            completed_tasks = [
                task_id for task_id, task in self._tasks.items()
                if task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]
            ]
            
            for task_id in completed_tasks:
                # 保存历史
                self.save_task_history(task_id)
                # 删除任务
                del self._tasks[task_id]
                if task_id in self._task_results:
                    del self._task_results[task_id]
            
            self.logger.info(f"Cleared {len(completed_tasks)} completed tasks")
            return len(completed_tasks)
    
    def _add_to_queue(self, task_id: str) -> None:
        """
        添加任务到队列
        
        Args:
            task_id: 任务ID
        """
        if task_id not in self._task_queue:
            task = self._tasks[task_id]
            
            # 按优先级插入队列
            if task.priority == TaskPriority.HIGH:
                self._task_queue.insert(0, task_id)
            elif task.priority == TaskPriority.LOW:
                self._task_queue.append(task_id)
            else:
                # NORMAL优先级，插入到HIGH之后
                high_count = sum(1 for tid in self._task_queue 
                               if self._tasks.get(tid) and 
                               self._tasks[tid].priority == TaskPriority.HIGH)
                self._task_queue.insert(high_count, task_id)
    
    def _notify_listeners(self, event: str, *args) -> None:
        """
        通知监听器
        
        Args:
            event: 事件名称
            *args: 事件参数
        """
        for listener in self._task_listeners:
            try:
                listener(event, *args)
            except Exception as e:
                self.logger.error(f"Error in task listener: {e}")