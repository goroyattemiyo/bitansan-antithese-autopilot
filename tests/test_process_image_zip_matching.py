from __future__ import annotations

import unittest

from src.process_image_zip import (
    normalize_time_slot,
    parse_filename,
    select_schedule_item,
    update_schedule_entries,
)


class ImageFilenameMatchingTests(unittest.TestCase):
    def test_night_is_normalized_to_evening(self):
        meta = parse_filename("2026-07-21_night_bitansan_sonemi_anxiety")
        self.assertEqual("2026-07-21", meta["date"])
        self.assertEqual("evening", meta["time_slot"])
        self.assertEqual("sonemi_anxiety", meta["category"])

    def test_simple_date_and_topic_is_allowed(self):
        meta = parse_filename("2026-07-21_sonemi_anxiety")
        self.assertEqual("evening", meta["time_slot"])
        self.assertEqual("sonemi_anxiety", meta["category"])

    def test_date_only_is_allowed(self):
        meta = parse_filename("2026-07-21")
        self.assertEqual("evening", meta["time_slot"])
        self.assertEqual("", meta["category"])

    def test_date_only_matches_unique_post(self):
        schedule = [
            {
                "date": "2026-07-21",
                "time_slot": "evening",
                "category": "emotional_scene",
            }
        ]
        entry = {
            "date": "2026-07-21",
            "time_slot": "evening",
            "category": "sonemi_anxiety",
        }
        self.assertIs(schedule[0], select_schedule_item(schedule, entry))

    def test_category_mismatch_does_not_block_linking(self):
        schedule = [
            {
                "date": "2026-07-21",
                "time_slot": "evening",
                "category": "emotional_scene",
                "status": "draft",
            }
        ]
        entry = {
            "date": "2026-07-21",
            "time_slot": "night",
            "category": "sonemi_anxiety",
            "local_webp": "assets/webp/example.webp",
            "image_url": "https://example.invalid/example.webp",
        }
        count = update_schedule_entries(schedule, [entry])
        self.assertEqual(1, count)
        self.assertEqual("ready", schedule[0]["status"])
        self.assertEqual(entry["image_url"], schedule[0]["image_url"])

    def test_ambiguous_date_does_not_guess_wrong_post(self):
        schedule = [
            {"date": "2026-07-21", "time_slot": "morning"},
            {"date": "2026-07-21", "time_slot": "evening"},
        ]
        entry = {
            "date": "2026-07-21",
            "time_slot": "afternoon",
            "category": "",
        }
        self.assertIsNone(select_schedule_item(schedule, entry))

    def test_slot_alias_helper(self):
        self.assertEqual("evening", normalize_time_slot("night"))
        self.assertEqual("morning", normalize_time_slot("am"))


if __name__ == "__main__":
    unittest.main()
