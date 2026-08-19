# 虚拟相机模拟器

把一张图片或一个视频持续输出为 Windows 中可被会议软件、浏览器和 OpenCV
识别的摄像头画面。

## 推荐方案

本项目采用两层结构：

1. **设备层**：安装 OBS Studio，并启用其 Virtual Camera 驱动。它负责向 Windows
   注册真正的摄像头设备。
2. **媒体层**：本目录中的 Python 程序读取图片或视频，统一尺寸和帧率，再通过
   `pyvirtualcam` 把帧送入虚拟摄像头。

这种方式开发和调试成本最低，适合先验证 `cat_pet` 等应用能否把媒体文件当作摄像头。
它不是内核驱动，发布时需要用户预先安装一个受支持的虚拟摄像头后端。

## 环境准备

- Windows 10/11、Python 3.10+
- 安装 [OBS Studio](https://obsproject.com/)，使用标准安装程序并保留 Virtual Camera 组件
- 安装本目录依赖：

```powershell
cd virtual_camera
python -m pip install -r requirements.txt
```

> 仅安装 OBS 即可，不需要打开 OBS。`pyvirtualcam` 会直接使用 OBS Virtual Camera
> 后端。若系统中存在多个后端，可用 `--backend obs` 明确选择。

可使用 Windows 包管理器安装：

```powershell
winget install -e --id OBSProject.OBSStudio
```

正常安装目录通常为 `C:\Program Files\obs-studio`。不要安装旧版独立插件
`obs-virtualcam-3.1.3`；当前 `pyvirtualcam` 使用的是新版 OBS 内置虚拟摄像头。
安装后如果仍无法发现设备，请重新打开终端或重启 Windows。

## 使用方法

图片会保持输出，直到按 `Ctrl+C`：

```powershell
python main.py image.jpg
```

视频默认循环播放，并沿用源视频帧率：

```powershell
python main.py demo.mp4
```

常用参数：

```powershell
python main.py demo.mp4 --width 1280 --height 720 --fps 30 --mirror
python main.py demo.mp4 --no-loop --backend obs
python main.py --list-backends
```

启动成功后，在目标软件的摄像头列表中选择 **OBS Virtual Camera**。例如在本仓库
的 [Cat Pet](../cat_pet/README.md) 配置中设置对应的 `camera_index`，即可用模拟画面
测试检测逻辑。

## 目录结构

```text
virtual_camera/
├── main.py             # 命令行入口
├── virtual_camera.py   # 媒体读取、画面适配和虚拟相机输出
├── requirements.txt
├── run.bat
└── README.md
```

## 其他可选方案

| 方案 | 优点 | 局限 | 适用阶段 |
|---|---|---|---|
| OBS Virtual Camera + Python | 快速、稳定、应用兼容性较好 | 依赖 OBS 驱动 | 当前推荐/MVP |
| Unity Capture + Python | 后端轻量 | 项目维护和兼容性需自行评估 | 内部分发 |
| Windows Media Foundation Virtual Camera | 可做独立安装包和自有设备名 | 需要 C++、COM 媒体源、安装注册和签名；主要面向较新的 Windows 11 | 产品化 |
| DirectShow Source Filter | 旧系统资料多 | 部分 UWP/现代会议软件无法枚举 | 仅兼容遗留软件 |
| Linux v4l2loopback | 原生、成熟 | 仅 Linux，不适用于当前仓库 | Linux 版本 |

如果后续要做成无需 OBS 的正式产品，建议新增 C++ 子项目，基于 Windows Media
Foundation 的虚拟相机 API 实现设备层；当前 Python 的媒体解码和尺寸策略可以作为
行为原型，但设备生命周期、权限、安装器和代码签名需单独设计。

## 已知限制

- 一次通常只能由一个进程向同一个虚拟相机后端发送画面。
- 带旋转元数据的视频，OpenCV 是否自动旋转取决于其构建版本。
- 音频不会作为摄像头的一部分输出。
- 目标应用已打开时，可能需要重新进入摄像头设置才能看到新设备。
