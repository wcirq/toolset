# Cat Pet — 酷炫小猫悬浮窗

Windows 桌面悬浮宠物，结合摄像头人体/姿态检测，在检测到多人时自动切换到指定
程序，可用于防摸鱼、隐私提醒和专注场景。

## 主要功能

- HOG/Haar 或 YOLO 人体检测，支持通过姿态模型统计头部关键点。
- 多人持续出现后切换目标程序，支持触发冷却和目标窗口最大化。
- 记录原窗口，可用快捷键或人员离开后的延迟任务自动切回。
- 右键启用或暂停监控；暂停时释放摄像头。
- 可在全屏游戏、会议或演示期间自动暂停监控。
- 摄像头预览、视频画面和检测标注可分别设置透明度。
- 两级形象选择：猫类下保留多种猫形象和配色；人类下提供与六套猫咪主题色对应的原图、卡通和抽象宝宝形象。
- 各类形象均支持动画、缩放和贴边形态。

## 环境准备

项目以 Windows 和 Python 3.13 为目标。建议使用独立虚拟环境：

```powershell
cd cat_pet
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

主要依赖包括 PyQt5、OpenCV、NumPy、RapidOCR 和 ONNX Runtime。YOLO 与本地
OCR 共用 ONNX Runtime，不再依赖 Torch、Torchvision 或 Ultralytics。

## 运行

```powershell
python main.py
```

也可以双击 `run.bat`。如需使用图片或视频模拟摄像头，可配合仓库中的
[Virtual Camera](../virtual_camera/README.md) 项目。

## 交互方式

| 操作 | 效果 |
|---|---|
| 左键点击猫头 | 打开聊天框（当前禁用） |
| 左键点击身体 | 播放摸猫爱心粒子效果 |
| 左键长按且不拖动 | 显示人体检测预览 |
| 左键拖拽 | 移动小猫或贴边吸附 |
| 双击 | 切换睡觉/醒来 |
| 右键 | 打开监控、预览、程序切换、设置和退出菜单 |
| 预览窗口滚轮 | 放大或缩小视频画面 |
| 全局快捷键 | 有记录时切回原窗口，否则切换到目标程序 |
| 监控开关快捷键 | 交替启用/禁用监控；左上角显示不同的渐变闪烁，范围可调并实时预览 |
| 截图快捷键（默认 `Alt+A`） | 框选区域后复制、OCR、翻译或生成无边框置顶贴图 |

贴图可用左键拖动，滚轮缩放，双击关闭；右键可复制图片、恢复原始大小或关闭。
OCR 和翻译默认关闭。OCR 可在“截图与贴图”设置页选择进程内 RapidOCR，或配置兼容 OpenAI
`chat/completions` 图片消息格式的第三方服务。截图仅在用户点击 OCR/翻译后发送；API Key
保存在本机配置文件中，并在程序日志中脱敏。

## 代码结构

`main.py` 只负责调用启动函数，核心代码位于 `coolcat/`：

| 路径 | 职责 |
|---|---|
| `coolcat/entrypoint.py` | QApplication 初始化与程序启动 |
| `coolcat/cat_window.py` | 主窗口、交互与监控协调 |
| `coolcat/runtime.py` | 基础依赖、日志、尺寸和配色常量 |
| `coolcat/config.py` | 默认配置及配置读写 |
| `coolcat/effects.py` | 粒子动画效果 |
| `coolcat/detection/camera.py` | 摄像头采集、人体/姿态检测与调试画面 |
| `coolcat/platform/windows.py` | Windows 窗口枚举、切换与全屏识别 |
| `coolcat/platform/hotkeys.py` | 全局快捷键 |
| `coolcat/platform/autostart.py` | 开机启动管理 |
| `coolcat/ui/` | 聊天层、预览窗口和设置对话框 |
| `config/config.json` | 源码运行配置 |
| `assets/` | 图标及模型文件 |
| `packaging/` | PyInstaller 与 Inno Setup 配置 |
| `tools/` | 开发辅助脚本 |
| `tests/` | 测试脚本 |

`coolcat/common.py` 是旧代码迁移期间的内部聚合层，不包含独立业务逻辑。

## 配置

源码运行读取 `config/config.json`；打包后读取 EXE 同目录的 `config.json`。缺失配置
项时使用程序默认值。

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `model` | `hog` | 检测模型：`yolo` 或 `hog` |
| `yolo_model` | `yolo26n.onnx` | YOLO ONNX 权重文件名 |
| `yolo_conf` | `0.4` | 人体检测置信度 |
| `pose_kpt_conf` | `0.5` | 姿态模型头部关键点置信度 |
| `dedup_iou` | `0.55` | 重复检测框合并阈值 |
| `trigger_count` | `2` | 触发人数阈值 |
| `sustain_sec` | `1.5` | 触发需要持续检出的秒数 |
| `trigger_cooldown_sec` | `10.0` | 自动切换后的冷却时间，`0` 表示关闭 |
| `target_exe` / `target_title` | `devenv` / `visual studio` | 自动切换的目标程序 |
| `maximize_target` | `false` | 是否最大化目标窗口 |
| `hotkey` | `Ctrl+Alt+V` | 全局快捷键 |
| `hotkey_enabled` | `true` | 是否注册全局快捷键 |
| `monitor_hotkey` | `Ctrl+Alt+M` | 启用/禁用监控的全局快捷键 |
| `monitor_hotkey_enabled` | `true` | 是否注册监控开关快捷键 |
| `monitor_effect_size` | `220` | 左上角渐变闪烁范围（像素） |
| `screenshot_hotkey` | `Alt+A` | 区域截图、OCR、翻译和贴图快捷键 |
| `screenshot_hotkey_enabled` | `true` | 是否注册全局截图快捷键 |
| `screenshot_ocr_provider` | `disabled` | OCR 服务：关闭或 `openai_compatible` |
| `screenshot_result_mode` | `image` | `image` 在原图擦除重绘，`popup` 弹出文字窗口 |
| `screenshot_api_endpoint` | 空 | 第三方 `chat/completions` 完整接口地址 |
| `screenshot_api_key` / `screenshot_api_model` | 空 | 第三方 API Key 与支持图片输入的模型 |
| `screenshot_translate_language` | `简体中文` | 截图翻译的目标语言 |

### 本地 RapidOCR（小体积方案）

安装依赖后，在设置 →“截图与贴图”→“OCR 服务”选择
“本地 RapidOCR SMALL（进程内推理）”即可。RapidOCR 3.9 以上的 wheel 已包含默认中英
SMALL ONNX 模型，不需要下载或启动额外 EXE。

本方案直接把截图字节传给 `RapidOCR()`，不启动外部进程、不监听端口，截图不会上传。
RapidOCR 本身不提供翻译；需要截图翻译时，切换为 OpenAI-compatible 图片接口。
| `camera_index` | `0` | OpenCV 摄像头编号 |
| `cat_scale` | `1.0` | 小猫缩放比例，范围 `0.6`～`2.0` |
| `character_category` | `cat` | 一级形象类别：`cat`（猫类）或 `human`（人类） |
| `cat_style` / `cat_color` | `0` / `0` | 当前类别下的具体形象索引及猫类配色索引 |
| `preview_scale` | `1.0` | 预览画面缩放比例 |
| `preview_window_opacity` | `0.85` | 预览窗口背景、边框和信息栏透明度 |
| `preview_video_opacity` | `0.85` | 视频画面透明度 |
| `preview_overlay_opacity` | `1.0` | 检测框、关键点和标签透明度 |
| `debug_save` | `false` | 按天保存触发截图，最多保留三个日期目录 |
| `auto_pause_fullscreen` | `false` | 前台全屏时自动暂停监控 |
| `auto_return_enabled` | `false` | 人员离开后是否自动切回原窗口 |
| `auto_return_delay_sec` | `10` | 人员离开后延迟切回的秒数 |
| `settings_password_hash` | SHA-256 | 设置页密码哈希，不保存明文 |

设置页支持实时预览；“保存并应用”不会关闭设置页。监控默认启用，暂停后会释放
摄像头。调试截图保存在 `debug_shots/YYYYMMDD/`，程序只清理由自身创建的日期目录。

## 模型文件与测试

模型统一放在 `assets/models/`。程序使用随项目提供的 ONNX 文件，不会自动下载；打包时
也会保持相同目录结构。测试脚本位于 `tests/`：

| 脚本 | 用途 |
|---|---|
| `tests/autostart_test.py` | 开机自启动测试 |
| `tests/settings_ui_test.py` | 设置界面测试 |
| `tests/pose_draw_test.py` | 姿态关键点绘制测试 |
| `tests/snap_test.py` | 贴边截图测试 |

## 打包 EXE

```powershell
python packaging/build.py
```

流程为生成图标、PyInstaller `onedir` 打包、复制模型与配置。输出位于
`dist/CoolCat/CoolCat.exe`。若无法删除旧输出目录，请先退出仍在运行的程序。

## 制作安装包

```powershell
winget install JRSoftware.InnoSetup
python packaging/build.py
"C:\Users\<用户名>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" packaging\coolcat_installer.iss
```

安装包输出到 `installer_output/`。只有编译末尾出现 `Successful compile` 才表示成功；
版本号位于 `packaging/coolcat_installer.iss` 的 `MyAppVersion`。

## 常见问题

- **ONNX Runtime DLL 初始化失败**：入口会在 PyQt5 前预加载 ONNX Runtime；YOLO
  与本地 OCR 共用同一套 CPU 推理运行时。
- **YOLO 检测失败**：确认权重位于 `assets/models/`；失败时程序会回退 HOG。
- **找不到摄像头**：检查 `camera_index`，并确认目标摄像头未被其他应用独占。
