# -*- mode: python ; coding: utf-8 -*-


from comtypes.client import GetModule
uia_module = GetModule('UIAutomationCore.dll')
uia_imports = [uia_module.__name__, uia_module.__wrapper_module__.__name__]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[('native/send_guard/bin/x64/Release/CoolCatSendGuardV2_64.dll', '.')],
    datas=[],
    hiddenimports=uia_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
