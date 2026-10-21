import json
import shutil
import subprocess
from pathlib import Path

def get_video_duration(video_path: Path) -> float:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return 59.0
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        val = res.stdout.strip()
        return float(val) if val else 59.0
    except Exception:
        return 59.0

def normalize_video(input_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        shutil.copy2(input_path, output_path)
        return output_path

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(input_path),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "128k",
        str(output_path)
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path
    except Exception:
        shutil.copy2(input_path, output_path)
        return output_path
