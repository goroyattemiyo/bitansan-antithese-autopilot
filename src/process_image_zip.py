from __future__ import annotations

import argparse
import os
import re
import tempfile
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from .schedule_store import load_schedule_files_for_dates, parse_date, save_schedule_file

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_TIME_SLOT = "evening"
DEFAULT_REPOSITORY = "goroyattemiyo/bitansan-antithese-autopilot"
DEFAULT_BRANCH = "main"

REPO_ROOT = Path(__file__).resolve().parents[1]
INCOMING_DIR = REPO_ROOT / "incoming"
WEBP_DIR = REPO_ROOT / "assets" / "webp"
IMAGE_URLS_PATH = REPO_ROOT / "posts" / "image_urls.yml"

DATE_PREFIX_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})(?:_(?P<rest>.*))?$")
DATE_ANY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

TIME_SLOT_ALIASES = {
    "morning": "morning",
    "am": "morning",
    "朝": "morning",
    "noon": "noon",
    "lunch": "noon",
    "昼": "noon",
    "afternoon": "afternoon",
    "pm": "afternoon",
    "午後": "afternoon",
    "evening": "evening",
    "night": "evening",
    "eve": "evening",
    "夜": "evening",
    "summary": "summary",
}


def load_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return default
    data = yaml.safe_load(text)
    return default if data is None else data


