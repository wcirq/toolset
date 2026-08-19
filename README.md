# AI桌面工具集

基于 **Python 3.13 / Windows** 的多子项目仓库。每个文件夹是一个独立子项目,自带代码、依赖清单与构建脚本。

## 子项目一览

| 子项目 | 说明 | 入口 |
|---|---|---|
| `cat_pet` | 酷炫小猫悬浮窗:桌面宠物 + 摄像头人体/姿态检测 | `cat_pet/main.py` |

> 各子项目独立管理源码、依赖和构建配置，互不影响。

## 环境准备

自行创建 Python 3.13 虚拟环境：

```bash
python -m venv venv
venv\Scripts\activate
pip install -r cat_pet/dependencies/requirements.txt -i https://pypi.doubanio.com/simple
```

依赖说明:

- **torch / torchvision**:Windows 下 PyPI 默认为 CPU 版;不需要 YOLO 时可删除这三行(`ultralytics` 一并删),程序自动回退 HOG 检测
- **pyinstaller**:仅编译 EXE 时需要

---

## cat_pet — 酷炫小猫悬浮窗

桌面悬浮小猫宠物,带摄像头人体检测。检测到多人时自动切换到指定目标程序(防摸鱼 / 专注提醒场景)。

主要功能：

- HOG/Haar 或 YOLO 人体检测，支持 pose 头部关键点计数。
- 多人持续出现后切换目标程序，支持触发冷却和目标窗口最大化。
- 切换前记录原窗口，可用快捷键切回，也可在人员离开后延迟自动切回。
- 右键随时启用或暂停监控；暂停时释放摄像头。
- 可选在全屏游戏、会议或演示期间自动暂停监控，退出全屏后恢复。
- 摄像头预览窗口、视频画面、检测标注可分别设置透明度。
- 多种猫品种和配色，贴边形象会跟随当前品种、颜色和屏幕边缘方向。

### 交互方式

| 操作 | 效果 |
|---|---|
| 左键点击猫头 | 聊天框(当前禁用) |
| 左键点击身体 | 摸摸猫(爱心粒子) |
| 左键长按(不拖动) | 显示摄像头预览(人体检测画面) |
| 左键拖拽 | 移动小猫 / 贴边吸附 |
| 双击 | 切换睡觉 / 醒来 |
| 右键 | 互动、启用/暂停监控、预览、切换程序、设置、开机启动、退出 |
| 滚轮(预览窗口) | 放大 / 缩小视频画面 |
| 全局快捷键 | 已记录原窗口时优先切回，否则切换到目标程序 |

### 运行(源码)

```bash
cd cat_pet
python main.py
```

或双击 `run.bat`。

### 代码结构

`cat_pet/main.py` 只负责调用启动函数，核心代码按职责放在 `cat_pet/coolcat/`：

| 路径 | 职责 |
|---|---|
| `entrypoint.py` | QApplication 初始化与程序启动 |
| `cat_window.py` | 桌面小猫主窗口、交互与监控协调 |
| `runtime.py` | 基础依赖、日志、尺寸和配色常量 |
| `config.py` | 默认配置、配置读取与保存 |
| `effects.py` | 粒子动画效果 |
| `detection/camera.py` | 摄像头采集、人体/姿态检测与调试图 |
| `platform/windows.py` | Windows 窗口枚举、切换与全屏识别 |
| `platform/hotkeys.py` | 全局快捷键 |
| `platform/autostart.py` | 开机启动管理 |
| `ui/chat.py` | 聊天悬浮层 |
| `ui/preview.py` | 摄像头预览窗口 |
| `ui/dialogs.py` | 身份验证、消息框和设置页面 |

`common.py` 仅是旧代码迁移期间的内部聚合层，不包含业务实现。

项目辅助文件也已分类：`assets/` 存放图标和模型，`config/` 存放源码配置，
`dependencies/` 存放依赖清单，`packaging/` 存放 EXE/安装包配置，
`tools/` 存放开发工具，`tests/` 存放测试脚本。

### 配置

