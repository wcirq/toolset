"""PyInstaller 运行时钩子: 在内置 pyi_rth_pyqt5 之前预加载 torch。

Windows 上若 PyQt5 先于 torch 加载, torch 的 c10.dll 会报
WinError 1114 (DLL 初始化例程失败)。源码运行时 main.py 顶部已做
torch 预导入, 但打包后 PyInstaller 的 pyi_rth_pyqt5 钩子在用户代码
之前执行, 会先导入 PyQt5。自定义 runtime-hook 优先于内置钩子运行,
在这里提前加载 torch 即可保持正确顺序。

torch 未打包或加载失败时静默跳过 (YOLO 功能自动回退到 HOG)。
"""
import os
import sys

if getattr(sys, "frozen", False):
    # 确保 _internal 根目录在 DLL 搜索路径中 (c10.dll 依赖 VC 运行库)
    try:
        os.add_dll_directory(sys._MEIPASS)
    except Exception:
        pass

try:
    import torch  # noqa: F401  必须早于 PyQt5
except Exception:
    pass
