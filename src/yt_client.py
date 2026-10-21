import time
from pathlib import Path
from typing import Dict, Any, Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from .auth import get_credentials

def get_youtube_service(creds=None):
    if creds is None:
        creds = get_credentials(service_type="youtube")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)

def verify_safety_gate(metadata: Dict[str, Any]):
    path_val = metadata.get("path")
    if path_val != "video_ai_gemini":
        raise RuntimeError(f"[block] Safety block: Unexpected metadata source '{path_val}'. Only 'video_ai_gemini' is allowed to publish live.")

def upload_video_resumable(
    service,
    video_path: Path,
    metadata: Dict[str, Any],
    privacy_status: str = "public",
    made_for_kids: bool = False,
    default_language: str = "en"
) -> Dict[str, Any]:
    verify_safety_gate(metadata)

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata.get("tags", []),
            "categoryId": "22",
            "defaultLanguage": default_language
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids
        }
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5
    )

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    return response

def get_channel_info(service):
    resp = service.channels().list(
        part="snippet,statistics,contentDetails,brandingSettings",
        mine=True
    ).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("No channel found for current credentials.")
    ch = items[0]
    return {
        "id": ch["id"],
        "title": ch["snippet"]["title"],
        "uploads_playlist_id": ch["contentDetails"]["relatedPlaylists"]["uploads"],
        "video_count": int(ch["statistics"].get("videoCount", 0)),
        "subscriber_count": int(ch["statistics"].get("subscriberCount", 0)),
        "brandingSettings": ch.get("brandingSettings", {})
    }
