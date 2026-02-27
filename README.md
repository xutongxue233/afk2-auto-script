# AFK2 自动化助手

基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 的《剑与远征：启程》(AFK Journey) 手游自动化脚本，使用 [MXU](https://github.com/MaaXYZ/MaaXYZ.github.io) 作为 GUI 客户端。

通过 Pipeline JSON 声明式定义任务流程，结合 OCR 文字识别与模板匹配，实现日常任务的自动化执行。

## 功能

| 任务 | 说明 |
|------|------|
| 唤醒游戏 | 启动游戏并等待进入主界面 |
| 收集挂机奖励 | 收集挂机产生的资源奖励 |
| 日常任务 | 一键领取日常任务奖励 |
| 征战推图 | 自动进行征战关卡挑战，可配置战斗次数 |
| 邮件收取 | 一键领取所有邮件附件 |
| 公会签到 | 自动完成公会每日签到 |
| 商店免费抽取 | 领取商店中的免费抽取机会 |

## 系统要求

- Windows 10/11
- Python 3.10+
- Android 设备（已开启 USB 调试）
- ADB 工具（需加入系统 PATH）

## 快速开始

### 1. 下载运行环境

- 从 [MXU Releases](https://github.com/MaaXYZ/MaaXYZ.github.io/releases) 下载 MXU，将 `mxu.exe` 放到项目根目录
- 从 [MaaFramework Releases](https://github.com/MaaXYZ/MaaFramework/releases) 下载运行库，解压到项目根目录的 `maafw/` 目录
- 确保系统 PATH 中包含 ADB 工具路径

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 下载 OCR 模型

从 [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets/tree/main/OCR/ppocr_v4/zh_cn) 下载以下文件到 `resource/model/ocr/` 目录：

- `det.onnx`
- `rec.onnx`
- `keys.txt`

### 4. 启动

运行 `start.bat` 或直接运行 `mxu.exe`，选择 ADB 控制器连接设备，勾选要执行的任务，点击开始。

## 项目结构

```
afk2-auto-script/
├── interface.json              # MXU 项目配置（PI V2）
├── resource/
│   ├── default_pipeline.json   # 全局默认 Pipeline 参数
│   ├── image/                  # 模板图片（720p 规格）
│   ├── model/ocr/              # OCR 模型文件
│   └── pipeline/               # Pipeline JSON 任务定义
│       ├── navigate.json       # 通用导航与返回主界面
│       ├── wake_game.json      # 唤醒游戏
│       ├── idle_reward.json    # 挂机奖励
│       ├── daily_task.json     # 日常任务
│       ├── campaign.json       # 征战推图
│       ├── mail.json           # 邮件收取
│       ├── guild.json          # 公会签到
│       └── shop.json           # 商店免费抽取
├── agent/                      # Python 自定义逻辑
│   ├── main.py                 # AgentServer 入口
│   ├── custom_action.py        # 自定义动作
│   └── custom_reco.py          # 自定义识别器
├── lang/
│   └── zh-cn.json              # 中文国际化
├── start.bat                   # 启动脚本
└── requirements.txt            # Python 依赖
```

## 开发

### Pipeline 编写

任务流程通过 JSON 文件定义在 `resource/pipeline/` 目录下，框架自动加载合并。节点名称全局唯一，可跨文件引用。

```json
{
    "NodeName": {
        "recognition": "OCR",
        "expected": ["目标文字"],
        "action": "Click",
        "target": true,
        "next": ["NextNode"]
    }
}
```

### 坐标系

基于 720p 竖屏分辨率（720x1600），所有 ROI 和坐标均以此为基准。

### 自定义逻辑

复杂逻辑通过 Python AgentServer 实现，代码在 `agent/` 目录下，使用装饰器注册自定义动作和识别器。

## 注意事项

- 设备需开启开发者选项和 USB 调试
- 首次连接需在设备上授权 ADB 调试
- 主要使用 OCR 文字识别，游戏界面文字变化时需更新 Pipeline 中的 expected 字段

## 致谢

本项目基于以下开源项目构建：

- [MaaFramework](https://github.com/MaaXYZ/MaaFramework) - 自动化测试框架，提供 ADB 控制、图像识别、OCR、Pipeline 任务编排等核心能力
- [MXU](https://github.com/MaaXYZ/MaaXYZ.github.io) - 通用 GUI 客户端，读取 interface.json 自动生成操作界面
- [MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights) - MAA 生态的起源项目，为游戏自动化提供了设计思路和架构参考
- [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets) - 提供 OCR 模型等公共资源

## 许可证

MIT License

## 免责声明

本工具仅供学习和研究使用，请勿用于商业用途。使用本工具产生的任何后果由使用者自行承担。
