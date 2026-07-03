from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def build_public_url(file_path: Path) -> str:
    path = file_path.resolve()
    relative = path.relative_to(REPO_ROOT).as_posix()
    repository = os.environ.get("GITHUB_REPOSITORY", "goroyattemiyo/bitansan-antithese-autopilot")
    branch = os.environ.get("GITHUB_REF_NAME", "main") or "main"
    return f"https://raw.githubusercontent.com/{repository}/{branch}/{relative}"
