# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path(SPECPATH).parent

a = Analysis(
    [str(project_root / 'launcher' / 'assistant.pyw')],
    pathex=[str(project_root / 'src')],
    binaries=[],
    datas=[
        (str(project_root / 'assets' / 'download-transfer-station.ico'), 'assets'),
        (
            str(project_root / 'src' / 'idm_eagle_bridge' / 'assets'),
            'idm_eagle_bridge/assets',
        ),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='下载中转站后台',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon=str(project_root / 'assets' / 'download-transfer-station.ico'),
    version=str(project_root / 'packaging' / 'download-transfer-station-version.txt'),
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='下载中转站后台',
)
