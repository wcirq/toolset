# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = os.path.abspath(os.path.join(SPECPATH, ".."))
rapidocr_datas = collect_data_files('rapidocr')
rapidocr_hiddenimports = collect_submodules('rapidocr.inference_engine.onnxruntime')


a = Analysis(
    [os.path.join(project_root, 'main.py')],
    pathex=[project_root],
    binaries=[],
    datas=rapidocr_datas,
    hiddenimports=rapidocr_hiddenimports + [
        'pythoncom', 'pywintypes', 'win32gui', 'win32com.client', 'win32com.shell.shell'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(SPECPATH, 'runtime_hooks',
                                'preload_vc_runtime.py')],
    excludes=[
        'torch', 'torchvision', 'ultralytics',
        'matplotlib',
        'rapidocr.inference_engine.pytorch',
        'rapidocr.inference_engine.paddle',
        'rapidocr.inference_engine.openvino',
        'rapidocr.inference_engine.tensorrt',
        'rapidocr.inference_engine.mnn',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CoolCat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(project_root, 'assets', 'cat.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CoolCat',
)
