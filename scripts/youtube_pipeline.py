#!/usr/bin/env python3
"""
Dread Files — YouTube Content Pipeline
Generates scary story scripts, ElevenLabs prompts, video scene breakdowns,
and SEO metadata using the Claude API. Run once per video, or import
generate_* functions into orchestrator.py for fully automated runs.

Usage:
    python youtube_pipeline.py
    python youtube_pipeline.py --topic "The Night Shift at Pinewood Asylum"
    python youtube_pipeline.py --topic "..." --length long

Requirements:
    pip install anthropic python-dotenv
    Set ANTHROPIC_API_KEY in .env or environment.
"""

import anthropic
import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent.parent / "config" / "channels.json"
OUTPUT_ROOT = Path(__file__).parent.parent / "output" / "youtube"

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)["youtube"]

# ── Prompts ───────────────────────────────────────────────────────────────────

SCRIPT_SYSTEM_PROMPT = """You are a YouTube scary story scriptwriter for the channel "Dread Files."

Tone rules (strict):
- Slow-burn dread. Never use jump-scare language.
- Open with an unsettling fact, question, or quiet detail that feels off.
- Build tension gradually across 3 acts. Payoff lands in the final 20%.
- Narration style: calm, measured, third-person. Think a documentary narrator who has seen too much.
- DO NOT include phrases like "BOOM", "suddenly!", or cheap shock moments.
- End with an unresolved, lingering question. Leave the viewer uneasy, not satisfied.

Script format:
- Hook (first ~30 seconds): one visceral opening line, then context.
- Act 1 (~30%): backstory, the "normal" before things go wrong.
- Act 2 (~50%): escalation. Strange things accumulate. Each detail slightly worse than the last.
- Act 3 (~20%): the climax and the unresolved ending.
- Outro CTA: "If this felt familiar — subscribe. New stories drop every week."

Output format (use these exact section headers):
[TITLE]
[HOOK]
[ACT 1]
[ACT 2]
[ACT 3]
[OUTRO CTA]
[WORD COUNT: approximately X words]
"""

SEO_SYSTEM_PROMPT = """You are an expert YouTube SEO specialist for the horror/scary stories niche.
Given a scary story script, produce:

1. VIDEO TITLE: Curiosity gap + keyword. Max 70 chars. Examples:
   - "The Nurse Who Refused to Enter Room 14 (True Story)"
   - "I Found My Missing Sister's Journal — I Wish I Hadn't"

2. DESCRIPTION: 3-4 paragraphs. First paragraph: hook (repeat title concept, add intrigue).
   Second: story summary (no spoilers). Third: keywords naturally woven in.
   Fourth: links placeholder section with [AFFILIATE_LINK_1], timestamps [00:00 Intro], subscribe CTA.

3. TAGS: 15 comma-separated tags. Mix: broad (scary stories, horror, creepy), specific (true horror story 2026, AI narrated horror), long-tail (scary stories for sleep, real horror reddit stories).

4. THUMBNAIL BRIEF: One paragraph describing the exact thumbnail to create in Canva/Midjourney.
   Include: background color/mood, focal element, text overlay (max 3 words), lighting direction.

5. ELEVENLABS VOICE NOTES: Specific pacing and emphasis notes for the narrator. Mark 3-5 key lines
   that need the most deliberate, slow delivery.

Output each section with its header label clearly marked."""

SCENE_SYSTEM_PROMPT = """You are a video editor and AI video prompt specialist for the horror/atmospheric YouTube niche.
Given a scary story script, produce a scene-by-scene visual breakdown.

For each scene:
- Scene number and timestamp estimate
- Setting description (location, lighting, time of day)
- Mood/atmosphere keywords
- Kling AI / Runway / Pika prompt (copy-paste ready, ~50-80 words each)
- CapCut/editing note: transitions, text overlays, sound design cues

Use atmospheric, cinematic, slow-moving visuals. No gore. Dread through shadow and silence.
Aim for 8-12 scenes per script."""

# ── Core generation ──────────────────────────────────────────────────────────

def generate_script(client: anthropic.Anthropic, topic: str, length: str, config: dict) -> str:
    word_target = "1,800-2,200 words" if length == "short" else "2,500-3,200 words"
    user_msg = (
        f"Write a scary story script for the Dread Files YouTube channel.\n\n"
        f"Topic/premise: {topic}\n"
        f"Target length: {word_target} (roughly 10-13 min narrated at 0.9x speed).\n\n"
        f"Channel tone: {config['tone']}. "
        f"Target audience: {config['target_audience']}."
    )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SCRIPT_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
    )
    return message.content[0].text


def generate_seo(client: anthropic.Anthropic, script: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": SEO_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": f"Generate YouTube SEO package for this script:\n\n{script}"}],
    )
    return message.content[0].text


