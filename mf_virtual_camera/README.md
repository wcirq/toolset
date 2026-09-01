# SSKJ Media Foundation Virtual Camera

这是一个面向 Windows 11 x64 的原生虚拟摄像头。它把图片或视频转换成摄像头画面，
并以 `SSKJ (Windows Virtual Camera)` 的名称提供给微信、Chrome、Edge、会议软件及
其他支持 Windows 摄像头的应用。

项目直接使用 Windows Media Foundation 虚拟相机 API，不依赖 OBS Studio、
OBS Virtual Camera 或 `pyvirtualcam`。

> 当前状态：设备注册、多种输入、跨会话传帧、多分辨率协商、发送端离线检测、
> Media Foundation 系统枚举和真实取帧均已验证；另提供企业微信可用的 x86
> DirectShow 兼容层。

## 功能与限制

- 输入：图片、视频文件、物理摄像头、OpenCV 可打开的网络流和程序生成测试画面。
- 输出设备：`SSKJ (Windows Virtual Camera)`。
- 企业微信兼容设备：`SSKJ DirectShow Camera`（x86 DirectShow）。
- Media Foundation 输出：`NV12`，支持 `1920×1080`、`1280×720`、`640×480`，30 FPS。
- DirectShow 输出：`YUY2`，支持上述三种分辨率，30 FPS。
- 播放：默认循环，支持水平镜像和指定输入发送节奏。
- 安装范围：虚拟相机的生命周期是系统级，访问范围是当前 Windows 用户。
- 平台：Windows 11 Build 22000 及以上；MF 构建 x64，DirectShow 兼容层构建 x86。
- 支持注册多个自定义名称的 MF 设备；当前所有实例共享同一路输入画面。
- 暂不支持音频、每实例独立画面、GPU 转换和任意尺寸协商。

## 工作原理

项目把“媒体解码”和“Windows 摄像头设备”分成两个独立进程：

```text
图片 / 视频 / 物理摄像头 / 网络流 / 测试图案
       │
       ▼
Python 发送端 + OpenCV
解码 → 等比缩放和黑边 → 可选镜像 → BGR 转 NV12
       │
       ▼
C:\ProgramData\SSKJVirtualCamera\frames.v1.bin
跨会话内存映射文件，包含协议头和两个帧槽
       │
       ▼
C++ MediaSource COM DLL
       │  IMFSample
       ▼
Windows Camera Frame Server
       │
       ├── 微信 / 会议软件
       ├── Chrome / Edge
       ├── Windows Camera
       └── OpenCV / 其他 Media Foundation 客户端
```

### 1. Python 发送端

发送端用 OpenCV 读取图片或逐帧解码视频，将画面等比缩放到 1280×720；剩余区域
用黑色补齐，而不是拉伸图像。随后把 OpenCV 的 BGR 数据转换为 Windows 视频管线
常用的 NV12 格式，并持续发布到共享帧文件。

图片默认以 30 FPS 重复发送；视频默认使用文件报告的帧率，无法读取帧率时回退到
30 FPS。`--fps` 只改变发送端读取和发布帧的节奏，不会改变虚拟摄像头对外声明的
固定 30 FPS 媒体类型。

### 2. 跨进程帧协议

MediaSource DLL 运行在 Windows Camera Frame Server 中，不在 Python 进程中，
所以双方不能共享 Python 或 NumPy 指针。项目使用以下固定大小文件作为内存映射：

```text
C:\ProgramData\SSKJVirtualCamera\frames.v1.bin
```

文件包含一个 128 字节协议头和两个 NV12 帧槽。写入端先完整写入非活动帧槽，更新
时间戳，最后发布递增序号；读取端在复制前后各检查一次序号，如果序号变化就放弃
该副本并重试。这个双缓冲设计可以避免使用全局锁，也不会让摄像头读到“写了一半”
的画面。

