"""Common utilities."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO_ROOT = Path(__file__).resolve().parents[1]


def now_jst() -> datetime:
    """Return current datetime in Asia/Tokyo."""
    return datetime.now(JST)


def today_jst_str() -> str:
    """Return current date as YYYY-MM-DD in Asia/Tokyo."""
    return now_jst().strftime("%Y-%m-%d")


def timestamp_jst() -> str:
    """Return ISO timestamp in Asia/Tokyo."""
    return now_jst().isoformat(timespec="seconds")


def require_env(name: str) -> str:
    """Read an environment variable or fail loudly."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def optional_env(name: str, default: str = "") -> str:
    """Read an optional environment variable."""
    return os.environ.get(name, default).strip()


def repo_path(*parts: str) -> Path:
    """Build a path under repository root."""
    return REPO_ROOT.joinpath(*parts)


def load_yaml(path: Path, default: Any = None) -> Any:
    """Load YAML. Return default when file is empty or missing."""
    if default is None:
        default = []
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return default
    data = yaml.safe_load(text)
    return default if data is None else data


def save_yaml(path: Path, data: Any) -> None:
    """Save YAML with stable UTF-8 output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def append_yaml_list(path: Path, item: dict[str, Any]) -> None:
    """Append an item to a YAML list file."""
    data = load_yaml(path, default=[])
    if not isinstance(data, list):
        raise ValueError(f"YAML file is not a list: {path}")
    data.append(item)
    save_yaml(path, data)
