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

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_TIME_SLOT = "evening"
DEFAULT_REPOSITORY = "goroyattemiyo/bitansan-antithese-autopilot"
DEFAULT_BRANCH = "main"

REPO_ROOT = Path(__file__).resolve().parents[1]
INCOMING_DIR = REPO_ROOT / "incoming"
WEBP_DIR = REPO_ROOT / "assets" / "webp"
SCHEDULE_PATH = REPO_ROOT / "posts" / "schedule.yml"
IMAGE_URLS_PATH = REPO_ROOT / "posts" / "image_urls.yml"

FULL_FILENAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<time_slot>[a-zA-Z0-9-]+)_bitansan_(?P<category>[a-zA-Z0-9_-]+)$"
)
DATE_SLOT_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<time_slot>[a-zA-Z0-9-]+)$"
)
DATE_ONLY_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})$")
DATE_ANY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


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
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def github_raw_url(file_path: Path) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
    branch = os.environ.get("GITHUB_REF_NAME", DEFAULT_BRANCH)
    if branch.startswith("refs/heads/"):
        branch = branch.removeprefix("refs/heads/")
    if not branch:
        branch = DEFAULT_BRANCH

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
        p
        for p in incoming_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def parse_filename(stem: str) -> dict[str, str]:
    """Parse image or zip filename stem.

    Accepted formats:
    - 2026-07-01
    - 2026-07-01_evening
    - 2026-07-01_evening_bitansan_intro
    """
    full_match = FULL_FILENAME_RE.match(stem)
    if full_match:
        return {
            "date": full_match.group("date"),
            "time_slot": full_match.group("time_slot"),
            "category": full_match.group("category"),
        }

    slot_match = DATE_SLOT_RE.match(stem)
    if slot_match:
        return {
            "date": slot_match.group("date"),
            "time_slot": slot_match.group("time_slot"),
            "category": "",
        }

    date_match = DATE_ONLY_RE.match(stem)
    if date_match:
        return {
            "date": date_match.group("date"),
            "time_slot": DEFAULT_TIME_SLOT,
            "category": "",
        }

    raise ValueError(
        f"Invalid filename format: {stem} "
        "(accepted: YYYY-MM-DD, YYYY-MM-DD_evening, or YYYY-MM-DD_evening_bitansan_category)"
    )


def try_parse_filename(stem: str) -> dict[str, str] | None:
    try:
        return parse_filename(stem)
    except ValueError:
        return None


def daterange(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days = (end - start).days + 1
    return [start + timedelta(days=i) for i in range(days)]


def infer_metas_from_zip_stem(zip_stem: str, image_count: int) -> list[dict[str, str]] | None:
    """Infer posting dates from a ZIP filename.

    Supported examples:
    - 2026-07-01.zip with one image
    - 2026-07-01_evening.zip with one image
    - bitansan_images_2026-06-29_to_2026-07-03.zip with five images
    """
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
        {"date": d.isoformat(), "time_slot": DEFAULT_TIME_SLOT, "category": ""}
        for d in dates
    ]


def meta_to_stem(meta: dict[str, str]) -> str:
    date_part = meta["date"]
    time_slot = meta.get("time_slot", DEFAULT_TIME_SLOT) or DEFAULT_TIME_SLOT
    category = meta.get("category", "")

    if category:
        return f"{date_part}_{time_slot}_bitansan_{category}"
    if time_slot != DEFAULT_TIME_SLOT:
        return f"{date_part}_{time_slot}"
    return date_part


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
                f"Invalid filename format: {src.stem} "
                "and no usable ZIP filename fallback was available."
            )
        meta = fallback_meta
        inferred_from = "zip_filename"

    final_stem = src.stem if inferred_from == "image_filename" else meta_to_stem(meta)
    webp_name = f"{final_stem}.webp"
    dst = WEBP_DIR / webp_name
    convert_to_webp(src, dst, quality=quality)

    image_url = ""
    status = "converted"
    image_host = "local"

    if publish_url:
        image_url = github_raw_url(dst)
        status = "github_raw"
        image_host = "github_raw"
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
        "time_slot": meta["time_slot"],
        "category": meta["category"],
        "local_webp": str(dst.relative_to(REPO_ROOT)).replace("\\", "/"),
        "image_url": image_url,
        "image_host": image_host,
        "status": status,
    }


def update_schedule(
    schedule: list[dict[str, Any]], entries: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    updated_count = 0

    for entry in entries:
        target_date = entry["date"]
        target_slot = entry["time_slot"]
        target_category = entry.get("category", "")

        matched = False
        for item in schedule:
            if not isinstance(item, dict):
                continue

            if str(item.get("date", "")) != target_date:
                continue
            if str(item.get("time_slot", "")) != target_slot:
                continue

            if target_category and item.get("category") and str(item.get("category")) != target_category:
                print(
                    f"warning: category mismatch for {target_date} {target_slot}: "
                    f"schedule={item.get('category')} zip={target_category}"
                )

            item["local_webp"] = entry["local_webp"]
            item["image_url"] = entry["image_url"]
            item["status"] = "ready" if entry.get("image_url") else "draft"
            item["error"] = ""
            matched = True
            updated_count += 1
            break

        if not matched:
            print(f"warning: no matching schedule entry found for {target_date} {target_slot}")

    return schedule, updated_count


def zip_image_members_in_order(zf: zipfile.ZipFile, extract_dir: Path) -> list[Path]:
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
    zip_path: Path,
    quality: int = 90,
    publish_url: bool = True,
) -> list[dict[str, Any]]:
    print(f"Processing zip: {zip_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        extract_dir = tmp_path / "extracted"
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
    image_path: Path,
    quality: int = 90,
    publish_url: bool = True,
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
        description="Process incoming ZIP or standalone image files into WebP files, public GitHub raw URLs, and schedule.yml updates."
    )
    parser.add_argument("--userhash", default="", help="Ignored. Kept for backward compatibility with old Catbox workflow.")
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--no-upload", action="store_true", help="Convert only. Do not write public image URLs; schedule stays draft.")
    parser.add_argument(
        "--delete-zip",
        action="store_true",
        help="Delete processed incoming ZIP/image files after successful processing.",
    )
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
        entries = process_zip(
            zip_path=zip_path,
            quality=args.quality,
            publish_url=publish_url,
        )
        all_entries.extend(entries)
        processed_inputs.append(zip_path)

    for image_path in standalone_images:
        entry = process_standalone_image(
            image_path=image_path,
            quality=args.quality,
            publish_url=publish_url,
        )
        all_entries.append(entry)
        processed_inputs.append(image_path)

    if args.delete_zip:
        for path in processed_inputs:
            path.unlink(missing_ok=True)
            print(f"deleted incoming file: {path.name}")

    existing_urls = load_yaml(IMAGE_URLS_PATH, default=[])
    if not isinstance(existing_urls, list):
        existing_urls = []
    merged_urls = existing_urls + all_entries
    save_yaml(IMAGE_URLS_PATH, merged_urls)
    print(f"saved: {IMAGE_URLS_PATH}")

    schedule = load_yaml(SCHEDULE_PATH, default=[])
    if not isinstance(schedule, list):
        raise ValueError("posts/schedule.yml must be a YAML list.")

    updated_schedule, updated_count = update_schedule(schedule, all_entries)
    save_yaml(SCHEDULE_PATH, updated_schedule)
    print(f"updated schedule count: {updated_count}")


if __name__ == "__main__":
    main()
