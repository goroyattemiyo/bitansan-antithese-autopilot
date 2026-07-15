from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.post_scheduler import hold_stale_ready_items
from src.schedule_store import ScheduleFile
from src.scheduler_core import JST


class PostSchedulerSafetyTests(unittest.TestCase):
    def test_only_untouched_stale_ready_posts_are_held(self):
        entries = [
            {
                "id": "stale",
                "status": "ready",
                "publish_after": "2026-07-15T07:00:00+09:00",
            },
            {
                "id": "recent",
                "status": "ready",
                "publish_after": "2026-07-15T10:30:00+09:00",
            },
            {
                "id": "resume",
                "status": "posting",
                "publish_after": "2026-07-15T07:00:00+09:00",
                "threads_post_id": "root-id",
            },
            {
                "id": "ready-with-root",
                "status": "ready",
                "publish_after": "2026-07-15T07:00:00+09:00",
                "thread_progress": {"root_post_id": "root-id"},
            },
        ]
        sf = ScheduleFile(
            Path(tempfile.gettempdir()) / "2026-07-13_to_2026-07-19.yml",
            datetime(2026, 7, 13).date(),
            datetime(2026, 7, 19).date(),
            entries,
        )
        now = datetime(2026, 7, 15, 11, 0, tzinfo=JST)

        changed = hold_stale_ready_items([sf], now, max_lateness_minutes=120)

        self.assertEqual([sf], changed)
        self.assertEqual("held", entries[0]["status"])
        self.assertIn("120", entries[0]["hold_reason"])
        self.assertEqual("ready", entries[1]["status"])
        self.assertEqual("posting", entries[2]["status"])
        self.assertEqual("ready", entries[3]["status"])

    def test_negative_lateness_is_rejected(self):
        now = datetime(2026, 7, 15, 11, 0, tzinfo=JST)
        with self.assertRaises(ValueError):
            hold_stale_ready_items([], now, max_lateness_minutes=-1)


if __name__ == "__main__":
    unittest.main()
