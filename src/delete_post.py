"""Guarded Threads post deletion."""
from __future__ import annotations

import argparse
import sys

from .threads_api import ThreadsAPI
from .utils import append_yaml_list, repo_path, require_env, timestamp_jst


def delete_post(post_id: str, confirm: bool) -> int:
    api = ThreadsAPI(
        access_token=require_env("BIKANSAN_ACCESS_TOKEN"),
        user_id=require_env("BIKANSAN_USER_ID"),
    )
    result = api.delete_post_safe(post_id, confirm=confirm)
    ok = "error" not in result
    append_yaml_list(
        repo_path("posts", "delete_queue.yml"),
        {
            "post_id": post_id,
            "deleted_at": timestamp_jst() if ok else "",
            "status": "deleted" if ok else "error",
            "result": result,
        },
    )
    print(result)
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-id", required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    sys.exit(delete_post(args.post_id, args.confirm))


if __name__ == "__main__":
    main()
