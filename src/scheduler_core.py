"""Pure scheduling helpers for minute-level Threads reservations."""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .schedule_store import ScheduleFile

JST = ZoneInfo("Asia/Tokyo")
CUTOFF = datetime.fromisoformat("2026-07-03T18:31:49+09:00").astimezone(JST)
SLOT_TIMES = {
    "morning": "07:00:00",
    "noon": "12:00:00",
    "afternoon": "15:00:00",
    "evening": "17:00:00",
    "night": "20:00:00",
    "summary": "21:00:00",
}


def parse_dt(value: Any) -> datetime:
    result = datetime.fromisoformat(str(value))
    if result.tzinfo is None:
        result = result.replace(tzinfo=JST)
    return result.astimezone(JST)


def iso_jst(value: datetime) -> str:
    return value.astimezone(JST).isoformat(timespec="seconds")


def stable_id(sf: ScheduleFile, index: int, item: dict[str, Any]) -> str:
    raw = "|".join((sf.path.name, str(index), str(item.get("date", "")), str(item.get("time_slot", "")), str(item.get("category", ""))))
    return "post_" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def legacy_time(item: dict[str, Any]) -> datetime:
    slot = str(item.get("time_slot", ""))
    if slot not in SLOT_TIMES:
        raise ValueError(f"scheduled_at missing; unsupported time_slot={slot!r}")
    return parse_dt(f"{item['date']}T{SLOT_TIMES[slot]}+09:00")


def materialize(sf: ScheduleFile, rng: random.Random) -> bool:
    """Create immutable reservation fields once. Never redraw publish_after."""
    changed = False
    for index, item in enumerate(sf.entries):
        if not isinstance(item, dict):
            continue
        if not item.get("id"):
            item["id"] = stable_id(sf, index, item)
            changed = True
        if str(item.get("status", "")).lower() not in {"ready", "posting"}:
            continue
        was_legacy = not item.get("scheduled_at")
        scheduled = legacy_time(item) if was_legacy else parse_dt(item["scheduled_at"])
        if was_legacy:
            item["scheduled_at"] = iso_jst(scheduled)
            changed = True
            if scheduled <= CUTOFF and "migration_hold" not in item:
                item["migration_hold"] = True
                changed = True
        if "delay_min_minutes" not in item:
            item["delay_min_minutes"] = 2
            changed = True
        if "delay_max_minutes" not in item:
            item["delay_max_minutes"] = 14
            changed = True
        if not item.get("publish_after"):
            low, high = int(item["delay_min_minutes"]), int(item["delay_max_minutes"])
            if low < 0 or high < low:
                raise ValueError(f"invalid delay range for {item['id']}: {low}-{high}")
            delay = int(item.get("delay_minutes", rng.randint(low, high)))
            item["delay_minutes"] = delay
            item["publish_after"] = iso_jst(parse_dt(item["scheduled_at"]) + timedelta(minutes=delay))
            changed = True
        if "thread_delay_min_seconds" not in item:
            item["thread_delay_min_seconds"] = 8
            changed = True
        if "thread_delay_max_seconds" not in item:
            item["thread_delay_max_seconds"] = 25
            changed = True
    return changed


def series_key(item: dict[str, Any]) -> str:
    return str(item.get("series_id") or item.get("series") or item.get("sequence_group") or ("songs" if item.get("song_no") else "")).strip()


def order_key(item: dict[str, Any]) -> tuple[datetime, str]:
    return parse_dt(item["scheduled_at"]), str(item.get("id", ""))


def out_of_order_blocked(item: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    if item.get("allow_out_of_order"):
        return False
    key = series_key(item)
    if not key:
        return False
    current = order_key(item)
    return any(
        other is not item
        and series_key(other) == key
        and str(other.get("status", "")).lower() == "posted"
        and order_key(other) > current
        for other in items
    )


def select_candidate(items: list[dict[str, Any]], now: datetime, requested_id: str = "", force_order: bool = False) -> dict[str, Any] | None:
    due: list[dict[str, Any]] = []
    allowed_statuses = {"ready", "posting"}
    if requested_id:
        allowed_statuses.add("error")

    for item in items:
        status = str(item.get("status", "")).lower()
        if status not in allowed_statuses:
            continue
        if requested_id and item.get("id") != requested_id:
            continue
        if item.get("migration_hold") and not requested_id:
            continue
        if not requested_id and parse_dt(item["publish_after"]) > now:
            continue
        if item.get("threads_post_id") and status == "ready":
            item["status"] = "posting"
        if not force_order and out_of_order_blocked(item, items):
            continue
        due.append(item)
    if not due:
        return None
    return min(due, key=lambda x: (0 if x.get("status") == "posting" else 1, parse_dt(x["publish_after"]), parse_dt(x["scheduled_at"]), str(x.get("id", ""))))
