"""Post today's ready schedule entry to Threads."""
from __future__ import annotations

import argparse
import sys
from typing import Any

from .threads_api import ThreadsAPI
from .utils import append_yaml_list, load_yaml, repo_path, require_env, save_yaml, timestamp_jst, today_jst_str


def find_post(schedule: list[dict[str, Any]], date: str, time_slot: str) -> dict[str, Any] | None:
    for item in schedule:
        if not isinstance(item, dict):
            continue
        if str(item.get("date")) != date:
            continue
        if str(item.get("time_slot")) != time_slot:
            continue
        if str(item.get("status", "")).lower() != "ready":
            continue
        if str(item.get("threads_post_id", "")).strip():
            continue
        return item
    return None


def post_daily(date: str, time_slot: str, dry_run: bool = False) -> int:
    schedule_path = repo_path("posts", "schedule.yml")
    posted_log_path = repo_path("posts", "posted_log.yml")
    schedule = load_yaml(schedule_path, default=[])
    if not isinstance(schedule, list):
        raise ValueError("posts/schedule.yml must be a YAML list.")

    item = find_post(schedule, date, time_slot)
    if not item:
        print(f"No ready post found for date={date} time_slot={time_slot}.")
        return 0

    text = str(item.get("text", "")).strip()
    image_url = str(item.get("image_url", "")).strip()
    alt = str(item.get("alt", "")).strip()

    if not text:
        raise ValueError("Schedule item has no text.")

    print(f"Target: {date} {time_slot} category={item.get('category')} character={item.get('character')}")
    print(text[:200])
    if image_url:
        print(f"image_url={image_url}")

    if dry_run:
        print("Dry run. No post was published.")
        return 0

    api = ThreadsAPI(
        access_token=require_env("BIKANSAN_ACCESS_TOKEN"),
        user_id=require_env("BIKANSAN_USER_ID"),
    )

    result = api.post_image(text, image_url, alt_text=alt) if image_url else api.post_text(text)
    if "error" in result:
        item["status"] = "error"
        item["error"] = str(result["error"])[:500]
        item["error_at"] = timestamp_jst()
        save_yaml(schedule_path, schedule)
        print(f"ERROR: {result}")
        return 1

    post_id = str(result.get("id", ""))
    if not post_id:
        item["status"] = "error"
        item["error"] = f"No post id in result: {result}"
        item["error_at"] = timestamp_jst()
        save_yaml(schedule_path, schedule)
        print(f"ERROR: {result}")
        return 1

    posted_at = timestamp_jst()
    item["status"] = "posted"
    item["threads_post_id"] = post_id
    item["posted_at"] = posted_at
    item["error"] = ""
    save_yaml(schedule_path, schedule)

    append_yaml_list(
        posted_log_path,
        {
            "post_id": post_id,
            "date": date,
            "time_slot": time_slot,
            "category": item.get("category", ""),
            "character": item.get("character", ""),
            "text_head": text[:80],
            "image_url": image_url,
            "posted_at": posted_at,
        },
    )
    print(f"Posted: {post_id}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=today_jst_str())
    parser.add_argument("--time-slot", default="evening")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(post_daily(args.date, args.time_slot, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
