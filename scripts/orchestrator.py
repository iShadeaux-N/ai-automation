#!/usr/bin/env python3
"""
Dread Files — Full Automation Orchestrator
Zero-touch pipeline: topic → script → voiceover → video clips → assemble → upload.

Usage:
    python orchestrator.py                      # fully automatic
    python orchestrator.py --topic "..."        # override topic
    python orchestrator.py --dry-run            # print steps, skip paid API calls
    python orchestrator.py --length short       # ~10 min video

Requirements (.env):
    ANTHROPIC_API_KEY
    ELEVENLABS_API_KEY
    RUNWAY_API_KEY
    STABILITY_API_KEY
    YOUTUBE_CLIENT_ID
    YOUTUBE_CLIENT_SECRET
"""

import argparse
import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import anthropic

# Local modules
sys.path.insert(0, str(Path(__file__).parent))
from auto_topic import pick_next_topic
from youtube_pipeline import (
    load_config,
    generate_script,
    generate_seo,
    generate_scene_breakdown,
    generate_elevenlabs_prompt,
    extract_title_from_script,
    save_outputs,
)
from elevenlabs_client import generate_voiceover
from runway_client import generate_clips
from video_assembler import assemble_video
from thumbnail_generator import generate_thumbnail
from youtube_uploader import upload_video

OUTPUT_ROOT = Path(__file__).parent.parent / "output" / "youtube"


def _step(label: str, dry_run: bool = False) -> None:
    marker = "[DRY RUN] " if dry_run else ""
    print(f"\n{'='*60}")
    print(f"  {marker}{label}")
    print(f"{'='*60}")


def run_pipeline(
    topic=None,
    length: str = "long",
    dry_run: bool = False,
) -> dict:
    """
    Run the full Dread Files pipeline end-to-end.
    Returns a result dict with paths and the YouTube video ID.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY not set.")

    config = load_config()
    client = anthropic.Anthropic(api_key=api_key)

    # ── Step 1: Topic ─────────────────────────────────────────────────────────
    _step("Step 1/8 — Selecting topic", dry_run)
    if not topic:
        topic = pick_next_topic(client)
    print(f"  Topic: {topic}")

    date_str = datetime.now().strftime("%Y-%m-%d")
    topic_slug = topic[:40].lower().replace(" ", "-").replace("/", "-")
    out_dir = OUTPUT_ROOT / f"{date_str}_{topic_slug}"
    clips_dir = out_dir / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 2: Script ────────────────────────────────────────────────────────
    _step("Step 2/8 — Writing script", dry_run)
    if dry_run:
        script = f"[TITLE]\nDry Run Story: {topic}\n[HOOK]\nThis is a dry run.\n[ACT 1]\nAct 1 placeholder.\n[ACT 2]\nAct 2 placeholder.\n[ACT 3]\nAct 3 placeholder.\n[OUTRO CTA]\nSubscribe.\n[WORD COUNT: approximately 50 words]"
    else:
        script = generate_script(client, topic, length, config)
    script_title = extract_title_from_script(script)
    print(f"  Title extracted: {script_title}")

    # ── Step 3: SEO + Scene breakdown (parallel) ──────────────────────────────
    _step("Step 3/8 — SEO metadata + scene breakdown (parallel)", dry_run)
    if dry_run:
        seo = "VIDEO TITLE: Dry Run Horror Story\nDESCRIPTION: A dry run.\nTAGS: scary, horror, test\nTHUMBNAIL BRIEF: Dark background, white text DRY RUN."
        scenes = "**Scene 1**\nSetting: Dark room\nRunway prompt: Dark atmospheric corridor, dim light, cinematic horror mood, slow camera drift."
    else:
        with ThreadPoolExecutor(max_workers=2) as executor:
            seo_future = executor.submit(generate_seo, client, script)
            scenes_future = executor.submit(generate_scene_breakdown, client, script)
            seo = seo_future.result()
            scenes = scenes_future.result()
    print("  ✓ SEO metadata and scene breakdown generated.")

    elevenlabs_settings = generate_elevenlabs_prompt(script_title, config)
    save_outputs(topic_slug, script, seo, scenes, elevenlabs_settings, out_dir)

    # ── Step 4: Voiceover ─────────────────────────────────────────────────────
    _step("Step 4/8 — Generating voiceover (ElevenLabs)", dry_run)
    voice_cfg = config["elevenlabs_voice"]
    audio_path = out_dir / "narration.mp3"
    generate_voiceover(
        script=script,
        out_path=audio_path,
        voice_id=voice_cfg["voice_id"],
        speed=voice_cfg["speed"],
        stability=voice_cfg["stability"] / 100,
        similarity_boost=voice_cfg["clarity"] / 100,
        style=voice_cfg["style_exaggeration"] / 100,
        # dry_run is handled inside by checking ELEVENLABS_API_KEY
    ) if not dry_run else print(f"  [DRY RUN] Would generate voiceover → {audio_path.name}")

    # ── Step 5: Video clips (Runway) ──────────────────────────────────────────
    _step("Step 5/8 — Generating video clips (Runway Gen-3)", dry_run)
    clip_paths = generate_clips(scenes, clips_dir, dry_run=dry_run)
    print(f"  ✓ {len(clip_paths)} clips ready.")

    # ── Step 6: Assemble video ────────────────────────────────────────────────
    _step("Step 6/8 — Assembling final video", dry_run)
    final_video_path = out_dir / "final_video.mp4"
    if not dry_run and audio_path.exists() and clip_paths:
        assemble_video(clip_paths, audio_path, final_video_path)
    else:
        print(f"  [DRY RUN] Would assemble video → {final_video_path.name}")

    # ── Step 7: Thumbnail ─────────────────────────────────────────────────────
    _step("Step 7/8 — Generating thumbnail (Stability AI)", dry_run)
    thumbnail_path = out_dir / "thumbnail.jpg"
    generate_thumbnail(seo, thumbnail_path, dry_run=dry_run)

    # ── Step 8: YouTube upload ────────────────────────────────────────────────
    _step("Step 8/8 — Uploading to YouTube", dry_run)
    video_id = upload_video(
        video_path=final_video_path,
        thumbnail_path=thumbnail_path,
        seo_metadata=seo,
        config=config,
        dry_run=dry_run,
    )

    # ── Manifest update ───────────────────────────────────────────────────────
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.update({
        "completed_at": datetime.now().isoformat(),
        "youtube_video_id": video_id,
        "youtube_url": f"https://youtu.be/{video_id}" if video_id != "DRY_RUN_VIDEO_ID" else "N/A",
        "final_video": str(final_video_path),
        "thumbnail": str(thumbnail_path),
        "audio": str(audio_path),
        "dry_run": dry_run,
    })
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"  Output dir : {out_dir}")
    if video_id != "DRY_RUN_VIDEO_ID":
        print(f"  YouTube    : https://youtu.be/{video_id}")
    print(f"{'='*60}\n")

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Dread Files full automation pipeline")
    parser.add_argument("--topic", type=str, default=None,
                        help="Override story topic (leave blank for auto-select)")
    parser.add_argument("--length", choices=["short", "long"], default="long")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print all steps without calling paid APIs")
    args = parser.parse_args()

    try:
        run_pipeline(topic=args.topic, length=args.length, dry_run=args.dry_run)
    except Exception:
        print("\n[ERROR] Pipeline failed:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
