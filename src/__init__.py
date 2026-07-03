"""Bikansan Antithese autopilot package."""
from __future__ import annotations

from pathlib import Path

from . import catbox
from .raw_image_url import build_public_url


def _use_public_github_raw(file_path: Path, userhash: str = "") -> str:
    """Return a public raw URL now that the repository is public."""
    del userhash
    return build_public_url(file_path)


# Keep the legacy import path working while bypassing Catbox uploads.
catbox.upload_file = _use_public_github_raw
