# Repository Guidelines

## 项目结构与模块
- `src/` 核心代码：`controller/` 设备与场景控制，`services/` 配置/日志/ADB 接口，`tasks/` 调度与具体任务，`recognition/` OCR 与模板匹配，`gui/` PyQt6 界面（tabs、widgets、main_window），`models/` 数据对象，`utils/` 单例、重试、异常。
- `src/resources/images/` 模板图；更新或新增时保持同名 PNG，便于识别匹配。
- `tests/unit/` Pytest 单测，覆盖主要服务、任务和识别模块。
- `config_default.yaml` 默认配置，`config.yaml` 用户覆写；`logs/` 运行日志；`templates/` 示例资源；`adb/` 内置 Windows ADB 工具。

## 构建、运行与开发命令
- 安装基础依赖：`pip install -r requirements.txt`
- 安装开发工具：`pip install -r requirements-dev.txt`
- 启动 GUI：`python run.py`
- 常用模式：`python run.py --mode daily|campaign|scheduler|test --debug`
- 单元测试：`pytest tests/unit -q`
- 覆盖率检查：`pytest --cov=src --cov-report=term-missing`
- 代码格式化/检查：`black src tests`；`flake8 src tests`；`mypy src`（按需补充类型）

## 编码风格与命名
- Python 3.8+；4 空格缩进；UTF-8。
- 使用 `black` 默认行宽（88）格式化；提交前保证 `flake8` 无警告。
- 命名：模块/函数/变量用 `snake_case`，类用 `PascalCase`，常量全大写。
- 日志通过 `services.log_service` 输出，避免裸 `print`；路径与 ADB 配置放入 `config.yaml`，勿写死。

## 测试准则
- 单测文件命名 `test_*.py`，用 `pytest` 断言；针对新任务/服务提供至少 1 个成功用例。
- 涉及 GUI 或 ADB 交互可用 `pytest-qt`、`pytest-mock` 做替身，确保无真实设备也能跑通。
- 覆盖率建议 ≥80%，关键分支（错误处理、重试）需断言。

## 提交与 PR
- 提交信息保持中文祈使或简短摘要，例如“修复设备断开重试”或“feat: 支持日常任务调度”；必要时附 Issue 编号。
- PR 描述应包含：变更点、测试结果（命令输出摘要）、是否影响 GUI（附截图），以及配置/文档更新说明。
- 新增模板图或配置示例需注明来源与适用版本；避免提交个人设备日志、临时密钥或 `.venv/` 内容。
