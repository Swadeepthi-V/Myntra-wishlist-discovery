"""
analysis/wishlist_stats.py — Myntra Wishlist-to-Purchase Behavior Analyzer

Standalone analysis script that computes summary statistics and behavioral
signals from the processed review data, without requiring the Streamlit UI.

Outputs:
  - Console summary table
  - analysis/conversion_summary.json  (machine-readable stats)
  - analysis/category_breakdown.json

Run:
    python analysis/wishlist_stats.py
"""

import os
import json
import logging
from collections import defaultdict
from statistics import mean, median

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_FILE   = os.path.join(BASE_DIR, "data", "processed", "reviews_clean.json")
ANALYSIS_DIR = os.path.join(BASE_DIR, "analysis")
os.makedirs(ANALYSIS_DIR, exist_ok=True)


def load_records() -> list[dict]:
    with open(CLEAN_FILE, encoding="utf-8") as f:
        return json.load(f)


def conversion_rate(records: list[dict]) -> float:
    """Compute overall wishlist-to-purchase conversion rate (excluding unknowns)."""
    known = [r for r in records if r.get("wishlist_to_purchase") is not None]
    if not known:
        return 0.0
    converted = sum(1 for r in known if r["wishlist_to_purchase"] is True)
    return round(converted / len(known) * 100, 2)


def by_category(records: list[dict]) -> dict:
    """Compute per-category stats: count, conversion_rate, avg_rating, avg_price."""
    cats: dict = defaultdict(lambda: {"total": 0, "converted": 0, "ratings": [], "prices": []})
    for r in records:
        cat = r.get("category", "Unknown")
        cats[cat]["total"] += 1
        if r.get("wishlist_to_purchase") is True:
            cats[cat]["converted"] += 1
        try:
            cats[cat]["ratings"].append(float(r["rating"]))
        except (ValueError, TypeError, KeyError):
            pass
        try:
            cats[cat]["prices"].append(float(r["price_inr"]))
        except (ValueError, TypeError, KeyError):
            pass

    result = {}
    for cat, data in sorted(cats.items(), key=lambda x: -x[1]["total"]):
        known = data["total"]
        conv  = data["converted"]
        result[cat] = {
            "total_reviews":     known,
            "converted":         conv,
            "conversion_rate_%": round(conv / known * 100, 1) if known > 0 else 0,
            "avg_rating":        round(mean(data["ratings"]), 2) if data["ratings"] else None,
            "avg_price_inr":     round(mean(data["prices"]), 0) if data["prices"] else None,
        }
    return result


def by_brand(records: list[dict], top_n: int = 10) -> dict:
    """Compute per-brand conversion stats. Returns top_n brands by review count."""
    brands: dict = defaultdict(lambda: {"total": 0, "converted": 0})
    for r in records:
        brand = r.get("brand", "Unknown")
        brands[brand]["total"] += 1
        if r.get("wishlist_to_purchase") is True:
            brands[brand]["converted"] += 1

    ranked = sorted(brands.items(), key=lambda x: -x[1]["total"])[:top_n]
    result = {}
    for brand, data in ranked:
        t = data["total"]
        c = data["converted"]
        result[brand] = {
            "total_reviews":     t,
            "converted":         c,
            "conversion_rate_%": round(c / t * 100, 1) if t > 0 else 0,
        }
    return result


def price_band_analysis(records: list[dict]) -> dict:
    """Analyze conversion rate across price bands."""
    bands = {
        "under_500":    {"range": "< ₹500",         "records": []},
        "500_999":      {"range": "₹500 – ₹999",    "records": []},
        "1000_1999":    {"range": "₹1000 – ₹1999",  "records": []},
        "2000_2999":    {"range": "₹2000 – ₹2999",  "records": []},
        "3000_plus":    {"range": "₹3000+",          "records": []},
    }

    for r in records:
        try:
            price = float(r.get("price_inr", ""))
        except (ValueError, TypeError):
            continue
        if price < 500:
            bands["under_500"]["records"].append(r)
        elif price < 1000:
            bands["500_999"]["records"].append(r)
        elif price < 2000:
            bands["1000_1999"]["records"].append(r)
        elif price < 3000:
            bands["2000_2999"]["records"].append(r)
        else:
            bands["3000_plus"]["records"].append(r)

    result = {}
    for key, data in bands.items():
        recs = data["records"]
        known = [r for r in recs if r.get("wishlist_to_purchase") is not None]
        conv  = sum(1 for r in known if r["wishlist_to_purchase"] is True)
        result[data["range"]] = {
            "total_reviews":     len(recs),
            "converted":         conv,
            "conversion_rate_%": round(conv / len(known) * 100, 1) if known else 0,
        }
    return result


def main():
    if not os.path.exists(CLEAN_FILE):
        logger.error(f"Clean data not found: {CLEAN_FILE}\nRun preprocess.py first.")
        raise FileNotFoundError(CLEAN_FILE)

    records = load_records()
    logger.info(f"Loaded {len(records)} clean records.")

    # ── Compute stats ──────────────────────────────────────────────────────────
    overall_conv = conversion_rate(records)
    cat_stats    = by_category(records)
    brand_stats  = by_brand(records, top_n=10)
    price_stats  = price_band_analysis(records)

    # ── Console output ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  MYNTRA WISHLIST-TO-PURCHASE ANALYSIS")
    print(f"{'='*60}")
    print(f"  Total records:          {len(records)}")
    print(f"  Overall conversion rate: {overall_conv}%")
    print(f"\n  BY CATEGORY:")
    print(f"  {'Category':<28} {'Reviews':>8} {'Conv%':>7} {'Avg ₹':>8}")
    print(f"  {'-'*54}")
    for cat, d in cat_stats.items():
        price_str = f"{int(d['avg_price_inr'])}" if d["avg_price_inr"] else "—"
        print(f"  {cat:<28} {d['total_reviews']:>8} {d['conversion_rate_%']:>6}% {price_str:>8}")

    print(f"\n  BY PRICE BAND:")
    print(f"  {'Price Band':<20} {'Reviews':>8} {'Conv%':>7}")
    print(f"  {'-'*38}")
    for band, d in price_stats.items():
        print(f"  {band:<20} {d['total_reviews']:>8} {d['conversion_rate_%']:>6}%")

    print(f"\n  TOP BRANDS:")
    print(f"  {'Brand':<20} {'Reviews':>8} {'Conv%':>7}")
    print(f"  {'-'*38}")
    for brand, d in brand_stats.items():
        print(f"  {brand:<20} {d['total_reviews']:>8} {d['conversion_rate_%']:>6}%")
    print(f"{'='*60}\n")

    # ── Write JSON outputs ─────────────────────────────────────────────────────
    summary = {
        "total_records":          len(records),
        "overall_conversion_pct": overall_conv,
        "by_category":            cat_stats,
        "by_brand":               brand_stats,
        "by_price_band":          price_stats,
    }
    summary_path = os.path.join(ANALYSIS_DIR, "conversion_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info(f"Wrote summary to {summary_path}")
    print(f"Analysis complete. Results saved to analysis/conversion_summary.json")


if __name__ == "__main__":
    main()