选择 ProgramData 文件而不是普通的 `Local\` 共享内存，是因为桌面 Python 进程和
可能运行在 Session 0 的 Frame Server 需要访问同一份数据。安装脚本会为 Users、
Local Service、SYSTEM 和 Administrators 配置所需 ACL。

协议细节见 [IPC 帧协议](docs/ipc-protocol.md)。

### 3. 原生 MediaSource

C++ DLL 实现 Media Foundation 所需的媒体源和媒体流接口，包括 `IMFMediaSource2`、
`IMFMediaStream2` 与 `IMFSampleAllocatorControl`。应用打开摄像头后，Frame Server
加载该 COM DLL，协商媒体类型，并不断向媒体流请求样本。

每次请求到来时，MediaSource 读取最新完整 NV12 帧，按消费者选择的分辨率缩放，
再写入 Frame Server 提供的 `IMFSample` 缓冲区，设置时间戳和持续时间并通过事件队列
交回系统。应用看到的是标准 Windows 摄像头流，不需要了解 Python 或共享文件。

IPC 仍固定为 1280×720，以保持协议 ABI 和发送端简单稳定；1920×1080 或 640×480
由原生读取端输出时转换。发送端超过 2 秒没有发布新序号时，MF 和 DirectShow 均会
显示灰色叉号离线画面，避免把最后一帧长期伪装成实时视频。

### 4. 设备注册和升级

Registrar 调用 Windows 11 的 `MFCreateVirtualCamera` 创建软件摄像头，并使用：

- `MFVirtualCameraType_SoftwareCameraSource`
- `MFVirtualCameraLifetime_System`
- `MFVirtualCameraAccess_CurrentUser`
- 视频摄像头和采集设备类别

Frame Server 会长期加载 DLL，直接覆盖同名文件可能得到“访问被拒绝”。安装器因此按
DLL 内容的 SHA-256 前 12 位部署，例如：

```text
C:\ProgramData\SSKJVirtualCamera\bin\SSKJVirtualCameraMediaSource-a44d72e1b404.dll
```

代码变化会产生新文件名，安装器注册新版本后刷新 Frame Server，并可清理旧版本。

更多设计说明见 [架构文档](docs/architecture.md)。

## 目录结构

```text
mf_virtual_camera/
├── CMakeLists.txt                 # C++ 总构建入口
├── CMakePresets.json              # Windows x64 构建与测试预设
├── native/
│   ├── common/                    # 公共 GUID、COM 辅助代码
│   ├── protocol/                  # C++ IPC 协议定义
│   ├── media_source/              # Media Foundation COM DLL
│   ├── directshow_source/         # x86/x64 DirectShow Source Filter
│   └── registrar/                 # 创建、启动、停止、移除设备
├── python/
│   ├── mf_virtual_camera/         # 图片/视频发送端
│   └── tests/                     # Python 测试
├── scripts/                       # 构建、安装、验证、卸载脚本
├── tests/native/                  # C++ 协议和 MediaSource 测试
├── tools/frame_probe/             # 独立系统取帧工具
└── docs/                          # 架构与 IPC 文档
```

## 环境要求

- Windows 11 x64，Build 22000 或更高。
- Visual Studio，包含“使用 C++ 的桌面开发”、MSVC x64 和 Windows SDK。
- CMake；当前脚本默认使用 Visual Studio 2026 自带的 CMake。
- Python 3.10 或更高。
- 管理员 PowerShell：安装、刷新 Frame Server 和卸载时需要。

如果使用不同的 Visual Studio 安装版本或路径，需要相应调整
[`scripts/build.ps1`](scripts/build.ps1) 中的 CMake 与 `vcvars64.bat` 路径。

## 快速开始

以下命令都从本项目根目录执行：

```powershell
cd D:\projects\temp\mf_virtual_camera
```

### 桌面软件与中文安装包

桌面版使用 PyQt5（Qt 5.15）实现统一深色界面，集成相机安装/卸载、自定义名称实例、
设备列表、图片/视频/摄像头/网络流/测试画面输入、循环、镜像、帧率、实时预览和
Python 帧处理插件。插件验证成功后可用于下一次发送，验证或运行失败会显示 traceback。

构建环境固定为 Conda 环境 `mf_virtual_camera`，安装包使用本机 Inno Setup 6 编译：

```powershell
conda activate mf_virtual_camera
.\scripts\build-desktop.ps1 -SkipNative
```

去掉 `-SkipNative` 会先重新构建 x64 Media Foundation 和 x86 DirectShow 原生组件。
输出文件：

```text
dist\installer\SSKJ-Camera-Studio-Setup-0.2.4.exe
```

安装软件不会自动注册虚拟摄像头；打开软件后在“虚拟相机”页点击安装，Windows 会
显示 UAC 确认。桌面程序架构和插件约定见 [桌面版架构](docs/desktop-architecture.md)。

### 第一步：构建原生组件

```powershell
.\scripts\build.ps1 -Configuration Release
```

构建产物位于 `build\windows-x64\`，主要包括 MediaSource DLL、Registrar 和取帧工具。

### 第二步：安装虚拟摄像头

打开管理员 PowerShell：

```powershell
.\scripts\install-dev.ps1 -SkipBuild -RefreshFrameServer -PruneOldVersions
```

| 参数 | 作用 |
|---|---|
| `-SkipBuild` | 使用现有 Release 产物，不重复构建 |
| `-RefreshFrameServer` | 安全终止专用 Frame Server 宿主，使 Windows 加载新 DLL |
| `-PruneOldVersions` | 尝试删除不再使用的旧哈希 DLL |

首次构建和安装也可以合并执行：

```powershell
.\scripts\install-dev.ps1 -RefreshFrameServer -PruneOldVersions
```

安装成功后，应用中的设备名称为 `SSKJ (Windows Virtual Camera)`。

### 第三步：安装 Python 发送端

```powershell
cd .\python
python -m pip install -e .
```

需要运行测试时安装测试依赖：

```powershell
python -m pip install -e ".[test]"
```

### 第四步：发送图片或视频

```powershell
# 图片默认持续循环
mfvc-send D:\media\picture.jpg

