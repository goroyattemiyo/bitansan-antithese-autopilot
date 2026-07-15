"""Collect weekly insights for recently posted Threads posts."""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .threads_api import ThreadsAPI
from .utils import (
    JST,
    load_yaml,
    now_jst,
    repo_path,
    save_yaml,
    require_env,
    timestamp_jst,
    today_jst_str,
)

METRIC_NAMES = ("views", "likes", "replies", "reposts", "quotes")
LEGACY_LOG_PATH = repo_path("posts", "insights_log.yml")
MONTHLY_LOG_DIR = repo_path("posts", "insights")
LATEST_PATH = repo_path("posts", "insights_latest.yml")


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
        value = None
        raw_values = item.get("values")
        if isinstance(raw_values, list) and raw_values:
            first = raw_values[0]
            if isinstance(first, dict):
                value = first.get("value")
        if name:
            values[str(name)] = value
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


def _load_list(path: Path) -> list[Any]:
    data = load_yaml(path, default=[])
    if not isinstance(data, list):
        raise ValueError(f"YAML file must be a list: {path}")
    return data


def _monthly_path(moment: datetime | None = None) -> Path:
    moment = moment or now_jst()
    return MONTHLY_LOG_DIR / f"{moment.strftime('%Y-%m')}.yml"


def _all_history() -> list[Any]:
    """Load legacy history and month-partitioned logs."""
    history: list[Any] = []
    if LEGACY_LOG_PATH.exists():
        history.extend(_load_list(LEGACY_LOG_PATH))
    if MONTHLY_LOG_DIR.exists():
        for path in sorted(MONTHLY_LOG_DIR.glob("????-??.yml")):
            history.extend(_load_list(path))
    return history


def _already_collected_today(log: list[Any], post_id: str, today: str) -> bool:
    for entry in reversed(log):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("post_id", "")) != post_id:
            continue
        if str(entry.get("collected_at", "")).startswith(today):
            return True
    return False


def _parse_posted_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _is_recent(item: dict[str, Any], active_days: int) -> bool:
    """Collect only posts inside the active analysis window."""
    posted_at = _parse_posted_at(item.get("posted_at"))
    if posted_at is None:
        return True
    cutoff = now_jst() - timedelta(days=max(active_days, 1))
    return posted_at >= cutoff


def _post_metadata(item: dict[str, Any]) -> dict[str, Any]:
    """Copy compact safe fields; full text remains in schedule YAML."""
    return {
        "schedule_id": item.get("schedule_id", ""),
        "scheduled_at": item.get("scheduled_at", ""),
        "posted_at": item.get("posted_at", ""),
        "category": item.get("category", ""),
        "series_id": item.get("series_id", ""),
        "thread_index": item.get("thread_index", 1),
        "thread_role": item.get("thread_role", "root"),
    }


def _build_latest(log: list[Any]) -> list[dict[str, Any]]:
    """Build one latest successful snapshot per post, newest post first."""
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
        key=lambda value: str(value.get("posted_at") or value.get("collected_at", "")),
        reverse=True,
    )


def collect(
    limit: int = 30,
    force: bool = False,
    active_days: int = 30,
    request_delay_seconds: float = 1.0,
) -> int:
    if request_delay_seconds < 0:
        raise ValueError("request_delay_seconds must be zero or greater")

    posted_log = _load_list(repo_path("posts", "posted_log.yml"))
    monthly_path = _monthly_path()
    monthly_log = _load_list(monthly_path)
    history = _all_history()

    api = ThreadsAPI(
        access_token=require_env("BIKANSAN_ACCESS_TOKEN"),
        user_id=require_env("BIKANSAN_USER_ID"),
    )

    today = today_jst_str()
    count = 0
    skipped_today = 0
    skipped_old = 0
    for item in reversed(posted_log[-limit:]):
        if not isinstance(item, dict):
            continue
        post_id = str(item.get("post_id", "")).strip()
        if not post_id:
            continue
        if not _is_recent(item, active_days):
            skipped_old += 1
            continue
        if not force and _already_collected_today(history, post_id, today):
            skipped_today += 1
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
        monthly_log.append(entry)
        history.append(entry)
        print(f"collected insights: {post_id}")
        count += 1

        if request_delay_seconds:
            time.sleep(request_delay_seconds)

    save_yaml(monthly_path, monthly_log)
    save_yaml(LATEST_PATH, _build_latest(history))
    print(
        f"collected count: {count}; skipped today: {skipped_today}; "
        f"skipped older than {active_days} days: {skipped_old}"
    )
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--active-days", type=int, default=30)
    parser.add_argument("--request-delay-seconds", type=float, default=1.0)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Collect again when a snapshot already exists for today (JST).",
    )
    args = parser.parse_args()
    collect(
        limit=args.limit,
        force=args.force,
        active_days=args.active_days,
        request_delay_seconds=args.request_delay_seconds,
    )


if __name__ == "__main__":
    main()
