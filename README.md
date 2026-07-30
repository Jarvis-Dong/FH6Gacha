# FH6Gacha

Forza Horizon 6 Steam 版后台抽奖工具。它既可以单独运行普通/超级抽奖，也可以在不修改官方 `FH6Auto.exe` 的情况下，跟随 FH6Auto 的刷图大循环自动开奖。

> 仅供 Python 自动化技术交流与学习使用。使用自动化工具的账号风险由使用者自行承担。

## 功能

- 普通抽奖、超级抽奖，可分别指定次数或抽到耗尽。
- 重复车三种策略：按价格判断、全部出售、全部保留。
- EasyOCR 识别重复车价格；按价格模式下 OCR 失败会保留车辆，绝不隐式误卖。
- 重复车关键按键使用同步后台消息，并在弹窗确认消失后才累计保留、出售和收入。
- 累计普通/超级次数、重复车、保留、出售、收入、OCR 失败和联动轮次。
- `PrintWindow` 后台截图与 `PostMessage` 后台键鼠，不移动物理鼠标、不抢游戏前台。
- 阶段绝对超时、连续未知画面推进上限、F8 紧急停止、主菜单归位验证。
- 可选 FH6Auto 联动；官方 EXE 不拆包、不重打包、不写进程内存、不注入 DLL，也不注入游戏进程。

## 两种模式

### 独立抽奖

1. 启动 FH6，并保持窗口模式或无边框窗口模式，不要最小化。
2. 打开 `FH6Gacha.exe`。
3. 设置普通/超级次数、重复车策略和价格阈值。
4. 选择“独立抽奖”，点击开始。

普通和超级次数都可设为 `0` 跳过。勾选“抽到耗尽”时内部最多尝试 999 次，并在检测到抽奖菜单已无次数后提前退出。

### 跟随 FH6Auto

联动流程：

```text
FH6Auto 跑图 -> 买车 -> 点技能 -> 卖车
                                  |
                          F9 暂停握手确认
                                  |
                    FH6Gacha 普通/超级抽奖
                                  |
                    确认回到主菜单 -> F9 恢复
                                  |
                           FH6Auto 下一轮
```

使用步骤：

1. 关闭正在运行的 `FH6Auto.exe`。
2. 在 FH6Auto 中把第 4 阶段设为“继续”，下一步设为 `1`；其余阶段保持 `1 -> 2 -> 3 -> 4 -> 1`。
3. 在 FH6Gacha 中选择“跟随 FH6Auto 自动循环”，选择同时包含 `FH6Auto.exe` 和 `config.json` 的目录。
4. 点击开始。FH6Gacha 会临时开启 FH6Auto 诊断日志，并启动原版 `FH6Auto.exe`。
5. 在原版 FH6Auto 界面正常点击“循环跑图”的开始按钮。

联动器只在日志中看到稳定循环边界后发送 F9，并且必须继续看到“任务已暂停”才会开始开奖。FH6Auto 的输入层会在每次按键和点击前执行 `check_pause()`；收到暂停日志后，桥接器还会留出短暂缓冲，让官方程序完成残余按键释放。开奖完成并确认回到主菜单后发送 F9，并要求看到“任务已恢复”。

暂停确认、开奖或恢复任一环节失败，联动器都会立即向 FH6Auto 发送 F8，要求官方任务安全停止，不会让它直接进入下一轮。GUI 的“紧急停止”在联动模式下也会停止两边。

联动全部结束后请关闭 FH6Auto 窗口，FH6Gacha 随后会恢复临时修改的诊断、关机和关闭游戏配置；异常退出时保留的备份会在下次启动自动恢复。

最后一轮在 FH6Auto 输出“达到设定的总循环次数”后，继续等待该诊断会话的完整 `report.txt` 落盘及资源清理缓冲，再执行开奖，不会依赖只显示在 UI、没有写入诊断文件的停止日志。

## 官方 EXE 更新

`FH6Auto.exe` 始终是官方原文件，更新时直接覆盖即可：

```text
下载新版 FH6Auto.exe -> 覆盖旧文件 -> 继续运行 FH6Gacha.exe
```

联动依赖以下公开诊断日志短语：

- `开启新一轮大循环`
- `达到设定的总循环次数`
- `任务已暂停`
- `任务已恢复`

最终轮另外以当前 `diagnostic_reports/<session>/report.txt` 完整落盘作为官方任务已经退出业务循环的证据。

新版如果修改这些协议，联动器不会猜测游戏状态，也不会开始开奖；独立抽奖仍可使用。确认新版本兼容后再更新桥接协议即可。

联动期间会临时设置：

- `diagnostic_mode=true`
- `debug_screenshots=true`
- `auto_close_game=false`
- `auto_shutdown=false`