# 视频结束后默认从头循环
mfvc-send D:\media\video.mp4

# 不安装命令入口时
python -m mf_virtual_camera.cli D:\media\video.mp4

# 使用物理摄像头（索引与 OpenCV 一致）
mfvc-send --camera 0

# 使用 RTSP/HTTP 等 OpenCV 能打开的网络流
mfvc-send --stream rtsp://user:password@example.test/live

# 使用自带时钟测试图案，无需媒体文件
mfvc-send --pattern clock
```

常用参数：

```powershell
# 水平镜像
mfvc-send D:\media\video.mp4 --mirror

# 指定输入播放/发送节奏
mfvc-send D:\media\video.mp4 --fps 25

# 图片只发布一次，或视频播放到末尾后退出
mfvc-send D:\media\picture.jpg --no-loop

# 查看完整帮助
mfvc-send --help
```

`--width` 和 `--height` 是发送端 IPC 画布尺寸，目前仍只接受 `1280` 和 `720`。
它们不是应用最终获取的分辨率；应用可从虚拟摄像头协商 1080p、720p 或 480p。

### 注册多个名称不同的 MF 摄像头

管理员 PowerShell 中执行：

```powershell
.\scripts\manage-instance.ps1 -Name "会议演示摄像头" -RefreshFrameServer
```

命令会生成并输出一个实例 GUID。移除时应同时传入原 GUID，防止误删其他实例：

```powershell
.\scripts\manage-instance.ps1 `
  -Name "会议演示摄像头" `
  -InstanceId "{生成时输出的 GUID}" `
  -Remove `
  -RefreshFrameServer
