#!/usr/bin/env python3
"""
Dread Files — Runway Gen-3 Video Client
Parses scene prompts from scene_breakdown.txt, submits each to the Runway Gen-3
Alpha API, polls until complete, and downloads the MP4 clips.
"""

import os
import re
import time
import requests
from pathlib import Path

RUNWAY_BASE = "https://api.dev.runwayml.com/v1"
POLL_INTERVAL = 10   # seconds between status checks
MAX_WAIT = 600        # 10 minutes max per clip
CLIP_DURATION = 5     # seconds per clip (Runway Gen-3 Alpha: 5 or 10)


def _get_api_key() -> str:
    key = os.environ.get("RUNWAY_API_KEY", "")
    if not key:
        raise EnvironmentError("RUNWAY_API_KEY not set.")
    return key


def _parse_scene_prompts(scene_breakdown: str) -> list[dict]:
    """
    Extract scene prompts from the scene_breakdown.txt content.
    Returns a list of dicts: {scene_num, prompt, timestamp_estimate}.
    """
    scenes = []
    # Match blocks that start with "Scene N" or "**Scene N**"
    blocks = re.split(r"\*{0,2}Scene\s+(\d+)\*{0,2}", scene_breakdown)
    # blocks[0] = preamble, then alternating: scene_num, block_text
    i = 1
    while i + 1 < len(blocks):
        scene_num = int(blocks[i])
        block = blocks[i + 1]

        # Extract Runway/Kling prompt — look for lines after "prompt:" or "Kling" or "Runway"
        prompt_match = re.search(
            r"(?:Kling AI|Runway|Pika)\s*(?:prompt)?[:\-]?\s*(.+?)(?:\n\n|\Z)",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if not prompt_match:
            # Fallback: take the longest paragraph in the block
            paragraphs = [p.strip() for p in block.split("\n\n") if len(p.strip()) > 40]
            prompt_text = max(paragraphs, key=len) if paragraphs else block.strip()[:300]
        else:
            prompt_text = prompt_match.group(1).strip()

        # Clean up the prompt — remove markdown and trim
        prompt_text = re.sub(r"\*+", "", prompt_text).strip()
        prompt_text = prompt_text[:500]  # Runway prompt cap

        # Extract timestamp estimate if present
        ts_match = re.search(r"(\d+:\d+|\d+\s*(?:sec|min))", block)
        timestamp = ts_match.group(1) if ts_match else f"~{scene_num * 60}s"

        scenes.append({
            "scene_num": scene_num,
            "prompt": prompt_text,
            "timestamp": timestamp,
        })
        i += 2

    return scenes


def _submit_generation(api_key: str, prompt: str) -> str:
    """Submit a text-to-video task and return the task ID."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Runway-Version": "2024-11-06",
    }
    payload = {
        "promptText": prompt,
        "model": "gen3a_turbo",
        "duration": CLIP_DURATION,
        "ratio": "1280:720",
        "watermark": False,
    }
    resp = requests.post(
        f"{RUNWAY_BASE}/image_to_video",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _poll_task(api_key: str, task_id: str) -> str:
    """Poll until the task is complete. Returns the output video URL."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Runway-Version": "2024-11-06",
    }
    waited = 0
    while waited < MAX_WAIT:
        resp = requests.get(
            f"{RUNWAY_BASE}/tasks/{task_id}",
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "")
        if status == "SUCCEEDED":
            return data["output"][0]
        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Runway task {task_id} ended with status: {status}")
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    raise TimeoutError(f"Runway task {task_id} did not complete within {MAX_WAIT}s")


def _download_clip(url: str, out_path: Path) -> None:
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def generate_clips(
    scene_breakdown: str,
    clips_dir: Path,
    dry_run: bool = False,
) -> list[Path]:
    """
    Parse scenes from scene_breakdown, generate a video clip for each,
    and save MP4s to clips_dir. Returns list of clip paths in scene order.
    """
    api_key = _get_api_key()
    scenes = _parse_scene_prompts(scene_breakdown)
    if not scenes:
        raise ValueError("No scenes found in scene breakdown.")

    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []

    print(f"  Runway: {len(scenes)} scenes to generate...")

    for scene in scenes:
        clip_path = clips_dir / f"scene_{scene['scene_num']:02d}.mp4"

        if dry_run:
            print(f"  [DRY RUN] Scene {scene['scene_num']}: {scene['prompt'][:60]}...")
            clip_paths.append(clip_path)
            continue

        if clip_path.exists():
            print(f"  Scene {scene['scene_num']}: already exists, skipping.")
            clip_paths.append(clip_path)
            continue

        print(f"  Scene {scene['scene_num']}: submitting to Runway...")
        task_id = _submit_generation(api_key, scene["prompt"])
        print(f"  Scene {scene['scene_num']}: task {task_id}, polling...")
        video_url = _poll_task(api_key, task_id)
        _download_clip(video_url, clip_path)
        print(f"  ✓ Scene {scene['scene_num']} saved: {clip_path.name}")
        clip_paths.append(clip_path)

    return clip_paths


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python runway_client.py scene_breakdown.txt clips_dir/")
        sys.exit(1)
    breakdown = Path(sys.argv[1]).read_text(encoding="utf-8")
    generate_clips(breakdown, Path(sys.argv[2]))
