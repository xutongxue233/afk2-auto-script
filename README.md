# 剑与远征启程自动化脚本

一个用于《剑与远征：启程》手游的自动化脚本工具，通过ADB与Android设备通信，实现游戏自动化操作。

## 功能特性

- 🎮 **游戏自动化**：自动唤醒游戏、执行日常任务
- 📱 **设备管理**：支持USB和无线ADB连接
- 🖼️ **智能识别**：图像识别和OCR文字识别
- 🎨 **图形界面**：基于PyQt6的友好用户界面
- 📝 **日志系统**：完整的操作日志记录
- ⚙️ **配置管理**：支持配置保存和加载

## 系统要求

- Windows 10/11
- Python 3.8+
- Android 7.0+
- ADB工具

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/afk2-auto-script.git
cd afk2-auto-script
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置ADB

确保ADB已安装并添加到系统PATH中，或在应用中指定ADB路径。

### 4. 启动应用

```bash
python run.py
```

## 项目结构

```
afk2-auto-script/
├── src/                    # 源代码
│   ├── services/          # 服务层
│   ├── controllers/       # 控制器
│   ├── recognition/       # 识别模块
│   ├── gui/              # 图形界面
│   ├── models/           # 数据模型
│   └── utils/            # 工具类
├── tests/                 # 测试代码
├── docs/                  # 文档
├── requirements.txt       # 项目依赖
└── run.py                # 启动脚本
```

## 使用说明

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

# 定时任务调度
python run.py --mode scheduler

# 调试模式
python run.py --debug
```

### GUI界面操作

1. **ADB配置页**
   - 扫描和连接Android设备
   - 支持USB和WiFi连接
   - 执行ADB命令

2. **任务管理页**
   - 快速执行日常任务、征战、收集奖励
   - 创建定时任务和循环任务
   - 查看任务执行状态

3. **实时监控页**
   - 实时显示设备屏幕
   - 场景自动识别
   - OCR文字识别

4. **设置页**
   - 配置ADB、游戏、识别参数
   - 导入/导出配置
   - 恢复默认设置

## 开发

### 安装开发依赖

```bash
pip install -r requirements-dev.txt
```

### 运行测试

```bash
pytest tests/
```

### 代码格式化

```bash
black src/ tests/
```

## 注意事项

- 请确保设备已开启开发者选项和USB调试
- 首次连接需要在设备上授权
- 游戏更新可能导致图像识别失效，需要更新模板图像

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

## 免责声明

本工具仅供学习和研究使用，请勿用于商业用途。使用本工具产生的任何后果由使用者自行承担。