# FH6 抽奖助手

Forza Horizon 6 抽奖/超级抽奖自动化工具，基于图像识别 + 硬件级键盘模拟实现全自动抽奖流程。

## 功能

- **普通抽奖** & **超级抽奖** — 设置次数后全自动循环执行
- **重复车辆处理** — 自动识别重复车辆弹窗，根据价格阈值决定保留或出售
- **OCR 价格识别** — 读取车辆售价，超出阈值自动保留
- **实时统计** — 累计车辆、入库、出售、收入 CR
- **F8 开始 / F9 紧急停止** — 全局热键，游戏外也能触发
- **设置持久化** — 次数、价格阈值自动记忆
- **日志文件** — 每次运行自动保存到 `logs/` 目录
- **支持 PyInstaller 打包** — 资源自动释放，首次运行从 exe 解压到当前目录

## 环境要求

- Windows 10+
- Python 3.10+
- Conda 环境（推荐）

## 安装

```bash
# 克隆仓库
git clone https://github.com/SaYa-t/FH6-AUTOGacha.git
cd FH6-AUTOGacha

# 安装依赖
pip install opencv-python numpy pyautogui pydirectinput pillow pywin32 easyocr pynput
```

## 使用

```bash
python gacha_app.py
```

1. 确保游戏已运行（`forzahorizon6.exe`）
2. 设置抽奖次数和价格阈值
3. 点击「开始」或按 F8
4. 按 F9 紧急停止

## GUI 布局

```
┌──────────────────────────────────────┐
│  就绪                                │
├──────────┬───────────────────────────┤
│ ▶ 开始   │ 普通抽奖次数    [__]      │
│ ■ 停止   │ 超级抽奖次数    [__]      │
│ ❤ 支持   │ 价格阈值      [______]    │
├──────────┴───────────────────────────┤
│  累计车辆: 0  入库: 0  出售: 0  收入: 0 CR  │
├──────────────────────────────────────┤
│  日志区域                            │
└──────────────────────────────────────┘
```

## 打包为 EXE

双击运行 `build.bat` 即可，或手动执行：

```bash
python -m PyInstaller -n "FH6-Gacha" -F -w gacha_app.py ^
  --add-data "images;images" ^
  --add-data "assets;assets" ^
  --add-data ".easyocr_models;.easyocr_models" ^
  --collect-all easyocr ^
  --hidden-import pynput.keyboard._win32 ^
  --hidden-import pynput.mouse._win32
```

输出: `dist/FH6-Gacha.exe`

首次运行会自动释放 `images/` `assets/` `.easyocr_models/` 到 exe 所在目录。

## 项目结构

```
FH6-AutoGacha/
├── gacha_app.py          # GUI 主程序
├── gacha_core.py         # 抽奖核心逻辑（图像识别/硬件输入/状态机）
├── roi_selector.py       # ROI 区域选择工具
├── images/               # 模板图片（用于图像识别）
│   ├── collectionjournal.png      # 主菜单锚点
│   ├── wheelspin_btn.png          # 普通抽奖按钮
│   ├── super_wheelspin_btn.png    # 超级抽奖按钮
│   ├── duplicate_car.png          # 重复车辆弹窗
│   ├── duplicate_car_price.png    # 价格区域
│   ├── enter_skip_prompt.png      # 跳过提示
│   └── gacha_prompt_area.png      # 领取提示
├── assets/
│   └── qrcode.png        # 赞助二维码
├── .easyocr_models/      # OCR 模型文件（自动下载）
├── logs/                 # 运行日志
└── .gacha_settings.json  # 用户设置（自动生成）
```

## 赞助支持

<img src="微信赞助.png" width="220">

## 致谢

- [FH6Auto](https://github.com/YOUSTHEONE/FH6Auto) — 最初正是因为 FH6Auto 才开启了本项目，大量代码参考其实现。在 FH6Auto 跑图刷钱的基础上，补齐了自动抽奖的功能
- 图像识别基于 OpenCV 模板匹配
- OCR 使用 [EasyOCR](https://github.com/JaidedAI/EasyOCR)

## 免责声明

本工具仅供 Python 自动化技术交流与学习。使用本脚本造成的游戏账号封禁等损失，由使用者自行承担。
