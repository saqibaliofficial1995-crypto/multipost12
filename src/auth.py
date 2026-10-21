import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/drive"
]

def get_tokens_dir() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    if (base_dir.parent / "tokens").exists():
        return base_dir.parent / "tokens"
    return base_dir / "tokens"

def get_credentials(service_type: str = "youtube") -> Credentials:
    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    refresh_token = os.environ.get("YT_REFRESH_TOKEN")

    if client_id and client_secret and refresh_token:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES
        )
        if not creds.valid:
            creds.refresh(Request())
        return creds

    tokens_dir = get_tokens_dir()
    token_file = None
    if service_type == "drive" and (tokens_dir / "token_drive.json").exists():
        token_file = tokens_dir / "token_drive.json"
    elif (tokens_dir / "token.json").exists():
        token_file = tokens_dir / "token.json"
    elif (tokens_dir / "token_yt.json").exists():
        token_file = tokens_dir / "token_yt.json"

    if token_file and token_file.exists():
        with open(token_file, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        creds = Credentials.from_authorized_user_info(data, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        return creds

    client_secret_file = tokens_dir / "client_secret.json"
    if client_secret_file.exists():
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), SCOPES)
        creds = flow.run_local_server(port=0)
        save_path = tokens_dir / ("token_drive.json" if service_type == "drive" else "token.json")
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        return creds

    raise RuntimeError("No credentials found in environment variables or tokens directory.")

def get_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()
    tokens_dir = get_tokens_dir()
    key_file = tokens_dir / "gemini_key.txt"
    if key_file.exists():
        with open(key_file, "r", encoding="utf-8-sig") as f:
            return f.read().strip()
    raise RuntimeError("Gemini API key not found in environment or tokens directory.")