```

各实例有独立名称和 CLSID，但当前都读取同一个 `frames.v1.bin`，因此显示相同画面。
要让多个设备同时显示不同内容，还需要把实例标识贯穿 COM 激活与 IPC 路径。

### 第五步：在应用中使用

保持发送端窗口运行，然后在微信、浏览器或会议软件的摄像头设置中选择
`SSKJ (Windows Virtual Camera)`。

浏览器第一次访问摄像头时需要授予权限。若设备列表在安装前已经打开，请关闭并
重新打开设置或重启目标应用。按 `Ctrl+C` 只会停止发送端，不会卸载设备。

### 企业微信 DirectShow 兼容层

企业微信 5.0 的主程序和会议模块是 x86，并使用传统 DirectShow 摄像头枚举。安装
32 位兼容层需要在管理员 PowerShell 中执行：

```powershell
.\scripts\build-directshow.ps1
.\scripts\install-directshow.ps1 -SkipBuild -PruneOldVersions
```

安装后用与企业微信相同的 x86 DirectShow 路径进行枚举和建图验证：

```powershell
.\build\windows-x86\tools\directshow_probe\Release\SSKJDirectShowProbe.exe
.\build\windows-x86\tools\directshow_probe\Release\SSKJDirectShowProbe.exe --open
```

预期设备名称为：

```text
SSKJ DirectShow Camera
```

`--open` 会把摄像头 Capture Pin 连接到 Null Renderer 并运行 1.2 秒，可验证 COM
激活、YUY2 协商、缓冲区分配、工作线程和真实推帧路径。当前 DirectShow 层支持
YUY2、30 FPS，分辨率为 1920×1080、1280×720 和 640×480。

它和 Media Foundation 相机读取同一个 `frames.v1.bin`，所以不需要启动第二个 Python
发送端。安装完成后必须完全退出企业微信及其托盘进程，再重新启动并选择
`SSKJ DirectShow Camera`。

卸载兼容层：

```powershell
.\scripts\uninstall-directshow.ps1 -RemoveDeployedFiles
```

该命令不会移除 Media Foundation 的 `SSKJ (Windows Virtual Camera)`。

## 验证

独立枚举和取帧：

```powershell
.\build\windows-x64\tools\frame_probe\Release\SSKJVirtualCameraProbe.exe
```

管理员 PowerShell 中进行一键完整验证：

```powershell
.\scripts\verify.ps1 `
  -SkipBuild `
  -PythonPath C:\path\to\python.exe `
  -Source D:\media\picture.jpg
```

该脚本会运行原生测试、Python 测试、后台发送端和系统 Media Foundation 真实取帧，
结束时自动清理后台发送进程。

保存诊断日志：

```powershell
.\scripts\verify-diagnostic.ps1 `
  -PythonPath C:\path\to\python.exe `
  -Source D:\media\picture.jpg
```

日志写入 `build\verify.log`。

### 企业微信设备枚举排除测试

如果浏览器和系统相机能使用 SSKJ，但企业微信不能，可以额外注册一台拥有独立
MediaSource CLSID 的诊断设备。在管理员 PowerShell 中执行：

```powershell
.\scripts\wecom-enumeration-test.ps1 -RefreshFrameServer
```

系统设备列表中应新增：

```text
SSKJ WeCom Detection Test (Windows Virtual Camera)
```

只检查系统枚举、不打开摄像头：

```powershell
.\build\windows-x64\tools\frame_probe\Release\SSKJVirtualCameraProbe.exe --list
```

然后完全退出企业微信，包括右下角托盘进程，再重新启动并查看摄像头列表。按结果判断：

| 系统结果 | 企业微信结果 | 说明 |
|---|---|---|
| 同时看到两台 SSKJ | 同时看到两台 | 企业微信能够刷新并枚举 MF 虚拟相机，问题更可能在媒体格式或启动过程 |
| 同时看到两台 SSKJ | 仍只看到原 SSKJ | 企业微信可能缓存设备列表，或按自身规则去重 |
| 同时看到两台 SSKJ | 两台都看不到 | 企业微信可能过滤 Windows 软件虚拟相机或走不兼容的枚举路径 |
| 能选择测试相机但黑屏 | — | 枚举已经成功，应继续排查 NV12、分辨率、帧率和首帧时序 |

