from __future__ import annotations

import argparse
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import requests
import yaml
from PIL import Image

CATBOX_API_URL = "https://catbox.moe/user/api.php"
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_TIME_SLOT = "evening"

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


def upload_to_catbox(file_path: Path, userhash: str = "") -> str:
    data: dict[str, Any] = {"reqtype": "fileupload"}
    if userhash:
        data["userhash"] = userhash

    with file_path.open("rb") as f:
        files = {"fileToUpload": (file_path.name, f)}
        resp = requests.post(CATBOX_API_URL, data=data, files=files, timeout=120)

    resp.raise_for_status()
    result = resp.text.strip()
    if not result.startswith("http"):
        raise RuntimeError(f"Catbox upload failed: {result}")
    return result


def find_zip_files(incoming_dir: Path) -> list[Path]:
    if not incoming_dir.exists():
        return []
    return sorted(p for p in incoming_dir.glob("*.zip") if p.is_file())


def find_standalone_images(incoming_dir: Path) -> list[Path]:
    """Find images directly under incoming/.

    This avoids large ZIP uploads. Put files like incoming/2026-07-01.png directly.
    Images inside subfolders are ignored here; ZIP extraction still scans recursively.
    """
    if not incoming_dir.exists():
        return []
    return sorted(
        p
        for p in incoming_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def list_images(base_dir: Path) -> list[Path]:
    results: list[Path] = []
    for path in base_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
            results.append(path)
    return sorted(results)


def parse_filename(stem: str) -> dict[str, str]:
    """Parse image filename stem.

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
    userhash: str = "",
    quality: int = 90,
    upload: bool = True,
) -> dict[str, Any]:
    meta = parse_filename(src.stem)
    webp_name = f"{src.stem}.webp"
    dst = WEBP_DIR / webp_name
    convert_to_webp(src, dst, quality=quality)

    image_url = ""
    status = "converted"

    if upload:
        image_url = upload_to_catbox(dst, userhash=userhash)
        status = "uploaded"
        print(f"uploaded: {dst.name} -> {image_url}")
    else:
        print(f"converted: {dst.name}")

    return {
        "source": source_label,
        "file": src.name,
        "stem": src.stem,
        "date": meta["date"],
        "time_slot": meta["time_slot"],
        "category": meta["category"],
        "local_webp": str(dst.relative_to(REPO_ROOT)).replace("\\", "/"),
        "image_url": image_url,
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

            # categoryが指定されている場合だけ照合。日付だけの画像名なら警告なしで更新する。
            if target_category and item.get("category") and str(item.get("category")) != target_category:
                print(
                    f"warning: category mismatch for {target_date} {target_slot}: "
                    f"schedule={item.get('category')} zip={target_category}"
                )

            item["local_webp"] = entry["local_webp"]
            item["image_url"] = entry["image_url"]
            # Catbox URLがあるときだけ投稿可能にする。--no-upload時は誤投稿防止のためdraftのまま。
            item["status"] = "ready" if entry.get("image_url") else "draft"
            item["error"] = ""
            matched = True
            updated_count += 1
            break

        if not matched:
            print(f"warning: no matching schedule entry found for {target_date} {target_slot}")

    return schedule, updated_count


def process_zip(
    zip_path: Path,
    userhash: str = "",
    quality: int = 90,
    upload: bool = True,
) -> list[dict[str, Any]]:
    print(f"Processing zip: {zip_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        image_files = list_images(extract_dir)
        if not image_files:
            raise RuntimeError(f"No image files found in zip: {zip_path.name}")

        entries: list[dict[str, Any]] = []

        for src in image_files:
            entry = build_entry(
                src=src,
                source_label=zip_path.name,
                userhash=userhash,
                quality=quality,
                upload=upload,
            )
            entry["zip_file"] = zip_path.name
            entries.append(entry)

        return entries


def process_standalone_image(
    image_path: Path,
    userhash: str = "",
    quality: int = 90,
    upload: bool = True,
) -> dict[str, Any]:
    print(f"Processing image: {image_path}")
    return build_entry(
        src=image_path,
        source_label="incoming",
        userhash=userhash,
        quality=quality,
        upload=upload,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process incoming ZIP or standalone image files into WebP files, Catbox URLs, and schedule.yml updates."
    )
    parser.add_argument("--userhash", default="")
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--no-upload", action="store_true")
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

    for zip_path in zip_files:
        entries = process_zip(
            zip_path=zip_path,
            userhash=args.userhash,
            quality=args.quality,
            upload=not args.no_upload,
        )
        all_entries.extend(entries)
        processed_inputs.append(zip_path)

    for image_path in standalone_images:
        entry = process_standalone_image(
            image_path=image_path,
            userhash=args.userhash,
            quality=args.quality,
            upload=not args.no_upload,
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
