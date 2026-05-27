#!/usr/bin/env python3
"""
Dread Files — YouTube Data API v3 Uploader
Uploads the final MP4 + thumbnail to YouTube with full metadata.
Handles OAuth2: on first run it opens a browser to authorize, then saves
a token file for all future unattended runs.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TOKEN_PATH = Path(__file__).parent.parent / "config" / "youtube_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
AI_DISCLOSURE = "\n\n---\nNarration in this video is AI-generated using ElevenLabs."


def _get_credentials():
    """Return valid OAuth2 credentials, refreshing or re-authorizing as needed."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
        return creds

    if not creds or not creds.valid:
        client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise EnvironmentError(
                "YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set for first-time auth."
            )
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

    return creds


def _extract_title(seo_metadata: str) -> str:
    match = re.search(r"(?:1\.|VIDEO TITLE)[:\s]*(.+)", seo_metadata, re.IGNORECASE)
    if match:
        title = match.group(1).strip().strip('"')
        return title[:100]
    return "Dread Files Horror Story"


def _extract_description(seo_metadata: str) -> str:
    match = re.search(
        r"(?:2\.|DESCRIPTION)[:\s]*(.+?)(?:\n\n3\.|\n\nTAGS|\Z)",
        seo_metadata,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip() + AI_DISCLOSURE
    return "A Dread Files original horror story." + AI_DISCLOSURE


def _extract_tags(seo_metadata: str) -> list[str]:
    match = re.search(
        r"(?:3\.|TAGS)[:\s]*(.+?)(?:\n\n4\.|\n\nTHUMBNAIL|\Z)",
        seo_metadata,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        raw = match.group(1).strip()
        tags = [t.strip().strip('"') for t in re.split(r"[,\n]", raw) if t.strip()]
        return tags[:500]  # YouTube tag limit
    return ["scary stories", "horror", "dread files", "AI narrated horror"]


def _next_upload_time(config: dict) -> str:
    """Return an ISO 8601 publish time for the next valid upload slot."""
    best_days = config.get("best_upload_days", ["Tuesday", "Thursday", "Saturday", "Sunday"])
    best_time = config.get("best_upload_time", "18:00")
    day_map = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6,
    }
    target_weekdays = sorted([day_map[d] for d in best_days if d in day_map])

    now = datetime.now(timezone.utc)
    try:
        t = datetime.strptime(best_time, "%I:%M %p")
    except ValueError:
        t = datetime.strptime(best_time, "%H:%M")
    hour, minute = t.hour, t.minute

    for offset in range(8):
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        from datetime import timedelta
        candidate += timedelta(days=offset)
        if candidate.weekday() in target_weekdays and candidate > now:
            return candidate.isoformat()

    # Fallback: 24 hours from now
    from datetime import timedelta
    return (now + timedelta(days=1)).isoformat()


def upload_video(
    video_path: Path,
    thumbnail_path: Path,
    seo_metadata: str,
    config: dict,
    dry_run: bool = False,
) -> str:
    """
    Upload video + thumbnail to YouTube with metadata.
    Returns the YouTube video ID (or a placeholder in dry_run mode).
    """
    title = _extract_title(seo_metadata)
    description = _extract_description(seo_metadata)
    tags = _extract_tags(seo_metadata)
    publish_at = _next_upload_time(config)

    if dry_run:
        print(f"  [DRY RUN] Would upload: {title}")
        print(f"  [DRY RUN] Scheduled for: {publish_at}")
        print(f"  [DRY RUN] Tags: {', '.join(tags[:5])}...")
        return "DRY_RUN_VIDEO_ID"

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    print(f"  YouTube: uploading '{title}'...")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",  # People & Blogs (commonly used for story channels)
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]
    print(f"  YouTube: upload complete — video ID: {video_id}")

    # Set thumbnail
    if thumbnail_path.exists():
        print(f"  YouTube: setting thumbnail...")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
        ).execute()
        print(f"  ✓ Thumbnail set.")

    print(f"  ✓ Scheduled to publish at: {publish_at}")
    return video_id


if __name__ == "__main__":
    import json
    if len(sys.argv) < 4:
        print("Usage: python youtube_uploader.py video.mp4 thumbnail.jpg seo_metadata.txt")
        sys.exit(1)
    config_path = Path(__file__).parent.parent / "config" / "channels.json"
    channel_config = json.loads(config_path.read_text())["youtube"]
    seo = Path(sys.argv[3]).read_text(encoding="utf-8")
    vid_id = upload_video(Path(sys.argv[1]), Path(sys.argv[2]), seo, channel_config)
    print(f"Video ID: {vid_id}")
