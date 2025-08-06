"""
任务执行器
负责具体任务的执行
"""

import time
import threading
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import traceback

from src.services.log_service import LoggerMixin
from src.models.task import TaskInfo, TaskStatus
from src.controller.afk2_controller import AFK2Controller
from src.services.adb_service import ADBService
from src.utils.exceptions import TaskError, TaskExecutionError


class TaskExecutor(LoggerMixin):
    """
    任务执行器
    负责执行具体的任务逻辑
    """
    
    def __init__(self, game_controller: Optional[AFK2Controller] = None):
        """
        初始化任务执行器
        
        Args:
            game_controller: 游戏控制器
        """
        self.game_controller = game_controller
        
        # 任务执行函数注册表
        self._executors: Dict[str, Callable] = {}
        
        # 执行上下文
        self._context: Dict[str, Any] = {}
        
        # 执行统计
        self._execution_stats: Dict[str, Dict[str, Any]] = {}
        
        # 注册内置执行器
        self._register_builtin_executors()
        
        self.logger.info("TaskExecutor initialized")
    
    def execute(self, task: TaskInfo) -> Any:
        """
        执行任务
        
        Args:
            task: 任务信息
        
        Returns:
            执行结果
        """
        start_time = time.time()
        
        try:
            # 获取执行器
            executor = self._executors.get(task.task_type)
            if not executor:
                raise TaskExecutionError(f"No executor for task type: {task.task_type}")
            
            self.logger.info(f"Executing task: {task.name} ({task.task_id})")
            
            # 设置超时
            if task.timeout:
                result = self._execute_with_timeout(executor, task, task.timeout)
            else:
                result = executor(task, self._context)
            
            # 更新统计
            self._update_stats(task.task_type, True, time.time() - start_time)
            
            self.logger.info(f"Task executed successfully: {task.name}")
            return result
            
        except Exception as e:
            # 更新统计
            self._update_stats(task.task_type, False, time.time() - start_time)
            
            self.logger.error(f"Task execution failed: {task.name} - {e}")
            self.logger.debug(traceback.format_exc())
            raise TaskExecutionError(f"Task execution failed: {e}")
    
    def register_executor(self, task_type: str, executor: Callable) -> None:
        """
        注册任务执行器
        
        Args:
            task_type: 任务类型
            executor: 执行函数
        """
        self._executors[task_type] = executor
        self.logger.info(f"Executor registered for type: {task_type}")
    
    def set_context(self, key: str, value: Any) -> None:
        """
        设置执行上下文
        
        Args:
            key: 键
            value: 值
        """
        self._context[key] = value
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """
        获取执行上下文
        
        Args:
            key: 键
            default: 默认值
        
        Returns:
            上下文值
        """
        return self._context.get(key, default)
    
    def get_statistics(self) -> Dict[str, Dict[str, Any]]:
        """
        获取执行统计
        
        Returns:
            统计信息
        """
        return self._execution_stats.copy()
    
    def _register_builtin_executors(self) -> None:
        """注册内置执行器"""
        
        # 日常任务执行器
        self.register_executor('daily_tasks', self._execute_daily_tasks)
        
        # 征战任务执行器
        self.register_executor('campaign', self._execute_campaign)
        
        # 收集奖励执行器
        self.register_executor('collect_rewards', self._execute_collect_rewards)
        
        # 英雄升级执行器
        self.register_executor('hero_upgrade', self._execute_hero_upgrade)
        
        # 公会任务执行器
        self.register_executor('guild_tasks', self._execute_guild_tasks)
        
        # 自定义脚本执行器
        self.register_executor('custom_script', self._execute_custom_script)
    
    def _execute_with_timeout(self, executor: Callable, task: TaskInfo, 
                            timeout: int) -> Any:
        """
        带超时的任务执行
        
        Args:
            executor: 执行函数
            task: 任务信息
            timeout: 超时时间（秒）
        
        Returns:
            执行结果
        """
        result = [None]
        exception = [None]
        
        def run():
            try:
                result[0] = executor(task, self._context)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            # 超时
            raise TaskExecutionError(f"Task timeout after {timeout} seconds")
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    def _update_stats(self, task_type: str, success: bool, duration: float) -> None:
        """
        更新执行统计
        
        Args:
            task_type: 任务类型
            success: 是否成功
            duration: 执行时长
        """
        if task_type not in self._execution_stats:
            self._execution_stats[task_type] = {
                'total': 0,
                'success': 0,
                'failed': 0,
                'total_duration': 0.0,
                'avg_duration': 0.0
            }
        
        stats = self._execution_stats[task_type]
        stats['total'] += 1
        
        if success:
            stats['success'] += 1
        else:
            stats['failed'] += 1
        
        stats['total_duration'] += duration
        stats['avg_duration'] = stats['total_duration'] / stats['total']
    
    # ========== 内置执行器实现 ==========
    
    def _execute_daily_tasks(self, task: TaskInfo, context: Dict[str, Any]) -> Dict[str, bool]:
        """
        执行日常任务
        
        Args:
            task: 任务信息
            context: 执行上下文
        
        Returns:
            任务执行结果
        """
        if not self.game_controller:
            raise TaskExecutionError("Game controller not available")
        
        # 确保游戏运行
        if not self.game_controller.is_game_running():
            self.game_controller.start_game()
        
        # 执行日常任务
        results = self.game_controller.perform_daily_tasks()
        
        self.logger.info(f"Daily tasks completed: {results}")
        return results
    
    def _execute_campaign(self, task: TaskInfo, context: Dict[str, Any]) -> bool:
        """
        执行征战任务
        
        Args:
            task: 任务信息
            context: 执行上下文
        
        Returns:
            是否成功
        """
        if not self.game_controller:
            raise TaskExecutionError("Game controller not available")
        
        # 获取参数
        max_battles = task.params.get('max_battles', 10)
        
        # 执行征战
        result = self.game_controller.auto_campaign(max_battles)
        
        return result
    
    def _execute_collect_rewards(self, task: TaskInfo, context: Dict[str, Any]) -> bool:
        """
        执行收集奖励任务
        
        Args:
            task: 任务信息
            context: 执行上下文
        
        Returns:
            是否成功
        """
        if not self.game_controller:
            raise TaskExecutionError("Game controller not available")
        
        # 收集各种奖励
        results = {
            'idle': self.game_controller.collect_idle_rewards(),
            'mail': self.game_controller.collect_mail(),
            'quest': self.game_controller.collect_quest_rewards()
        }
        
        self.logger.info(f"Rewards collected: {results}")
        return all(results.values())
    
    def _execute_hero_upgrade(self, task: TaskInfo, context: Dict[str, Any]) -> bool:
        """
        执行英雄升级任务
        
        Args:
            task: 任务信息
            context: 执行上下文
        
        Returns:
            是否成功
        """
        if not self.game_controller:
            raise TaskExecutionError("Game controller not available")
        
        # 执行英雄升级
        result = self.game_controller.upgrade_heroes()
        
        return result
    
    def _execute_guild_tasks(self, task: TaskInfo, context: Dict[str, Any]) -> bool:
        """
        执行公会任务
        
        Args:
            task: 任务信息
            context: 执行上下文
        
        Returns:
            是否成功
        """
        if not self.game_controller:
            raise TaskExecutionError("Game controller not available")
        
        # 公会签到
        result = self.game_controller.guild_checkin()
        
        # TODO: 添加其他公会任务
        
        return result
    
    def _execute_custom_script(self, task: TaskInfo, context: Dict[str, Any]) -> Any:
        """
        执行自定义脚本
        
        Args:
            task: 任务信息
            context: 执行上下文
        
        Returns:
            脚本执行结果
        """
        script_path = task.params.get('script_path')
        script_code = task.params.get('script_code')
        
        if script_path:
            # 执行脚本文件
            with open(script_path, 'r', encoding='utf-8') as f:
                script_code = f.read()
        
        if not script_code:
            raise TaskExecutionError("No script provided")
        
        # 准备执行环境
        exec_globals = {
            'game_controller': self.game_controller,
            'context': context,
            'task': task,
            'logger': self.logger
        }
        
        # 执行脚本
        exec_locals = {}
        exec(script_code, exec_globals, exec_locals)
        
        # 返回结果
        return exec_locals.get('result', True)