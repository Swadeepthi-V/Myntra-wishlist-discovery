"""
scrapers/app_store_scraper.py — Myntra Wishlist-to-Purchase Behavior Analyzer

Fetches up to APP_STORE_MAX_REVIEWS reviews from the Apple App Store
for the app defined in config.py, using the `app-store-scraper` library.

Output schema per record:
    source  : "App Store"
    date    : ISO-8601 string (UTC)
    text    : review body text
    rating  : int  1–5
    url     : null (App Store reviews have no direct permalink)

Output file: data/raw/app_store_reviews.json

Install dependency:
    pip install app-store-scraper

Run:
    python scrapers/app_store_scraper.py
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

# ── Import app-store-scraper, avoiding self-import collision ───────────────────
# When run as `python scrapers/app_store_scraper.py`, Python inserts the
# scrapers/ directory at sys.path[0], which causes `from app_store_scraper
# import AppStore` to import THIS file instead of the installed package.
# Fix: temporarily strip scrapers/ from sys.path while loading the library.
_SCRAPERS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT    = os.path.dirname(_SCRAPERS_DIR)

# Remove scrapers/ from path, add project root for config, then import
_saved_path = sys.path[:]
sys.path = [p for p in sys.path if os.path.abspath(p) != _SCRAPERS_DIR]
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

try:
    from app_store_scraper import AppStore
except ImportError:
    sys.path = _saved_path
    print(
        "ERROR: app-store-scraper is not installed.\n"
        "Fix: pip install app-store-scraper"
    )
    sys.exit(1)
finally:
    # Restore scrapers/ so any relative imports within this file still work
    if _SCRAPERS_DIR not in sys.path:
        sys.path.append(_SCRAPERS_DIR)

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR     = os.path.join(BASE_DIR, "data", "raw")
OUTPUT_FILE = os.path.join(RAW_DIR, "app_store_reviews.json")
os.makedirs(RAW_DIR, exist_ok=True)


import time
import requests as _requests

# iTunes RSS API caps at 50 reviews per page, max 10 pages (500 total)
ITUNES_RSS_URL = (
    "https://itunes.apple.com/{country}/rss/customerreviews"
    "/page={page}/id={app_id}/sortby=mostrecent/json"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*",
}


def _to_iso(value) -> str:
    """Convert a date string or datetime to an ISO-8601 UTC string."""
    if not value:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    # iTunes dates: "2024-03-15T10:00:00-07:00"
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return str(value)


def fetch_app_store_reviews(
    app_id: str,
    country: str,
    max_reviews: int,
) -> list[dict]:
    """
    Fetch up to `max_reviews` reviews via the iTunes RSS JSON API directly.
    Apple's API supports up to 10 pages x 50 reviews = 500 reviews max.
    Returns raw entry dicts from the feed.
    """
    logger.info(
        f"Fetching up to {max_reviews} App Store reviews for app_id='{app_id}' "
        f"country='{country}' via iTunes RSS API ..."
    )

    all_entries: list[dict] = []
    max_pages = min(10, -(-max_reviews // 50))  # ceil division

    for page in range(1, max_pages + 1):
        if len(all_entries) >= max_reviews:
            break

        url = ITUNES_RSS_URL.format(country=country, page=page, app_id=app_id)
        logger.info(f"  Fetching page {page}/{max_pages} ...")

        try:
            resp = _requests.get(url, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            feed = resp.json().get("feed", {})
        except Exception as exc:
            logger.error(f"  Page {page} fetch error: {exc}")
            break

        entries = feed.get("entry", [])
        if not entries:
            logger.info(f"  No entries on page {page} — stopping.")
            break

        # First entry on page 1 is app metadata (no im:rating) — skip it
        if page == 1 and entries and "im:rating" not in entries[0]:
            entries = entries[1:]

        all_entries.extend(entries)
        logger.info(f"  Page {page}: {len(entries)} reviews (total: {len(all_entries)})")
        time.sleep(0.3)

    logger.info(f"Fetched {len(all_entries)} raw App Store reviews.")
    return all_entries[:max_reviews]



def _label(entry: dict, key: str, default="") -> str:
    """Extract the 'label' string from an iTunes RSS nested dict field."""
    val = entry.get(key, {})
    if isinstance(val, dict):
        return str(val.get("label", default)).strip()
    return str(val).strip() if val else default


def normalise(raw: dict) -> dict:
    """
    Map an iTunes RSS JSON entry dict to the project output schema.
    iTunes RSS entries look like:
      { "im:rating": {"label": "5"}, "title": {"label": "Great app"}, ... }
    """
    title  = _label(raw, "title")
    body   = _label(raw, "content")
    text   = f"{title} — {body}" if title and body else (title or body)

    try:
        rating = int(_label(raw, "im:rating"))
        rating = rating if 1 <= rating <= 5 else None
    except (ValueError, TypeError):
        rating = None

    date_raw = _label(raw, "updated")

    return {
        "source": "App Store",
        "date":   _to_iso(date_raw),
        "text":   text,
        "rating": rating,
        "url":    None,   # App Store reviews have no direct permalink
    }


def main():
    app_id      = config.APP_STORE_ID
    country     = config.APP_STORE_COUNTRY
    max_reviews = config.APP_STORE_MAX_REVIEWS

    if not app_id or app_id == "0":
        logger.error(
            "APP_STORE_ID is not configured.\n"
            "Edit config.py and set the correct numeric App Store ID."
        )
        sys.exit(1)

    # ── Fetch ──────────────────────────────────────────────────────────────────
    raw_reviews = fetch_app_store_reviews(
        app_id=app_id,
        country=country,
        max_reviews=max_reviews,
    )

    if not raw_reviews:
        logger.warning("No reviews fetched. Check the app ID, country, and internet connection.")

    # ── Normalise ──────────────────────────────────────────────────────────────
    records = [normalise(r) for r in raw_reviews]

    # ── Drop records with empty text ───────────────────────────────────────────
    before = len(records)
    records = [r for r in records if r["text"]]
    dropped = before - len(records)
    if dropped:
        logger.info(f"Dropped {dropped} records with empty review text.")

    # ── Trim to requested limit (library may return slightly more) ─────────────
    if len(records) > max_reviews:
        records = records[:max_reviews]
        logger.info(f"Trimmed to {max_reviews} records as requested.")

    # ── Save ───────────────────────────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, default=str)

    # ── Summary ────────────────────────────────────────────────────────────────
    rated = [r for r in records if r["rating"] is not None]
    avg_rating = round(sum(r["rating"] for r in rated) / len(rated), 2) if rated else "N/A"
    rating_dist = {i: sum(1 for r in rated if r["rating"] == i) for i in range(1, 6)}

    print("\n" + "=" * 55)
    print("  APP STORE SCRAPER — SUMMARY")
    print("=" * 55)
    print(f"  App ID           : {app_id}")
    print(f"  Country          : {country}")
    print(f"  Reviews saved    : {len(records)}")
    print(f"  Average rating   : {avg_rating} / 5")
    print(f"  Rating breakdown : {rating_dist}")
    print(f"  Output file      : {OUTPUT_FILE}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
