"""
scrapers/preprocess.py — Myntra Wishlist-to-Purchase Behavior Analyzer

Merges and cleans all raw data sources into data/processed/reviews_clean.json.

Raw input files consumed (all optional — missing files are skipped):
  data/raw/reviews_raw.json        ← from scrapers/myntra_scraper.py (synthetic/CSV)
  data/raw/play_store_reviews.json ← from scrapers/play_store_scraper.py
  data/raw/app_store_reviews.json  ← from scrapers/app_store_scraper.py
  data/raw/youtube_comments.json   ← from scrapers/youtube_comments_scraper.py

Transformations applied:
  - Strip whitespace from all string fields
  - Normalize rating to integer string "1"–"5" (null preserved for YouTube)
  - Normalize wishlist_to_purchase to Python bool
  - Remove records missing both product_name and review_text
  - Deduplicate by (source, text) composite key
  - Ensure price_inr is a clean numeric string (strip ₹, commas, etc.)

Run:
    python scrapers/preprocess.py
"""

import os
import re
import json
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR       = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
CLEAN_FILE    = os.path.join(PROCESSED_DIR, "reviews_clean.json")

# All raw source files — missing files are silently skipped
RAW_SOURCES: dict[str, str] = {
    "Myntra (synthetic/CSV)": os.path.join(RAW_DIR, "reviews_raw.json"),
    "Play Store":             os.path.join(RAW_DIR, "play_store_reviews.json"),
    "App Store":              os.path.join(RAW_DIR, "app_store_reviews.json"),
    "YouTube":                os.path.join(RAW_DIR, "youtube_comments.json"),
}

os.makedirs(PROCESSED_DIR, exist_ok=True)

TRUTHY  = {"true", "1", "yes", "y", "purchased", "bought"}
FALSY   = {"false", "0", "no", "n", "not purchased", "wishlisted"}


def normalize_bool(value) -> bool | None:
    """Normalize wishlist_to_purchase to Python bool. Returns None if ambiguous."""
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in TRUTHY:
        return True
    if s in FALSY:
        return False
    return None   # ambiguous — keep record but flag as unknown


def normalize_price(raw: str) -> str:
    """Strip ₹, commas, spaces from price string and return numeric string."""
    cleaned = re.sub(r"[₹,\s]", "", str(raw)).strip()
    # Keep only digits and an optional decimal point
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    return cleaned if cleaned else ""


def normalize_rating(raw) -> str | None:
    """Normalize rating to integer string 1–5. Returns None if not applicable (e.g. YouTube)."""
    if raw is None or str(raw).strip() in ("", "null", "None"):
        return None
    try:
        val = round(float(str(raw).strip()))
        if 1 <= val <= 5:
            return str(val)
    except (ValueError, TypeError):
        pass
    return None


def clean_record(record: dict) -> dict | None:
    """
    Clean and validate a single review record.
    Handles two schemas:
      - Myntra/synthetic: product_name, review_text, brand, category, ...
      - Scrapers (Play Store / App Store / YouTube): source, text, rating, url, date
    Returns None if the record has no usable text and should be dropped.
    """
    cleaned = {}

    # ── Detect schema type ─────────────────────────────────────────────────────
    has_product = bool(str(record.get("product_name", "")).strip())
    has_source  = bool(str(record.get("source", "")).strip())

    # Flat scraper schema (Play Store / App Store / YouTube)
    if has_source and not has_product:
        text = str(record.get("text", "")).strip()
        if not text:
            return None   # Drop empty comments/reviews

        cleaned["source"]     = str(record.get("source", "")).strip()
        cleaned["date"]       = str(record.get("date", "")).strip()
        cleaned["review_text"] = text
        cleaned["rating"]     = normalize_rating(record.get("rating"))
        cleaned["url"]        = str(record.get("url") or "").strip() or None
        # Fields not present in this schema — set to empty / None
        cleaned["product_name"]          = ""
        cleaned["product_id"]            = ""
        cleaned["brand"]                 = ""
        cleaned["category"]              = ""
        cleaned["color"]                 = ""
        cleaned["size"]                  = ""
        cleaned["source_url"]            = cleaned["url"] or ""
        cleaned["scraped_at"]            = cleaned["date"]
        cleaned["price_inr"]             = ""
        cleaned["wishlist_to_purchase"]  = None
        return cleaned

    # Myntra / synthetic / CSV schema
    product_name = str(record.get("product_name", "")).strip()
    review_text  = str(record.get("review_text", "")).strip()
    if not product_name and not review_text:
        return None   # Nothing useful

    cleaned["product_name"] = product_name
    cleaned["product_id"]   = str(record.get("product_id", "")).strip() or "UNKNOWN"
    cleaned["brand"]        = str(record.get("brand", "")).strip()
    cleaned["category"]     = str(record.get("category", "")).strip()
    cleaned["color"]        = str(record.get("color", "")).strip()
    cleaned["size"]         = str(record.get("size", "")).strip()
    cleaned["source_url"]   = str(record.get("source_url", "")).strip()
    cleaned["scraped_at"]   = str(record.get("scraped_at", "")).strip()
    cleaned["review_text"]  = review_text
    cleaned["source"]       = str(record.get("source", "Myntra")).strip() or "Myntra"
    cleaned["date"]         = cleaned["scraped_at"]
    cleaned["url"]          = None

    # Normalize numeric / bool fields
    cleaned["price_inr"]            = normalize_price(record.get("price_inr", ""))
    cleaned["rating"]               = normalize_rating(record.get("rating", ""))
    cleaned["wishlist_to_purchase"]  = normalize_bool(record.get("wishlist_to_purchase"))

    return cleaned


