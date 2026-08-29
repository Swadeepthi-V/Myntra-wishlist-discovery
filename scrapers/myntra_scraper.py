"""
scrapers/myntra_scraper.py — Myntra Wishlist-to-Purchase Behavior Analyzer

Scaffolded scraper for collecting Myntra product reviews and wishlist data.

NOTE: Myntra is a JavaScript-rendered SPA. True scraping requires either:
  (a) Selenium / Playwright with a real browser session, OR
  (b) Intercepting the Myntra API endpoints via browser DevTools and
      replicating those authenticated requests.

This file provides:
  1. A data-model spec (what fields we need per review record).
  2. A placeholder fetch() stub you can wire to your preferred scraping method.
  3. A CSV → JSON converter for data collected via manual export or a tool
     like Octoparse / ParseHub.
  4. A synthetic data generator for development/testing until real data arrives.

Output: data/raw/reviews_raw.json

Run:
    python scrapers/myntra_scraper.py --mode synthetic --n 200
    python scrapers/myntra_scraper.py --mode csv --input my_export.csv
"""

import os
import csv
import json
import random
import argparse
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR    = os.path.join(BASE_DIR, "data", "raw")
os.makedirs(RAW_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(RAW_DIR, "reviews_raw.json")

# ── Required fields spec ───────────────────────────────────────────────────────
# Each review record MUST contain these fields for ingest.py to work correctly.
REQUIRED_FIELDS = [
    "product_id",           # str: Myntra product ID (from URL)
    "product_name",         # str: Full product name
    "brand",                # str: Brand name
    "category",             # str: e.g. "Kurtas & Suits", "Dresses"
    "rating",               # str: "1"–"5"
    "review_text",          # str: Full review body (may be empty)
    "price_inr",            # str: Listed price at time of review
    "color",                # str: Selected color/variant
    "size",                 # str: Selected size
    "wishlist_to_purchase",  # bool/str: True if item was later purchased
    "source_url",           # str: Product URL
    "scraped_at",           # str: ISO-8601 timestamp
]

# ── Synthetic data config (for dev/testing) ────────────────────────────────────
BRANDS = [
    "Libas", "W", "Biba", "Global Desi", "FabIndia",
    "H&M", "Zara", "Mango", "AND", "Chemistry",
    "Nike", "Adidas", "Puma", "Skechers", "Crocs",
    "Caprese", "Hidesign", "Baggit", "Fastrack", "Lavie",
]

CATEGORIES = [
    "Kurtas & Suits", "Dresses", "T-Shirts", "Jeans",
    "Footwear", "Bags & Clutches", "Jewellery",
    "Sportswear", "Winter Wear", "Beauty & Personal Care",
]

PRODUCT_TEMPLATES = {
    "Kurtas & Suits":         ["Printed Anarkali Kurta", "Embroidered Straight Kurta", "Floral Kurti"],
    "Dresses":                ["Wrap Midi Dress", "Bodycon Mini Dress", "Floral Maxi Dress"],
    "T-Shirts":               ["Graphic Round Neck Tee", "Solid Polo Shirt", "Oversized Crop Top"],
    "Jeans":                  ["Slim Fit Mid Rise Jeans", "Wide Leg Jeans", "Distressed Skinny Jeans"],
    "Footwear":               ["Block Heel Sandals", "White Sneakers", "Ethnic Mojari"],
    "Bags & Clutches":        ["Sling Bag", "Tote Handbag", "Quilted Clutch"],
    "Jewellery":              ["Oxidised Silver Earrings", "Layered Necklace Set", "Statement Bangles"],
    "Sportswear":             ["Dry-Fit Running Shorts", "Sports Bra", "Training Joggers"],
    "Winter Wear":            ["Quilted Puffer Jacket", "Cable Knit Sweater", "Faux Fur Shrug"],
    "Beauty & Personal Care": ["Moisturising Face Serum", "Matte Lipstick", "Kajal Pencil"],
}

REVIEW_SNIPPETS_YES = [  # wishlist_to_purchase = True
    "Exactly as shown. Bought it without hesitation after seeing the price drop.",
    "Quality is outstanding. Wore it to a wedding and got so many compliments.",
    "Finally pulled the trigger — the fit is perfect and fabric is premium.",
    "Was in my wishlist for 2 months. Sale price made it a no-brainer.",
    "Looks even better in person. Super happy with this purchase.",
    "Size guide was accurate. First time I got the right fit on Myntra.",
    "The colour is vibrant and the stitching is very neat.",
    "Quick delivery, well packed. Exactly what I was hoping for.",
]

REVIEW_SNIPPETS_NO = [  # wishlist_to_purchase = False (still reviewing — cross-site data)
    "Nice design but the fabric feels cheap for the price.",
    "Sizing runs small. My usual M was too tight.",
    "Love the look but hesitating because of the high price.",
    "Color is slightly different from the images — disappointed.",
    "Still in my wishlist. Waiting for a sale before buying.",
    "Material is not as described. Expected cotton, got polyester.",
    "The kurta looks good but the dupatta quality is poor.",
    "Too expensive for what it is. Will wait for a discount.",
]

SIZES  = ["XS", "S", "M", "L", "XL", "XXL", "6", "7", "8", "9", "10", "Free Size"]
COLORS = ["Black", "White", "Red", "Navy Blue", "Olive Green", "Blush Pink",
          "Mustard", "Teal", "Maroon", "Ivory", "Printed", "Multi"]


def generate_synthetic_record(idx: int) -> dict:
    """Generate one synthetic review record for development/testing."""
    category = random.choice(CATEGORIES)
    brand    = random.choice(BRANDS)
    product_templates = PRODUCT_TEMPLATES.get(category, ["Product"])
    product_name = f"{brand} {random.choice(product_templates)}"
    converted    = random.random() > 0.45          # ~55% conversion rate
    review_pool  = REVIEW_SNIPPETS_YES if converted else REVIEW_SNIPPETS_NO
    rating_val   = random.choices([5, 4, 3, 2, 1], weights=[35, 30, 20, 10, 5])[0]
    price        = random.choice([299, 499, 699, 999, 1299, 1599, 1999, 2499, 2999, 3999])
    days_ago     = random.randint(1, 365)
    scraped_date = (datetime.utcnow() - timedelta(days=days_ago)).isoformat() + "Z"

    return {
        "product_id":           f"MYN{idx:06d}",
        "product_name":         product_name,
        "brand":                brand,
        "category":             category,
        "rating":               str(rating_val),
        "review_text":          random.choice(review_pool),
        "price_inr":            str(price),
        "color":                random.choice(COLORS),
        "size":                 random.choice(SIZES),
        "wishlist_to_purchase": converted,
        "source_url":           f"https://www.myntra.com/{brand.lower().replace(' ', '-')}/{idx}",
        "scraped_at":           scraped_date,
    }


def from_csv(input_path: str) -> list[dict]:
    """
    Convert a CSV export (e.g. from Octoparse / ParseHub) into the standard
    review record format. Column names are mapped loosely.
    Update the mapping below to match your actual export column names.
    """
    FIELD_MAP = {
        # CSV column name  →  our field name
        "Product ID":      "product_id",
        "Name":            "product_name",
        "Brand":           "brand",
        "Category":        "category",
        "Star Rating":     "rating",
        "Review":          "review_text",
        "Price":           "price_inr",
        "Colour":          "color",
        "Size":            "size",
        "Purchased":       "wishlist_to_purchase",
        "URL":             "source_url",
    }

    records = []
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            record = {}
            for csv_col, our_field in FIELD_MAP.items():
                record[our_field] = row.get(csv_col, "").strip()
            record["scraped_at"] = datetime.utcnow().isoformat() + "Z"
            if not record.get("product_id"):
                record["product_id"] = f"CSV{i:05d}"
            records.append(record)

    logger.info(f"Converted {len(records)} rows from CSV.")
    return records


def main():
    parser = argparse.ArgumentParser(description="Myntra review scraper / data generator")
    parser.add_argument(
        "--mode", choices=["synthetic", "csv"],
        default="synthetic",
        help="Data source: 'synthetic' (fake data for dev) or 'csv' (real export)",
    )
    parser.add_argument("--n",     type=int, default=200,
                        help="Number of synthetic records to generate (default: 200)")
    parser.add_argument("--input", type=str, default=None,
                        help="Path to input CSV file (required for --mode csv)")
    args = parser.parse_args()

    if args.mode == "synthetic":
        logger.info(f"Generating {args.n} synthetic review records ...")
        records = [generate_synthetic_record(i) for i in range(args.n)]

    elif args.mode == "csv":
        if not args.input:
            parser.error("--input is required for --mode csv")
        logger.info(f"Loading CSV from: {args.input}")
        records = from_csv(args.input)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(records)} records to {OUTPUT_FILE}")
    print(f"\nDone — {len(records)} records written to:\n  {OUTPUT_FILE}")
    print("Next step: python scrapers/preprocess.py")


if __name__ == "__main__":
    main()
