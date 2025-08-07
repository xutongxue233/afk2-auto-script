# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

《剑与远征：启程》(AFK2) 手游自动化脚本，通过 ADB 与 Android 设备通信实现游戏自动化操作。基于 PyQt6 构建 GUI 界面，支持图像识别、OCR 文字识别和任务调度。

## 常用命令

### 开发环境设置
```bash
# 安装依赖
pip install -r requirements.txt

# 安装开发依赖
pip install -r requirements-dev.txt

# 最小依赖（无GUI）
pip install -r requirements-minimal.txt
```

### 运行模式
```bash
# GUI模式（默认）
python run.py

# 测试ADB连接
python run.py --mode test

# 执行日常任务
python run.py --mode daily

# 征战推图
python run.py --mode campaign --battles 10

# 任务调度器
python run.py --mode scheduler

# 调试模式
python run.py --debug
```

### 测试和代码质量
```bash
# 运行所有测试
pytest tests/

# 运行单个测试文件
pytest tests/unit/test_adb_service.py

# 代码格式化
black src/ tests/

# 代码检查
flake8 src/
mypy src/
pylint src/
```

## 架构设计

### 核心模块分层

1. **服务层 (src/services/)**
   - `adb_service.py`: ADB设备管理、截图、点击、滑动等操作
   - `config_service.py`: 配置文件管理（YAML格式）
   - `log_service.py`: 日志系统

2. **控制器层 (src/controller/)**
   - `base_controller.py`: 游戏控制器基类，定义通用接口
   - `afk2_controller.py`: AFK2游戏特定控制逻辑
   - `scene_detector.py`: 游戏场景识别

3. **识别层 (src/recognition/)**
   - `image_recognizer.py`: 模板匹配图像识别
   - `ocr_engine.py`: PaddleOCR文字识别引擎

4. **任务系统 (src/tasks/)**
   - `task_manager.py`: 任务管理器，处理任务队列
   - `task_executor.py`: 任务执行器
   - `task_scheduler.py`: 定时任务调度
   - `builtin_tasks.py`: 内置任务（日常、征战、收集奖励）
   - `daily_idle_reward_task.py`: 挂机奖励任务

5. **GUI界面 (src/gui/)**
   - `main_window.py`: 主窗口框架
   - `tabs/`: 各功能页签（ADB配置、任务管理、实时监控、设置）
   - `widgets/`: 自定义组件（日志、状态显示）

### 关键设计模式

- **单例模式**: ConfigService 确保全局配置一致性
- **观察者模式**: 任务状态变更通知
- **策略模式**: 不同OCR引擎切换（PaddleOCR/Tesseract）
- **工厂模式**: 任务创建

### ADB集成

项目内置 Windows ADB 工具（adb/目录），自动处理设备连接：
- USB连接：自动检测并连接
- WiFi连接：支持无线调试
- 设备状态管理：自动重连机制

### 图像识别策略

1. **模板匹配**: OpenCV模板匹配，用于识别固定UI元素
2. **OCR识别**: PaddleOCR识别游戏内文字
3. **场景检测**: 基于多个特征点判断当前游戏场景

模板图像存储在 `src/resources/images/`：
- `idle_mode.png`: 挂机界面
- `collect_reward.png`: 奖励收集按钮
- `current_progress.png`: 当前进度
- `hourglass.png`: 沙漏图标

## 配置管理

配置文件优先级：
1. `config.yaml` (用户配置)
2. `config_default.yaml` (默认配置)

主要配置项：
- **adb**: ADB路径、设备ID、连接参数
- **game**: 包名(com.lilithgame.igame.android.cn)、启动等待时间
- **recognition**: 图像识别阈值、OCR语言
- **ui**: 界面主题、窗口大小

## 任务系统

### 内置任务类型
- **DailyTask**: 日常任务（签到、邮件、任务领取）
- **CampaignTask**: 征战推图
- **CollectRewardTask**: 收集挂机奖励
- **DailyIdleRewardTask**: 定时收集挂机奖励

### 任务状态流转
```
PENDING -> RUNNING -> COMPLETED/FAILED
         -> CANCELLED (用户取消)
         -> SCHEDULED (定时任务)
```

## 开发注意事项

1. **Windows路径处理**: 使用 `pathlib.Path` 处理路径，自动处理反斜杠
2. **ADB命令超时**: 默认30秒，可在配置中调整
3. **图像识别阈值**: 默认0.8，过低可能误识别
4. **游戏包名**: 国服为 `com.lilithgame.igame.android.cn`
5. **错误重试**: 大部分操作支持自动重试（默认3次）

## 图像识别技巧

- 涉及到识别图片的时候需要对图片进行黑白滤镜处理，这样才能保证识别的准确率
- 识别的图片都必须是英文命名，如果不是需要修改为英文

## 测试策略

- **单元测试**: 测试独立模块功能
- **Mock ADB**: 测试使用 Mock 对象模拟 ADB 操作
- **图像识别测试**: 使用预存的截图测试识别准确率

## 依赖版本

核心依赖：
- PyQt6 >= 6.6.0 (GUI框架)
- opencv-python >= 4.9.0 (图像处理)
- paddlepaddle >= 2.5.0 + paddleocr >= 2.7.0 (OCR识别)
- PyYAML >= 6.0.1 (配置文件)
- schedule >= 1.2.0 (任务调度)