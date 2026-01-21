# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None

project_dir = Path(__file__).resolve().parent.parent
assets_dir = project_dir / "assets"

a = Analysis(
    [str(project_dir / "index.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[(str(assets_dir), "assets")],
    hiddenimports=["PyQt6.QtMultimedia"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name="蒜皮宝宝",
    debug=False,
    bootloader_ignore_signals=False,
    exclude_binaries=True,
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="蒜皮宝宝",
)
