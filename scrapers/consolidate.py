"""
scrapers/consolidate.py — Myntra Wishlist-to-Purchase Behavior Analyzer

Loads all three raw scraper outputs, normalises them into one consistent
schema, deduplicates, filters low-signal entries, and writes a single
combined CSV ready for analysis and ingestion.

Output schema (all_reviews.csv):
    source      str   "Play Store" | "App Store" | "YouTube"
    date        str   ISO-8601 UTC (empty string if unknown)
    text        str   review / comment body
    rating      float 1.0–5.0 or empty
    url         str   direct link or empty

Filters applied:
    - text must contain >= 5 words (removes emoji-only, "nice", "good 👍", etc.)
    - exact duplicate (source, text) pairs removed

Run:
    python scrapers/consolidate.py
"""

import os
import sys
import csv
import json
import logging
import re
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR        = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR  = os.path.join(BASE_DIR, "data", "processed")
OUTPUT_CSV     = os.path.join(PROCESSED_DIR, "all_reviews.csv")
os.makedirs(PROCESSED_DIR, exist_ok=True)

RAW_FILES = {
    "Play Store": os.path.join(RAW_DIR, "play_store_reviews.json"),
    "App Store":  os.path.join(RAW_DIR, "app_store_reviews.json"),
    "YouTube":    os.path.join(RAW_DIR, "youtube_comments.json"),
}

