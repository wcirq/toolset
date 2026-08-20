# 架构说明

## 设计原则

1. **设备层与媒体输入解耦**：MediaSource 只负责按 Media Foundation 约定提供帧，
   不直接解析图片或视频。
2. **协议先行**：C++ DLL 会被 Windows Frame Server 加载，必须把越界访问、ABI
   变化和发送端崩溃视为正常故障场景。
3. **先固定格式再扩展**：第一阶段只暴露 NV12、1280×720、30 FPS，稳定后再增加
   格式协商，避免同时调试协议、颜色和媒体类型。
4. **可诊断、可卸载**：任何系统注册都必须有对应的查询和移除操作，不依赖手动
   清理注册表。

## 进程边界

MediaSource DLL 不运行在 Python 进程中。目标应用打开摄像头时，Windows Camera
Frame Server 会加载该 DLL。因此两端不能直接传递 Python/NumPy 指针，必须使用
操作系统级 IPC。

首版选择位于 `C:\ProgramData\SSKJVirtualCamera` 的双缓冲内存映射文件：

- 文件映射不受 Windows 会话命名空间隔离影响，桌面 Python 进程与 Session 0 的
  Frame Server 能访问同一组内存页。
- 安装脚本向本机 Users 和 Local Service 授予运行所需的修改权限。

- 控制区保存 magic、协议版本、帧序号、尺寸、步长、像素格式和时间戳。
- 两个帧槽交替写入，避免读取方看到写到一半的画面。
- 写入端发布递增序号；读取端永远获取最近一个完整帧。
- 发送端退出后保留最后一帧，并可在超时后切换到占位画面。
- MediaSource 必须校验所有来自共享内存的长度和偏移，不能信任发送端数据。

## 为什么首版使用 NV12

NV12 是 Windows 视频管线广泛使用的 4:2:0 格式。由 Python 发送端完成 BGR 到
NV12 的转换，可以让 Frame Server 内的 DLL 保持简单，降低摄像头消费者进程受
崩溃影响的风险。代价是发送端需要一次颜色转换，且宽高必须为偶数。

## 注册范围

开发阶段优先使用 `MFVirtualCameraAccess_CurrentUser`：

- 通常不需要为所有用户写入系统范围配置。
- 便于开发期间反复注册和移除。
- 减少错误安装影响整台机器的风险。

MSI 交付阶段再评估 `MFVirtualCameraAccess_AllUsers`，该模式需要管理员权限。

## 构建策略

- C++20、MSVC、CMake，首版仅构建 x64 Release/Debug。
- Windows SDK 最低 10.0.22000.0。
- Python 包使用 `pyproject.toml`，保持与 C++ 构建相互独立。
- Release DLL 构建名保持稳定；开发安装时按 SHA-256 内容哈希复制到受保护的
  ProgramData `bin` 目录，避免 Frame Server 锁定构建产物并支持可靠升级。
- WiX 只消费已经验证过的 Release 产物，不在安装阶段执行编译。
- GUID/CLSID 集中定义，开发、测试和发布实例使用不同标识，避免互相覆盖。

## 交付阶段

### M1：系统可枚举（已完成）

编译最小 MediaSource 和 Registrar，注册后能在支持的应用中看到设备。

当前实现从协议 ABI、Registrar 和可重复构建开始。Registrar 只有在 MediaSource
COM DLL 完成并注册后才允许执行 `install`，避免留下无法激活的摄像头设备。

### M2：可传输画面（已完成）

完成共享内存协议与 Python 发送端，使固定测试图能持续输出。

### M3：可用播放器（已完成固定格式 MVP）

接入图片/视频解码、循环、镜像和等比缩放，处理发送端退出与重启。

### M4：可安装

完成 MSI、升级/卸载、依赖检查、日志和兼容性测试。
