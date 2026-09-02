"""Preload the newest bundled MSVC runtime before PyQt loads its older copy."""

import ctypes
import os
import sys


if sys.platform == "win32":
    runtime_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    for dll_name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
        dll_path = os.path.join(runtime_dir, dll_name)
        if os.path.isfile(dll_path):
            ctypes.WinDLL(dll_path)
