"""
任务管理系统单元测试
"""

import pytest
import time
import threading
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil

from src.tasks.task_manager import TaskManager, TaskResult
from src.tasks.task_scheduler import TaskScheduler
from src.tasks.task_executor import TaskExecutor
from src.tasks.builtin_tasks import (
    DailyTask, CampaignTask, CollectRewardTask,
    TaskTemplateManager
)
from src.models.task import TaskInfo, TaskStatus, TaskPriority, TaskGroup
from src.controller.afk2_controller import AFK2Controller
from src.utils.exceptions import TaskError, TaskNotFoundError, TaskExecutionError


@pytest.fixture
def temp_history_dir():
    """创建临时历史目录"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def task_manager(temp_history_dir):
    """创建任务管理器"""
    return TaskManager(
        max_concurrent_tasks=3,
        task_history_dir=temp_history_dir
    )


@pytest.fixture
def mock_game_controller():
    """创建模拟游戏控制器"""
    mock = MagicMock(spec=AFK2Controller)
    mock.is_game_running.return_value = True
    mock.perform_daily_tasks.return_value = {'test': True}
    mock.auto_campaign.return_value = True
    mock.collect_idle_rewards.return_value = True
    mock.collect_mail.return_value = True
    mock.collect_quest_rewards.return_value = True
    return mock


@pytest.fixture
def task_executor(mock_game_controller):
    """创建任务执行器"""
    return TaskExecutor(game_controller=mock_game_controller)


@pytest.fixture
def task_scheduler(task_manager, task_executor):
    """创建任务调度器"""
    return TaskScheduler(
        task_manager=task_manager,
        task_executor=task_executor,
        max_workers=2
    )


class TestTaskManager:
    """任务管理器测试"""
    
    def test_init(self, temp_history_dir):
        """测试初始化"""
        manager = TaskManager(task_history_dir=temp_history_dir)
        assert manager.max_concurrent_tasks == 5
        assert manager.task_history_dir == temp_history_dir
        assert len(manager._tasks) == 0
    
    def test_create_task(self, task_manager):
        """测试创建任务"""
        task_id = task_manager.create_task(
            name="Test Task",
            task_type="test",
            params={'key': 'value'},
            priority=TaskPriority.HIGH
        )
        
        assert task_id is not None
        assert task_id in task_manager._tasks
        
        task = task_manager.get_task(task_id)
        assert task.name == "Test Task"
        assert task.task_type == "test"
        assert task.params == {'key': 'value'}
        assert task.priority == TaskPriority.HIGH
        assert task.status == TaskStatus.PENDING
    
    def test_get_task(self, task_manager):
        """测试获取任务"""
        task_id = task_manager.create_task("Test", "test")
        
        task = task_manager.get_task(task_id)
        assert task is not None
        assert task.task_id == task_id
        
        # 不存在的任务
        assert task_manager.get_task("nonexistent") is None
    
    def test_list_tasks(self, task_manager):
        """测试列出任务"""
        # 创建多个任务
        task1 = task_manager.create_task("Task1", "test", priority=TaskPriority.HIGH)
        task2 = task_manager.create_task("Task2", "test", priority=TaskPriority.LOW)
        task3 = task_manager.create_task("Task3", "test", group=TaskGroup.DAILY)
        
        # 列出所有任务
        all_tasks = task_manager.list_tasks()
        assert len(all_tasks) == 3
        
        # 按状态筛选
        pending_tasks = task_manager.list_tasks(status=TaskStatus.PENDING)
        assert len(pending_tasks) == 3
        
        # 按组筛选
        daily_tasks = task_manager.list_tasks(group=TaskGroup.DAILY)
        assert len(daily_tasks) == 1
    
    def test_update_task_status(self, task_manager):
        """测试更新任务状态"""
        task_id = task_manager.create_task("Test", "test")
        
        # 更新状态
        task_manager.update_task_status(task_id, TaskStatus.RUNNING)
        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.RUNNING
        
        # 更新为完成
        task_manager.update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            result={'success': True}
        )
        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        
        result = task_manager.get_task_result(task_id)
        assert result.status == TaskStatus.COMPLETED
        assert result.result == {'success': True}
    
    def test_cancel_task(self, task_manager):
        """测试取消任务"""
        task_id = task_manager.create_task("Test", "test")
        
        # 取消待执行任务
        success = task_manager.cancel_task(task_id)
        assert success is True
        
        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.CANCELLED
        
        # 不能取消已完成的任务
        task_manager.update_task_status(task_id, TaskStatus.COMPLETED)
        success = task_manager.cancel_task(task_id)
        assert success is False
    
    def test_retry_task(self, task_manager):
        """测试重试任务"""
        task_id = task_manager.create_task("Test", "test", max_retries=3)
        
        # 设置为失败状态
        task_manager.update_task_status(task_id, TaskStatus.FAILED)
        
        # 重试
        success = task_manager.retry_task(task_id)
        assert success is True
        
        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.PENDING
        assert task.retry_count == 1
        
        # 达到最大重试次数
        task.retry_count = 3
        task.status = TaskStatus.FAILED
        success = task_manager.retry_task(task_id)
        assert success is False
    
    def test_delete_task(self, task_manager):
        """测试删除任务"""
        task_id = task_manager.create_task("Test", "test")
        
        # 删除任务
        success = task_manager.delete_task(task_id)
        assert success is True
        assert task_manager.get_task(task_id) is None
        
        # 不能删除运行中的任务
        task_id2 = task_manager.create_task("Test2", "test")
        task_manager.update_task_status(task_id2, TaskStatus.RUNNING)
        success = task_manager.delete_task(task_id2)
        assert success is False
    
    def test_register_executor(self, task_manager):
        """测试注册执行器"""
        def test_executor(task):
            return "executed"
        
        task_manager.register_executor("test_type", test_executor)
        executor = task_manager.get_executor("test_type")
        assert executor == test_executor
    
    def test_save_load_history(self, task_manager):
        """测试保存和加载历史"""
        task_id = task_manager.create_task("Test", "test")
        task_manager.update_task_status(task_id, TaskStatus.COMPLETED)
        
        # 保存历史
        task_manager.save_task_history(task_id)
        
        # 加载历史
        history = task_manager.load_task_history(task_id)
        assert history is not None
        assert history['task']['name'] == "Test"
        assert history['result']['status'] == "completed"
    
    def test_statistics(self, task_manager):
        """测试统计信息"""
        # 创建不同状态的任务
        task1 = task_manager.create_task("Task1", "test")
        task2 = task_manager.create_task("Task2", "test")
        task_manager.update_task_status(task2, TaskStatus.RUNNING)
        task3 = task_manager.create_task("Task3", "test")
        task_manager.update_task_status(task3, TaskStatus.COMPLETED)
        
        stats = task_manager.get_statistics()
        assert stats['total'] == 3
        assert stats['pending'] == 1
        assert stats['running'] == 1
        assert stats['completed'] == 1
    
    def test_clear_completed_tasks(self, task_manager):
        """测试清理已完成任务"""
        # 创建任务
        task1 = task_manager.create_task("Task1", "test")
        task2 = task_manager.create_task("Task2", "test")
        task_manager.update_task_status(task1, TaskStatus.COMPLETED)
        task_manager.update_task_status(task2, TaskStatus.CANCELLED)
        
        # 清理
        count = task_manager.clear_completed_tasks()
        assert count == 2
        assert len(task_manager._tasks) == 0


class TestTaskScheduler:
    """任务调度器测试"""
    
    def test_init(self, task_manager):
        """测试初始化"""
        scheduler = TaskScheduler(task_manager, max_workers=3)
        assert scheduler.task_manager == task_manager
        assert scheduler.max_workers == 3
        assert not scheduler.is_running
    
    def test_start_stop(self, task_scheduler):
        """测试启动和停止"""
        # 启动
        task_scheduler.start()
        assert task_scheduler.is_running
        
        # 停止
        task_scheduler.stop(wait=False)
        time.sleep(0.1)
        assert not task_scheduler.is_running
    
    def test_schedule_task(self, task_manager, task_scheduler):
        """测试调度任务"""
        task_id = task_manager.create_task("Test", "test")
        
        with patch.object(task_scheduler, '_enqueue_task'):
            task_scheduler.schedule_task(task_id)
            task_scheduler._enqueue_task.assert_called_once()
    
    def test_schedule_recurring_task(self, task_scheduler):
        """测试调度循环任务"""
        job_id = task_scheduler.schedule_recurring_task(
            name="Test Recurring",
            task_type="test",
            interval=timedelta(minutes=5),
            params={'key': 'value'}
        )
        
        assert job_id in task_scheduler._cron_jobs
        job = task_scheduler._cron_jobs[job_id]
        assert job['name'] == "Test Recurring"
        assert job['interval'] == timedelta(minutes=5)
        assert job['enabled'] is True
    
    def test_cancel_recurring_task(self, task_scheduler):
        """测试取消循环任务"""
        job_id = task_scheduler.schedule_recurring_task(
            name="Test",
            task_type="test",
            interval=timedelta(minutes=5)
        )
        
        success = task_scheduler.cancel_recurring_task(job_id)
        assert success is True
        assert task_scheduler._cron_jobs[job_id]['enabled'] is False
    
    def test_get_queue_status(self, task_scheduler):
        """测试获取队列状态"""
        status = task_scheduler.get_queue_status()
        assert 'queue_size' in status
        assert 'scheduled_tasks' in status
        assert 'recurring_tasks' in status
        assert 'available_workers' in status


class TestTaskExecutor:
    """任务执行器测试"""
    
    def test_init(self, mock_game_controller):
        """测试初始化"""
        executor = TaskExecutor(game_controller=mock_game_controller)
        assert executor.game_controller == mock_game_controller
        assert len(executor._executors) > 0
    
    def test_execute_task(self, task_executor):
        """测试执行任务"""
        # 创建任务
        task = TaskInfo(
            task_id="test_id",
            name="Test Task",
            task_type="daily_tasks",
            params={},
            status=TaskStatus.RUNNING
        )
        
        # 执行任务
        result = task_executor.execute(task)
        assert result is not None
        assert isinstance(result, dict)
    
    def test_register_executor(self, task_executor):
        """测试注册执行器"""
        def custom_executor(task, context):
            return "custom_result"
        
        task_executor.register_executor("custom", custom_executor)
        assert "custom" in task_executor._executors
    
    def test_context_management(self, task_executor):
        """测试上下文管理"""
        task_executor.set_context("key", "value")
        assert task_executor.get_context("key") == "value"
        assert task_executor.get_context("nonexistent", "default") == "default"
    
    def test_statistics(self, task_executor):
        """测试执行统计"""
        # 执行任务
        task = TaskInfo(
            task_id="test",
            name="Test",
            task_type="collect_rewards",
            params={},
            status=TaskStatus.RUNNING
        )
        
        task_executor.execute(task)
        
        stats = task_executor.get_statistics()
        assert 'collect_rewards' in stats
        assert stats['collect_rewards']['total'] == 1
        assert stats['collect_rewards']['success'] == 1


class TestBuiltinTasks:
    """内置任务测试"""
    
    def test_daily_task(self, task_manager):
        """测试日常任务"""
        daily_task = DailyTask(task_manager)
        
        # 创建日常任务
        task_id = daily_task.create()
        assert task_id is not None
        
        task = task_manager.get_task(task_id)
        assert task.name == "每日任务合集"
        assert task.task_type == "daily_tasks"
    
    def test_daily_subtasks(self, task_manager):
        """测试日常子任务"""
        daily_task = DailyTask(task_manager)
        
        # 创建子任务
        task_ids = daily_task.create_subtasks()
        assert len(task_ids) == 4
        
        # 验证依赖关系
        campaign_task = task_manager.get_task(task_ids[1])
        assert len(campaign_task.dependencies) == 1
    
    def test_campaign_task(self, task_manager):
        """测试征战任务"""
        campaign_task = CampaignTask(task_manager)
        
        task_id = campaign_task.create(
            max_battles=5,
            use_quick_battle=True
        )
        
        task = task_manager.get_task(task_id)
        assert task.task_type == "campaign"
        assert task.params['max_battles'] == 5
        assert task.params['use_quick_battle'] is True
    
    def test_template_manager(self):
        """测试任务模板管理器"""
        manager = TaskTemplateManager()
        
        # 获取内置模板
        template = manager.get_template("daily_full")
        assert template is not None
        assert template.task_type == "daily_tasks"
        
        # 列出所有模板
        templates = manager.list_templates()
        assert len(templates) > 0