"""Split legacy posts/schedule.yml into weekly schedule files."""
from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from .schedule_store import (
    LEGACY_SCHEDULE_PATH,
    SCHEDULES_DIR,
    parse_date,
    save_schedule_file,
    schedule_path_for_date,
    week_bounds,
    ScheduleFile,
)
from .utils import load_yaml


def split_schedule(overwrite: bool = False) -> int:
    data = load_yaml(LEGACY_SCHEDULE_PATH, default=[])
    if not isinstance(data, list):
        raise ValueError("posts/schedule.yml must be a YAML list.")

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    skipped = 0

    for item in data:
        if not isinstance(item, dict) or not item.get("date"):
            skipped += 1
            continue
        d = parse_date(str(item["date"]))
        start, end = week_bounds(d)
        groups[(start.isoformat(), end.isoformat())].append(item)

    SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0

    for (start_raw, end_raw), entries in sorted(groups.items()):
        start = parse_date(start_raw)
        end = parse_date(end_raw)
        path = schedule_path_for_date(start)
        if path.exists() and not overwrite:
            print(f"skip existing: {path}")
            continue
        save_schedule_file(ScheduleFile(path=path, start=start, end=end, entries=entries))
        print(f"wrote: {path} entries={len(entries)}")
        written += 1

    print(f"split schedule files written: {written}")
    print(f"skipped invalid entries: {skipped}")
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    split_schedule(overwrite=args.overwrite)


if __name__ == "__main__":
    main()
