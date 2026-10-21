import io
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from .auth import get_credentials

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv"}

def get_drive_service(creds=None):
    if creds is None:
        creds = get_credentials(service_type="drive")
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def list_all_files_in_folder(service, folder_id: str) -> List[Dict[str, Any]]:
    files = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"
    while True:
        response = service.files().list(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType, size, createdTime)",
            pageSize=100,
            pageToken=page_token
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files

def audit_drive_folder(service, folder_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    all_files = list_all_files_in_folder(service, folder_id)
    videos = []
    non_conforming = []
    for item in all_files:
        name = item.get("name", "")
        mime = item.get("mimeType", "")
        ext = Path(name).suffix.lower()
        if mime == "application/vnd.google-apps.folder":
            continue
        if ext in VIDEO_EXTENSIONS or (mime and mime.startswith("video/")):
            videos.append(item)
        else:
            non_conforming.append(item)
    return videos, non_conforming

def get_or_create_uploaded_folder(service, parent_folder_id: str) -> str:
    query = f"'{parent_folder_id}' in parents and name = 'Uploaded' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    response = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = response.get("files", [])
    if files:
        return files[0]["id"]
    file_metadata = {
        "name": "Uploaded",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id]
    }
    folder = service.files().create(body=file_metadata, fields="id").execute()
    return folder.get("id")

def download_file(service, file_id: str, destination_path: Path) -> Path:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(str(destination_path), "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024 * 10)
        done = False
        while not done:
            status, done = downloader.next_chunk()
    return destination_path

def move_to_uploaded(service, file_id: str, current_parent_id: str, uploaded_folder_id: str):
    service.files().update(
        fileId=file_id,
        addParents=uploaded_folder_id,
        removeParents=current_parent_id,
        fields="id, parents"
    ).execute()
