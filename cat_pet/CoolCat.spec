# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

rapidocr_datas = collect_data_files('rapidocr')
rapidocr_hiddenimports = collect_submodules('rapidocr.inference_engine.onnxruntime')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=rapidocr_datas,
    hiddenimports=rapidocr_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(project_root, 'packaging', 'runtime_hooks',
                                'preload_vc_runtime.py')],
    excludes=[
        'torch', 'torchvision', 'ultralytics', 'matplotlib',
        'rapidocr.inference_engine.pytorch', 'rapidocr.inference_engine.paddle',
        'rapidocr.inference_engine.openvino', 'rapidocr.inference_engine.tensorrt',
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
    icon=['assets\\cat.ico'],
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
