#!/usr/bin/env python3
"""
FitDrop — TikTok Content Pipeline
Generates 3 video scripts with hooks, CapCut/InVideo prompts, captions,
and hashtags for a TikTok Shop clothing affiliate product using Claude API.

Usage:
    python tiktok_pipeline.py
    python tiktok_pipeline.py --product "Ekko Tank Top" --price "$24.99"
    python tiktok_pipeline.py --product "Sweat Shorts" --angle styling

Requirements:
    pip install anthropic python-dotenv
    Set ANTHROPIC_API_KEY in .env or environment.
"""

import anthropic
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent.parent / "config" / "channels.json"
OUTPUT_ROOT = Path(__file__).parent.parent / "output" / "tiktok"

def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())["tiktok"]

# ── Prompts ───────────────────────────────────────────────────────────────────

SCRIPT_SYSTEM_PROMPT = """You are a TikTok video scriptwriter for the FitDrop clothing affiliate account.

Platform rules (2026):
- Saves and watch time past 8 seconds matter more than likes. Optimize for both.
- Hook must land in the FIRST 1-2 seconds. If the viewer isn't hooked, they scroll.
- Videos: 15-45 seconds max. Every second must earn the next.
- Tone: authentic, relatable, slightly conversational. NOT salesy. NOT infomercial.
- The product solves a problem or answers a desire — show that, don't announce it.
- End with a clear, low-friction CTA: "link in bio" or "tap the TikTok Shop link below."

Hook formulas that work for clothing:
- Transformation: "This is what $25 looks like vs. what it FEELS like"
- Social proof: "This is why this tank is on every GRWM right now"
- Size/inclusivity: "Finally a [item] that actually fits size [X]"
- Styling: "3 ways to style this one piece — none of them look cheap"
- Curiosity gap: "I wore this every day for a week — here's what happened"

Script format per video:
[VIDEO TITLE / CONCEPT]
[HOOK — first 2 seconds, on-screen text]
[SCENES — beat-by-beat breakdown, 3-6 beats, each 3-8 seconds]
[CTA — final 2-3 seconds]
[SUGGESTED AUDIO — trending sound style or specific track type]

Write exactly 3 script variations. Label them VIDEO 1, VIDEO 2, VIDEO 3.
Each must use a different hook angle."""

CAPTION_SYSTEM_PROMPT = """You are a TikTok caption and hashtag specialist for clothing/fashion content.

Given product details and scripts, write:

For each of the 3 videos:
[VIDEO X CAPTION]
- First line: scroll-stopping opener (question, bold statement, or relatable moment). Max 100 chars.
- Body: 1-2 sentences naturally mentioning the product. Sound human, not branded.
- Disclosure: "ad | affiliate link in bio ✌️"
- End: relevant emoji cluster

[VIDEO X HASHTAGS]
- 12-15 hashtags
- Mix: broad (#FashionTikTok, #OOTD), product-specific (#EkkoTank, #SweatShorts),
  viral (#TikTokMadeMeBuyIt, #FitCheck), and niche-relevant (#ComfyFits, #CasualStyle)
- Include #TikTokShop and #ad on every post (required for compliance)

Keep captions under 150 characters before hashtags."""

CAPCUT_SYSTEM_PROMPT = """You are a CapCut AI video editor specializing in TikTok clothing content.

Given 3 video scripts, write a CapCut or InVideo assembly prompt for each.

For each video include:
[VIDEO X — CAPCUT PROMPT]
- Opening frame: describe first visual (model/flat-lay/product in hand, lighting, angle)
- Scene transitions: specify beat-by-beat (cut, zoom, swipe, etc.)
- Text overlays: exact text + timing + style (bold white, outline, lower-third)
- B-roll guidance: list 3-4 specific stock clips or AI-generated clips to source
- Filter/vibe: one-word color grade direction (e.g., "warm golden", "clean white", "moody dark")
- Audio: music energy description + when to sync cuts to beat
- AI Avatar note (if applicable): skin tone, clothing, gestures matching product

Keep each prompt under 200 words."""

# ── Core generation ──────────────────────────────────────────────────────────

def get_product_hooks(config: dict, product_name: str) -> list[str]:
    for p in config["products"]:
        if product_name.lower() in p["name"].lower():
            return p["key_hooks"]
    return []


