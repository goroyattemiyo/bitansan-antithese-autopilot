"""Collect daily insights for posted Threads posts."""
from __future__ import annotations

import argparse
from typing import Any

from .threads_api import ThreadsAPI
from .utils import load_yaml, repo_path, save_yaml, require_env, timestamp_jst, today_jst_str

METRIC_NAMES = ("views", "likes", "replies", "reposts", "quotes")


def flatten_insights(result: dict[str, Any]) -> dict[str, Any]:
    """Flatten Threads insights response into {metric: value}."""
    values: dict[str, Any] = {}
    data = result.get("data", [])
    if not isinstance(data, list):
        return {"raw": result}
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        val = None
        raw_values = item.get("values")
        if isinstance(raw_values, list) and raw_values:
            first = raw_values[0]
            if isinstance(first, dict):
                val = first.get("value")
        if name:
            values[str(name)] = val
    return values


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def calculate_rates(metrics: dict[str, Any]) -> dict[str, float]:
    """Return percentages useful for chat-based comparison."""
    views = _number(metrics.get("views"))
    likes = _number(metrics.get("likes"))
    replies = _number(metrics.get("replies"))
    reposts = _number(metrics.get("reposts"))
    quotes = _number(metrics.get("quotes"))
    if views <= 0:
        return {
            "engagement_rate_pct": 0.0,
            "reply_rate_pct": 0.0,
            "spread_rate_pct": 0.0,
        }
    return {
        "engagement_rate_pct": round((likes + replies + reposts + quotes) / views * 100, 2),
        "reply_rate_pct": round(replies / views * 100, 2),
        "spread_rate_pct": round((reposts + quotes) / views * 100, 2),
    }


def _already_collected_today(log: list[Any], post_id: str, today: str) -> bool:
    for entry in reversed(log):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("post_id", "")) != post_id:
            continue
        if str(entry.get("collected_at", "")).startswith(today):
            return True
    return False


def _post_metadata(item: dict[str, Any]) -> dict[str, Any]:
    """Copy safe fields needed by ChatGPT without exposing credentials."""
    return {
        "schedule_id": item.get("schedule_id", ""),
        "scheduled_at": item.get("scheduled_at", ""),
        "posted_at": item.get("posted_at", ""),
        "category": item.get("category", ""),
        "series_id": item.get("series_id", ""),
        "thread_index": item.get("thread_index", 1),
        "thread_role": item.get("thread_role", "root"),
        "text_head": item.get("text_head", ""),
        "image_url": item.get("image_url", ""),
    }


def _build_latest(log: list[Any]) -> list[dict[str, Any]]:
    """Build one latest successful snapshot per post, newest collection first."""
    latest_by_post: dict[str, dict[str, Any]] = {}
    for entry in log:
        if not isinstance(entry, dict):
            continue
        post_id = str(entry.get("post_id", "")).strip()
        if not post_id or entry.get("raw_error"):
            continue
        latest_by_post[post_id] = entry
    return sorted(
        latest_by_post.values(),
        key=lambda value: str(value.get("collected_at", "")),
        reverse=True,
    )


def collect(limit: int = 30, force: bool = False) -> int:
    posted_log = load_yaml(repo_path("posts", "posted_log.yml"), default=[])
    if not isinstance(posted_log, list):
        raise ValueError("posts/posted_log.yml must be a YAML list.")

    insights_path = repo_path("posts", "insights_log.yml")
    insights_log = load_yaml(insights_path, default=[])
    if not isinstance(insights_log, list):
        raise ValueError("posts/insights_log.yml must be a YAML list.")

    api = ThreadsAPI(
        access_token=require_env("BIKANSAN_ACCESS_TOKEN"),
        user_id=require_env("BIKANSAN_USER_ID"),
    )

    today = today_jst_str()
    count = 0
    skipped = 0
    for item in reversed(posted_log[-limit:]):
        if not isinstance(item, dict):
            continue
        post_id = str(item.get("post_id", "")).strip()
        if not post_id:
            continue
        if not force and _already_collected_today(insights_log, post_id, today):
            skipped += 1
            continue

        result = api.get_post_insights(post_id)
        metrics = flatten_insights(result) if "error" not in result else {}
        entry = {
            "post_id": post_id,
            "collected_at": timestamp_jst(),
            **_post_metadata(item),
            "metrics": {name: metrics.get(name, 0) for name in METRIC_NAMES},
            "rates": calculate_rates(metrics),
            "raw_error": result.get("error", ""),
        }
        insights_log.append(entry)
        print(f"collected insights: {post_id}")
        count += 1

    save_yaml(insights_path, insights_log)
    save_yaml(repo_path("posts", "insights_latest.yml"), _build_latest(insights_log))
    print(f"collected count: {count}; skipped today: {skipped}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Collect again even when a snapshot already exists for today (JST).",
    )
    args = parser.parse_args()
    collect(limit=args.limit, force=args.force)


if __name__ == "__main__":
    main()
