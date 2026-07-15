"""Process one explicit chat-created Threads insights request.

The workflow is triggered only when control/collect_insights.yml changes. A
separate state file records the last successful request_id so workflow reruns do
not repeat API reads.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .collect_insights import collect
from .utils import load_yaml, repo_path, save_yaml, timestamp_jst

REQUEST_PATH = repo_path("control", "collect_insights.yml")
STATE_PATH = repo_path("control", "collect_insights_state.yml")
REQUEST_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
MAX_LIMIT = 30
MAX_ACTIVE_DAYS = 90
MIN_REQUEST_DELAY_SECONDS = 1.0
MAX_REQUEST_DELAY_SECONDS = 30.0

Collector = Callable[..., int]


def _require_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return value


def _require_float(value: Any, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return result


def validate_request(raw: Any) -> dict[str, Any]:
    """Validate and normalize a request that is enabled for execution."""
    if not isinstance(raw, dict):
        raise ValueError("Insight request YAML must be a mapping")

    request_id = str(raw.get("request_id", "")).strip()
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError(
            "request_id must be 1-64 characters using letters, numbers, dot, underscore, colon, or hyphen"
        )

    force = raw.get("force", False)
    if not isinstance(force, bool):
        raise ValueError("force must be true or false")

    return {
        "request_id": request_id,
        "limit": _require_int(raw.get("limit", 30), "limit", 1, MAX_LIMIT),
        "active_days": _require_int(
            raw.get("active_days", 30), "active_days", 1, MAX_ACTIVE_DAYS
        ),
        "request_delay_seconds": _require_float(
            raw.get("request_delay_seconds", MIN_REQUEST_DELAY_SECONDS),
            "request_delay_seconds",
            MIN_REQUEST_DELAY_SECONDS,
            MAX_REQUEST_DELAY_SECONDS,
        ),
        "force": force,
    }


def process_request(
    request_path: Path = REQUEST_PATH,
    state_path: Path = STATE_PATH,
    collector: Collector = collect,
    timestamp_fn: Callable[[], str] = timestamp_jst,
) -> int:
    """Process the current request once and persist its successful request_id."""
    raw_request = load_yaml(request_path, default={})
    if not isinstance(raw_request, dict):
        raise ValueError("Insight request YAML must be a mapping")

    enabled = raw_request.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be true or false")
    if not enabled:
        print("Insight request is disabled; no API call was made.")
        return 0

    request = validate_request(raw_request)
    state = load_yaml(state_path, default={})
    if not isinstance(state, dict):
        raise ValueError("Insight request state YAML must be a mapping")

    if state.get("last_processed_request_id") == request["request_id"]:
        print(f"Insight request already processed: {request['request_id']}")
        return 0

    collected_count = collector(
        limit=request["limit"],
        force=request["force"],
        active_days=request["active_days"],
        request_delay_seconds=request["request_delay_seconds"],
    )

    save_yaml(
        state_path,
        {
            "last_processed_request_id": request["request_id"],
            "processed_at": timestamp_fn(),
            "collected_count": collected_count,
            "parameters": {
                "limit": request["limit"],
                "active_days": request["active_days"],
                "request_delay_seconds": request["request_delay_seconds"],
                "force": request["force"],
            },
        },
    )
    print(
        f"Processed insight request {request['request_id']}; "
        f"collected count: {collected_count}"
    )
    return collected_count


def main() -> None:
    process_request()


if __name__ == "__main__":
    main()
