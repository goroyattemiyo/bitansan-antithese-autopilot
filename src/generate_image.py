"""OpenAI image generation helper."""
from __future__ import annotations

import base64
import os
from pathlib import Path

from openai import OpenAI


def generate_webp_image(
    prompt: str,
    output_path: Path,
    model: str | None = None,
    size: str | None = None,
    quality: str | None = None,
) -> Path:
    """Generate one WebP image and save it to output_path."""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = model or os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
    size = size or os.environ.get("OPENAI_IMAGE_SIZE", "1024x1536")
    quality = quality or os.environ.get("OPENAI_IMAGE_QUALITY", "medium")

    response = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        output_format="webp",
        n=1,
    )

    if not response.data:
        raise RuntimeError("OpenAI image response did not include data.")

    b64_json = response.data[0].b64_json
    if not b64_json:
        raise RuntimeError("OpenAI image response did not include b64_json.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(b64_json))
    return output_path
