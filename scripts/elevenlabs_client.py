#!/usr/bin/env python3
"""
Dread Files — ElevenLabs Voiceover Client
Converts a narration script to an MP3 via the ElevenLabs API.
Handles long scripts by chunking at sentence boundaries.
"""

import os
import re
import requests
from pathlib import Path

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
MAX_CHARS_PER_CHUNK = 2500  # ElevenLabs free tier limit per request


def _get_api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise EnvironmentError("ELEVENLABS_API_KEY not set.")
    return key


def _clean_script(script: str) -> str:
    """Strip section headers and keep only the narration text."""
    lines = []
    for line in script.splitlines():
        stripped = line.strip()
        # Drop header tags like [TITLE], [HOOK], [WORD COUNT: ...]
        if re.match(r"^\[.+\]$", stripped):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> list[str]:
    """Split text at sentence boundaries to stay under max_chars."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_chars:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def generate_voiceover(
    script: str,
    out_path: Path,
    voice_id: str = "pNInz6obpgDQGcFmaJgB",  # Adam
    speed: float = 0.90,
    stability: float = 0.75,
    similarity_boost: float = 0.80,
    style: float = 0.15,
) -> Path:
    """
    Generate an MP3 from the narration script and save to out_path.
    Returns the path to the saved MP3.
    """
    api_key = _get_api_key()
    narration = _clean_script(script)
    chunks = _chunk_text(narration)

    audio_parts: list[bytes] = []

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    for i, chunk in enumerate(chunks, 1):
        print(f"  ElevenLabs: generating chunk {i}/{len(chunks)} ({len(chunk)} chars)...")
        payload = {
            "text": chunk,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
                "use_speaker_boost": True,
                "speed": speed,
            },
        }
        resp = requests.post(
            f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        audio_parts.append(resp.content)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        for part in audio_parts:
            f.write(part)

    print(f"  ✓ Voiceover saved: {out_path} ({out_path.stat().st_size // 1024} KB)")
    return out_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python elevenlabs_client.py script.txt output.mp3")
        sys.exit(1)
    script_text = Path(sys.argv[1]).read_text(encoding="utf-8")
    generate_voiceover(script_text, Path(sys.argv[2]))
