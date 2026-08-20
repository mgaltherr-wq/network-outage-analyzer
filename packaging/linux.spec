# PyInstaller spec for the Linux build. Build from the repo root with:
#   pyinstaller --distpath dist/linux packaging/linux.spec
# Produces dist/linux/NetworkOutageAnalyzer/ (onedir — AppImage tooling wants
# a directory tree, not a single binary), which the AppImage build step wraps.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent

# pysnmp/pyasn1 rely on dynamic imports that PyInstaller's static analysis
# can't see; pulling in every submodule is more robust than hand-picking a
# list that will silently go stale as those packages change.
hiddenimports = collect_submodules("pysnmp") + collect_submodules("pyasn1")

a = Analysis(
    [str(ROOT / "app" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "app" / "dashboard.html"), "app"),
        (str(ROOT / "app" / "settings.html"), "app"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NetworkOutageAnalyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="NetworkOutageAnalyzer",
)
