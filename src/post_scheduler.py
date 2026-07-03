"""Scan all schedules and publish at most one due parent post."""
from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .schedule_store import ScheduleFile, load_active_schedule_files, save_schedule_file
from .scheduler_core import JST, iso_jst, materialize, parse_dt, select_candidate
from .threads_api import ThreadsAPI
from .utils import append_yaml_list, repo_path, require_env


def now_jst() -> datetime:
    return datetime.now(ZoneInfo("Asia/Tokyo"))


def normalize_thread_posts(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError("thread_posts must be a list")
    result = []
    for index, value in enumerate(raw, start=1):
        part = {"text": value} if isinstance(value, str) else value
        if not isinstance(part, dict):
            raise ValueError(f"thread_posts[{index}] must be dict or string")
        text = str(part.get("text", "")).strip()
        image_url = str(part.get("image_url", "")).strip()
        if text or image_url:
            result.append({"index": index, "text": text, "image_url": image_url, "alt": str(part.get("alt", "")).strip()})
    return result


def publish_one(api: ThreadsAPI, text: str, image_url: str = "", alt: str = "", reply_to_id: str = "") -> dict[str, Any]:
    if image_url:
        return api.post_image(text, image_url, alt_text=alt, reply_to_id=reply_to_id)
    return api.post_text(text, reply_to_id=reply_to_id)


def git_checkpoint(paths: list[Path], message: str) -> None:
    if os.getenv("AUTO_COMMIT_PROGRESS", "").lower() != "true":
        return
    relative = [str(path.relative_to(repo_path())) for path in paths]
    subprocess.run(["git", "add", *relative], cwd=repo_path(), check=True)
    clean = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_path())
    if clean.returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", message], cwd=repo_path(), check=True)
    subprocess.run(["git", "push"], cwd=repo_path(), check=True)


def save_checkpoint(sf: ScheduleFile, item: dict[str, Any], message: str) -> None:
    progress = item.setdefault("thread_progress", {})
    progress["updated_at"] = iso_jst(now_jst())
    save_schedule_file(sf)
    git_checkpoint([sf.path], message)


def log_post(item: dict[str, Any], post_id: str, role: str, index: int, reply_to_id: str = "") -> None:
    append_yaml_list(repo_path("posts", "posted_log.yml"), {
        "post_id": post_id,
        "schedule_id": item.get("id", ""),
        "date": item.get("date", ""),
        "time_slot": item.get("time_slot", ""),
        "category": item.get("category", ""),
        "thread_index": index,
        "thread_role": role,
        "reply_to_id": reply_to_id,
        "posted_at": iso_jst(now_jst()),
    })


def find_file(files: list[ScheduleFile], item: dict[str, Any]) -> ScheduleFile:
    for sf in files:
        if any(entry is item for entry in sf.entries):
            return sf
    raise RuntimeError("schedule file not found")


