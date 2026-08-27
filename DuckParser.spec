# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller DuckParser.spec --noconfirm
#
# datas must list every runtime data dir: the app reads themes/base.qss,
# themes/palettes.json, localization/*.json and ico/*.jpg from disk at startup.

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    # Listed file by file on purpose: passing whole directories drags in
    # __pycache__ and the .py sources next to the .json files.
    # ico/original.png is build-time only -- it becomes the embedded icon below.
    datas=[
        ('themes/base.qss', 'themes'),
        ('themes/palettes.json', 'themes'),
        ('localization/en.json', 'localization'),
        ('localization/ru.json', 'localization'),
        ('localization/ua.json', 'localization'),
        ('ico/48x48.jpg', 'ico'),
        ('ico/85x85.jpg', 'ico'),
        ('ico/close.png', 'ico'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtQuick', 'PySide6.Qt3DCore', 'tkinter'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DuckParser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['ico/original.png'],
)
