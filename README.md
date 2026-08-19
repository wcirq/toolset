# AI桌面工具集

基于 **Python 3.13 / Windows** 的多子项目仓库。每个文件夹是一个独立子项目,自带代码、依赖清单与构建脚本。

## 子项目一览

| 子项目 | 说明 | 入口 |
|---|---|---|
| `cat_pet` | 酷炫小猫悬浮窗:桌面宠物 + 摄像头人体/姿态检测 | `cat_pet/main.py` |

> **新建子项目**:在根目录新建文件夹,放入代码与 `requirements.txt`,并在上表登记一行。各子项目独立安装依赖、独立构建,互不影响。

## 环境准备

以 `cat_pet` 为例,创建独立虚拟环境:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r cat_pet/requirements.txt -i https://pypi.doubanio.com/simple
```

依赖说明:

- **torch / torchvision**:Windows 下 PyPI 默认为 CPU 版;不需要 YOLO 时可删除这三行(`ultralytics` 一并删),程序自动回退 HOG 检测
- **pyinstaller**:仅编译 EXE 时需要

---

## cat_pet — 酷炫小猫悬浮窗

桌面悬浮小猫宠物,带摄像头人体检测。检测到多人时自动切换到指定目标程序(防摸鱼 / 专注提醒场景)。

### 交互方式

| 操作 | 效果 |
|---|---|
| 左键点击猫头 | 聊天框(当前禁用) |
| 左键点击身体 | 摸摸猫(爱心粒子) |
| 左键长按(不拖动) | 显示摄像头预览(人体检测画面) |
| 左键拖拽 | 移动小猫 / 贴边吸附 |
| 双击 | 切换睡觉 / 醒来 |
| 右键 | 菜单:换颜色 / 跟随鼠标 / 设置 / 退出 |
| 滚轮(预览窗口) | 放大 / 缩小视频画面 |
| 全局快捷键 | 快速切换到设置中指定的目标程序 |

### 运行(源码)

```bash
cd cat_pet
python main.py
```

或双击 `run.bat`。

### 配置(`config.json`)

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `model` | `yolo` | 检测模型:`yolo` / `hog` |
| `yolo_model` | `yolo26n-pose.pt` | YOLO 权重文件 |
| `yolo_conf` | `0.4` | 人体检测置信度 |
| `pose_kpt_conf` | `0.85` | 姿态关键点置信度 |
| `dedup_iou` | `0.55` | 多人去重 IOU 阈值 |
| `trigger_count` | `2` | 触发人数阈值 |
| `sustain_sec` | `0.0` | 触发需持续秒数 |
| `target_exe` / `target_title` | `devenv` / `visual studio` | 自动切换的目标程序 |
| `hotkey` | `Ctrl+Alt+V` | 全局快捷键 |
| `camera_index` | `0` | 摄像头编号 |
| `cat_scale` | `0.6` | 小猫缩放比例 |
| `debug_save` | `true` | 是否保存调试截图 |

### 编译 EXE

```bash
cd cat_pet
python build.py
```

流程:`生成图标(cat.ico)` → `PyInstaller 打包(onedir 模式)` → `复制权重与配置`。

产物:`cat_pet/dist/CoolCat/CoolCat.exe`(双击运行;`run.bat` 走的是源码,不影响)。

> 若提示无法删除旧输出目录,说明 `CoolCat.exe` 正在运行,先退出再重跑 `build.py`。

### 制作安装包(Inno Setup)

把 `dist/CoolCat` 目录打成单文件安装程序 `CoolCat_Setup_vX.X.X.exe`(含桌面快捷方式、卸载程序、卸载时自动清理开机启动注册表项)。

**一次性准备:安装 Inno Setup**

```bash
winget install JRSoftware.InnoSetup
```

装到 `%LOCALAPPDATA%\Programs\Inno Setup 6`(用户目录,无需管理员)。脚本 `coolcat_installer.iss` 已在 `cat_pet/` 目录。

**打包命令**

```bash
cd cat_pet
"C:\Users\<用户名>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" coolcat_installer.iss
```

产物:`cat_pet/installer_output/CoolCat_Setup_v1.0.1.exe`(约 205MB)。

**注意事项**

- 先跑 `python build.py` 得到最新 `dist/CoolCat`,再打安装包(安装包只是压缩 `dist` 目录)
- 编译耗时约 5 分钟;**结尾必须出现 `Successful compile` 才算成功**,中途停止的产物是半成品,运行会报 "setup files are corrupted"
- 改版本号:编辑 `coolcat_installer.iss` 第 4 行 `#define MyAppVersion`
- 安装界面为英文;中文语言文件(`ChineseSimplified.isl`)在官方仓库 Unofficial 目录,需手动下载放到 `Inno Setup 6\Languages\`,再把 `[Languages]` 段改回 `chinesesimp`
- 压缩选项在 `[Setup]` 段:`Compression=lzma2/ultra64` + `SolidCompression=yes`,想打快包可改 `lzma2/fast`

### 模型文件

`yolo26n.pt`、`yolo26n-pose.pt` 体积较大,未纳入版本管理。首次运行 ultralytics 会自动下载;也可手动将权重放到 `cat_pet/` 目录。

### 工具 / 测试脚本

| 脚本 | 用途 |
|---|---|
| `make_icon.py` | 用 QPainter 绘制小猫图标 `cat.ico` |
| `rthook_torch.py` | PyInstaller 运行时钩子:打包后先于 PyQt5 加载 torch,修复 c10.dll 报错 |
| `check_exe_main.py` | 检查打包产物 EXE 内是否包含目标模块 |
| `autostart_test.py` | 开机自启动(注册表)功能测试 |
| `settings_ui_test.py` | 设置界面测试 |
| `pose_draw_test.py` | 姿态关键点绘制测试 |
| `snap_test.py` | 截图功能测试 |

### 常见问题

- **c10.dll WinError 1114**:PyQt5 先于 torch 加载导致。源码运行 `main.py` 已在开头预导入 torch;打包时 `build.py` 通过 `--runtime-hook rthook_torch.py` 修复。
- **YOLO 检测失败**:确认 `yolo26n-pose.pt` 存在;缺失时会回退 HOG 检测。