def save_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def github_raw_url(file_path: Path) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
    branch = os.environ.get("GITHUB_REF_NAME", DEFAULT_BRANCH)
    if branch.startswith("refs/heads/"):
        branch = branch.removeprefix("refs/heads/")
    branch = branch or DEFAULT_BRANCH
    relative_path = str(file_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{relative_path}"


def find_zip_files(incoming_dir: Path) -> list[Path]:
    if not incoming_dir.exists():
        return []
    return sorted(p for p in incoming_dir.glob("*.zip") if p.is_file())


def find_standalone_images(incoming_dir: Path) -> list[Path]:
    if not incoming_dir.exists():
        return []
    return sorted(
        p for p in incoming_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def normalize_time_slot(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return TIME_SLOT_ALIASES.get(raw, raw)


def _extract_slot_and_category(rest: str) -> tuple[str, str]:
    if not rest:
        return DEFAULT_TIME_SLOT, ""

    tokens = [token for token in rest.split("_") if token]
    if not tokens:
        return DEFAULT_TIME_SLOT, ""

    first = tokens[0]
    normalized = normalize_time_slot(first)
    if first.lower() in TIME_SLOT_ALIASES or first in TIME_SLOT_ALIASES:
        remaining = tokens[1:]
        if remaining and remaining[0].lower() == "bitansan":
            remaining = remaining[1:]
        return normalized, "_".join(remaining)

    # A date plus a free-form topic is still usable. The schedule matcher will
    # pick the only post on that date, or the default evening post.
    return DEFAULT_TIME_SLOT, rest.removeprefix("bitansan_")


def parse_filename(stem: str) -> dict[str, str]:
    match = DATE_PREFIX_RE.fullmatch(stem)
    if not match:
        raise ValueError(
            f"Invalid filename format: {stem}. Filename must begin with YYYY-MM-DD."
        )

    slot, category = _extract_slot_and_category(match.group("rest") or "")
    return {
        "date": match.group("date"),
        "time_slot": normalize_time_slot(slot) or DEFAULT_TIME_SLOT,
        "category": category,
    }


def try_parse_filename(stem: str) -> dict[str, str] | None:
    try:
        return parse_filename(stem)
    except ValueError:
        return None


def daterange(start: date, end: date) -> list[date]:
    if end < start:
        return []
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def infer_metas_from_zip_stem(
    zip_stem: str, image_count: int
) -> list[dict[str, str]] | None:
    direct_meta = try_parse_filename(zip_stem)
    if direct_meta is not None and image_count == 1:
        return [direct_meta]

    date_strings = DATE_ANY_RE.findall(zip_stem)
    if len(date_strings) < 2:
        return None

    start = datetime.strptime(date_strings[0], "%Y-%m-%d").date()
    end = datetime.strptime(date_strings[1], "%Y-%m-%d").date()
    dates = daterange(start, end)
    if len(dates) != image_count:
        print(
            f"warning: zip date range {date_strings[0]} to {date_strings[1]} "
            f"contains {len(dates)} days, but zip has {image_count} image(s)."
        )
        return None

    return [
        {"date": day.isoformat(), "time_slot": DEFAULT_TIME_SLOT, "category": ""}
        for day in dates
    ]


def meta_to_stem(meta: dict[str, str]) -> str:
    date_part = meta["date"]
    time_slot = normalize_time_slot(meta.get("time_slot", DEFAULT_TIME_SLOT)) or DEFAULT_TIME_SLOT
    category = meta.get("category", "")
    if category:
        return f"{date_part}_{time_slot}_bitansan_{category}"
    return f"{date_part}_{time_slot}"


def convert_to_webp(src_path: Path, dst_path: Path, quality: int = 90) -> Path:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    if src_path.suffix.lower() == ".webp":
        dst_path.write_bytes(src_path.read_bytes())
        return dst_path
    with Image.open(src_path) as img:
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.save(dst_path, "WEBP", quality=quality, method=6)
    return dst_path


def build_entry(
    src: Path,
    source_label: str,
    quality: int = 90,
    publish_url: bool = True,
    fallback_meta: dict[str, str] | None = None,
) -> dict[str, Any]:
    meta = try_parse_filename(src.stem)
    inferred_from = "image_filename"
    if meta is None:
        if fallback_meta is None:
            raise ValueError(
                f"Invalid filename format: {src.stem}. Include a YYYY-MM-DD date "
                "in the image filename or use a dated ZIP filename."
            )
        meta = fallback_meta
        inferred_from = "zip_filename"

    final_stem = src.stem if inferred_from == "image_filename" else meta_to_stem(meta)
    dst = WEBP_DIR / f"{final_stem}.webp"
    convert_to_webp(src, dst, quality=quality)

    image_url = github_raw_url(dst) if publish_url else ""
    if image_url:
        print(f"public image URL: {dst.name} -> {image_url}")
    else:
        print(f"converted: {dst.name}")

    return {
        "source": source_label,
        "file": src.name,
        "stem": final_stem,
        "original_stem": src.stem,
        "inferred_from": inferred_from,
        "date": meta["date"],
        "time_slot": normalize_time_slot(meta.get("time_slot")) or DEFAULT_TIME_SLOT,
        "category": meta.get("category", ""),
        "local_webp": str(dst.relative_to(REPO_ROOT)).replace("\\", "/"),
        "image_url": image_url,
        "image_host": "github_raw" if image_url else "local",
        "status": "github_raw" if image_url else "converted",
    }


def _candidate_items(schedule: list[dict[str, Any]], target_date: str) -> list[dict[str, Any]]:
    return [
        item
        for item in schedule
        if isinstance(item, dict) and str(item.get("date", "")) == target_date
    ]


def select_schedule_item(
    schedule: list[dict[str, Any]], entry: dict[str, Any]
) -> dict[str, Any] | None:
    candidates = _candidate_items(schedule, entry["date"])
    if not candidates:
        return None

    target_slot = normalize_time_slot(entry.get("time_slot"))
    slot_matches = [
        item
        for item in candidates
        if normalize_time_slot(item.get("time_slot")) == target_slot
    ]
    if len(slot_matches) == 1:
        return slot_matches[0]

    # When a date has only one post, the date is sufficient. This supports
    # simple filenames such as 2026-07-21.png or 2026-07-21_any-topic.png.
    if len(candidates) == 1:
        print(
            f"info: matched image by date only: {entry['date']} "
            f"({entry.get('time_slot')} -> {candidates[0].get('time_slot')})"
        )
        return candidates[0]

    # Prefer the normal evening post when the image uses night/evening or no
    # meaningful time token and several posts exist on the same date.
    evening_matches = [
        item
        for item in candidates
        if normalize_time_slot(item.get("time_slot")) == DEFAULT_TIME_SLOT
    ]
    if target_slot == DEFAULT_TIME_SLOT and len(evening_matches) == 1:
        return evening_matches[0]

    return None


def update_schedule_entries(
    schedule: list[dict[str, Any]], entries: list[dict[str, Any]]
) -> int:
    updated_count = 0
    for entry in entries:
        item = select_schedule_item(schedule, entry)
        if item is None:
            print(
                f"warning: no unambiguous schedule entry found for "
                f"{entry['date']} {entry.get('time_slot')}"
            )
            continue

        target_category = entry.get("category", "")
        schedule_category = str(item.get("category", ""))
        if target_category and schedule_category and target_category != schedule_category:
            print(
                f"info: category label differs but image was linked by date/time: "
                f"schedule={schedule_category} image={target_category}"
            )

        item["local_webp"] = entry["local_webp"]
        item["image_url"] = entry["image_url"]
        item["status"] = "ready" if entry.get("image_url") else "draft"
        item["error"] = ""
        updated_count += 1
    return updated_count


def update_schedule_files(entries: list[dict[str, Any]]) -> int:
    dates = sorted({entry["date"] for entry in entries if entry.get("date")})
    schedule_files = load_schedule_files_for_dates(dates)
    total = 0
    for schedule_file in schedule_files:
        scoped_entries = [
            entry
            for entry in entries
            if schedule_file.contains(parse_date(entry["date"]))
        ]
        if not scoped_entries:
            continue
        count = update_schedule_entries(schedule_file.entries, scoped_entries)
        save_schedule_file(schedule_file)
        print(f"updated schedule file: {schedule_file.path} count={count}")
        total += count
    return total


def zip_image_members_in_order(
    zf: zipfile.ZipFile, extract_dir: Path
) -> list[Path]:
    zf.extractall(extract_dir)
    image_files: list[Path] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        member_path = Path(info.filename)
        if member_path.suffix.lower() not in SUPPORTED_EXTS:
            continue
        extracted_path = extract_dir / member_path
        if extracted_path.exists() and extracted_path.is_file():
            image_files.append(extracted_path)
    return image_files


def process_zip(
    zip_path: Path, quality: int = 90, publish_url: bool = True
) -> list[dict[str, Any]]:
    print(f"Processing zip: {zip_path}")
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_dir = Path(tmpdir) / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            image_files = zip_image_members_in_order(zf, extract_dir)
        if not image_files:
            raise RuntimeError(f"No image files found in zip: {zip_path.name}")

        fallback_metas = infer_metas_from_zip_stem(zip_path.stem, len(image_files))
        entries: list[dict[str, Any]] = []
        for index, src in enumerate(image_files):
            fallback_meta = fallback_metas[index] if fallback_metas else None
            entry = build_entry(
                src=src,
                source_label=zip_path.name,
                quality=quality,
                publish_url=publish_url,
                fallback_meta=fallback_meta,
            )
            entry["zip_file"] = zip_path.name
            entry["zip_index"] = index + 1
            entries.append(entry)
        return entries


def process_standalone_image(
    image_path: Path, quality: int = 90, publish_url: bool = True
) -> dict[str, Any]:
    print(f"Processing image: {image_path}")
    return build_entry(
        src=image_path,
        source_label="incoming",
        quality=quality,
        publish_url=publish_url,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Process incoming ZIP or image files into WebP files, public GitHub "
            "raw URLs, and schedule updates. Image filenames only need to begin "
            "with YYYY-MM-DD; night and evening are treated as the same slot."
        )
    )
    parser.add_argument("--userhash", default="", help="Ignored; retained for compatibility.")
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--delete-zip", action="store_true")
    args = parser.parse_args()

    WEBP_DIR.mkdir(parents=True, exist_ok=True)
    zip_files = find_zip_files(INCOMING_DIR)
    standalone_images = find_standalone_images(INCOMING_DIR)
    if not zip_files and not standalone_images:
        print("No zip or image files found in incoming/.")
        return

    all_entries: list[dict[str, Any]] = []
    processed_inputs: list[Path] = []
    publish_url = not args.no_upload

    for zip_path in zip_files:
        all_entries.extend(process_zip(zip_path, args.quality, publish_url))
        processed_inputs.append(zip_path)
    for image_path in standalone_images:
        all_entries.append(process_standalone_image(image_path, args.quality, publish_url))
        processed_inputs.append(image_path)

    if args.delete_zip:
        for path in processed_inputs:
            path.unlink(missing_ok=True)
            print(f"deleted incoming file: {path.name}")

    existing_urls = load_yaml(IMAGE_URLS_PATH, default=[])
    if not isinstance(existing_urls, list):
        existing_urls = []
    save_yaml(IMAGE_URLS_PATH, existing_urls + all_entries)
    print(f"saved: {IMAGE_URLS_PATH}")

    updated_count = update_schedule_files(all_entries)
    print(f"updated schedule count: {updated_count}")


if __name__ == "__main__":
    main()
