"""Smoke test for Threads API credentials."""
from __future__ import annotations

import argparse
import sys

from .threads_api import ThreadsAPI
from .utils import require_env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-text", default="")
    args = parser.parse_args()

    configured_user_id = require_env("BIKANSAN_USER_ID")
    api = ThreadsAPI(
        access_token=require_env("BIKANSAN_ACCESS_TOKEN"),
        user_id=configured_user_id,
    )

    me = api.get_me()
    print("=== /me ===")
    print(me)
    if "error" in me:
        sys.exit(1)

    actual_user_id = str(me.get("id", "")).strip()
    if actual_user_id and actual_user_id != configured_user_id:
        print("ERROR: BIKANSAN_USER_ID does not match /me id.")
        print(f"Set BIKANSAN_USER_ID to this value: {actual_user_id}")
        sys.exit(1)

    if args.post_text.strip():
        print("=== test post ===")
        result = api.post_text(args.post_text.strip())
        print(result)
        if "error" in result:
            sys.exit(1)


if __name__ == "__main__":
    main()
