# main.spec
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],  # Path to your main script
    pathex=[],    # Add any additional paths if needed
    binaries=[('immich-go.exe', '.')],  # Add binary files (e.g., immich-go.exe)
    datas=[('assets', 'assets'), ('run_immich.bat', '.')],  # Include the assets folder
    hiddenimports=[],  # Add any hidden imports if needed
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RaidCloud image Compressor',  # Name of the executable
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress the executable
    console=False,  # Set to False for no console window
    icon='assets\icon.ico',  # Optional: Add an icon for the executable
    onefile=True
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MyApp',  # Name of the output folder
)