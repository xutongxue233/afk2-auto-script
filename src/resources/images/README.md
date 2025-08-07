# 图片资源说明

## 主要UI元素

### 首页相关
- `home_indicator.png` - 首页标志（右下角区域的UI元素）
- `mystery_house.png` - 神秘屋图标（备用首页判断）

### 对话框按钮
- `cancel_button.png` - 取消按钮（X图标）
- `confirm_button.png` - 确认按钮（✓图标）

### 挂机奖励相关
- `idle_mode.png` - 挂机模式界面标志
- `collect_reward.png` - 收集奖励按钮
- `current_progress.png` - 当前进度标志
- `hourglass.png` - 沙漏图标

### 返回按钮
- `back_button_1.png` - 返回按钮样式1
- `back_button_2.png` - 返回按钮样式2

## 图片捕获建议

1. **分辨率**：使用1080x2400或更高分辨率截图
2. **格式**：PNG格式，保持透明度
3. **裁剪**：只保留关键UI元素，去除背景
4. **命名**：使用英文描述性命名

## 图片处理建议

1. **UI元素识别**：
   - 使用轮廓匹配（Canny边缘检测）
   - 对背景变化鲁棒
   - 阈值建议：0.35-0.5

2. **文字识别**：
   - 使用OCR引擎
   - 支持中文识别
   - 可用于检测对话框文字

3. **调试模式**：
   - 启用debug_output保存识别过程图片
   - 查看不同预处理效果
   - 优化模板和阈值