from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SCHEDULE_PATH = Path("posts/schedule.yml")

SONG_URLS = {
    "01": "https://suno.com/s/cVsGi56XmJtlAdwf",
    "02": "https://suno.com/s/es5rbgIz7aJZQSEL",
    "03": "https://suno.com/s/M3w0Mfr6sacsz4QQ",
    "04": "https://suno.com/s/1lBRaI56R2ewBbLX",
    "05": "https://suno.com/s/WXu10C1NgEBnd1N4",
}

TITLE_KEYS = {
    "01": ["01", "song_01", "song01", "いいね", "奪って"],
    "02": ["02", "song_02", "song02", "センター病棟"],
    "03": ["03", "song_03", "song03", "わたしじゃダメなの"],
    "04": ["04", "song_04", "song04", "毒蜜シンドローム"],
    "05": ["05", "song_05", "song05", "共犯者コール"],
}


def load_schedule() -> list[dict[str, Any]]:
    data = yaml.safe_load(SCHEDULE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("posts/schedule.yml must be a YAML list")
    return data


def dump_schedule(data: list[dict[str, Any]]) -> None:
    SCHEDULE_PATH.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def find_song_no(item: dict[str, Any]) -> str | None:
    category = str(item.get("category", ""))
    theme = str(item.get("theme", ""))
    text = str(item.get("text", ""))
    haystack = "\n".join([category, theme, text])

    for song_no, keys in TITLE_KEYS.items():
        if any(key in haystack for key in keys):
            return song_no
    return None


def append_url(text: str, url: str) -> str:
    if "suno.com/s/" in text or url in text:
        return text
    return text.rstrip() + "\n\n聴く：\n" + url


def main() -> None:
    schedule = load_schedule()
    updated = 0

    for item in schedule:
        if not isinstance(item, dict):
            continue
        song_no = find_song_no(item)
        if not song_no:
            continue
        url = SONG_URLS[song_no]
        old_text = str(item.get("text", ""))
        new_text = append_url(old_text, url)
        if new_text != old_text:
            item["text"] = new_text
            item["song_url"] = url
            item["song_no"] = song_no
            updated += 1
        else:
            item.setdefault("song_url", url)
            item.setdefault("song_no", song_no)

    dump_schedule(schedule)
    print(f"updated song URL entries: {updated}")


if __name__ == "__main__":
    main()
