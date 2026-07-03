"""Threads Graph API wrapper."""
from __future__ import annotations

import os
import time
from typing import Any

import requests


class ThreadsAPI:
    """Small wrapper for Threads Graph API."""

    BASE_URL = "https://graph.threads.net/v1.0"
    MAX_RETRIES = 3
    RETRY_BASE_WAIT = 3

    def __init__(self, access_token: str, user_id: str | None = None):
        self.access_token = access_token
        self.user_id = user_id

    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Retry transient failures while preserving actionable 4xx responses."""
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                resp = requests.request(method, url, timeout=60, **kwargs)

                try:
                    data = resp.json()
                except ValueError:
                    data = {"raw": resp.text}

                if resp.status_code >= 400:
                    error = data.get("error", data) if isinstance(data, dict) else data
                    payload = {
                        "error": error,
                        "status_code": resp.status_code,
                    }

                    # Client-side failures will not improve by retrying.
                    # 429 is transient and may be retried below.
                    if 400 <= resp.status_code < 500 and resp.status_code != 429:
                        return payload

                    message = error.get("message") if isinstance(error, dict) else str(error)
                    raise requests.exceptions.RequestException(
                        f"HTTP {resp.status_code}: {message}"
                    )

                if isinstance(data, dict) and "error" in data:
                    return data

                return data if isinstance(data, dict) else {"data": data}

            except requests.exceptions.RequestException as exc:
                last_error = exc
                if attempt < self.MAX_RETRIES - 1:
                    wait = self.RETRY_BASE_WAIT * (2**attempt)
                    print(f"Retry {attempt + 1}/{self.MAX_RETRIES} after {wait}s: {exc}")
                    time.sleep(wait)

        return {"error": str(last_error)}

    def _require_user_id(self) -> str:
        if not self.user_id:
            raise RuntimeError("Threads user_id is required for this operation.")
        return self.user_id

    def get_me(self) -> dict[str, Any]:
        """Return the token owner profile."""
        url = f"{self.BASE_URL}/me"
        params = {
            "fields": "id,username,name,threads_profile_picture_url,threads_biography",
            "access_token": self.access_token,
        }
        return self._request_with_retry("GET", url, params=params)

    def create_text_container(self, text: str, reply_to_id: str = "") -> dict[str, Any]:
        """Create a text post or reply container."""
        url = f"{self.BASE_URL}/{self._require_user_id()}/threads"
        data = {
            "media_type": "TEXT",
            "text": text,
            "access_token": self.access_token,
        }
        if reply_to_id:
            data["reply_to_id"] = reply_to_id
        return self._request_with_retry("POST", url, data=data)

    def create_image_container(
        self,
        text: str,
        image_url: str,
        alt_text: str = "",
        location_id: str = "",
        reply_to_id: str = "",
    ) -> dict[str, Any]:
        """Create an image post or reply container."""
        url = f"{self.BASE_URL}/{self._require_user_id()}/threads"
        data = {
            "media_type": "IMAGE",
            "image_url": image_url,
            "text": text,
            "access_token": self.access_token,
        }
        if alt_text:
            data["alt_text"] = alt_text
        if location_id:
            data["location_id"] = location_id
        if reply_to_id:
            data["reply_to_id"] = reply_to_id
        return self._request_with_retry("POST", url, data=data)

    def publish(self, creation_id: str) -> dict[str, Any]:
        """Publish a created container."""
        url = f"{self.BASE_URL}/{self._require_user_id()}/threads_publish"
        data = {
            "creation_id": creation_id,
            "access_token": self.access_token,
        }
        return self._request_with_retry("POST", url, data=data)

    def post_text(
        self,
        text: str,
        wait_seconds: int = 2,
        reply_to_id: str = "",
    ) -> dict[str, Any]:
        """Create and publish a text post or reply."""
        container = self.create_text_container(text, reply_to_id=reply_to_id)
        if "error" in container:
            return container

        creation_id = container.get("id")
        if not creation_id:
            return {"error": "Container ID was not returned.", "container": container}

        time.sleep(wait_seconds)
        return self.publish(creation_id)

    def post_image(
        self,
        text: str,
        image_url: str,
        alt_text: str = "",
        wait_seconds: int = 2,
        reply_to_id: str = "",
    ) -> dict[str, Any]:
        """Create and publish an image post or reply."""
        container = self.create_image_container(text, image_url, alt_text, reply_to_id=reply_to_id)
        if "error" in container:
            return container

        creation_id = container.get("id")
        if not creation_id:
            return {"error": "Container ID was not returned.", "container": container}

        time.sleep(wait_seconds)
        return self.publish(creation_id)

    def get_post(self, media_id: str) -> dict[str, Any]:
        """Fetch a Threads post by ID."""
        url = f"{self.BASE_URL}/{media_id}"
        params = {
            "fields": "id,media_type,media_url,permalink,owner,username,text,timestamp,shortcode,thumbnail_url",
            "access_token": self.access_token,
        }
        return self._request_with_retry("GET", url, params=params)

    def get_user_posts(self, limit: int = 25) -> dict[str, Any]:
        """Fetch recent posts for the configured user."""
        url = f"{self.BASE_URL}/{self._require_user_id()}/threads"
        params = {
            "fields": "id,media_type,media_url,permalink,text,timestamp,shortcode,thumbnail_url",
            "limit": limit,
            "access_token": self.access_token,
        }
        return self._request_with_retry("GET", url, params=params)

    def get_post_insights(
        self,
        media_id: str,
        metrics: str = "views,likes,replies,reposts,quotes",
    ) -> dict[str, Any]:
        """Fetch insight metrics for a post."""
        url = f"{self.BASE_URL}/{media_id}/insights"
        params = {
            "metric": metrics,
            "access_token": self.access_token,
        }
        return self._request_with_retry("GET", url, params=params)

    def delete_post(self, media_id: str) -> dict[str, Any]:
        """Delete a post. Prefer delete_post_safe from scripts."""
        url = f"{self.BASE_URL}/{media_id}"
        params = {"access_token": self.access_token}
        return self._request_with_retry("DELETE", url, params=params)

    def delete_post_safe(self, media_id: str, confirm: bool = False) -> dict[str, Any]:
        """Guarded deletion for workflow use."""
        if os.environ.get("ALLOW_THREADS_DELETE", "").lower() != "true":
            return {"error": "Deletion is locked. Set ALLOW_THREADS_DELETE=true."}
        if not confirm:
            return {"error": "Deletion requires confirm=True."}
        return self.delete_post(media_id)
