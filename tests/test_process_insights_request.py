from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.process_insights_request import process_request, validate_request
from src.utils import load_yaml, save_yaml


class ProcessInsightsRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.request_path = root / "collect_insights.yml"
        self.state_path = root / "collect_insights_state.yml"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_disabled_request_makes_no_api_call(self):
        save_yaml(self.request_path, {"enabled": False})
        collector = Mock(return_value=3)

        result = process_request(
            self.request_path,
            self.state_path,
            collector=collector,
            timestamp_fn=lambda: "2026-07-15T10:00:00+09:00",
        )

        self.assertEqual(0, result)
        collector.assert_not_called()
        self.assertFalse(self.state_path.exists())

    def test_valid_request_is_processed_and_recorded(self):
        save_yaml(
            self.request_path,
            {
                "enabled": True,
                "request_id": "20260715-100000",
                "limit": 20,
                "active_days": 14,
                "request_delay_seconds": 1.5,
                "force": False,
            },
        )
        collector = Mock(return_value=7)

        result = process_request(
            self.request_path,
            self.state_path,
            collector=collector,
            timestamp_fn=lambda: "2026-07-15T10:01:00+09:00",
        )

        self.assertEqual(7, result)
        collector.assert_called_once_with(
            limit=20,
            force=False,
            active_days=14,
            request_delay_seconds=1.5,
        )
        state = load_yaml(self.state_path, default={})
        self.assertEqual("20260715-100000", state["last_processed_request_id"])
        self.assertEqual(7, state["collected_count"])

    def test_same_request_id_is_idempotent(self):
        save_yaml(
            self.request_path,
            {
                "enabled": True,
                "request_id": "20260715-100000",
                "limit": 30,
                "active_days": 30,
                "request_delay_seconds": 1.0,
                "force": False,
            },
        )
        save_yaml(
            self.state_path,
            {"last_processed_request_id": "20260715-100000"},
        )
        collector = Mock(return_value=9)

        result = process_request(
            self.request_path,
            self.state_path,
            collector=collector,
        )

        self.assertEqual(0, result)
        collector.assert_not_called()

    def test_limit_above_safety_cap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "limit must be between 1 and 30"):
            validate_request(
                {
                    "request_id": "20260715-100000",
                    "limit": 31,
                    "active_days": 30,
                    "request_delay_seconds": 1.0,
                    "force": False,
                }
            )

    def test_delay_below_one_second_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError, "request_delay_seconds must be between 1.0 and 30.0"
        ):
            validate_request(
                {
                    "request_id": "20260715-100000",
                    "limit": 30,
                    "active_days": 30,
                    "request_delay_seconds": 0.5,
                    "force": False,
                }
            )


if __name__ == "__main__":
    unittest.main()
