# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

root = Path(SPECPATH).parent
datas = [
    (str(root / "scripts"), "scripts"),
    (str(root / "build" / "windows-x64" / "native" / "media_source" / "Release" / "SSKJVirtualCameraMediaSource.dll"), "build/windows-x64/native/media_source/Release"),
    (str(root / "build" / "windows-x64" / "native" / "registrar" / "Release" / "SSKJVirtualCameraRegistrar.exe"), "build/windows-x64/native/registrar/Release"),
    (str(root / "build" / "windows-x64" / "tools" / "frame_probe" / "Release" / "SSKJVirtualCameraProbe.exe"), "build/windows-x64/tools/frame_probe/Release"),
]
binaries = [(str(path), ".") for path in (Path(sys.prefix) / "Library" / "bin").glob("*.dll")]
if (root / "build/windows-x86/native/directshow_source/Release/SSKJDirectShowCamera.dll").exists():
    datas.append((str(root / "build/windows-x86/native/directshow_source/Release/SSKJDirectShowCamera.dll"), "build/windows-x86/native/directshow_source/Release"))

a = Analysis(
    [str(root / "packaging" / "desktop_entry.py")],
    pathex=[str(root / "python")], binaries=binaries, datas=datas,
    hiddenimports=["cv2", "numpy", "PyQt5.sip"], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=["tkinter", "pytest"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SSKJCameraStudio",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True,
               name="SSKJCameraStudio")
