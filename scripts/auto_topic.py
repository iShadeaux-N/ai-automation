#!/usr/bin/env python3
"""
Dread Files — Auto Topic Selector
Reads the 30-day content calendar and the output directory to find the next
un-published story topic. Falls back to asking Claude to generate a fresh one
if all calendar topics are exhausted.
"""

import anthropic
import json
import os
import re
from pathlib import Path

CALENDAR_PATH = Path(__file__).parent.parent / "docs" / "youtube_30day_calendar.md"
OUTPUT_ROOT = Path(__file__).parent.parent / "output" / "youtube"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "channels.json"

TOPIC_GENERATOR_PROMPT = """You are a horror/scary story content strategist for the YouTube channel "Dread Files."
Generate a single compelling story premise for a slow-burn horror narration video.

Rules:
- It must feel like it COULD be a true story (urban legend, unexplained event, eerie location)
- Must have a strong hook concept (one sentence that feels wrong)
- Avoid supernatural clichés (no jump scares, no obvious ghosts)
- Aim for: abandoned places, unsolved disappearances, eerie patterns in data/records, liminal spaces,
  institutional horror (hospitals, prisons, corporate), internet/found footage horror

Output: Just the topic/premise in one sentence. No explanation."""


def _get_published_slugs() -> set[str]:
    """Return slugs of already-generated topics from the output directory."""
    if not OUTPUT_ROOT.exists():
        return set()
    slugs = set()
    for entry in OUTPUT_ROOT.iterdir():
        if entry.is_dir():
            # Directory names are YYYY-MM-DD_topic-slug
            parts = entry.name.split("_", 1)
            if len(parts) == 2:
                slugs.add(parts[1])
    return slugs


def _extract_calendar_topics() -> list[str]:
    """Parse the 30-day calendar markdown and return all title concepts."""
    if not CALENDAR_PATH.exists():
        return []
    text = CALENDAR_PATH.read_text(encoding="utf-8")
    # Match lines like: **Title:** The Night Shift Worker...
    titles = re.findall(r"\*\*Title:\*\*\s+(.+)", text)
    # Also match table rows like: | 17 | The 911 Call... | ...
    table_rows = re.findall(r"\|\s*\d+\s*\|\s*([^|]+)\s*\|", text)
    return titles + [r.strip() for r in table_rows if r.strip()]


def _slug(topic: str) -> str:
    return topic[:40].lower().replace(" ", "-").replace("/", "-")


def pick_next_topic(client: anthropic.Anthropic | None = None) -> str:
    """Return the next un-published topic from the calendar, or generate a new one."""
    published = _get_published_slugs()
    calendar_topics = _extract_calendar_topics()

    for topic in calendar_topics:
        if _slug(topic) not in published:
            return topic

    # All calendar topics exhausted — generate a fresh one with Claude
    if client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": TOPIC_GENERATOR_PROMPT}],
    )
    return message.content[0].text.strip()


if __name__ == "__main__":
    import sys
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY not set.")
    client = anthropic.Anthropic(api_key=api_key)
    topic = pick_next_topic(client)
    print(f"Next topic: {topic}")