def generate_scripts(client: anthropic.Anthropic, product: str, price: str,
                     angle: str, config: dict) -> str:
    hooks = get_product_hooks(config, product)
    hook_context = f"\nPre-approved hooks for this product:\n" + "\n".join(f"- {h}" for h in hooks) if hooks else ""
    user_msg = (
        f"Write 3 TikTok video scripts for:\n\n"
        f"Product: {product}\n"
        f"Price: {price}\n"
        f"Primary angle focus: {angle}\n"
        f"Brand: FitDrop\n"
        f"Target audience: {config['target_audience']}\n"
        f"{hook_context}\n\n"
        f"Disclosure to include somewhere natural: '{config['disclosure_caption']}'"
    )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=SCRIPT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return message.content[0].text


def generate_captions(client: anthropic.Anthropic, product: str, scripts: str,
                      config: dict) -> str:
    default_tags = " ".join(config["default_hashtags"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=CAPTION_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Write captions and hashtags for 3 TikTok videos promoting: {product}\n\n"
                f"Standard hashtags to always include: {default_tags}\n\n"
                f"Scripts summary:\n{scripts[:2000]}"
            )
        }],
    )
    return message.content[0].text


def generate_capcut_prompts(client: anthropic.Anthropic, scripts: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=CAPCUT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Create CapCut assembly prompts for:\n\n{scripts[:2500]}"}],
    )
    return message.content[0].text

# ── Output ────────────────────────────────────────────────────────────────────

def save_outputs(product_slug: str, scripts: str, captions: str,
                 capcut: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "scripts.txt").write_text(scripts, encoding="utf-8")
    (out_dir / "captions_hashtags.txt").write_text(captions, encoding="utf-8")
    (out_dir / "capcut_prompts.txt").write_text(capcut, encoding="utf-8")

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "product_slug": product_slug,
        "files": [
            "scripts.txt — 3 video scripts with hooks, beats, CTAs",
            "captions_hashtags.txt — TikTok captions + hashtag sets for each video",
            "capcut_prompts.txt — CapCut/InVideo assembly instructions",
        ],
        "next_steps": [
            "1. Pick strongest script from scripts.txt (usually VIDEO 1 or whichever has the boldest hook)",
            "2. Open CapCut → New Project → paste capcut_prompts.txt scene by scene",
            "3. Add AI Avatar or record yourself using script as teleprompter",
            "4. Export 1080x1920 (9:16), max quality",
            "5. Post on TikTok: use caption + hashtags from captions_hashtags.txt",
            "6. Update affiliate link in bio before posting",
            "7. Log performance in pivot_tracker.py after 48 hours",
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\n✓ Output saved to: {out_dir}")
    for f in ["scripts.txt", "captions_hashtags.txt", "capcut_prompts.txt", "manifest.json"]:
        print(f"  → {f}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate TikTok clothing content package")
    parser.add_argument("--product", type=str, default=None,
                        help='Product name, e.g. "Ekko Tank Top"')
    parser.add_argument("--price", type=str, default="$24.99",
                        help='Product price, e.g. "$24.99"')
    parser.add_argument("--angle", type=str, default="lifestyle",
                        choices=["lifestyle", "styling", "comfort", "social_proof", "transformation"],
                        help="Primary hook angle for this batch")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY not set. Add it to your .env file or environment.")

    config = load_config()
    client = anthropic.Anthropic(api_key=api_key)

    product = args.product
    if not product:
        print("Available products:")
        for i, p in enumerate(config["products"], 1):
            print(f"  {i}. {p['name']} — {p['price_range']}")
        product = input("\nEnter product name: ").strip()
        if not product:
            sys.exit("No product provided.")

    date_str = datetime.now().strftime("%Y-%m-%d")
    product_slug = product[:30].lower().replace(" ", "-")
    out_dir = OUTPUT_ROOT / f"{date_str}_{product_slug}"

    print(f"\nGenerating content package for: {product}")
    print("This takes ~20-40 seconds...\n")

    print("[1/3] Writing 3 video scripts...")
    scripts = generate_scripts(client, product, args.price, args.angle, config)

    print("[2/3] Writing captions and hashtags...")
    captions = generate_captions(client, product, scripts, config)

    print("[3/3] Writing CapCut assembly prompts...")
    capcut = generate_capcut_prompts(client, scripts)

    save_outputs(product_slug, scripts, captions, capcut, out_dir)
    print("\nDone. Open manifest.json for next steps.")


if __name__ == "__main__":
    main()
