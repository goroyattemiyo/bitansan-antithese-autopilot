"""Generate scheduled posts from posts/ideas.yml.

This script generates:
- post text
- image prompt
- WebP image under assets/webp/
- Catbox image URL
- posts/schedule.yml entries
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from .catbox import upload_file
from .generate_image import generate_webp_image
from .generate_text import generate_image_prompt, generate_post_text
from .utils import load_yaml, optional_env, repo_path, save_yaml, timestamp_jst


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "post"


def schedule_key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("date", "")), str(item.get("time_slot", ""))


def build_webp_path(idea: dict[str, Any]) -> Path:
    date = str(idea.get("date", "unknown-date"))
    slot = slugify(str(idea.get("time_slot", "post")))
    char = slugify(str(idea.get("character", "bikansan")))
    return repo_path("assets", "webp", f"{date}-{slot}-{char}.webp")


def prepare(limit: int = 7, force: bool = False, upload: bool = True) -> int:
    ideas_path = repo_path("posts", "ideas.yml")
    schedule_path = repo_path("posts", "schedule.yml")

    ideas = load_yaml(ideas_path, default=[])
    schedule = load_yaml(schedule_path, default=[])
    if not isinstance(ideas, list):
        raise ValueError("posts/ideas.yml must be a YAML list.")
    if not isinstance(schedule, list):
        raise ValueError("posts/schedule.yml must be a YAML list.")

    existing = {schedule_key(item) for item in schedule if isinstance(item, dict)}
    created = 0
    userhash = optional_env("CATBOX_USERHASH")

    for idea in ideas:
        if created >= limit:
            break
        if not isinstance(idea, dict):
            continue

        key = schedule_key(idea)
        if key in existing and not force:
            print(f"skip existing schedule: {key}")
            continue

        print(f"prepare: {key}")
        post_text = generate_post_text(idea)
        image_prompt = generate_image_prompt(idea, post_text)
        webp_path = build_webp_path(idea)
        generate_webp_image(image_prompt, webp_path)

        image_url = ""
        if upload:
            image_url = upload_file(webp_path, userhash=userhash)

        entry = {
            "date": idea.get("date", ""),
            "time_slot": idea.get("time_slot", "evening"),
            "category": idea.get("category", "daily"),
            "character": idea.get("character", "netami_sonemi"),
            "theme": idea.get("theme", ""),
            "text": post_text,
            "image_prompt": image_prompt,
            "local_webp": str(webp_path.relative_to(repo_path())),
            "image_url": image_url,
            "alt": idea.get(
                "alt",
                "紫ツインテールのねたみと緑ショートのそねみが並ぶ、微炭酸アンチテーゼのダークアイドル風イラスト",
            ),
            "status": "ready" if image_url else "generated",
            "threads_post_id": "",
            "generated_at": timestamp_jst(),
            "posted_at": "",
        }

        if force and key in existing:
            schedule = [x for x in schedule if schedule_key(x) != key]

        schedule.append(entry)
        existing.add(key)
        created += 1

    save_yaml(schedule_path, schedule)
    print(f"created schedule entries: {created}")
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=7)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()
    prepare(limit=args.limit, force=args.force, upload=not args.no_upload)


if __name__ == "__main__":
    main()