def generate_scene_breakdown(client: anthropic.Anthropic, script: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=[
            {
                "type": "text",
                "text": SCENE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": f"Create scene-by-scene video breakdown for:\n\n{script}"}],
    )
    return message.content[0].text


def extract_title_from_script(script: str) -> str:
    match = re.search(r"\[TITLE\]\s*(.+)", script)
    if match:
        return match.group(1).strip()
    return "Untitled"


def generate_elevenlabs_prompt(script_title: str, config: dict) -> str:
    voice = config["elevenlabs_voice"]
    return f"""ELEVENLABS VOICE SETTINGS — {script_title}
═══════════════════════════════════════

Voice ID: {voice['voice_id']}
Speed: {voice['speed']}x  (IMPORTANT: slower than default — builds dread)
Stability: {voice['stability']}%
Clarity + Similarity Enhancement: {voice['clarity']}%
Style Exaggeration: {voice['style_exaggeration']}%

Post-production notes:
- Add subtle room reverb (small-to-medium room, low wet %)
- Light EQ cut at 6-8kHz to reduce harshness
- Slight compression (2:1 ratio) for consistent loudness
- Export: 44.1kHz / 320kbps MP3

Pacing notes:
- Pause 0.5s after every period in the Hook section
- Pause 1s before the final line of Act 3
- Do not rush the opening. Silence is tension.
- {voice['notes']}
"""

# ── Output ────────────────────────────────────────────────────────────────────

def save_outputs(topic_slug: str, script: str, seo: str,
                 scenes: str, elevenlabs: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "script.txt").write_text(script, encoding="utf-8")
    (out_dir / "seo_metadata.txt").write_text(seo, encoding="utf-8")
    (out_dir / "scene_breakdown.txt").write_text(scenes, encoding="utf-8")
    (out_dir / "elevenlabs_settings.txt").write_text(elevenlabs, encoding="utf-8")

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "topic_slug": topic_slug,
        "files": [
            "script.txt — full narration script",
            "seo_metadata.txt — title, description, tags, thumbnail brief",
            "scene_breakdown.txt — Kling/Runway/Pika prompts per scene",
            "elevenlabs_settings.txt — voice settings + pacing notes",
        ],
        "next_steps": [
            "1. Record voiceover: paste script.txt into ElevenLabs with settings from elevenlabs_settings.txt",
            "2. Generate visuals: use prompts from scene_breakdown.txt in Kling AI or Runway",
            "3. Edit in CapCut or DaVinci: sync audio to scenes, add text overlays per scene notes",
            "4. Build thumbnail: use brief from seo_metadata.txt in Canva or Midjourney",
            "5. Upload to YouTube: paste title, description, tags from seo_metadata.txt",
            "6. Log performance in pivot_tracker.py after 48 hours",
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\n✓ Output saved to: {out_dir}")
    for f in ["script.txt", "seo_metadata.txt", "scene_breakdown.txt", "elevenlabs_settings.txt", "manifest.json"]:
        print(f"  → {f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate YouTube scary story content package")
    parser.add_argument("--topic", type=str, default=None,
                        help="Story premise or title concept (leave blank to be prompted)")
    parser.add_argument("--length", choices=["short", "long"], default="long",
                        help="Script length: short (~10 min) or long (~13 min)")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY not set. Add it to your .env file or environment.")

    config = load_config()
    client = anthropic.Anthropic(api_key=api_key)

    topic = args.topic
    if not topic:
        topic = input("Enter story topic or premise: ").strip()
        if not topic:
            sys.exit("No topic provided.")

    date_str = datetime.now().strftime("%Y-%m-%d")
    topic_slug = topic[:40].lower().replace(" ", "-").replace("/", "-")
    out_dir = OUTPUT_ROOT / f"{date_str}_{topic_slug}"

    print(f"\nGenerating content package for: {topic}")
    print("This takes ~30-60 seconds...\n")

    print("[1/4] Writing script...")
    script = generate_script(client, topic, args.length, config)

    print("[2/4] Generating SEO metadata and scene breakdown in parallel...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        seo_future = executor.submit(generate_seo, client, script)
        scenes_future = executor.submit(generate_scene_breakdown, client, script)
        seo = seo_future.result()
        scenes = scenes_future.result()

    print("[3/4] Extracting title and writing ElevenLabs settings...")
    script_title = extract_title_from_script(script)
    elevenlabs = generate_elevenlabs_prompt(script_title, config)

    print("[4/4] Saving outputs...")
    save_outputs(topic_slug, script, seo, scenes, elevenlabs, out_dir)
    print("\nDone. Open manifest.json for next steps.")


if __name__ == "__main__":
    main()
