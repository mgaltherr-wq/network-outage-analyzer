"""Per-user, writable, persistent storage location for .env and ip_addresses.json.

Used by both source runs (`python run.py`, `uvicorn app.dashboard:app`) and
packaged builds. A single code path matters because PyInstaller's frozen
bundle extracts to a temp directory that's read-only and wiped between runs,
so anything computed from `Path(__file__)` (the old behavior) silently loses
data once packaged.
"""

import os
from pathlib import Path

APP_NAME = "NetworkOutageAnalyzer"      # Windows: %APPDATA%\NetworkOutageAnalyzer
APP_SLUG = "network-outage-analyzer"    # Linux: ~/.config/network-outage-analyzer


def user_data_dir() -> Path:
    override = os.environ.get("NOA_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_NAME
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
        path = Path(base) / APP_SLUG

    path.mkdir(parents=True, exist_ok=True)
    return path


def migrate_legacy_file(filename: str) -> None:
    """One-time copy of a pre-existing repo-root file into the new location."""
    legacy = Path(__file__).resolve().parents[1] / filename
    target = user_data_dir() / filename
    if legacy.exists() and not target.exists():
        target.write_bytes(legacy.read_bytes())
