"""
任务管理标签页
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QComboBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QCheckBox, QTimeEdit, QDateTimeEdit,
    QSplitter, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QTime, QDateTime, QTimer
from PyQt6.QtGui import QColor, QFont

from src.tasks.task_manager import TaskManager
from src.tasks.task_scheduler import TaskScheduler
from src.tasks.builtin_tasks import (
    DailyIdleRewardTaskBuilder,
    TaskTemplateManager
)
from src.controller.afk2_controller import AFK2Controller
from src.models.task import TaskInfo, TaskStatus, TaskPriority, TaskGroup
from src.services.log_service import LoggerMixin


class TaskTab(QWidget, LoggerMixin):
    """
    任务管理标签页
    """
    
    def __init__(self, task_manager: TaskManager,
                 task_scheduler: TaskScheduler,
                 game_controller: AFK2Controller):
        """
        初始化任务管理标签页
        
        Args:
            task_manager: 任务管理器
            task_scheduler: 任务调度器
            game_controller: 游戏控制器
        """
        super().__init__()
        self.task_manager = task_manager
        self.task_scheduler = task_scheduler
        self.game_controller = game_controller
        self.template_manager = TaskTemplateManager()
        
        self._init_ui()
        
        # 定时刷新任务列表
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_task_list)
        self.refresh_timer.start(2000)  # 每2秒刷新
        
        # 初始加载
        self._refresh_task_list()
        self._load_templates()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # 左侧面板 - 任务控制
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        splitter.addWidget(left_panel)
        
        # 快速任务组
        quick_group = QGroupBox("快速任务")
        quick_layout = QVBoxLayout()
        quick_group.setLayout(quick_layout)
        left_layout.addWidget(quick_group)
        
        # 唤醒游戏选择框
        self.wake_game_check = QCheckBox("唤醒游戏")
        self.wake_game_check.setToolTip("在执行任务前先确保游戏处于运行状态")
        self.wake_game_check.setChecked(True)  # 默认勾选
        quick_layout.addWidget(self.wake_game_check)
        
        # 快速任务按钮
        quick_btn_layout = QHBoxLayout()
        quick_layout.addLayout(quick_btn_layout)
        
        self.daily_btn = QPushButton("执行日常")
        self.daily_btn.clicked.connect(self._execute_daily_tasks)
        quick_btn_layout.addWidget(self.daily_btn)
        
        self.campaign_btn = QPushButton("征战推图")
        self.campaign_btn.clicked.connect(self._execute_campaign)
        quick_btn_layout.addWidget(self.campaign_btn)
        
        self.collect_btn = QPushButton("收集奖励")
        self.collect_btn.clicked.connect(self._collect_rewards)
        quick_btn_layout.addWidget(self.collect_btn)
        
        # 任务模板组
        template_group = QGroupBox("任务模板")
        template_layout = QVBoxLayout()
        template_group.setLayout(template_layout)
        left_layout.addWidget(template_group)
        
        # 模板选择
        template_select_layout = QHBoxLayout()
        template_layout.addLayout(template_select_layout)
        
        template_select_layout.addWidget(QLabel("选择模板:"))
        self.template_combo = QComboBox()
        template_select_layout.addWidget(self.template_combo)
        
        self.create_from_template_btn = QPushButton("创建任务")
        self.create_from_template_btn.clicked.connect(self._create_from_template)
        template_select_layout.addWidget(self.create_from_template_btn)
        
        # 定时任务组
        schedule_group = QGroupBox("定时任务")
        schedule_layout = QVBoxLayout()
        schedule_group.setLayout(schedule_layout)
        left_layout.addWidget(schedule_group)
        
        # 任务类型选择
        type_layout = QHBoxLayout()
        schedule_layout.addLayout(type_layout)
        
        type_layout.addWidget(QLabel("任务类型:"))
        self.task_type_combo = QComboBox()
        self.task_type_combo.addItems([
            "每日任务",
            "征战任务",
            "收集奖励",
            "英雄升级",
            "公会任务"
        ])
        type_layout.addWidget(self.task_type_combo)
        
        # 执行时间设置
        time_layout = QHBoxLayout()
        schedule_layout.addLayout(time_layout)
        
        time_layout.addWidget(QLabel("执行时间:"))
        self.schedule_time = QDateTimeEdit()
        self.schedule_time.setDateTime(QDateTime.currentDateTime())
        self.schedule_time.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.schedule_time.setCalendarPopup(True)
        time_layout.addWidget(self.schedule_time)
        
        # 循环设置
        repeat_layout = QHBoxLayout()
        schedule_layout.addLayout(repeat_layout)
        
        self.repeat_check = QCheckBox("循环执行")
        self.repeat_check.toggled.connect(self._on_repeat_toggled)
        repeat_layout.addWidget(self.repeat_check)
        
        repeat_layout.addWidget(QLabel("间隔:"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setMinimum(1)
        self.interval_spin.setMaximum(24)
        self.interval_spin.setValue(1)
        self.interval_spin.setEnabled(False)
        repeat_layout.addWidget(self.interval_spin)
        
        self.interval_unit = QComboBox()
        self.interval_unit.addItems(["小时", "天"])
        self.interval_unit.setEnabled(False)
        repeat_layout.addWidget(self.interval_unit)
        
        repeat_layout.addStretch()
        
        # 添加定时任务按钮
        self.add_schedule_btn = QPushButton("添加定时任务")
        self.add_schedule_btn.clicked.connect(self._add_scheduled_task)
        schedule_layout.addWidget(self.add_schedule_btn)
        
        left_layout.addStretch()
        
        # 右侧面板 - 任务列表
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        splitter.addWidget(right_panel)
        
        # 任务列表组
        list_group = QGroupBox("任务列表")
        list_layout = QVBoxLayout()
        list_group.setLayout(list_layout)
        right_layout.addWidget(list_group)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        list_layout.addLayout(control_layout)
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self._refresh_task_list)
        control_layout.addWidget(self.refresh_btn)
        
        self.cancel_btn = QPushButton("取消选中")
        self.cancel_btn.clicked.connect(self._cancel_selected_task)
        control_layout.addWidget(self.cancel_btn)
        
        self.retry_btn = QPushButton("重试选中")
        self.retry_btn.clicked.connect(self._retry_selected_task)
        control_layout.addWidget(self.retry_btn)
        
        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.clicked.connect(self._delete_selected_task)
        control_layout.addWidget(self.delete_btn)
        
        self.clear_btn = QPushButton("清理已完成")
        self.clear_btn.clicked.connect(self._clear_completed_tasks)
        control_layout.addWidget(self.clear_btn)
        
        control_layout.addStretch()
        
        # 添加执行按钮
        self.execute_btn = QPushButton("执行选中")
        self.execute_btn.clicked.connect(self._execute_selected_task)
        self.execute_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        control_layout.addWidget(self.execute_btn)
        
        self.execute_all_btn = QPushButton("执行全部")
        self.execute_all_btn.clicked.connect(self._execute_all_pending_tasks)
        self.execute_all_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; }")
        control_layout.addWidget(self.execute_all_btn)
        
        # 任务表格
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(7)
        self.task_table.setHorizontalHeaderLabels([
            "任务ID", "名称", "类型", "状态", "优先级", "创建时间", "操作"
        ])
        self.task_table.horizontalHeader().setStretchLastSection(True)
        self.task_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.task_table.setSortingEnabled(True)
        list_layout.addWidget(self.task_table)
        
        # 统计信息
        stats_layout = QHBoxLayout()
        list_layout.addLayout(stats_layout)
        
        self.stats_label = QLabel("统计: 总数:0 待执行:0 运行中:0 已完成:0 失败:0")
        self.stats_label.setFont(QFont("Arial", 10))
        stats_layout.addWidget(self.stats_label)
        
        stats_layout.addStretch()
        
        # 设置分割器比例
        splitter.setSizes([400, 600])
    
    def _on_repeat_toggled(self, checked: bool):
        """循环复选框切换"""
        self.interval_spin.setEnabled(checked)
        self.interval_unit.setEnabled(checked)
    
    def _refresh_task_list(self):
        """刷新任务列表"""
        # 获取所有任务
        tasks = self.task_manager.list_tasks()
        
        # 更新表格
        self.task_table.setRowCount(len(tasks))
        
        for i, task in enumerate(tasks):
            # 任务ID
            self.task_table.setItem(i, 0, QTableWidgetItem(task.task_id))
            
            # 名称
            self.task_table.setItem(i, 1, QTableWidgetItem(task.task_name))
            
            # 类型
            task_type = task.metadata.get('task_type', '') if hasattr(task, 'metadata') else ''
            self.task_table.setItem(i, 2, QTableWidgetItem(task_type))
            
            # 状态
            status_item = QTableWidgetItem(task.status.value)
            if task.status == TaskStatus.COMPLETED:
                status_item.setForeground(QColor(0, 128, 0))
            elif task.status == TaskStatus.FAILED:
                status_item.setForeground(QColor(255, 0, 0))
            elif task.status == TaskStatus.RUNNING:
                status_item.setForeground(QColor(0, 0, 255))
            elif task.status == TaskStatus.CANCELLED:
                status_item.setForeground(QColor(128, 128, 128))
            self.task_table.setItem(i, 3, status_item)
            
            # 优先级
            priority_item = QTableWidgetItem(task.priority.value)
            if task.priority == TaskPriority.HIGH:
                priority_item.setForeground(QColor(255, 0, 0))
            elif task.priority == TaskPriority.LOW:
                priority_item.setForeground(QColor(128, 128, 128))
            self.task_table.setItem(i, 4, priority_item)
            
            # 创建时间
            if hasattr(task, 'start_time') and task.start_time:
                create_time = task.start_time.strftime("%H:%M:%S")
            else:
                create_time = "-"
            self.task_table.setItem(i, 5, QTableWidgetItem(create_time))
            
            # 操作按钮（预留）
            self.task_table.setItem(i, 6, QTableWidgetItem(""))
        
        # 更新统计信息
        stats = self.task_manager.get_statistics()
        self.stats_label.setText(
            f"统计: 总数:{stats['total']} "
            f"待执行:{stats.get('pending', 0)} "
            f"队列中:{stats.get('queued', 0)} "
            f"运行中:{stats.get('running', 0)} "
            f"已完成:{stats.get('completed', 0)} "
            f"失败:{stats.get('failed', 0)}"
        )
    
    def _load_templates(self):
        """加载任务模板"""
        templates = self.template_manager.list_templates()
        self.template_combo.clear()
        for template in templates:
            self.template_combo.addItem(template.description, template.name)
    
    def _execute_daily_tasks(self):
        """执行每日挂机奖励任务"""
        try:
            # 创建每日挂机奖励任务
            daily_idle = DailyIdleRewardTaskBuilder(self.task_manager)
            task_id = daily_idle.create()
            
            # 获取任务并设置唤醒游戏标志
            task = self.task_manager.get_task(task_id)
            if task and self.wake_game_check.isChecked():
                task.metadata['wake_game'] = True
            
            self.logger.info(f"Daily idle reward task created: {task_id}")
            self._refresh_task_list()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建任务失败: {e}")
    
    def _execute_campaign(self):
        """执行征战任务（暂不支持）"""
        QMessageBox.warning(self, "不支持", "征战任务暂不支持")
    
    def _collect_rewards(self):
        """收集奖励（暂不支持）"""
        QMessageBox.warning(self, "不支持", "收集奖励任务暂不支持")
    
    def _create_from_template(self):
        """从模板创建任务"""
        template_name = self.template_combo.currentData()
        if not template_name:
            QMessageBox.warning(self, "警告", "请选择任务模板")
            return
        
        try:
            # 从模板创建任务
            task_id = self.template_manager.create_task_from_template(
                self.task_manager,
                template_name
            )
            
            self.logger.info(f"Task created from template: {template_name}")
            self._refresh_task_list()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建任务失败: {e}")
    
    def _add_scheduled_task(self):
        """添加定时任务"""
        task_types = {
            "每日任务": "daily_tasks",
            "征战任务": "campaign",
            "收集奖励": "collect_rewards",
            "英雄升级": "hero_upgrade",
            "公会任务": "guild_tasks"
        }
        
        task_name = self.task_type_combo.currentText()
        task_type = task_types.get(task_name)
        
        if not task_type:
            QMessageBox.warning(self, "警告", "请选择任务类型")
            return
        
        scheduled_time = self.schedule_time.dateTime().toPyDateTime()
        
        if self.repeat_check.isChecked():
            # 循环任务
            interval_value = self.interval_spin.value()
            interval_unit = self.interval_unit.currentText()
            
            if interval_unit == "小时":
                interval = timedelta(hours=interval_value)
            else:
                interval = timedelta(days=interval_value)
            
            job_id = self.task_scheduler.schedule_recurring_task(
                name=task_name,
                task_type=task_type,
                interval=interval,
                start_time=scheduled_time
            )
            
            QMessageBox.information(
                self,
                "成功",
                f"已添加循环任务\nID: {job_id}\n首次执行: {scheduled_time}"
            )
        else:
            # 单次定时任务
            task_id = self.task_manager.create_task(
                name=f"定时-{task_name}",
                task_type=task_type,
                scheduled_time=scheduled_time
            )
            
            self.task_scheduler.schedule_task(task_id, scheduled_time)
            
            QMessageBox.information(
                self,
                "成功",
                f"已添加定时任务\n执行时间: {scheduled_time}"
            )
        
        self.logger.info(f"Scheduled task added: {task_name} at {scheduled_time}")
    
    def _get_selected_task_id(self) -> Optional[str]:
        """获取选中的任务ID"""
        row = self.task_table.currentRow()
        if row < 0:
            return None
        
        task_id_item = self.task_table.item(row, 0)
        if task_id_item:
            return task_id_item.text()
        
        return None
    
    def _cancel_selected_task(self):
        """取消选中的任务"""
        task_id = self._get_selected_task_id()
        if not task_id:
            QMessageBox.warning(self, "警告", "请选择任务")
            return
        
        if self.task_manager.cancel_task(task_id):
            QMessageBox.information(self, "成功", "任务已取消")
            self._refresh_task_list()
        else:
            QMessageBox.warning(self, "警告", "无法取消该任务")
    
    def _retry_selected_task(self):
        """重试选中的任务"""
        task_id = self._get_selected_task_id()
        if not task_id:
            QMessageBox.warning(self, "警告", "请选择任务")
            return
        
        if self.task_manager.retry_task(task_id):
            QMessageBox.information(self, "成功", "任务已重新加入队列")
            self._refresh_task_list()
        else:
            QMessageBox.warning(self, "警告", "无法重试该任务")
    
    def _delete_selected_task(self):
        """删除选中的任务"""
        task_id = self._get_selected_task_id()
        if not task_id:
            QMessageBox.warning(self, "警告", "请选择任务")
            return
        
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除任务 {task_id} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.task_manager.delete_task(task_id):
                QMessageBox.information(self, "成功", "任务已删除")
                self._refresh_task_list()
            else:
                QMessageBox.warning(self, "警告", "无法删除该任务")
    
    def _clear_completed_tasks(self):
        """清理已完成的任务"""
        count = self.task_manager.clear_completed_tasks()
        QMessageBox.information(self, "成功", f"已清理 {count} 个已完成任务")
        self._refresh_task_list()
    
    def start_selected_tasks(self):
        """开始选中的任务（由主窗口调用）"""
        # 获取所有待执行任务
        pending_tasks = self.task_manager.list_tasks(status=TaskStatus.PENDING)
        
        for task in pending_tasks:
            self.task_scheduler.schedule_task(task.task_id)
        
        if pending_tasks:
            QMessageBox.information(self, "成功", f"已开始 {len(pending_tasks)} 个任务")
    
    def stop_all_tasks(self):
        """停止所有任务（由主窗口调用）"""
        # 取消所有运行中和待执行的任务
        tasks = self.task_manager.list_tasks()
        cancelled_count = 0
        
        for task in tasks:
            if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                if self.task_manager.cancel_task(task.task_id):
                    cancelled_count += 1
        
        if cancelled_count > 0:
            QMessageBox.information(self, "成功", f"已停止 {cancelled_count} 个任务")
    
    def _execute_selected_task(self):
        """执行选中的任务"""
        task_id = self._get_selected_task_id()
        if not task_id:
            QMessageBox.warning(self, "警告", "请选择要执行的任务")
            return
        
        # 获取任务信息
        task = self.task_manager.get_task(task_id)
        if not task:
            QMessageBox.warning(self, "警告", "任务不存在")
            return
        
        # 检查任务状态
        if task.status != TaskStatus.PENDING:
            if task.status == TaskStatus.RUNNING:
                QMessageBox.information(self, "提示", "任务正在执行中")
            elif task.status == TaskStatus.COMPLETED:
                QMessageBox.information(self, "提示", "任务已完成")
            elif task.status == TaskStatus.FAILED:
                reply = QMessageBox.question(
                    self,
                    "确认重试",
                    "任务执行失败，是否重试？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._retry_selected_task()
            else:
                QMessageBox.information(self, "提示", f"任务状态为 {task.status.value}，无法执行")
            return
        
        try:
            # 检查是否需要唤醒游戏
            if self.wake_game_check.isChecked():
                self._wake_game_if_needed()
            
            # 调度任务执行
            self.task_scheduler.schedule_task(task_id)
            self.logger.info(f"Task scheduled for execution: {task_id} - {task.task_name}")
            
            # 刷新任务列表
            self._refresh_task_list()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"执行任务失败: {e}")
            self.logger.error(f"Failed to execute task {task_id}: {e}")
    
    def _wake_game_if_needed(self):
        """如果需要，唤醒游戏"""
        try:
            # 检查游戏是否已运行
            if not self.game_controller.is_game_running():
                self.logger.info("游戏未运行，正在唤醒游戏...")
                
                # 创建唤醒游戏任务
                from src.tasks.wake_game_task import WakeGameTask
                wake_task = WakeGameTask(
                    name="唤醒游戏（任务前准备）",
                    wait_for_main=True,
                    startup_timeout=30.0
                )
                
                # 执行唤醒任务
                if wake_task.execute(self.game_controller):
                    self.logger.info("游戏唤醒成功")
                else:
                    raise Exception("游戏唤醒失败")
            else:
                self.logger.info("游戏已在运行")
        except Exception as e:
            self.logger.error(f"唤醒游戏失败: {e}")
            raise
    
    def _execute_all_pending_tasks(self):
        """执行所有待执行的任务"""
        # 获取所有待执行任务
        pending_tasks = self.task_manager.list_tasks(status=TaskStatus.PENDING)
        
        if not pending_tasks:
            QMessageBox.information(self, "提示", "没有待执行的任务")
            return
        
        # 确认执行
        reply = QMessageBox.question(
            self,
            "确认执行",
            f"确定要执行全部 {len(pending_tasks)} 个待执行任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            # 检查是否需要唤醒游戏
            if self.wake_game_check.isChecked():
                self._wake_game_if_needed()
            
            # 按优先级排序任务
            pending_tasks.sort(key=lambda t: (
                0 if t.priority == TaskPriority.HIGH else 
                1 if t.priority == TaskPriority.NORMAL else 2
            ))
            
            executed_count = 0
            failed_tasks = []
            
            for task in pending_tasks:
                try:
                    self.task_scheduler.schedule_task(task.task_id)
                    executed_count += 1
                    self.logger.info(f"Task scheduled: {task.task_id} - {task.task_name}")
                except Exception as e:
                    failed_tasks.append(task.task_name)
                    self.logger.error(f"Failed to schedule task {task.task_id}: {e}")
            
            # 显示结果
            if executed_count > 0:
                message = f"已开始执行 {executed_count} 个任务"
                if failed_tasks:
                    message += f"\n\n以下任务执行失败:\n" + "\n".join(failed_tasks)
                QMessageBox.information(self, "执行结果", message)
            else:
                QMessageBox.warning(self, "警告", "没有任务被执行")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"执行任务失败: {e}")
            self.logger.error(f"Failed to execute all tasks: {e}")
        
        # 刷新任务列表
        self._refresh_task_list()