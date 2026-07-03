from __future__ import annotations

from pathlib import Path

from src import catbox
from src.raw_image_url import build_public_url


def _public_image_url(file_path: Path, userhash: str = "") -> str:
    return build_public_url(file_path)


catbox.upload_file = _public_image_url
