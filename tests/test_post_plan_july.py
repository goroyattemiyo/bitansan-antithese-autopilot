from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEDULES = [
    ROOT / "posts/schedules/2026-07-13_to_2026-07-19.yml",
    ROOT / "posts/schedules/2026-07-20_to_2026-07-26.yml",
    ROOT / "posts/schedules/2026-07-27_to_2026-08-02.yml",
]
START = date(2026, 7, 16)
END = date(2026, 7, 30)


def load_entries() -> list[dict]:
    entries: list[dict] = []
    for path in SCHEDULES:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise AssertionError(f"schedule must be a list: {path}")
        entries.extend(item for item in data if isinstance(item, dict))
    return entries


class JulyPostPlanTests(unittest.TestCase):
    def setUp(self):
        self.entries = load_entries()
        self.active = [
            item
            for item in self.entries
            if START <= date.fromisoformat(str(item.get("date"))) <= END
            and str(item.get("status", "")).lower() in {"ready", "posting"}
        ]

    def test_exactly_one_active_post_per_day(self):
        counts: dict[str, int] = {}
        for item in self.active:
            counts[str(item["date"])] = counts.get(str(item["date"]), 0) + 1
        expected_dates = {
            (START.fromordinal(START.toordinal() + offset)).isoformat()
            for offset in range((END - START).days + 1)
        }
        self.assertEqual(expected_dates, set(counts))
        self.assertTrue(all(count == 1 for count in counts.values()), counts)

    def test_active_posts_are_evening_only(self):
        self.assertTrue(self.active)
        self.assertTrue(all(item.get("time_slot") == "evening" for item in self.active))

    def test_only_release_days_have_thread_replies(self):
        with_replies = {
            str(item["date"]): len(item.get("thread_posts") or [])
            for item in self.active
            if item.get("thread_posts")
        }
        self.assertEqual({"2026-07-20": 1, "2026-07-28": 1}, with_replies)

    def test_no_active_post_uses_draft_status(self):
        self.assertFalse(any(str(item.get("status")).lower() == "draft" for item in self.active))

    def test_future_character_alt_text_uses_green_short_hair(self):
        image_posts = [item for item in self.active if item.get("image_url")]
        self.assertTrue(image_posts)
        for item in image_posts:
            self.assertIn("そねみ（緑髪ショート）", str(item.get("alt", "")))


if __name__ == "__main__":
    unittest.main()
