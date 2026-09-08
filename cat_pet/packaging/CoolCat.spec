# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = os.path.abspath(os.path.join(SPECPATH, ".."))
rapidocr_datas = collect_data_files('rapidocr')
rapidocr_hiddenimports = collect_submodules('rapidocr.inference_engine.onnxruntime')
close_guard_dll = os.path.join(project_root, 'native', 'close_guard', 'bin',
                               'x64', 'Release', 'CoolCatCloseGuard64.dll')
native_binaries = [(close_guard_dll, '.')] if os.path.isfile(close_guard_dll) else []

send_guard_dll = os.path.join(project_root, 'native', 'send_guard', 'bin',
                              'x64', 'Release', 'CoolCatSendGuardV2_64.dll')
if not os.path.isfile(send_guard_dll):
    raise RuntimeError('请先构建 native/send_guard/build.bat')
native_binaries.append((send_guard_dll, '.'))


from comtypes.client import GetModule
uia_module = GetModule('UIAutomationCore.dll')
uia_imports = [uia_module.__name__, uia_module.__wrapper_module__.__name__]

a = Analysis(
    [os.path.join(project_root, 'main.py')],
    pathex=[project_root],
    binaries=native_binaries,
    datas=rapidocr_datas,
    hiddenimports=rapidocr_hiddenimports + uia_imports + [
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