联动退出时仅在这些值仍是桥接器设置值的情况下恢复原值，不会覆盖你同时修改的其他配置。

## 重复车策略

| 策略 | OCR | 行为 |
|---|---|---|
| 按价格判断 | 使用 | 高于阈值保留，否则出售；OCR 失败保留 |
| 全部出售 | 使用 | 所有重复车直接出售；OCR 仅用于收入统计，失败仍出售 |
| 全部保留 | 不使用 | 所有重复车进入车库 |

EasyOCR 模型保存在 EXE 同目录的 `.easyocr_models/`。如果构建包没有内置模型，第一次需要价格的重复车会在安全时限内等待模型联网下载和初始化；下载失败会记录日志。按价格策略会保留车辆，“全部出售”仍会出售但该车收入无法计入统计。

## 快捷键

- 空闲时 `F8`：开始当前模式。
- 运行时 `F8` 或点击“紧急停止”：联动模式下原版 FH6Auto 也会收到 F8。
- 独立模式运行时 `F9`：停止抽奖。
- 联动模式的 `F9` 由暂停/恢复握手专用，请不要手工按 F9。

## 源码运行

环境：Windows 10/11、Python 3.10+、FH6 简体中文、Steam 版。

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python gacha_app.py
```

## 打包

```bat
build.bat
```

构建脚本会先核验依赖、预下载 EasyOCR 模型、运行完整测试，再生成 `dist\FH6Gacha.exe`，最后用 `--smoke-test` 启动打包产物并确认它能正常初始化和退出。模型下载成功时会直接打进 EXE；构建阶段下载失败时仍可生成程序，并在首次按价格抽奖时重试下载。GitHub Actions 构建要求模型准备与打包后冒烟测试都成功后才会上传产物。

日常可运行 `start.bat`，它按顺序寻找根目录 EXE、`dist` 产物或本地虚拟环境。

仓库还提供 `.github/workflows/build.yml`。在 GitHub Actions 手动运行 `Build Windows EXE`，或推送 `v*` tag，可下载 `FH6Gacha-windows` 构建产物。

## 自动化检查

```bat
python -m unittest discover -s tests -v
python -m py_compile gacha_app.py gacha_backend.py gacha_bridge.py gacha_core.py gacha_policy.py
```

测试覆盖：重复车安全策略与动作确认、FH6Auto 日志协议、旧日志不重放、新日志跟随、配置临时修改/恢复、中间轮暂停/恢复/失败停止，以及最终轮报告握手。

## Windows 实机验收清单

发布前必须在真实 FH6 Steam 环境逐项验证：

- [ ] 1080p 窗口/无边框下，游戏在后台时能识别普通和超级抽奖入口。
- [ ] 普通抽奖 1 次、超级抽奖 1 次均可领取并回到主菜单。
- [ ] “全部出售”和“全部保留”各验证一辆重复车。
- [ ] 按价格模式分别验证低于、高于阈值，以及 OCR 模型不可用时保留。
- [ ] 无抽奖次数时能提前结束，不进入未知画面死循环。
- [ ] 独立模式运行中 F8/F9 均能释放输入并停止。
- [ ] FH6Auto 两轮流程能在第一轮卖车后暂停、开奖、恢复跑图。
- [ ] FH6Auto 单轮流程停止后仍执行最终开奖。
- [ ] 联动开奖识别失败时会以 F8 停止 FH6Auto，不会继续跑图。
- [ ] 更新后的官方 EXE 替换后，兼容时正常握手；不兼容时不接管。
- [ ] 长时间运行后检查 `.easyocr_models/`、`logs/` 和诊断截图磁盘占用。

当前仓库可在非 Windows 主机完成语法和纯逻辑测试，但 `PrintWindow`、`PostMessage`、全局热键、PyInstaller Windows 产物以及 FH6 菜单模板只能通过上述 Windows 实机清单证明。

## 项目结构

```text
gacha_app.py       GUI、独立模式和联动模式入口
gacha_core.py      普通/超级抽奖状态机、重复车与 OCR
gacha_backend.py   Steam FH6 窗口发现、PrintWindow、PostMessage
gacha_bridge.py    FH6Auto 日志、配置保护、暂停/恢复握手
gacha_policy.py    可测试的重复车安全决策
images/            FH6 菜单模板
tests/             纯逻辑回归测试
```

## 致谢

- [deYangar/FH6_Auto](https://github.com/deYangar/FH6_Auto)：后台截图、后台输入和四阶段自动化的设计参考。
- [SaYa-t/FH6-AUTOGacha](https://github.com/SaYa-t/FH6-AUTOGacha)：原始普通/超级抽奖状态机和模板。
