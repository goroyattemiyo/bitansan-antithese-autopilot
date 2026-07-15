from __future__ import annotations

import random
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.schedule_store import ScheduleFile
from src.scheduler_core import JST, materialize, select_candidate


class SchedulerCoreTests(unittest.TestCase):
    def schedule_file(self, entries):
        return ScheduleFile(Path(tempfile.gettempdir()) / "2026-07-06_to_2026-07-12.yml", datetime(2026, 7, 6).date(), datetime(2026, 7, 12).date(), entries)

    def test_publish_after_is_created_once(self):
        item = {"date": "2026-07-06", "time_slot": "morning", "status": "ready"}
        sf = self.schedule_file([item])
        self.assertTrue(materialize(sf, random.Random(1)))
        first_delay = item["delay_minutes"]
        first_publish_after = item["publish_after"]
        self.assertFalse(materialize(sf, random.Random(999)))
        self.assertEqual(first_delay, item["delay_minutes"])
        self.assertEqual(first_publish_after, item["publish_after"])

    def test_legacy_slot_is_materialized(self):
        item = {"date": "2026-07-06", "time_slot": "evening", "status": "ready"}
        materialize(self.schedule_file([item]), random.Random(2))
        self.assertEqual("2026-07-06T17:00:00+09:00", item["scheduled_at"])
        self.assertGreaterEqual(item["delay_minutes"], 2)
        self.assertLessEqual(item["delay_minutes"], 14)

    def test_selects_only_oldest_due_candidate(self):
        items = [
            {"id": "b", "status": "ready", "scheduled_at": "2026-07-06T08:00:00+09:00", "publish_after": "2026-07-06T08:10:00+09:00"},
            {"id": "a", "status": "ready", "scheduled_at": "2026-07-06T07:00:00+09:00", "publish_after": "2026-07-06T07:10:00+09:00"},
        ]
        selected = select_candidate(items, datetime(2026, 7, 6, 9, 0, tzinfo=JST))
        self.assertEqual("a", selected["id"])

    def test_posting_resume_has_priority(self):
        items = [
            {"id": "ready", "status": "ready", "scheduled_at": "2026-07-06T06:00:00+09:00", "publish_after": "2026-07-06T06:01:00+09:00"},
            {"id": "resume", "status": "posting", "scheduled_at": "2026-07-06T07:00:00+09:00", "publish_after": "2026-07-06T07:01:00+09:00"},
        ]
        selected = select_candidate(items, datetime(2026, 7, 6, 9, 0, tzinfo=JST))
        self.assertEqual("resume", selected["id"])

    def test_later_posted_blocks_older_same_series(self):
        items = [
            {"id": "old", "series_id": "songs", "status": "ready", "scheduled_at": "2026-07-06T07:00:00+09:00", "publish_after": "2026-07-06T07:02:00+09:00"},
            {"id": "new", "series_id": "songs", "status": "posted", "scheduled_at": "2026-07-07T07:00:00+09:00", "publish_after": "2026-07-07T07:02:00+09:00"},
        ]
        self.assertIsNone(select_candidate(items, datetime(2026, 7, 8, 9, 0, tzinfo=JST)))
        items[0]["allow_out_of_order"] = True
        self.assertEqual("old", select_candidate(items, datetime(2026, 7, 8, 9, 0, tzinfo=JST))["id"])

    def test_migration_hold_is_not_automatic(self):
        item = {"id": "held", "status": "ready", "migration_hold": True, "scheduled_at": "2026-07-03T07:00:00+09:00", "publish_after": "2026-07-03T07:02:00+09:00"}
        self.assertIsNone(select_candidate([item], datetime(2026, 7, 3, 19, 0, tzinfo=JST)))
        self.assertEqual("held", select_candidate([item], datetime(2026, 7, 3, 19, 0, tzinfo=JST), requested_id="held")["id"])

    def test_safety_held_post_requires_explicit_id(self):
        item = {"id": "safety-held", "status": "held", "scheduled_at": "2026-07-06T07:00:00+09:00", "publish_after": "2026-07-06T07:02:00+09:00"}
        now = datetime(2026, 7, 6, 12, 0, tzinfo=JST)
        self.assertIsNone(select_candidate([item], now))
        self.assertEqual("safety-held", select_candidate([item], now, requested_id="safety-held")["id"])


if __name__ == "__main__":
    unittest.main()