测试设备和原设备读取同一个 `frames.v1.bin`，因此运行一次 Python 发送端即可为两台
设备提供相同画面。验证完成后移除测试设备：

```powershell
.\scripts\wecom-enumeration-test.ps1 -Remove -RefreshFrameServer
```

该操作不会移除正式的 `SSKJ (Windows Virtual Camera)`。

## 更新开发版本

修改 C++ 后执行：

```powershell
.\scripts\build.ps1 -Configuration Release
.\scripts\install-dev.ps1 -SkipBuild -RefreshFrameServer -PruneOldVersions
```

不要手动结束任意 `svchost.exe`。刷新脚本会先确认目标 PID 只托管 `FrameServer`
服务且进程确实是 `svchost`，检查通过后才终止该专用宿主。

## 卸载

管理员 PowerShell 中移除设备并反注册 COM DLL：

```powershell
.\scripts\uninstall-dev.ps1 -RefreshFrameServer
```

同时删除 ProgramData 中的帧文件和部署 DLL：

```powershell
.\scripts\uninstall-dev.ps1 -RefreshFrameServer -RemoveRuntimeData
```

`-RemoveRuntimeData` 会删除整个 `C:\ProgramData\SSKJVirtualCamera`，只应在确定不再
使用该虚拟摄像头时执行。

## 常见问题

### 还需要安装 OBS Studio 吗？

不需要。本项目自己实现并注册 Windows Media Foundation 虚拟摄像头。OBS 可以作为
独立的画面混合或直播工具使用，但不是本项目的运行依赖。

### 为什么 `pyvirtualcam --device test` 不能改设备名？

`pyvirtualcam` 是向已有后端发送帧的客户端，OBS 后端只接受 OBS 创建的固定设备。
本项目的设备名由原生 Registrar 注册，因此绕开了这个限制。

### 设备出现了，但画面没有更新

1. 确认 Python 发送端仍在运行且没有报错。
2. 确认输入文件能被 OpenCV 读取。
3. 确认应用选择的是 `SSKJ (Windows Virtual Camera)`。
4. 重新打开应用的摄像头设置。
5. DLL 更新后运行 `.\scripts\install-dev.ps1 -SkipBuild -RefreshFrameServer`。

### 安装时报“访问被拒绝”或 COM 无法加载

必须使用管理员 PowerShell。安装器会把 DLL 部署到 ProgramData，并为 SYSTEM、
Administrators、Local Service 和 Users 设置权限。如果进程仍加载旧 DLL，请使用
`-RefreshFrameServer`，不要手动覆盖被占用的文件。

### 能否修改分辨率或设备名？

可用 `manage-instance.ps1` 注册自定义名称。应用可协商 1080p、720p 或 480p；发送端
IPC 仍固定为 720p。若要增加其他输出尺寸，需同时扩展 MF/DirectShow 媒体类型列表和
缩放测试，不能只修改 Python 参数。

## 后续方向

- 为不同虚拟相机实例提供彼此独立的 IPC 通道和输入画面。
- 增加 GPU 解码、颜色转换和更低拷贝路径。
- 提供正式 MSI、代码签名、升级与回滚策略。

## 开发与测试踩坑记录

下面记录的是本项目从“设备能够注册”到“系统能够读取真实画面”过程中实际遇到的
问题。虚拟摄像头开发的困难往往不在图片解码，而在 COM 激活、Frame Server 进程
边界、Media Foundation 状态机和 Windows 权限。

### 1. `pyvirtualcam` 不能凭空创建任意名称的摄像头

**现象**

```text
'obs' backend: This backend supports only the 'OBS Virtual Camera' device.
'unitycapture' backend: No camera registered with this name.
```

**原因**

