from __future__ import annotations

import argparse
from typing import Any

from .schedule_store import load_active_schedule_files, save_schedule_file

SONG_URLS = {
    "01": "https://suno.com/s/cVsGi56XmJtlAdwf",
    "02": "https://suno.com/s/es5rbgIz7aJZQSEL",
    "03": "https://suno.com/s/M3w0Mfr6sacsz4QQ",
    "04": "https://suno.com/s/1lBRaI56R2ewBbLX",
    "05": "https://suno.com/s/WXu10C1NgEBnd1N4",
}

SONG_TITLES = {
    "01": "いいね、奪ってあげる。",
    "02": "センター病棟",
    "03": "わたしじゃダメなの？",
    "04": "毒蜜シンドローム",
    "05": "共犯者コール",
}

TITLE_KEYS = {
    "01": ["song_01", "song01", "いいね", "奪って", "01「"],
    "02": ["song_02", "song02", "センター病棟", "02「"],
    "03": ["song_03", "song03", "わたしじゃダメなの", "03「"],
    "04": ["song_04", "song04", "毒蜜シンドローム", "04「"],
    "05": ["song_05", "song05", "共犯者コール", "05「"],
}


def find_song_no(item: dict[str, Any]) -> str | None:
    category = str(item.get("category", ""))
    theme = str(item.get("theme", ""))
    text = str(item.get("text", ""))
    haystack = "\n".join([category, theme, text])

    for song_no, keys in TITLE_KEYS.items():
        if any(key in haystack for key in keys):
            return song_no
    return None


def strip_inline_suno_url(text: str) -> str:
    lines = text.rstrip().splitlines()
    cleaned: list[str] = []
    skip_next_url = False

    for line in lines:
        stripped = line.strip()
        if stripped in {"聴く：", "聴く:"}:
            skip_next_url = True
            continue
        if skip_next_url and "suno.com/s/" in stripped:
            skip_next_url = False
            continue
        skip_next_url = False
        cleaned.append(line)

    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned)


def make_link_reply(song_no: str, url: str) -> str:
    title = SONG_TITLES[song_no]
    return f"聴く：\n{song_no}「{title}」\n{url}"


def make_follow_reply(song_no: str) -> str:
    title = SONG_TITLES[song_no]
    return f"{song_no}「{title}」を聴いたら、感想を教えてください。\n\n共犯者たちの反応、マネージャーが見ています。"


def thread_has_url(thread_posts: list[Any], url: str) -> bool:
    for part in thread_posts:
        if isinstance(part, dict) and url in str(part.get("text", "")):
            return True
        if isinstance(part, str) and url in part:
            return True
    return False


def update_entries(entries: list[dict[str, Any]]) -> int:
    updated = 0
    for item in entries:
        if not isinstance(item, dict):
            continue
        song_no = find_song_no(item)
        if not song_no:
            continue

        url = SONG_URLS[song_no]
        item["song_url"] = url
        item["song_no"] = song_no
        item["text"] = strip_inline_suno_url(str(item.get("text", "")))

        thread_posts = item.get("thread_posts", [])
        if not isinstance(thread_posts, list):
            thread_posts = []

        if not thread_has_url(thread_posts, url):
            thread_posts.append({"text": make_link_reply(song_no, url)})
            thread_posts.append({"text": make_follow_reply(song_no)})
            item["thread_posts"] = thread_posts
            updated += 1
        else:
            item["thread_posts"] = thread_posts
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Also process past weekly schedule files.")
    args = parser.parse_args()

    schedule_files = load_active_schedule_files(include_past=args.all)
    total = 0

    for schedule_file in schedule_files:
        updated = update_entries(schedule_file.entries)
        if updated:
            save_schedule_file(schedule_file)
        print(f"{schedule_file.path}: updated={updated}")
        total += updated

    print(f"updated song thread entries: {total}")


if __name__ == "__main__":
    main()
