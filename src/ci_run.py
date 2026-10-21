import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .auth import get_credentials
from .drive_client import (
    get_drive_service,
    audit_drive_folder,
    download_file,
    get_or_create_uploaded_folder,
    move_to_uploaded
)
from .normalize import get_video_duration, normalize_video
from .llm_meta import generate_metadata_from_gemini, validate_metadata
from .yt_client import get_youtube_service, upload_video_resumable, get_channel_info

def load_json(file_path: Path):
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def save_json(file_path: Path, data):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    parser = argparse.ArgumentParser(description="Channel 12 Automation CI Runner")
    parser.add_argument("--dry-run", action="store_true", help="Run without uploading or modifying state")
    parser.add_argument("--max-uploads", type=int, default=1, help="Max videos to process per run")
    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parent.parent
    config_file = repo_dir / "config.json"
    state_file = repo_dir / "state" / "uploaded.json"

    config = load_json(config_file)
    state = load_json(state_file)
    if "items" not in state:
        state["items"] = {}
    if "history" not in state:
        state["history"] = []

    folder_id = config.get("drive_folder_id", "1-krSHZuIFegBppIsVzZUu_iUhosB6TbN")
    model_name = config.get("model", "gemini-flash-lite-latest")
    privacy_status = config.get("privacy_status", "public")
    made_for_kids = config.get("made_for_kids", False)
    default_lang = config.get("default_language", "en")
    max_uploads = args.max_uploads or config.get("max_uploads_per_run", 1)

    drive_service = get_drive_service()
    yt_service = get_youtube_service()

    channel_info_before = get_channel_info(yt_service)
    videos_before, non_conf = audit_drive_folder(drive_service, folder_id)

    pending_videos = [v for v in videos_before if v["id"] not in state["items"]]
    if not pending_videos:
        print("No new pending videos found in Drive folder.")
        return

    to_process = pending_videos[:max_uploads]
    print(f"Found {len(pending_videos)} pending videos. Processing {len(to_process)} video(s). Dry run: {args.dry_run}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        for vid in to_process:
            file_id = vid["id"]
            file_name = vid["name"]
            print(f"--- Processing video ID: {file_id} ({file_name}) ---")
            raw_path = tmp_path / f"raw_{file_name}"
            norm_path = tmp_path / f"norm_{file_name}.mp4"

            download_file(drive_service, file_id, raw_path)
            duration = get_video_duration(raw_path)
            normalize_video(raw_path, norm_path)
            duration_norm = get_video_duration(norm_path)

            metadata = generate_metadata_from_gemini(norm_path, model_name=model_name, duration=duration_norm)
            is_valid, msg = validate_metadata(metadata, duration_norm)
            if not is_valid:
                print(f"[warning] Metadata initial validation warning: {msg}. Sanitized version will be used.")

            run_id = f"run_{int(time.time())}_{file_id[:8]}"

            if args.dry_run:
                print("\n================ DRY RUN SUMMARY ================")
                print(f"Run ID: {run_id}")
                print(f"Duration: {duration_norm:.2f}s")
                print(f"Inferred Topic: {metadata.get('inferred_topic')}")
                print(f"Title ({len(metadata['title'])} chars): {metadata['title']}")
                print(f"Tag Count ({len(metadata.get('tags', []))}): {metadata.get('tags')}")
                print(f"Hashtags: {' '.join(metadata.get('hashtags', []))}")
                print(f"Metadata Path: {metadata.get('path')}")
                print(f"Model: {metadata.get('model')}")
                print(f"Gemini File ID: {metadata.get('gemini_file_id')}")
                print("=================================================\n")
                continue

            yt_res = upload_video_resumable(
                service=yt_service,
                video_path=norm_path,
                metadata=metadata,
                privacy_status=privacy_status,
                made_for_kids=made_for_kids,
                default_language=default_lang
            )
            video_id = yt_res.get("id")
            video_url = f"https://youtu.be/{video_id}"

            uploaded_folder_id = get_or_create_uploaded_folder(drive_service, folder_id)
            move_to_uploaded(drive_service, file_id, folder_id, uploaded_folder_id)

            state["items"][file_id] = {
                "video_id": video_id,
                "title": metadata["title"],
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "url": video_url,
                "inferred_topic": metadata.get("inferred_topic"),
                "gemini_file_id": metadata.get("gemini_file_id")
            }
            state["history"].append({
                "run_id": run_id,
                "drive_file_id": file_id,
                "video_id": video_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            save_json(state_file, state)

            videos_after, _ = audit_drive_folder(drive_service, folder_id)
            channel_info_after = get_channel_info(yt_service)

            print("\n================ LIVE UPLOAD REPORT ================")
            print(f"Run ID: {run_id}")
            print(f"Duration: {duration_norm:.2f}s")
            print(f"Video ID: {video_id}")
            print(f"Video URL: {video_url}")
            print(f"Title: {metadata['title']}")
            print(f"Tags: {metadata.get('tags')}")
            print(f"Hashtags: {metadata.get('hashtags')}")
            print(f"Privacy Status: {privacy_status}")
            print(f"Processing Status: {yt_res.get('status', {}).get('uploadStatus', 'uploaded')}")
            print(f"Made For Kids: {made_for_kids}")
            print(f"Default Language: {default_lang}")
            print(f"Drive Video Count: {len(videos_before)} -> {len(videos_after)}")
            print(f"Channel Video Count: {channel_info_before['video_count']} -> {channel_info_after['video_count']}")
            print("===================================================\n")

if __name__ == "__main__":
    main()
