import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from googleapiclient.discovery import build
from .auth import get_credentials
from .yt_client import get_youtube_service, get_channel_info

def get_yt_analytics_service(creds=None):
    if creds is None:
        creds = get_credentials(service_type="youtube")
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

def run_weekly_analytics():
    creds = get_credentials(service_type="youtube")
    yt_service = get_youtube_service(creds)
    analytics_service = get_yt_analytics_service(creds)

    ch_info = get_channel_info(yt_service)
    channel_id = ch_info["id"]

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=7)

    repo_dir = Path(__file__).resolve().parent.parent
    reports_dir = repo_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_data = {
        "channel_id": channel_id,
        "channel_title": ch_info["title"],
        "total_subscribers": ch_info["subscriber_count"],
        "total_videos": ch_info["video_count"],
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        res = analytics_service.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost"
        ).execute()
        report_data["metrics"] = res
    except Exception as e:
        report_data["metrics_error"] = str(e)

    report_file = reports_dir / f"analytics_{end_date.isoformat()}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print(f"Weekly analytics saved to {report_file}")

if __name__ == "__main__":
    run_weekly_analytics()
