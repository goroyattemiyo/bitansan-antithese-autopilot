"""Catbox uploader."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

CATBOX_API_URL = "https://catbox.moe/user/api.php"


def upload_file(file_path: Path, userhash: str = "") -> str:
    """Upload a file to Catbox and return its public URL."""
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    data: dict[str, Any] = {"reqtype": "fileupload"}
    if userhash:
        data["userhash"] = userhash

    with file_path.open("rb") as fp:
        files = {"fileToUpload": (file_path.name, fp)}
        resp = requests.post(CATBOX_API_URL, data=data, files=files, timeout=120)

    resp.raise_for_status()
    text = resp.text.strip()
    if not text.startswith("http"):
        raise RuntimeError(f"Catbox upload failed: {text}")
    return text
