import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple
import requests
from .auth import get_gemini_key

CURRENCY_REGEX = re.compile(r"[\$\€\£\¥\₹]|(\b(USD|AED|EUR|GBP|INR|PKR)\b)", re.IGNORECASE)
MAGNITUDE_REGEX = re.compile(r"\b\d+([.,]\d+)?\s*(m|b|k|million|billion|sqft|sq\s*ft|feet)\b", re.IGNORECASE)

def upload_video_to_gemini(video_path: Path, api_key: str) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
    headers = {
        "X-Goog-Upload-Command": "start, upload, finalize",
        "X-Goog-Upload-Header-Content-Length": str(video_path.stat().st_size),
        "X-Goog-Upload-Header-Content-Type": "video/mp4",
        "Content-Type": "video/mp4"
    }
    with open(video_path, "rb") as f:
        resp = requests.post(url, headers=headers, data=f, timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to upload video to Gemini Files API: {resp.status_code} - {resp.text}")
    file_info = resp.json().get("file", {})
    file_uri = file_info.get("uri")
    file_name = file_info.get("name")
    
    get_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
    for _ in range(30):
        check_resp = requests.get(get_url, timeout=30)
        if check_resp.status_code == 200:
            state = check_resp.json().get("state")
            if state == "ACTIVE":
                return {"file_uri": file_uri, "name": file_name, "id": file_name}
            elif state == "FAILED":
                raise RuntimeError("Gemini file processing failed")
        time.sleep(2)
    return {"file_uri": file_uri, "name": file_name, "id": file_name}

def validate_metadata(meta: Dict[str, Any], duration: float) -> Tuple[bool, str]:
    title = meta.get("title", "")
    description = meta.get("description", "")
    tags = meta.get("tags", [])
    hashtags = meta.get("hashtags", [])

    if len(title) >= 60:
        return False, f"Title length {len(title)} >= 60"
    
    if len(tags) < 10 or len(tags) > 15:
        return False, f"Tag count {len(tags)} not between 10 and 15"
    
    joined_tags = ",".join(tags)
    if len(joined_tags) >= 460:
        return False, f"Joined tags length {len(joined_tags)} >= 460"
    
    if len(hashtags) != 3:
        return False, f"Hashtag count {len(hashtags)} != 3"
    
    if duration <= 60.0:
        if not any(h.lower() == "#shorts" for h in hashtags):
            return False, "Shorts duration <= 60s must include #shorts"
            
    combined_text = f"{title} {description} {' '.join(tags)} {' '.join(hashtags)}"
    if CURRENCY_REGEX.search(combined_text):
        return False, "Currency symbols or currency codes detected"
    if MAGNITUDE_REGEX.search(combined_text):
        return False, "Magnitude claim detected"
        
    return True, "Valid"

def sanitize_and_fix_metadata(meta: Dict[str, Any], duration: float) -> Dict[str, Any]:
    title = meta.get("title", "").strip()
    title = CURRENCY_REGEX.sub("", title)
    title = MAGNITUDE_REGEX.sub("", title).strip()
    if len(title) >= 60:
        title = title[:59].rsplit(" ", 1)[0]
    if not title:
        title = "Incredible Moment You Must Watch"

    tags = meta.get("tags", [])
    cleaned_tags = []
    for t in tags:
        t_clean = CURRENCY_REGEX.sub("", t)
        t_clean = MAGNITUDE_REGEX.sub("", t_clean).strip()
        if t_clean and t_clean not in cleaned_tags:
            cleaned_tags.append(t_clean)
    
    while len(cleaned_tags) < 10:
        cleaned_tags.append(f"video highlight {len(cleaned_tags)+1}")
    if len(cleaned_tags) > 15:
        cleaned_tags = cleaned_tags[:15]
        
    while len(",".join(cleaned_tags)) >= 460 and len(cleaned_tags) > 10:
        cleaned_tags.pop()

    raw_hashtags = meta.get("hashtags", [])
    hashtags = []
    for h in raw_hashtags:
        h_clean = h.strip()
        if not h_clean.startswith("#"):
            h_clean = f"#{h_clean}"
        h_clean = CURRENCY_REGEX.sub("", h_clean)
        h_clean = MAGNITUDE_REGEX.sub("", h_clean)
        if h_clean and h_clean != "#" and h_clean not in hashtags:
            hashtags.append(h_clean)

    if duration <= 60.0:
        if not any(h.lower() == "#shorts" for h in hashtags):
            if len(hashtags) >= 3:
                hashtags[2] = "#shorts"
            else:
                hashtags.append("#shorts")

    fallback_tags = ["#viral", "#trending", "#daily"]
    idx = 0
    while len(hashtags) < 3:
        cand = fallback_tags[idx % len(fallback_tags)]
        if cand not in hashtags:
            hashtags.append(cand)
        idx += 1
    if len(hashtags) > 3:
        hashtags = hashtags[:3]

    raw_desc = meta.get("description", "").strip()
    raw_desc = CURRENCY_REGEX.sub("", raw_desc)
    raw_desc = MAGNITUDE_REGEX.sub("", raw_desc).strip()
    
    # Description separator fix: clean formatting
    hashtags_block = " ".join(hashtags)
    if raw_desc:
        description = f"{raw_desc}\n\n{hashtags_block}\n\nGladys Garza Official Channel"
    else:
        description = f"Watch this amazing video!\n\n{hashtags_block}\n\nGladys Garza Official Channel"

    return {
        "title": title,
        "description": description,
        "tags": cleaned_tags,
        "hashtags": hashtags,
        "path": "video_ai_gemini"
    }

def generate_metadata_from_gemini(video_path: Path, model_name: str = "gemini-flash-lite-latest", duration: float = 59.0) -> Dict[str, Any]:
    api_key = get_gemini_key()
    uploaded = upload_video_to_gemini(video_path, api_key)
    file_uri = uploaded["file_uri"]

    prompt = (
        "Watch this video carefully and generate metadata strictly in JSON format.\n"
        "Rules:\n"
        "1. title: Under 60 characters, engaging and descriptive of the actual visual content.\n"
        "2. description: 2-3 sentences describing what happens in the video.\n"
        "3. tags: Exactly 12 to 14 relevant tags. Total comma-separated length must be under 400 characters.\n"
        "4. hashtags: Exactly 3 relevant hashtags starting with # (include #shorts if video is under 60 seconds).\n"
        "5. topic: One short sentence identifying the exact visual topic/niche.\n"
        "ABSOLUTELY FORBIDDEN:\n"
        "- Do NOT include any currency symbols ($ , € , £ , ¥ , ₹) or codes (USD, EUR, etc.).\n"
        "- Do NOT include any magnitude claims (e.g., million, billion, k, sqft, feet).\n"
        "- Do NOT invent false facts.\n"
        "Return ONLY a valid JSON object with keys: title, description, tags, hashtags, topic."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"fileData": {"fileUri": file_uri, "mimeType": "video/mp4"}},
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }
    resp = requests.post(url, json=payload, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API generateContent call failed: {resp.status_code} - {resp.text}")
    
    result = resp.json()
    candidates = result.get("candidates", [])
    if not candidates:
        raise RuntimeError("No candidate returned by Gemini.")
    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
    
    try:
        data = json.loads(text)
    except Exception:
        clean = re.sub(r"^```json\s*", "", text.strip())
        clean = re.sub(r"\s*```$", "", clean)
        data = json.loads(clean)

    data = sanitize_and_fix_metadata(data, duration)
    data["gemini_file_id"] = uploaded.get("id")
    data["model"] = model_name
    data["inferred_topic"] = data.get("topic", "General Video Highlight")
    return data
