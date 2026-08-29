"""
scrapers/youtube_comments_scraper.py — Myntra Wishlist-to-Purchase Behavior Analyzer

Fetches top-level comments from a list of YouTube videos using the
YouTube Data API v3. Designed for Myntra haul/review/unboxing videos.

Output schema per record:
    source  : "YouTube"
    date    : ISO-8601 string (UTC) — comment publish date
    text    : comment text
    rating  : null  (YouTube has no per-comment rating)
    url     : direct link to the comment (video URL + &lc=<comment_id>)

Output file: data/raw/youtube_comments.json

Install dependency:
    pip install google-api-python-client

Run:
    1. Set YOUTUBE_API_KEY and YOUTUBE_VIDEO_IDS in config.py
    2. python scrapers/youtube_comments_scraper.py

API Quota note:
    Each commentThreads.list call costs 1 unit.
    Default free quota is 10,000 units/day.
    At 100 results/page, fetching 200 comments/video ≈ 2 units/video.
"""

import os
import sys
import json
import logging
import time
from datetime import datetime, timezone

# ── Add project root to path so config.py is importable ───────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print(
        "ERROR: google-api-python-client is not installed.\n"
        "Fix: pip install google-api-python-client"
    )
    sys.exit(1)

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR     = os.path.join(BASE_DIR, "data", "raw")
OUTPUT_FILE = os.path.join(RAW_DIR, "youtube_comments.json")
os.makedirs(RAW_DIR, exist_ok=True)

YOUTUBE_API_SERVICE = "youtube"
YOUTUBE_API_VERSION = "v3"
PAGE_SIZE           = 100   # max allowed by the API per request


def build_youtube_client(api_key: str):
    """Initialise and return the YouTube API client."""
    return build(YOUTUBE_API_SERVICE, YOUTUBE_API_VERSION, developerKey=api_key)


def _comment_url(video_id: str, comment_id: str) -> str:
    """Return a direct link to the comment thread."""
    return f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"


def _to_iso(value: str) -> str:
    """
    YouTube returns RFC 3339 strings like '2024-03-15T12:34:56.000Z'.
    Parse and re-emit as ISO-8601 UTC.
    """
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return value


def fetch_comments_for_video(
    youtube,
    video_id: str,
    max_comments: int,
) -> list[dict]:
    """
    Fetch up to `max_comments` top-level comments for a single video.
    Returns normalised records in the project output schema.
    """
    logger.info(f"  Fetching comments for video: {video_id} (max={max_comments})")
    records: list[dict] = []
    page_token = None

    while len(records) < max_comments:
        remaining = max_comments - len(records)
        fetch_count = min(PAGE_SIZE, remaining)

        try:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=fetch_count,
                order="relevance",          # "relevance" or "time"
                textFormat="plainText",
                pageToken=page_token,
            )
            response = request.execute()

        except HttpError as exc:
            status = exc.resp.status
            if status == 403:
                logger.error(
                    f"  403 Forbidden for video {video_id}. "
                    "Comments may be disabled or your API key is invalid."
                )
            elif status == 404:
                logger.error(f"  404 Not Found — video '{video_id}' does not exist or is private.")
            else:
                logger.error(f"  YouTube API HttpError {status}: {exc}")
            break

        except Exception as exc:
            logger.error(f"  Unexpected error for video {video_id}: {exc}", exc_info=True)
            break

        items = response.get("items", [])
        if not items:
            break

        for item in items:
            top = item["snippet"]["topLevelComment"]["snippet"]
            comment_id = item["snippet"]["topLevelComment"]["id"]
            records.append({
                "source": "YouTube",
                "date":   _to_iso(top.get("publishedAt", "")),
                "text":   (top.get("textDisplay") or "").strip(),
                "rating": None,   # YouTube has no per-comment star rating
                "url":    _comment_url(video_id, comment_id),
                # extra metadata (useful for analysis, stripped during preprocess if unwanted)
                "_video_id":     video_id,
                "_like_count":   top.get("likeCount", 0),
                "_reply_count":  item["snippet"].get("totalReplyCount", 0),
            })

        page_token = response.get("nextPageToken")
        logger.info(f"    Page fetched — comments so far: {len(records)}")

        if not page_token:
            break

        # Be polite to the API — small delay between pages
        time.sleep(0.2)

    logger.info(f"  Done: {len(records)} comments fetched for {video_id}")
    return records


def main():
    api_key   = config.YOUTUBE_API_KEY
    video_ids = config.YOUTUBE_VIDEO_IDS
    max_per_video = config.YOUTUBE_MAX_COMMENTS_PER_VIDEO

    # ── Validate config ────────────────────────────────────────────────────────
    if not api_key or api_key == "YOUR_YOUTUBE_API_KEY_HERE":
        logger.error(
            "YOUTUBE_API_KEY is not configured.\n"
            "Edit config.py and set your YouTube Data API v3 key.\n"
            "Get one free at: https://console.cloud.google.com"
        )
        sys.exit(1)

    if not video_ids:
        logger.error(
            "YOUTUBE_VIDEO_IDS is empty.\n"
            "Edit config.py and add at least one YouTube video ID."
        )
        sys.exit(1)

    # ── Build client ───────────────────────────────────────────────────────────
    try:
        youtube = build_youtube_client(api_key)
    except Exception as exc:
        logger.error(f"Failed to build YouTube API client: {exc}")
        sys.exit(1)

    # ── Fetch comments from all videos ─────────────────────────────────────────
    all_records: list[dict] = []
    per_video_counts: dict[str, int] = {}

    for video_id in video_ids:
        try:
            records = fetch_comments_for_video(youtube, video_id, max_per_video)
        except Exception as exc:
            logger.error(f"Unhandled error for video {video_id}: {exc}", exc_info=True)
            records = []

        # Drop empty-text comments
        records = [r for r in records if r["text"]]
        per_video_counts[video_id] = len(records)
        all_records.extend(records)

    # ── Save ───────────────────────────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2, default=str)

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  YOUTUBE COMMENTS SCRAPER — SUMMARY")
    print("=" * 55)
    print(f"  Videos requested : {len(video_ids)}")
    print(f"  Total comments   : {len(all_records)}")
    print(f"  Per-video counts :")
    for vid, count in per_video_counts.items():
        url = f"https://youtu.be/{vid}"
        print(f"    {vid}  ->  {count:>4} comments   ({url})")
    print(f"  Output file      : {OUTPUT_FILE}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
