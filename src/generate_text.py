"""OpenAI text helpers for post text and image prompts."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from .utils import repo_path


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _client() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _response_text(prompt: str, model: str | None = None) -> str:
    client = _client()
    model = model or os.environ.get("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    result = client.responses.create(
        model=model,
        input=prompt,
    )
    text = getattr(result, "output_text", "")
    if not text:
        raise RuntimeError("OpenAI response did not include output_text.")
    return text.strip()


def build_context(idea: dict[str, Any]) -> str:
    """Build compact idea context for prompts."""
    return "\n".join(
        [
            f"date: {idea.get('date', '')}",
            f"time_slot: {idea.get('time_slot', '')}",
            f"category: {idea.get('category', '')}",
            f"character: {idea.get('character', '')}",
            f"theme: {idea.get('theme', '')}",
            f"outfit: {idea.get('outfit', '')}",
            f"mood: {idea.get('mood', '')}",
            f"must_include: {idea.get('must_include', [])}",
            f"avoid: {idea.get('avoid', [])}",
        ]
    )


def generate_post_text(idea: dict[str, Any]) -> str:
    character_rules = _read_prompt(repo_path("prompts", "character_rules.md"))
    post_rules = _read_prompt(repo_path("prompts", "post_text_prompt.md"))
    safety_rules = _read_prompt(repo_path("prompts", "safety_rules.md"))
    prompt = f"""
{character_rules}

{post_rules}

{safety_rules}

## 今回の投稿ネタ
{build_context(idea)}
""".strip()
    return _response_text(prompt)


def generate_image_prompt(idea: dict[str, Any], post_text: str) -> str:
    character_rules = _read_prompt(repo_path("prompts", "character_rules.md"))
    image_rules = _read_prompt(repo_path("prompts", "image_prompt.md"))
    safety_rules = _read_prompt(repo_path("prompts", "safety_rules.md"))
    prompt = f"""
{character_rules}

{image_rules}

{safety_rules}

## 今回の投稿ネタ
{build_context(idea)}

## 投稿文
{post_text}
""".strip()
    return _response_text(prompt)