`pyvirtualcam` 只是向已有虚拟摄像头后端发送帧，不负责在 Windows 中注册新的摄像头
驱动。OBS 后端只能找到 OBS 注册的设备，传入 `--device test` 不会创建名为 `test`
的新设备。

**解决方案**

改用 Windows 11 原生 `MFCreateVirtualCamera` 注册设备，并自己实现 Media Foundation
MediaSource。设备名称由 Registrar 决定，发送端不再依赖 OBS 或 `pyvirtualcam`。

### 2. 注册成功不等于能够取到视频帧

**现象**

设备已经出现在系统列表中，但打开后黑屏、一直等待，或者取帧工具只能枚举设备而
读不到有效样本。

**原因**

虚拟摄像头注册只证明 Windows 保存了设备描述，并不证明 MediaSource 完整实现了
Frame Server 所需的接口和状态变化。真正打开设备时才会触发 COM 激活、媒体类型
协商、流启动、样本分配和事件队列交互。

**解决方案**

把验证分为三层：

1. 协议单元测试验证帧布局和边界。
2. MediaSource 冒烟测试验证 COM 对象和基本状态机。
3. `frame_probe` 通过系统 Media Foundation 枚举设备并读取真实样本。

只有第三层成功，才能说明微信或浏览器所走的系统路径基本可用。

### 3. Frame Server 要求正确初始化样本分配器

**现象**

MediaSource 能被加载，流也能启动，但首次请求帧时失败，或者应用迟迟收不到样本。

**原因**

Windows Camera Frame Server 不只是调用最基础的 `IMFMediaSource`。它还会通过
`IMFSampleAllocatorControl` 把自己的样本分配器交给媒体源。如果实现了接口却没有
在 `InitializeSampleAllocator` 中正确保存和使用分配器，返回的样本不符合 Frame
Server 的预期。

**解决方案**

MediaSource 实现 `IMFSampleAllocatorControl`，接受 Frame Server 初始化的 allocator，
后续优先从该 allocator 分配 `IMFSample`，再填充 NV12 数据、时间戳和持续时间。
这是从“能枚举”走到“能看到第一帧”的关键修复之一。

### 4. 第一次读取出现 Stream Tick 不一定是错误

**现象**

系统探针第一次 `ReadSample` 没有返回视频样本，而是得到流事件标志，容易被误判为
摄像头失效。

**原因**

Media Foundation 流启动阶段允许先返回 `MF_SOURCE_READERF_STREAMTICK`。这表示时间线
发生推进但当前调用没有携带媒体样本，是合法的启动行为。

**解决方案**

探针不能把第一次无样本直接判定为失败，而应识别 Stream Tick，在有限次数和超时
范围内继续读取。当前验证中通常第一次得到 `0x100`，随后一次返回有效样本。

### 5. `Local\` 共享内存在跨会话场景下不可见

**现象**

Python 发送端显示正在写帧，本进程测试也通过，但 Frame Server 始终读取不到数据。

**原因**

