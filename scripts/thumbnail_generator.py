#!/usr/bin/env python3
"""
Dread Files — Thumbnail Generator
Extracts the thumbnail brief from SEO metadata and calls Stability AI SDXL
to generate a 1280x720 horror-atmospheric thumbnail.
"""

import os
import re
import requests
import base64
from pathlib import Path

STABILITY_BASE = "https://api.stability.ai/v2beta/stable-image/generate/core"
THUMBNAIL_W = 1344   # SDXL core supported width (nearest to 1280)
THUMBNAIL_H = 768    # SDXL core supported height (nearest to 720)

NEGATIVE_PROMPT = (
    "text, watermark, logo, cartoonish, bright colors, daylight, happy, "
    "people smiling, gore, blood, weapons, ugly, blurry, low quality"
)


def _get_api_key() -> str:
    key = os.environ.get("STABILITY_API_KEY", "")
    if not key:
        raise EnvironmentError("STABILITY_API_KEY not set.")
    return key


def _extract_thumbnail_brief(seo_metadata: str) -> str:
    """Pull the THUMBNAIL BRIEF section from seo_metadata.txt content."""
    match = re.search(
        r"(?:4\.|THUMBNAIL BRIEF)[:\s]*(.+?)(?:\n\n5\.|\n\nELEVENLABS|\Z)",
        seo_metadata,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    # Fallback: return entire SEO metadata trimmed
    return seo_metadata[:400].strip()


def _build_prompt(thumbnail_brief: str) -> str:
    """Wrap the thumbnail brief in cinematographic framing for SDXL."""
    return (
        f"YouTube horror thumbnail, cinematic, atmospheric dread, "
        f"dark color palette, dramatic lighting, high contrast, photorealistic. "
        f"{thumbnail_brief} "
        f"No text. Sharp focus. Professional photography style."
    )


def generate_thumbnail(
    seo_metadata: str,
    out_path: Path,
    dry_run: bool = False,
) -> Path:
    """
    Generate a 1280x720 thumbnail JPG from the SEO metadata thumbnail brief.
    Returns the path to the saved image.
    """
    brief = _extract_thumbnail_brief(seo_metadata)
    prompt = _build_prompt(brief)

    if dry_run:
        print(f"  [DRY RUN] Thumbnail prompt: {prompt[:80]}...")
        return out_path

    api_key = _get_api_key()
    print(f"  Stability AI: generating thumbnail...")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "image/*",
    }
    data = {
        "prompt": prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "aspect_ratio": "16:9",
        "output_format": "jpeg",
    }

    resp = requests.post(
        STABILITY_BASE,
        headers=headers,
        files={"none": ""},
        data=data,
        timeout=60,
    )
    resp.raise_for_status()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(resp.content)

    print(f"  ✓ Thumbnail saved: {out_path} ({out_path.stat().st_size // 1024} KB)")
    return out_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python thumbnail_generator.py seo_metadata.txt thumbnail.jpg")
        sys.exit(1)
    seo = Path(sys.argv[1]).read_text(encoding="utf-8")
    generate_thumbnail(seo, Path(sys.argv[2]))