MIN_WORDS = 5   # entries with fewer words are treated as low-signal


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalise_date(value) -> str:
    """Return ISO-8601 UTC string, or empty string on failure."""
    if not value:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    s = str(value).strip()
    for fmt in (
        None,           # try fromisoformat first
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return s   # return raw string if parsing fails


def _normalise_rating(value) -> str:
    """Return rating as float string '1.0'–'5.0', or empty string."""
    if value is None or str(value).strip() in ("", "null", "None"):
        return ""
    try:
        r = float(value)
        if 1.0 <= r <= 5.0:
            return f"{r:.1f}"
    except (ValueError, TypeError):
        pass
    return ""


def _word_count(text: str) -> int:
    """Count whitespace-separated tokens, ignoring pure-emoji / punctuation tokens."""
    tokens = re.findall(r"[a-zA-Z0-9\u0900-\u097F\u0600-\u06FF]+", text)
    return len(tokens)


def _clean_text(text: str) -> str:
    """Strip leading/trailing whitespace and collapse internal runs of whitespace."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


# ── Normalise each source ──────────────────────────────────────────────────────

def normalise_record(raw: dict, source_label: str) -> dict | None:
    """
    Convert one raw record (any source) into the unified output schema.
    Returns None if the record should be discarded.
    """
    # ── text ──────────────────────────────────────────────────────────────────
    # Play Store / App Store use 'text'; YouTube uses 'text'; preprocess uses 'review_text'
    text = _clean_text(
        raw.get("text") or raw.get("review_text") or raw.get("content") or ""
    )
    if not text:
        return None

    # ── source ────────────────────────────────────────────────────────────────
    source = str(raw.get("source") or source_label).strip() or source_label

    # ── date ──────────────────────────────────────────────────────────────────
    date = _normalise_date(
        raw.get("date") or raw.get("scraped_at") or raw.get("updated") or ""
    )

    # ── rating ────────────────────────────────────────────────────────────────
    rating = _normalise_rating(raw.get("rating"))

    # ── url ───────────────────────────────────────────────────────────────────
    url = str(raw.get("url") or raw.get("source_url") or "").strip()

    return {
        "source": source,
        "date":   date,
        "text":   text,
        "rating": rating,
        "url":    url,
    }


# ── Pipeline ──────────────────────────────────────────────────────────────────

def load_source(label: str, filepath: str) -> list[dict]:
    """Load and normalise one raw JSON file. Returns list of unified records."""
    if not os.path.exists(filepath):
        logger.warning(f"  File not found, skipping '{label}': {filepath}")
        return []

    with open(filepath, encoding="utf-8") as f:
        raw_records = json.load(f)

    logger.info(f"  Loaded {len(raw_records):>5} raw records from '{label}'")

    normalised = []
    for r in raw_records:
        record = normalise_record(r, label)
        if record:
            normalised.append(record)

    dropped = len(raw_records) - len(normalised)
    if dropped:
        logger.info(f"    Dropped {dropped} records with no text")
    return normalised


def deduplicate(records: list[dict]) -> tuple[list[dict], int]:
    """Remove exact (source, text) duplicates. Returns (unique_records, n_removed)."""
    seen: set = set()
    unique = []
    for r in records:
        key = (r["source"], r["text"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(r)
    removed = len(records) - len(unique)
    return unique, removed


def filter_low_signal(records: list[dict], min_words: int) -> tuple[list[dict], int]:
    """Remove entries with fewer than `min_words` word-like tokens."""
    kept = [r for r in records if _word_count(r["text"]) >= min_words]
    removed = len(records) - len(kept)
    return kept, removed


def date_range(records: list[dict]) -> tuple[str, str]:
    """Return (earliest_date, latest_date) from the dataset, ignoring blanks."""
    dates = [r["date"] for r in records if r["date"]]
    if not dates:
        return ("—", "—")
    dates_sorted = sorted(dates)
    return dates_sorted[0][:10], dates_sorted[-1][:10]   # YYYY-MM-DD


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("  CONSOLIDATE — loading all raw sources")
    logger.info("=" * 60)

    # ── 1. Load & normalise each source ───────────────────────────────────────
    all_records: list[dict] = []
    raw_counts:  dict[str, int] = {}

    for label, filepath in RAW_FILES.items():
        records = load_source(label, filepath)
        raw_counts[label] = len(records)
        all_records.extend(records)

    logger.info(f"  Total after loading     : {len(all_records)}")

    # ── 2. Deduplicate ────────────────────────────────────────────────────────
    all_records, n_dedup = deduplicate(all_records)
    logger.info(f"  After deduplication     : {len(all_records)}  (removed {n_dedup})")

    # ── 3. Filter low-signal entries ──────────────────────────────────────────
    all_records, n_filtered = filter_low_signal(all_records, MIN_WORDS)
    logger.info(f"  After <{MIN_WORDS}-word filter   : {len(all_records)}  (removed {n_filtered})")

    if not all_records:
        logger.error("No records remain after filtering. Check raw data files.")
        sys.exit(1)

    # ── 4. Sort by date descending ────────────────────────────────────────────
    all_records.sort(key=lambda r: r["date"], reverse=True)

    # ── 5. Write CSV ──────────────────────────────────────────────────────────
    fieldnames = ["source", "date", "text", "rating", "url"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_records)

    logger.info(f"  Written to: {OUTPUT_CSV}")

    # ── 6. Per-source counts in final output ──────────────────────────────────
    from collections import Counter
    final_counts = Counter(r["source"] for r in all_records)

    # ── 7. Date range ─────────────────────────────────────────────────────────
    earliest, latest = date_range(all_records)

    # ── 8. Summary print ──────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print("  CONSOLIDATE PIPELINE -- SUMMARY")
    print("=" * 62)
    print(f"  {'Source':<20} {'Raw':>6}  {'Final':>6}  {'Dropped':>8}")
    print(f"  {'-'*50}")
    for label in RAW_FILES:
        raw_n   = raw_counts.get(label, 0)
        final_n = final_counts.get(label, 0)
        print(f"  {label:<20} {raw_n:>6}  {final_n:>6}  {raw_n - final_n:>8}")
    print(f"  {'-'*50}")
    total_raw   = sum(raw_counts.values())
    total_final = len(all_records)
    print(f"  {'TOTAL':<20} {total_raw:>6}  {total_final:>6}  {total_raw - total_final:>8}")
    print()
    print(f"  Deduplicates removed  : {n_dedup}")
    print(f"  Low-signal removed    : {n_filtered}  (< {MIN_WORDS} words)")
    print(f"  Date range            : {earliest}  to  {latest}")
    print(f"  Output                : {OUTPUT_CSV}")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
