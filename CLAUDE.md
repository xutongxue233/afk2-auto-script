# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

《剑与远征：启程》(AFK2) 手游自动化脚本，基于 MaaFramework 实现游戏自动化操作。使用 Pipeline JSON 定义任务流程，Python AgentServer 实现自定义逻辑，MXU (Tauri + React) 作为 GUI 界面。

## 技术架构

- **MaaFramework**: 核心自动化框架，提供 ADB 控制、图像识别、OCR、任务编排
- **Pipeline JSON**: 声明式任务流程定义
- **Python AgentServer**: 自定义识别器和动作
- **MXU**: 基于 Tauri + React 的 GUI 客户端，读取 interface.json 自动生成界面

## 目录结构

```
afk2-auto-script/
├── interface.json                  # PI V2 配置文件（MXU 读取）
├── resource/
│   ├── default_pipeline.json       # 全局默认 Pipeline 参数
│   ├── image/                      # 模板图片（720p 规格）
│   ├── model/ocr/                  # OCR 模型文件
│   └── pipeline/                   # Pipeline JSON 任务定义
│       ├── navigate.json           # 通用导航/返回主界面
│       ├── wake_game.json          # 唤醒游戏
│       ├── idle_reward.json        # 挂机奖励
│       ├── daily_task.json         # 日常任务
│       ├── campaign.json           # 征战推图
│       ├── mail.json               # 邮件收取
│       ├── guild.json              # 公会签到
│       └── shop.json               # 商店免费抽取
├── agent/                          # Python 自定义逻辑
│   ├── main.py                     # AgentServer 入口
│   ├── custom_reco.py              # 自定义识别器
│   └── custom_action.py            # 自定义动作
├── lang/
│   └── zh-cn.json                  # 中文国际化
├── mxu.exe                         # MXU GUI 客户端（.gitignore）
├── maafw/                          # MaaFramework 运行库（.gitignore）
├── config/                         # 运行时配置（.gitignore）
├── debug/                          # 调试输出（.gitignore）
└── requirements.txt                # Python 依赖（MaaFw）
```

## 常用命令

### 安装依赖
```bash
pip install -r requirements-maa.txt
```

### 运行
通过 MXU 启动，MXU 读取 assets/interface.json 自动管理任务执行。

## Pipeline JSON 编写规范

### 节点结构
```json
{
    "NodeName": {
        "recognition": "TemplateMatch|OCR|DirectHit|Custom",
        "template": ["image.png"],
        "expected": ["文字"],
        "action": "Click|DoNothing|StartApp|Custom|ClickKey|StopTask",
        "target": true,
        "timeout": 20000,
        "next": ["NextNode1", "NextNode2"],
        "on_error": ["ErrorHandler"],
        "pre_delay": 0,
        "post_delay": 0
    }
}
```

### 识别类型
- **DirectHit**: 无需识别，直接命中
- **TemplateMatch**: 模板匹配（图片），threshold 默认 0.7
- **OCR**: 文字识别，threshold 默认 0.3
- **Custom**: 自定义识别器（Python Agent）

### 动作类型
- **Click**: 点击（target: true 点击识别位置，或固定坐标 [x,y]）
- **DoNothing**: 不执行操作
- **StartApp**: 启动应用（需 package 参数）
- **ClickKey**: 按键（key: 4 = Android 返回键）
- **Custom**: 自定义动作（Python Agent）
- **StopTask**: 停止当前任务

### 坐标系
- 基于 720p 分辨率（短边 720，即竖屏 720x1280）
- ROI 格式: [x, y, w, h]

## 模板图片规范

- 存储位置: `resource/image/`
- 必须基于 720p 截图裁剪
- 必须使用英文命名
- 当前图片从 1080p 按 2/3 比例缩放而来

## Python Agent

### 自定义动作
- `check_campaign_failure`: 征战连续失败计数，达到阈值返回 False 停止任务
- `reset_campaign_failure`: 胜利时重置失败计数

### 自定义识别器
- `detect_exit_dialog`: 检测退出确认弹窗

## 关键配置

- **游戏包名**: `com.lilithgame.igame.android.cn`
- **控制器**: Android ADB，display_short_side: 720
- **默认超时**: 20000ms
- **模板匹配阈值**: 0.7
- **OCR 阈值**: 0.3

## 任务列表

| 任务 | 入口节点 | 说明 |
|------|----------|------|
| WakeGame | StartWakeGame | 启动游戏并等待主界面 |
| IdleReward | StartIdleReward | 收集挂机奖励（默认勾选） |
| DailyTask | StartDailyTask | 一键领取日常任务 |
| Campaign | StartCampaign | 征战推图（可配置战斗次数） |
| CollectMail | StartCollectMail | 一键领取邮件 |
| GuildCheckin | StartGuildCheckin | 公会签到 |
| ShopFreeDraw | StartShopFreeDraw | 商店免费抽取 |

## 开发注意事项

1. Pipeline JSON 文件放在 `resource/pipeline/` 下，框架自动加载合并
2. 节点名称全局唯一，跨文件引用
3. `next` 列表按顺序尝试识别，第一个匹配的执行
4. Custom action 返回 False 触发 `on_error` 处理
5. 图片路径相对于 `resource/image/`
6. 国际化字符串以 `$` 开头，从 lang JSON 中读取

## 依赖

- MaaFw >= 5.7.0
