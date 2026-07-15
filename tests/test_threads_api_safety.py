from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from src.threads_api import ThreadsAPI


class DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.payload = payload
        self.text = ""

    def json(self):
        return self.payload


class ThreadsAPISafetyTests(unittest.TestCase):
    def setUp(self):
        self.api = ThreadsAPI("token", "user")

    @patch("src.threads_api.requests.request")
    def test_post_server_error_is_not_retried(self, request_mock):
        request_mock.return_value = DummyResponse(500, {"error": {"message": "server error"}})

        result = self.api.create_text_container("hello")

        self.assertEqual(1, request_mock.call_count)
        self.assertEqual("non_idempotent_request", result["retry_skipped"])

    @patch("src.threads_api.requests.request")
    def test_post_transport_error_is_not_retried(self, request_mock):
        request_mock.side_effect = requests.exceptions.Timeout("timed out")

        result = self.api.publish("creation-id")

        self.assertEqual(1, request_mock.call_count)
        self.assertFalse(result["error"]["retry_safe"])
        self.assertEqual("non_idempotent_request", result["retry_skipped"])

    @patch("src.threads_api.time.sleep")
    @patch("src.threads_api.requests.request")
    def test_get_transient_error_is_retried(self, request_mock, sleep_mock):
        request_mock.side_effect = [
            DummyResponse(500, {"error": {"message": "server error"}}),
            DummyResponse(429, {"error": {"message": "rate limited"}}),
            DummyResponse(200, {"data": []}),
        ]

        result = self.api.get_post_insights("post-id")

        self.assertEqual({"data": []}, result)
        self.assertEqual(3, request_mock.call_count)
        self.assertEqual(2, sleep_mock.call_count)


if __name__ == "__main__":
    unittest.main()