源码运行读取 `cat_pet/config/config.json`；打包后的程序读取 EXE 同目录的 `config.json`。缺少配置项时会使用下表中的程序默认值：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `model` | `hog` | 检测模型：`yolo` / `hog` |
| `yolo_model` | `yolo26n.pt` | YOLO 权重文件名 |
| `yolo_conf` | `0.4` | 人体检测置信度 |
| `pose_kpt_conf` | `0.5` | pose 模型头部关键点置信度 |
| `dedup_iou` | `0.55` | 重复检测框合并阈值 |
| `trigger_count` | `2` | 触发人数阈值 |
| `sustain_sec` | `1.5` | 触发需要持续检出的秒数 |
| `trigger_cooldown_sec` | `10.0` | 自动切换后的冷却秒数，`0` 表示关闭冷却 |
| `target_exe` / `target_title` | `devenv` / `visual studio` | 自动切换的目标程序 |
| `maximize_target` | `false` | 切换时是否最大化目标程序 |
| `hotkey` | `Ctrl+Alt+V` | 全局快捷键 |
| `hotkey_enabled` | `true` | 是否注册全局快捷键 |
| `camera_index` | `0` | 摄像头编号 |
| `cat_scale` | `1.0` | 小猫缩放比例，范围 `0.6`～`2.0` |
| `cat_style` / `cat_color` | `0` / `0` | 小猫品种与配色索引，可独立组合 |
| `preview_scale` | `1.0` | 预览窗口缩放，滚轮调整后自动记忆 |
| `preview_window_opacity` | `0.85` | 预览窗口背景、边框和信息栏透明度 |
| `preview_video_opacity` | `0.85` | 摄像头画面透明度 |
| `preview_overlay_opacity` | `1.0` | 人体框、关键点和标签透明度 |
| `debug_save` | `false` | 按天保存触发截图，最多保留三个日期目录 |
| `auto_pause_fullscreen` | `false` | 前台窗口全屏时自动暂停监控 |
| `auto_return_enabled` | `false` | 人员离开后是否自动切回原窗口 |
| `auto_return_delay_sec` | `10` | 人员离开后延迟切回的秒数 |
| `settings_password_hash` | SHA-256 | 设置页面密码哈希，不保存明文 |

设置页中的小猫品种、配色、尺寸和预览窗口三层透明度支持实时预览。
"保存并应用"不会关闭设置页; 退出时如有未保存修改, 程序会询问是否保存。
小猫贴边后会按当前品种和配色绘制抽象化探头形象; 上/下边缘只露窗口高度的 1/4, 左/右边缘只露窗口宽度的 1/4, 并自动调整朝向。

监控每次启动默认启用。右键暂停会停止检测线程并释放摄像头；再次启用时重新打开摄像头。全屏自动暂停开关默认关闭。

调试截图默认关闭。开启后保存在 `debug_shots/YYYYMMDD/`，程序只清理由自身创建的日期目录并保留最近三个。

### 编译 EXE

```bash
cd cat_pet
python packaging/build.py
```

流程:`生成图标(assets/cat.ico)` → `PyInstaller 打包(onedir 模式)` → `复制权重与配置`。

产物:`cat_pet/dist/CoolCat/CoolCat.exe`(双击运行;`run.bat` 走的是源码,不影响)。

> 若提示无法删除旧输出目录，说明 `CoolCat.exe` 正在运行；先退出程序，再重新运行 `python packaging/build.py`。

### 制作安装包(Inno Setup)

把 `dist/CoolCat` 目录打成单文件安装程序 `CoolCat_Setup_vX.X.X.exe`(含桌面快捷方式、卸载程序、卸载时自动清理开机启动注册表项)。

**一次性准备:安装 Inno Setup**

```bash
winget install JRSoftware.InnoSetup
```

装到 `%LOCALAPPDATA%\Programs\Inno Setup 6`(用户目录,无需管理员)。脚本位于 `cat_pet/packaging/`。

**打包命令**

```bash
cd cat_pet
"C:\Users\<用户名>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" packaging\coolcat_installer.iss
```

产物:`cat_pet/installer_output/CoolCat_Setup_v1.0.exe`。

**注意事项**

- 先跑 `python packaging/build.py` 得到最新 `dist/CoolCat`,再打安装包(安装包只是压缩 `dist` 目录)
- 编译耗时约 5 分钟;**结尾必须出现 `Successful compile` 才算成功**,中途停止的产物是半成品,运行会报 "setup files are corrupted"
- 改版本号:编辑 `packaging/coolcat_installer.iss` 中的 `#define MyAppVersion`
- 压缩选项在 `[Setup]` 段:`Compression=lzma2/ultra64` + `SolidCompression=yes`,想打快包可改 `lzma2/fast`

### 模型文件

模型文件统一放在 `cat_pet/assets/models/`。程序会优先从这里加载；缺失时也会由 ultralytics 下载到这个目录。打包时保持相同的 `assets/models/` 结构复制到 EXE 输出目录。

### 工具 / 测试脚本

| 脚本 | 用途 |
|---|---|
| `tools/make_icon.py` | 用 QPainter 生成 `assets/cat.ico` |
| `packaging/rthook_torch.py` | PyInstaller 的 torch 运行时钩子 |
| `tools/check_exe_main.py` | 检查打包产物 EXE 内是否包含目标模块 |
| `tests/autostart_test.py` | 开机自启动功能测试 |
| `tests/settings_ui_test.py` | 设置界面测试 |
| `tests/pose_draw_test.py` | 姿态关键点绘制测试 |
| `tests/snap_test.py` | 贴边截图测试 |

### 常见问题

- **c10.dll WinError 1114**:PyQt5 先于 torch 加载导致。源码会预导入 torch；打包时由 `packaging/rthook_torch.py` 修复。
- **YOLO 检测失败**:确认对应权重存在于 `assets/models/`；缺失时会回退 HOG 检测。
