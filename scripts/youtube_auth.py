#!/usr/bin/env python3
"""
One-time YouTube OAuth2 authorization.
Run this locally to generate config/youtube_token.json.
After this runs successfully, the pipeline can upload without a browser.
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path

TOKEN_PATH = Path(__file__).parent.parent / "config" / "youtube_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")

if not client_id or not client_secret:
    sys.exit("Error: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET not set in .env")

client_config = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

print("Opening browser for YouTube authorization...")
print("Sign in with your Dread Files Google account and click Allow.\n")

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
creds = flow.run_local_server(port=8080, open_browser=True)

TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
TOKEN_PATH.write_text(creds.to_json())
print(f"\n✓ Token saved to {TOKEN_PATH}")
print("You can now run the full pipeline — YouTube uploads will work automatically.")
