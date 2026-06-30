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


def normalize_thread_posts(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError("thread_posts must be a list.")

    results: list[dict[str, Any]] = []
    for index, part in enumerate(raw, start=1):
        if isinstance(part, str):
            part = {"text": part}
        if not isinstance(part, dict):
            raise ValueError(f"thread_posts[{index}] must be a dict or string.")
        text = str(part.get("text", "")).strip()
        image_url = str(part.get("image_url", "")).strip()
        alt = str(part.get("alt", "")).strip()
        if not text and not image_url:
            continue
        results.append(
            {
                "text": text,
                "image_url": image_url,
                "alt": alt,
                "index": index,
            }
        )
    return results


def publish_one(api: ThreadsAPI, text: str, image_url: str = "", alt: str = "", reply_to_id: str = "") -> dict[str, Any]:
    if image_url:
        return api.post_image(text, image_url, alt_text=alt, reply_to_id=reply_to_id)
    return api.post_text(text, reply_to_id=reply_to_id)


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
    thread_posts = normalize_thread_posts(item.get("thread_posts", []))

    if not text:
        raise ValueError("Schedule item has no text.")

    print(f"Target: {date} {time_slot} category={item.get('category')} character={item.get('character')}")
    print(text[:200])
    if image_url:
        print(f"image_url={image_url}")
    if thread_posts:
        print(f"thread replies: {len(thread_posts)}")
        for part in thread_posts:
            print(f"reply {part['index']}: {str(part.get('text', ''))[:120]}")

    if dry_run:
        print("Dry run. No post was published.")
        return 0

    api = ThreadsAPI(
        access_token=require_env("BIKANSAN_ACCESS_TOKEN"),
        user_id=require_env("BIKANSAN_USER_ID"),
    )

    root_result = publish_one(api, text, image_url=image_url, alt=alt)
    if "error" in root_result:
        item["status"] = "error"
        item["error"] = str(root_result["error"])[:500]
        item["error_at"] = timestamp_jst()
        save_yaml(schedule_path, schedule)
        print(f"ERROR: {root_result}")
        return 1

    root_post_id = str(root_result.get("id", ""))
    if not root_post_id:
        item["status"] = "error"
        item["error"] = f"No post id in result: {root_result}"
        item["error_at"] = timestamp_jst()
        save_yaml(schedule_path, schedule)
        print(f"ERROR: {root_result}")
        return 1

    posted_at = timestamp_jst()
    item["threads_post_id"] = root_post_id
    item["posted_at"] = posted_at
    item["error"] = ""

    append_yaml_list(
        posted_log_path,
        {
            "post_id": root_post_id,
            "date": date,
            "time_slot": time_slot,
            "category": item.get("category", ""),
            "character": item.get("character", ""),
            "thread_index": 1,
            "thread_role": "root",
            "text_head": text[:80],
            "image_url": image_url,
            "posted_at": posted_at,
        },
    )
    print(f"Posted root: {root_post_id}")

    reply_ids: list[str] = []
    parent_id = root_post_id

    for part in thread_posts:
        reply_to_id = parent_id
        result = publish_one(
            api,
            str(part.get("text", "")).strip(),
            image_url=str(part.get("image_url", "")).strip(),
            alt=str(part.get("alt", "")).strip(),
            reply_to_id=reply_to_id,
        )
        if "error" in result:
            item["status"] = "error"
            item["error"] = f"Thread reply {part['index']} failed: {str(result['error'])[:400]}"
            item["error_at"] = timestamp_jst()
            item["thread_post_ids"] = reply_ids
            save_yaml(schedule_path, schedule)
            print(f"ERROR: {result}")
            return 1

        reply_id = str(result.get("id", ""))
        if not reply_id:
            item["status"] = "error"
            item["error"] = f"No reply post id in result: {result}"
            item["error_at"] = timestamp_jst()
            item["thread_post_ids"] = reply_ids
            save_yaml(schedule_path, schedule)
            print(f"ERROR: {result}")
            return 1

        reply_ids.append(reply_id)
        parent_id = reply_id
        reply_posted_at = timestamp_jst()
        append_yaml_list(
            posted_log_path,
            {
                "post_id": reply_id,
                "date": date,
                "time_slot": time_slot,
                "category": item.get("category", ""),
                "character": item.get("character", ""),
                "thread_index": int(part["index"]) + 1,
                "thread_role": "reply",
                "reply_to_id": reply_to_id,
                "text_head": str(part.get("text", ""))[:80],
                "image_url": str(part.get("image_url", "")),
                "posted_at": reply_posted_at,
            },
        )
        print(f"Posted reply {part['index']}: {reply_id}")

    item["status"] = "posted"
    item["thread_post_ids"] = reply_ids
    item["thread_count"] = 1 + len(reply_ids)
    save_yaml(schedule_path, schedule)

    print(f"Posted thread root={root_post_id} replies={len(reply_ids)}")
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
