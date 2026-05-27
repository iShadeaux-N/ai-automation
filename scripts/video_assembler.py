#!/usr/bin/env python3
"""
Dread Files — Video Assembler
Concatenates Runway MP4 clips and overlays the ElevenLabs MP3 narration
to produce the final YouTube video using moviepy.
"""

import subprocess
import tempfile
from pathlib import Path


def _get_clip_duration(clip_path: Path) -> float:
    """Return duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", str(clip_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import json
    data = json.loads(result.stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return float(stream.get("duration", 0))
    return 0.0


def assemble_video(
    clip_paths: list[Path],
    audio_path: Path,
    out_path: Path,
    dry_run: bool = False,
) -> Path:
    """
    Concatenate clips and lay the narration audio on top.
    The video is looped/trimmed to match the audio length.
    Returns path to the final MP4.
    """
    if dry_run:
        print(f"  [DRY RUN] Would assemble {len(clip_paths)} clips + {audio_path.name} → {out_path.name}")
        return out_path

    if not clip_paths:
        raise ValueError("No clips provided to assemble.")

    print(f"  Assembler: concatenating {len(clip_paths)} clips...")

    # Build ffmpeg concat list
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for clip in clip_paths:
            f.write(f"file '{clip.resolve()}'\n")
        concat_list = Path(f.name)

    try:
        # Step 1: concatenate all clips into one silent video
        concat_path = out_path.parent / "_concat_tmp.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-c", "copy",
                str(concat_path),
            ],
            check=True,
            capture_output=True,
        )

        # Step 2: get audio duration to know final video length
        audio_duration = float(subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                "-of", "csv=p=0", str(audio_path),
            ],
            capture_output=True, text=True, check=True,
        ).stdout.strip())

        # Step 3: loop the concatenated video to match audio duration, overlay audio
        # -stream_loop -1 loops the video indefinitely, -t cuts at audio length
        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", str(concat_path),
                "-i", str(audio_path),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-t", str(audio_duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )

        concat_path.unlink(missing_ok=True)
        print(f"  ✓ Final video saved: {out_path} ({out_path.stat().st_size // (1024*1024)} MB, {audio_duration:.0f}s)")
        return out_path

    finally:
        concat_list.unlink(missing_ok=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: python video_assembler.py clips_dir/ narration.mp3 output.mp4")
        sys.exit(1)
    clips = sorted(Path(sys.argv[1]).glob("scene_*.mp4"))
    assemble_video(clips, Path(sys.argv[2]), Path(sys.argv[3]))
