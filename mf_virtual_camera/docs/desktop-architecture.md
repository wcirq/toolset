# 桌面版架构

桌面版采用“薄 UI、复用发送内核、复用原生安装链”的结构，不改变已经验证过的
Media Foundation、DirectShow 和 IPC ABI。

```text
SSKJ Camera Studio (PyQt5 / Qt 5.15)
├── CameraManager ── PowerShell/Registrar ── MediaSource DLL
├── SourceController ── media.py ── OpenCV
├── PluginHost ── 独立验证进程 + 实时受控调用
└── SenderWorker ── formats.py + ipc.py ── frames.v1.bin
                                            │
                     MF x64 / DirectShow x86 virtual cameras
```

## 模块边界

- `desktop/app.py`：进程入口、冻结程序路径处理和插件验证子命令。
- `desktop/main_window.py`：基于 Qt5 的无边框主窗口、导航、表单、日志和预览。
- `desktop/camera_manager.py`：安装、卸载、自定义实例和列表查询；需要时触发 UAC。
- `desktop/sender.py`：媒体生命周期、节奏、镜像、缩放、插件和 IPC 发布。
- `desktop/plugin_host.py`：插件静态加载、独立进程样帧验证、热切换。
- `desktop/theme.py`：应用统一色板和控件绘制规则。
- `packaging/`：PyInstaller 规格、运行时装配和 Inno Setup 安装器。

## 插件约定

代码必须定义：

```python
def process(frame, context):
    # frame: 可写的 BGR numpy.ndarray
    # context: frame_index、timestamp、fps、width、height
    return frame
```

验证进程会用一张测试帧执行函数，并检查返回值是否为非空 `uint8 HxWx3` 数组。
验证成功后才替换当前插件。实时异常不会终止 UI，而会停用插件并把完整 traceback
送到错误面板。

插件是本机 Python 代码，拥有与应用相同的用户权限，只应粘贴可信代码。子进程验证
用于故障隔离和超时控制，不是安全沙箱。

## 打包布局

PyInstaller 使用 onedir 模式，保留 Qt 插件目录并把以下现有产物作为数据文件装入：

- x64 MediaSource DLL、Registrar、Frame Probe；
- x86 DirectShow DLL 和 Probe；
- 安装、卸载、运行时准备和 Frame Server 刷新脚本。

Inno Setup 6 只安装桌面程序及上述资源，不在安装器阶段注册摄像头；用户在 UI 中点击
安装时才通过 UAC 明确授权。这样升级桌面软件不会隐式改变系统摄像头状态。
