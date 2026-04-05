# -*- mode: python ; coding: utf-8 -*-
import sys

# Mac-specific PyInstaller spec file
block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[], # binary_manager will auto-download the correct mac binary
    datas=[('assets', 'assets')], # Include assets folder
    hiddenimports=[],
    hookspath=[],
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
    exclude_binaries=True,
    name='RaidCloud Immich Suite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/icon.icns', # Uncomment this AFTER you convert your .ico to .icns!
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RaidCloud Immich Suite',
)

app = BUNDLE(
    coll,
    name='RaidCloud Immich Suite.app',
    icon=None, # Update to 'assets/icon.icns' once ready
    bundle_identifier='com.raidcloud.immichsuite',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '2.0.0',
        'CFBundleVersion': '2.0.0',
    },
)
