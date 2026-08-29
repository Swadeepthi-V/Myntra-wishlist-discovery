"""
scrapers/play_store_scraper.py — Myntra Wishlist-to-Purchase Behavior Analyzer

Fetches up to PLAY_STORE_MAX_REVIEWS reviews from the Google Play Store
for the package defined in config.py, using the `google-play-scraper` library.

Output schema per record:
    source  : "Play Store"
    date    : ISO-8601 string (UTC)
    text    : review body text
    rating  : int  1–5
    url     : null (Play Store reviews have no direct permalink)

Output file: data/raw/play_store_reviews.json

Install dependency:
    pip install google-play-scraper

Run:
    python scrapers/play_store_scraper.py
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

# ── Add project root to path so config.py is importable ───────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from google_play_scraper import reviews, Sort
except ImportError:
    print(
        "ERROR: google-play-scraper is not installed.\n"
        "Fix: pip install google-play-scraper"
    )
    sys.exit(1)

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR     = os.path.join(BASE_DIR, "data", "raw")
OUTPUT_FILE = os.path.join(RAW_DIR, "play_store_reviews.json")
os.makedirs(RAW_DIR, exist_ok=True)


def _to_iso(value) -> str:
    """Convert a datetime object or timestamp to an ISO-8601 UTC string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    # epoch int/float
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except Exception:
        return str(value)


def fetch_play_store_reviews(
    package: str,
    max_reviews: int,
    lang: str = "en",
    country: str = "in",
) -> list[dict]:
    """
    Fetch up to `max_reviews` reviews from the Play Store, sorted newest-first.
    Returns records in the standardised schema.
    """
    logger.info(
        f"Fetching up to {max_reviews} Play Store reviews for package '{package}' "
        f"(lang={lang}, country={country}) ..."
    )

    all_reviews: list[dict] = []
    continuation_token = None
    batch_size = 200   # google-play-scraper returns up to 200 per call

    while len(all_reviews) < max_reviews:
        remaining = max_reviews - len(all_reviews)
        fetch_count = min(batch_size, remaining)

        try:
            result, continuation_token = reviews(
                package,
                lang=lang,
                country=country,
                sort=Sort.NEWEST,
                count=fetch_count,
                continuation_token=continuation_token,
            )
        except Exception as exc:
            logger.error(f"Play Store API error: {exc}", exc_info=True)
            break

        if not result:
            logger.info("No more reviews returned — stopping.")
            break

        all_reviews.extend(result)
        logger.info(f"  Fetched {len(result)} reviews (total so far: {len(all_reviews)})")

        if continuation_token is None:
            logger.info("No continuation token — all available reviews fetched.")
            break

    logger.info(f"Raw fetch complete: {len(all_reviews)} reviews collected.")
    return all_reviews


def normalise(raw: dict) -> dict:
    """Map a google-play-scraper result dict to the project output schema."""
    return {
        "source": "Play Store",
        "date":   _to_iso(raw.get("at")),
        "text":   (raw.get("content") or "").strip(),
        "rating": raw.get("score"),   # int 1–5
        "url":    None,               # Play Store has no review permalink
    }


def main():
    package     = config.PLAY_STORE_PACKAGE
    max_reviews = config.PLAY_STORE_MAX_REVIEWS

    if not package or package == "com.example.placeholder":
        logger.error(
            "PLAY_STORE_PACKAGE is not configured.\n"
            "Edit config.py and set the correct package name."
        )
        sys.exit(1)

    # ── Fetch ──────────────────────────────────────────────────────────────────
    raw_reviews = fetch_play_store_reviews(package, max_reviews)

    if not raw_reviews:
        logger.warning("No reviews fetched. Check the package name and your internet connection.")

    # ── Normalise ──────────────────────────────────────────────────────────────
    records = [normalise(r) for r in raw_reviews]

    # ── Drop records with empty text (optional — comment out to keep them) ─────
    before = len(records)
    records = [r for r in records if r["text"]]
    dropped = before - len(records)
    if dropped:
        logger.info(f"Dropped {dropped} records with empty review text.")

    # ── Save ───────────────────────────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, default=str)

    # ── Summary ────────────────────────────────────────────────────────────────
    rated = [r for r in records if r["rating"] is not None]
    avg_rating = round(sum(r["rating"] for r in rated) / len(rated), 2) if rated else "N/A"
    rating_dist = {i: sum(1 for r in rated if r["rating"] == i) for i in range(1, 6)}

    print("\n" + "=" * 55)
    print("  PLAY STORE SCRAPER — SUMMARY")
    print("=" * 55)
    print(f"  Package          : {package}")
    print(f"  Reviews saved    : {len(records)}")
    print(f"  Average rating   : {avg_rating} / 5")
    print(f"  Rating breakdown : {rating_dist}")
    print(f"  Output file      : {OUTPUT_FILE}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
