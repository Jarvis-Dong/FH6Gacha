# v1.0.0 — 首发正式版

全自动 FH6 抽奖助手，基于图像识别 + 硬件级键盘模拟，支持普通抽奖、超级抽奖、重复车辆智能处理。

## 功能

- **普通抽奖** & **超级抽奖** — 设置次数后全自动循环执行
- **重复车辆处理** — OCR 识别车辆售价，根据价格阈值自动保留或出售
- **实时统计** — 累计车辆、入库、出售、收入 CR
- **F8 开始 / F9 紧急停止** — pynput 全局热键，游戏外也能触发
- **设置持久化** — 次数、价格阈值自动记忆
- **日志文件** — 每次运行自动保存到 `logs/` 目录
- **打包为 EXE** — 资源自动释放，首运行从 exe 解压到当前目录

## 环境要求

- Windows 10+
- Python 3.10+

## 安装 & 使用

```bash
# 克隆仓库
git clone https://github.com/SaYa-t/FH6-AUTOGacha.git
cd FH6-AUTOGacha

# 安装依赖
pip install opencv-python numpy pyautogui pydirectinput pillow pywin32 easyocr pynput

# 运行
python gacha_app.py
```

或下载附件 `FH6-Gacha.exe` 直接运行。

## 致谢

[FH6Auto](https://github.com/YOUSTHEONE/FH6Auto) — 领路人项目，大量代码参考其实现。在 FH6Auto 跑图刷钱的基础上，补齐了自动抽奖这最后一块拼图，二者配合实现真正的电表倒转。
