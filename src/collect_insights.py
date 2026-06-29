"""Collect insights for posted Threads posts."""
from __future__ import annotations

import argparse
from typing import Any

from .threads_api import ThreadsAPI
from .utils import append_yaml_list, load_yaml, repo_path, require_env, timestamp_jst


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


def collect(limit: int = 30) -> int:
    posted_log = load_yaml(repo_path("posts", "posted_log.yml"), default=[])
    if not isinstance(posted_log, list):
        raise ValueError("posts/posted_log.yml must be a YAML list.")

    api = ThreadsAPI(
        access_token=require_env("BIKANSAN_ACCESS_TOKEN"),
        user_id=require_env("BIKANSAN_USER_ID"),
    )

    count = 0
    for item in reversed(posted_log[-limit:]):
        if not isinstance(item, dict):
            continue
        post_id = str(item.get("post_id", "")).strip()
        if not post_id:
            continue

        result = api.get_post_insights(post_id)
        entry = {
            "post_id": post_id,
            "collected_at": timestamp_jst(),
            "metrics": flatten_insights(result) if "error" not in result else {},
            "raw_error": result.get("error", ""),
        }
        append_yaml_list(repo_path("posts", "insights_log.yml"), entry)
        print(f"collected insights: {post_id}")
        count += 1

    print(f"collected count: {count}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    collect(limit=args.limit)


if __name__ == "__main__":
    main()