def deduplicate(records: list[dict]) -> list[dict]:
    """Remove records with duplicate (product_id, review_text) pairs."""
    seen = set()
    unique = []
    for r in records:
        key = (r.get("product_id", ""), r.get("review_text", ""))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def deduplicate_cross_source(records: list[dict]) -> list[dict]:
    """
    Deduplicate across all sources by (source, text) composite key.
    Keeps first occurrence.
    """
    seen = set()
    unique = []
    for r in records:
        key = (r.get("source", ""), r.get("review_text") or r.get("text", ""))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def main():
    # ── Load all available raw sources ────────────────────────────────────────
    all_raw: list[dict] = []
    source_counts_raw: dict[str, int] = {}

    for source_label, filepath in RAW_SOURCES.items():
        if not os.path.exists(filepath):
            logger.info(f"Skipping '{source_label}' — file not found: {filepath}")
            source_counts_raw[source_label] = 0
            continue
        with open(filepath, encoding="utf-8") as f:
            records = json.load(f)
        logger.info(f"Loaded {len(records)} raw records from '{source_label}'.")
        source_counts_raw[source_label] = len(records)
        all_raw.extend(records)

    total_raw = len(all_raw)
    if total_raw == 0:
        logger.error(
            "No raw data files found. Run at least one scraper first:\n"
            "  python scrapers/myntra_scraper.py --mode synthetic --n 500\n"
            "  python scrapers/play_store_scraper.py\n"
            "  python scrapers/app_store_scraper.py\n"
            "  python scrapers/youtube_comments_scraper.py"
        )
        raise FileNotFoundError("No raw data available in data/raw/")

    logger.info(f"Total raw records across all sources: {total_raw}")

    # ── Clean ──────────────────────────────────────────────────────────────────
    cleaned = []
    dropped = 0
    for r in all_raw:
        result = clean_record(r)
        if result is not None:
            cleaned.append(result)
        else:
            dropped += 1

    logger.info(f"Cleaned: {len(cleaned)} records kept, {dropped} dropped.")

    # ── Deduplicate ────────────────────────────────────────────────────────────
    before_dedup = len(cleaned)
    cleaned = deduplicate(cleaned)                  # (product_id, review_text)
    cleaned = deduplicate_cross_source(cleaned)     # (source, text) cross-source
    removed_dedup = before_dedup - len(cleaned)
    logger.info(f"Deduplicated: removed {removed_dedup} duplicates.")

    # ── Wishlist conversion stats (only meaningful for Myntra source) ──────────
    converted     = sum(1 for r in cleaned if r.get("wishlist_to_purchase") is True)
    not_converted = sum(1 for r in cleaned if r.get("wishlist_to_purchase") is False)
    unknown       = sum(1 for r in cleaned if r.get("wishlist_to_purchase") is None)

    # ── Per-source breakdown in cleaned output ─────────────────────────────────
    source_out: dict = defaultdict(int)
    for r in cleaned:
        source_out[r.get("source", "Unknown")] += 1

    # ── Write ──────────────────────────────────────────────────────────────────
    with open(CLEAN_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2, default=str)

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  PREPROCESSING — SUMMARY")
    print("=" * 60)
    print(f"  {'Source':<28} {'Raw':>6}  {'Clean':>6}")
    print(f"  {'-'*44}")
    for label, raw_count in source_counts_raw.items():
        # Map label to schema 'source' value
        source_key = label if label != "Myntra (synthetic/CSV)" else "Myntra"
        clean_count = source_out.get(source_key, source_out.get(label, "—"))
        print(f"  {label:<28} {raw_count:>6}  {clean_count:>6}")
    print(f"  {'-'*44}")
    print(f"  {'TOTAL':<28} {total_raw:>6}  {len(cleaned):>6}")
    print(f"\n  Duplicates removed   : {removed_dedup}")
    print(f"  Wishlist converted   : {converted}")
    print(f"  Wishlist not conv.   : {not_converted}")
    print(f"  Conversion unknown   : {unknown}")
    print(f"\n  Output -> {CLEAN_FILE}")
    print("=" * 60)
    print("\nNext step: python ingest.py\n")


if __name__ == "__main__":
    main()
