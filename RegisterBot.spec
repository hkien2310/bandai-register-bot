# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

import os
datas_list = [('src', 'src')]
if os.path.exists('data/credentials.json'):
    datas_list.append(('data/credentials.json', 'data'))
else:
    print("WARNING: data/credentials.json not found! The build will not contain credentials.")

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=datas_list,
    hiddenimports=['gspread', 'playwright', 'requests', 'beautifulsoup4'],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BandaiRegister',
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
)

app = BUNDLE(
    exe,
    name='BandaiRegister.app',
    icon=None,
    bundle_identifier=None,
)
