"""
任务调度器
负责任务的调度和定时执行
"""

import time
import threading
import schedule
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from queue import PriorityQueue, Queue
import heapq

from src.services.log_service import LoggerMixin
from src.tasks.task_manager import TaskManager
from src.tasks.task_executor import TaskExecutor
from src.models.task import TaskInfo, TaskStatus, TaskPriority
from src.utils.exceptions import TaskError


class TaskScheduler(LoggerMixin):
    """
    任务调度器
    负责任务的调度、优先级管理和定时执行
    """
    
    def __init__(self, task_manager: TaskManager,
                 task_executor: Optional['TaskExecutor'] = None,
                 max_workers: int = 5):
        """
        初始化任务调度器
        
        Args:
            task_manager: 任务管理器
            task_executor: 任务执行器
            max_workers: 最大工作线程数
        """
        self.task_manager = task_manager
        self.task_executor = task_executor
        self.max_workers = max_workers
        
        # 调度状态
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._worker_threads: List[threading.Thread] = []
        
        # 任务队列（优先级队列）
        self._priority_queue = PriorityQueue()
        self._scheduled_tasks: Dict[str, datetime] = {}
        
        # 定时任务
        self._cron_jobs: Dict[str, Dict[str, Any]] = {}
        
        # 线程池
        self._thread_pool: List[threading.Thread] = []
        self._available_workers = threading.Semaphore(max_workers)
        
        # 停止事件
        self._stop_event = threading.Event()
        
        self.logger.info(f"TaskScheduler initialized with {max_workers} workers")
    
    def start(self) -> None:
        """启动调度器"""
        if self._running:
            self.logger.warning("Scheduler is already running")
            return
        
        self._running = True
        self._stop_event.clear()
        
        # 启动调度线程
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="TaskScheduler-Main"
        )
        self._scheduler_thread.daemon = True
        self._scheduler_thread.start()
        
        # 启动工作线程
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"TaskWorker-{i}"
            )
            worker.daemon = True
            worker.start()
            self._worker_threads.append(worker)
        
        # 启动定时任务线程
        cron_thread = threading.Thread(
            target=self._cron_loop,
            name="TaskScheduler-Cron"
        )
        cron_thread.daemon = True
        cron_thread.start()
        
        self.logger.info("Task scheduler started")
    
    def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        """
        停止调度器
        
        Args:
            wait: 是否等待任务完成
            timeout: 等待超时时间
        """
        if not self._running:
            return
        
        self.logger.info("Stopping task scheduler...")
        self._running = False
        self._stop_event.set()
        
        if wait:
            # 等待所有工作线程结束
            start_time = time.time()
            for worker in self._worker_threads:
                remaining = timeout - (time.time() - start_time)
                if remaining > 0:
                    worker.join(timeout=remaining)
        
        self._worker_threads.clear()
        self.logger.info("Task scheduler stopped")
    
    def schedule_task(self, task_id: str, 
                     scheduled_time: Optional[datetime] = None) -> None:
        """
        调度任务
        
        Args:
            task_id: 任务ID
            scheduled_time: 计划执行时间
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            raise TaskError(f"Task {task_id} not found")
        
        if scheduled_time:
            # 定时任务
            self._scheduled_tasks[task_id] = scheduled_time
            self.logger.info(f"Task {task_id} scheduled for {scheduled_time}")
        else:
            # 立即执行
            self._enqueue_task(task)
    
    def schedule_recurring_task(self, name: str, task_type: str,
                              interval: timedelta,
                              params: Optional[Dict[str, Any]] = None,
                              start_time: Optional[datetime] = None) -> str:
        """
        调度循环任务
        
        Args:
            name: 任务名称
            task_type: 任务类型
            interval: 执行间隔
            params: 任务参数
            start_time: 首次执行时间
        
        Returns:
            循环任务ID
        """
        job_id = f"recurring_{name}_{int(time.time())}"
        
        self._cron_jobs[job_id] = {
            'name': name,
            'task_type': task_type,
            'interval': interval,
            'params': params or {},
            'next_run': start_time or datetime.now(),
            'enabled': True
        }
        
        self.logger.info(f"Recurring task scheduled: {job_id} every {interval}")
        return job_id
    
    def schedule_daily_task(self, name: str, task_type: str,
                          time_str: str,
                          params: Optional[Dict[str, Any]] = None) -> str:
        """
        调度每日任务
        
        Args:
            name: 任务名称
            task_type: 任务类型
            time_str: 执行时间（如 "08:00"）
            params: 任务参数
        
        Returns:
            任务ID
        """
        # 使用schedule库设置每日任务
        def create_task():
            task_id = self.task_manager.create_task(
                name=f"Daily-{name}",
                task_type=task_type,
                params=params,
                priority=TaskPriority.NORMAL
            )
            self.schedule_task(task_id)
        
        schedule.every().day.at(time_str).do(create_task)
        
        job_id = f"daily_{name}_{time_str.replace(':', '')}"
        self.logger.info(f"Daily task scheduled: {job_id} at {time_str}")
        
        return job_id
    
    def cancel_recurring_task(self, job_id: str) -> bool:
        """
        取消循环任务
        
        Args:
            job_id: 循环任务ID
        
        Returns:
            是否成功取消
        """
        if job_id in self._cron_jobs:
            self._cron_jobs[job_id]['enabled'] = False
            self.logger.info(f"Recurring task cancelled: {job_id}")
            return True
        return False
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        获取队列状态
        
        Returns:
            队列状态信息
        """
        return {
            'queue_size': self._priority_queue.qsize(),
            'scheduled_tasks': len(self._scheduled_tasks),
            'recurring_tasks': len([j for j in self._cron_jobs.values() if j['enabled']]),
            'available_workers': self._available_workers._value,
            'running': self._running
        }
    
    def _scheduler_loop(self) -> None:
        """调度器主循环"""
        while self._running:
            try:
                # 检查定时任务
                self._check_scheduled_tasks()
                
                # 检查依赖任务
                self._check_task_dependencies()
                
                # 睡眠一段时间
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Scheduler loop error: {e}")
    
    def _worker_loop(self) -> None:
        """工作线程循环"""
        while self._running:
            try:
                # 从队列获取任务（阻塞，超时1秒）
                task = self._dequeue_task(timeout=1)
                
                if task:
                    # 获取工作许可
                    self._available_workers.acquire()
                    
                    try:
                        # 执行任务
                        self._execute_task(task)
                    finally:
                        # 释放工作许可
                        self._available_workers.release()
                        
            except Exception as e:
                self.logger.error(f"Worker loop error: {e}")
    
    def _cron_loop(self) -> None:
        """定时任务循环"""
        while self._running:
            try:
                # 运行schedule库的待执行任务
                schedule.run_pending()
                
                # 检查循环任务
                now = datetime.now()
                for job_id, job in self._cron_jobs.items():
                    if not job['enabled']:
                        continue
                    
                    if now >= job['next_run']:
                        # 创建任务
                        task_id = self.task_manager.create_task(
                            name=job['name'],
                            task_type=job['task_type'],
                            params=job['params']
                        )
                        
                        # 调度任务
                        self.schedule_task(task_id)
                        
                        # 更新下次运行时间
                        job['next_run'] = now + job['interval']
                        
                        self.logger.debug(f"Recurring task triggered: {job_id}")
                
                # 睡眠
                time.sleep(10)
                
            except Exception as e:
                self.logger.error(f"Cron loop error: {e}")
    
    def _check_scheduled_tasks(self) -> None:
        """检查定时任务"""
        now = datetime.now()
        due_tasks = []
        
        for task_id, scheduled_time in list(self._scheduled_tasks.items()):
            if now >= scheduled_time:
                due_tasks.append(task_id)
        
        for task_id in due_tasks:
            task = self.task_manager.get_task(task_id)
            if task:
                self._enqueue_task(task)
                del self._scheduled_tasks[task_id]
                self.logger.info(f"Scheduled task triggered: {task_id}")
    
    def _check_task_dependencies(self) -> None:
        """检查任务依赖"""
        pending_tasks = self.task_manager.list_tasks(status=TaskStatus.PENDING)
        
        for task in pending_tasks:
            if task.dependencies:
                # 检查所有依赖是否完成
                all_completed = True
                for dep_id in task.dependencies:
                    dep_task = self.task_manager.get_task(dep_id)
                    if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                        all_completed = False
                        break
                
                if all_completed:
                    # 依赖满足，加入队列
                    self._enqueue_task(task)
                    self.logger.info(f"Task {task.task_id} dependencies satisfied")
    
    def _enqueue_task(self, task: TaskInfo) -> None:
        """
        将任务加入队列
        
        Args:
            task: 任务信息
        """
        # 计算优先级值（越小越优先）
        priority_value = {
            TaskPriority.HIGH: 0,
            TaskPriority.NORMAL: 1,
            TaskPriority.LOW: 2
        }.get(task.priority, 1)
        
        # 加入优先级队列
        self._priority_queue.put((priority_value, time.time(), task))
        
        # 更新任务状态
        self.task_manager.update_task_status(task.task_id, TaskStatus.QUEUED)
    
    def _dequeue_task(self, timeout: float = 1.0) -> Optional[TaskInfo]:
        """
        从队列获取任务
        
        Args:
            timeout: 超时时间
        
        Returns:
            任务信息
        """
        try:
            _, _, task = self._priority_queue.get(timeout=timeout)
            return task
        except:
            return None
    
    def _execute_task(self, task: TaskInfo) -> None:
        """
        执行任务
        
        Args:
            task: 任务信息
        """
        try:
            # 更新状态为运行中
            self.task_manager.update_task_status(task.task_id, TaskStatus.RUNNING)
            
            # 获取执行器
            if self.task_executor:
                # 使用任务执行器
                result = self.task_executor.execute(task)
            else:
                # 使用注册的执行器函数
                executor = self.task_manager.get_executor(task.task_type)
                if executor:
                    result = executor(task)
                else:
                    raise TaskError(f"No executor found for task type: {task.task_type}")
            
            # 更新状态为完成
            self.task_manager.update_task_status(
                task.task_id,
                TaskStatus.COMPLETED,
                result=result
            )
            
            self.logger.info(f"Task completed: {task.task_id}")
            
        except Exception as e:
            self.logger.error(f"Task execution failed: {task.task_id} - {e}")
            
            # 更新状态为失败
            self.task_manager.update_task_status(
                task.task_id,
                TaskStatus.FAILED,
                error=str(e)
            )
            
            # 检查是否需要重试
            if task.retry_count < task.max_retries:
                self.task_manager.retry_task(task.task_id)
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running