def publish(item: dict[str, Any], sf: ScheduleFile, api: ThreadsAPI, rng: random.Random) -> int:
    if str(item.get("status", "")).lower() == "posted":
        print("Already posted; skipped.")
        return 0
    text = str(item.get("text", "")).strip()
    if not text:
        raise ValueError("Schedule item has no text")

    parts = normalize_thread_posts(item.get("thread_posts", []))
    progress = item.setdefault("thread_progress", {})
    reply_ids = [str(x) for x in progress.get("reply_ids", [])]
    completed = int(progress.get("completed_replies", len(reply_ids)))
    root_id = str(progress.get("root_post_id") or item.get("threads_post_id") or "").strip()

    item["status"] = "posting"
    item["error"] = ""
    save_checkpoint(sf, item, f"chore: mark {item['id']} posting")

    if not root_id:
        result = publish_one(api, text, str(item.get("image_url", "")).strip(), str(item.get("alt", "")).strip())
        if "error" in result or not result.get("id"):
            item["status"] = "error"
            item["error"] = f"Root post failed: {str(result.get('error') or result)[:500]}"
            item["error_at"] = iso_jst(now_jst())
            save_checkpoint(sf, item, f"chore: record {item['id']} root error")
            return 1
        root_id = str(result["id"])
        item["threads_post_id"] = root_id
        progress["root_post_id"] = root_id
        progress["reply_ids"] = reply_ids
        progress["completed_replies"] = completed
        log_post(item, root_id, "root", 1)
        save_checkpoint(sf, item, f"chore: checkpoint {item['id']} root")
        print(f"Posted root: {root_id}")

    low = int(item.get("thread_delay_min_seconds", 8))
    high = int(item.get("thread_delay_max_seconds", 25))
    if low < 0 or high < low:
        raise ValueError(f"invalid thread delay range: {low}-{high}")
    parent_id = reply_ids[-1] if reply_ids else root_id

    for part in parts[completed:]:
        time.sleep(rng.randint(low, high))
        reply_to_id = parent_id
        result = publish_one(api, part["text"], part["image_url"], part["alt"], reply_to_id)
        if "error" in result or not result.get("id"):
            item["status"] = "error"
            item["error"] = f"Thread reply {part['index']} failed: {str(result.get('error') or result)[:400]}"
            item["error_at"] = iso_jst(now_jst())
            progress["reply_ids"] = reply_ids
            progress["completed_replies"] = completed
            save_checkpoint(sf, item, f"chore: record {item['id']} reply error")
            return 1
        reply_id = str(result["id"])
        reply_ids.append(reply_id)
        completed += 1
        parent_id = reply_id
        progress["reply_ids"] = reply_ids
        progress["completed_replies"] = completed
        log_post(item, reply_id, "reply", completed + 1, reply_to_id)
        save_checkpoint(sf, item, f"chore: checkpoint {item['id']} reply {completed}")
        print(f"Posted reply {part['index']}: {reply_id}")

    item["status"] = "posted"
    item["posted_at"] = iso_jst(now_jst())
    item["thread_post_ids"] = reply_ids
    item["thread_count"] = 1 + len(reply_ids)
    item["error"] = ""
    progress["root_post_id"] = root_id
    progress["reply_ids"] = reply_ids
    progress["completed_replies"] = completed
    save_checkpoint(sf, item, f"chore: complete {item['id']}")
    return 0


def run(dry_run: bool = False, requested_id: str = "", allow_out_of_order: bool = False, current_time: datetime | None = None, seed: int | None = None) -> int:
    now = (current_time or now_jst()).astimezone(JST)
    rng = random.Random(seed)
    files = load_active_schedule_files(include_past=True)
    changed = [sf for sf in files if materialize(sf, rng)]

    if not dry_run:
        for sf in changed:
            save_schedule_file(sf)
        if changed:
            git_checkpoint([sf.path for sf in changed], "chore: materialize immutable publish times")

    items = [item for sf in files for item in sf.entries if isinstance(item, dict)]
    candidate = select_candidate(items, now, requested_id, allow_out_of_order)
    if not candidate:
        print("No eligible post found.")
        return 0
    print(f"Candidate id={candidate.get('id')} publish_after={candidate.get('publish_after')} status={candidate.get('status')}")
    print(str(candidate.get("text", ""))[:300])
    if dry_run:
        print("Dry run. No API call or YAML update was performed.")
        return 0

    api = ThreadsAPI(require_env("BIKANSAN_ACCESS_TOKEN"), require_env("BIKANSAN_USER_ID"))
    return publish(candidate, find_file(files, candidate), api, rng)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--id", default="")
    parser.add_argument("--allow-out-of-order", action="store_true")
    parser.add_argument("--now", default="")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    now = parse_dt(args.now) if args.now else None
    sys.exit(run(args.dry_run, args.id, args.allow_out_of_order, now, args.seed))


if __name__ == "__main__":
    main()