桌面程序和 Camera Frame Server 可能位于不同 Windows Session。`Local\` 命名对象
只在当前会话命名空间内可见，因此两边看似打开了同名共享内存，实际上不是同一个
对象。

**解决方案**

改用 `C:\ProgramData\SSKJVirtualCamera\frames.v1.bin`，两端把同一个磁盘文件映射到
内存。文件路径跨会话稳定，同时可以用 ACL 明确授予 Local Service 和普通用户访问权。

### 6. 共享缓冲区必须避免读取半帧

**现象**

高频发送时可能出现撕裂、颜色异常或偶发协议校验失败。

**原因**

一帧 1280×720 NV12 数据约 1.3 MiB，不可能通过一次原子写完成。如果读取方恰好在
写入过程中复制同一缓冲区，就会得到新旧数据混合的半帧。

**解决方案**

使用两个帧槽和递增发布序号：写入端只修改非活动槽，全部写完后最后更新对齐的
64 位序号；读取端复制前后检查序号，不一致就重试。协议头使用固定宽度小端整数，
C++ 用 `static_assert`、Python 用 `struct` 格式共同约束 128 字节 ABI。

### 7. Frame Server 会长期锁住已加载的 DLL

**现象**

重新构建或安装时出现：

```text
Access denied
```

即使代码构建成功，也无法覆盖 ProgramData 中正在使用的 DLL。

**原因**

MediaSource 是进程内 COM DLL。Frame Server 加载后，Windows 会保持模块文件打开；
直接用固定名称覆盖或删除正在加载的 DLL 会失败。

**解决方案**

Release 构建产物保持固定名称，但安装时根据 SHA-256 内容哈希生成部署文件名。新代码
得到新文件，COM 注册切换到新路径，然后安全刷新 Frame Server。旧 DLL 在不再占用后
由 `-PruneOldVersions` 清理。

安装器还要处理“内容没有变化”的情况：如果同一哈希文件已经存在，应直接复用，
不能再次 `Copy-Item -Force` 覆盖正在加载的相同文件。

### 8. 目录 ACL 正确，已有 DLL 的 ACL 仍可能错误

**现象**

部署目录看起来已经给 Users 和 Local Service 授权，但 Registrar 验证时仍报告：

```text
MediaSource COM component is not registered or cannot be loaded.
```

或者普通用户无法读取 DLL 的安全信息。

**原因**

已有文件可能关闭了继承或保留旧 ACL。只修改父目录并不能保证被复用的旧文件获得
正确权限。

**解决方案**

安装器除了设置 `bin` 目录 ACL，还对最终哈希 DLL 显式设置：

- SYSTEM：完全控制。
- Administrators：完全控制。
- Local Service：读取和执行。
- Users：读取和执行。

这样无论文件是新复制还是已有复用，Frame Server 都能加载它。

### 9. 刷新 Frame Server 不能随意结束 `svchost.exe`

**现象**

注册表已经指向新 DLL，但测试仍然执行旧代码；直接结束错误的 `svchost.exe` 又可能
影响其他 Windows 服务。

**原因**

Frame Server 可能继续驻留并持有旧 COM 模块，而一个 `svchost.exe` 也可能托管多个
系统服务。

**解决方案**

刷新脚本先查询 `FrameServer` 服务 PID，再确认：

1. 该 PID 只托管一个服务。
2. 唯一服务名称确实是 `FrameServer`。
3. 进程名确实是 `svchost`。

三个条件全部满足才终止该进程，让 Windows 在下一次打开摄像头时重新启动服务并加载
新 DLL。验证脚本也会先停止可能残留的项目探针，避免它继续占用摄像头。

### 10. PowerShell 会把原生程序的 stderr 包装成错误记录

**现象**

C++ 探针只是把诊断信息写到 stderr，但 Windows PowerShell 在重定向日志时把它包装成
`NativeCommandError`。脚本设置 `$ErrorActionPreference = 'Stop'` 后，正常诊断输出也
可能中断安装或验证流程。

**原因**

Windows PowerShell 对原生进程 stderr 的处理不同于普通控制台：文本输出可能进入
PowerShell 错误流，而不只是保留原生程序退出码。

**解决方案**

- 普通诊断信息改写到 stdout，只把真正错误写到 stderr。
- 调用探针时临时允许错误流继续，执行后以 `$LASTEXITCODE` 判断成功或失败。
- 诊断包装脚本用 `try/catch` 保存完整日志和明确的 `EXIT=<code>`。

脚本不能只凭“终端出现红字”判断原生程序失败，退出码才是最终依据。

### 11. Media Foundation 对象的清理顺序很重要

**现象**

探针已经成功读取帧，但退出时可能出现异常、资源未释放或后续测试不稳定。

**原因**

Source Reader、样本和 MediaSource 之间存在引用关系。如果先对 MediaSource 调用
`Shutdown`，而 Reader 或 Sample 仍在使用它，清理过程可能进入不合法状态。

**解决方案**

按照依赖关系逆序释放：先释放样本，再释放 Source Reader，最后调用 MediaSource
`Shutdown`，随后执行 Media Foundation 和 COM 的全局清理。

### 12. 图片的 `--no-loop` 容易出现边界错误

**现象**

对图片使用 `--no-loop` 时仍可能重复发送，而不是只发布一帧后退出。

**原因**

图片生成器通常先 `yield` 一次，再进入循环。如果循环条件或生成器结构写得不清晰，
单帧模式很容易意外进入重复分支。

**解决方案**

图片迭代器明确执行一次 `yield frame`，之后只有 `loop=True` 才继续生成，并增加单元
测试断言 `--no-loop` 恰好产生一帧。类似的生命周期边界要通过测试固定下来，不能只
靠人工观察播放窗口。

### 13. Python 测试通过后仍可能出现 pytest 临时目录警告

**现象**

测试显示 `6 passed` 且退出码为 0，但退出阶段可能看到 Windows 临时目录的
`PermissionError`。

**原因**

pytest 清理 `%LOCALAPPDATA%\Temp\pytest-of-<user>` 中的历史链接或目录时，可能遇到
其他权限上下文创建的残留项。这不代表项目测试失败。

**解决方案**

以 pytest 退出码和测试结果为准，同时把真正的系统摄像头验收交给 `frame_probe`。
如果需要消除警告，可在确认目录不被其他测试使用后，用创建它的权限上下文清理对应
pytest 临时目录；不要在项目脚本中递归删除整个用户 Temp。

### 14. 自动测试必须覆盖真实的 Windows 消费路径

**现象**

颜色转换、共享协议和 COM 单元测试都通过，但微信或浏览器仍可能打不开设备。

**原因**

单元测试通常在当前进程直接创建对象，无法覆盖 Frame Server 的服务身份、跨会话
权限、系统设备枚举、样本 allocator 和实际启动顺序。

**解决方案**

`verify.ps1` 将测试串成完整闭环：

```text
原生测试 → Python 测试 → 启动发送端 → 系统枚举设备 → 读取真实帧 → 清理进程
```

发布或修改 MediaSource、IPC、ACL、安装脚本后，都应执行这套系统级验证，而不能只
运行某一侧的单元测试。

### 15. 企业微信看不到设备并不只是 x86/x64 位数问题

**现象**

Windows 相机和浏览器能看到 SSKJ，企业微信 5.0.10.6015 只显示物理的 FHD Camera。
企业微信主程序及其会议模块确实是 x86，因此最初容易怀疑它无法使用 x64 虚拟相机。

**排除过程**

1. 把 Media Foundation `frame_probe` 单独编译为 x86；它仍能枚举正式 SSKJ，证明
   32 位应用可以通过 Windows Frame Server 看到该 MF 虚拟相机。
2. 编写 `tools/directshow_probe`，分别构建 x86 和 x64 版本。
3. 两种位数的 DirectShow 探针都只枚举到 FHD Camera，与企业微信设备列表完全一致。

**结论**

根因是采集 API 路径而不是单纯位数：当前 SSKJ 只注册为 Windows 11 Media Foundation
虚拟相机，没有注册到 DirectShow 的 `CLSID_VideoInputDeviceCategory`。企业微信会议
模块很可能使用 32 位 DirectShow 枚举，所以完全看不到这两台 MF 测试设备。

**解决方案与实施结果**

项目现已增加 32 位 DirectShow Source Filter，并注册到
`CLSID_VideoInputDeviceCategory`。它继续读取现有 `frames.v1.bin`，把 NV12 转换为
企业微信更常用的 YUY2，支持 1920×1080、1280×720 和 640×480。x86 探针已验证设备枚举成功，
并能完成 Capture Graph 建图和持续推帧。x64 DLL也能构建，正式安装包阶段可再把两种
位数统一纳入安装和卸载流程。
