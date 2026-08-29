"""
config.py — Myntra Wishlist-to-Purchase Behavior Analyzer
Central configuration. Fill in your credentials before running any scraper.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # loads .env from the project root

# ── Google Play Store ──────────────────────────────────────────────────────────
# Package name from the Play Store URL:
# https://play.google.com/store/apps/details?id=<PLAY_STORE_PACKAGE>
PLAY_STORE_PACKAGE: str = "com.myntra.android"

# ── Apple App Store ────────────────────────────────────────────────────────────
# Numeric App ID from the App Store URL:
# https://apps.apple.com/in/app/myntra-fashion-shopping-app/id<APP_STORE_ID>
APP_STORE_ID: str = "907394059"

# ISO 3166-1 alpha-2 country code for the App Store storefront to scrape
APP_STORE_COUNTRY: str = "in"

# ── YouTube Data API v3 ────────────────────────────────────────────────────────
# Loaded automatically from .env (YOUTUBE_API_KEY=...)
# Get a free key at: https://console.cloud.google.com → Enable "YouTube Data API v3"
YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")

# Video IDs to scrape — just the ID portion of https://www.youtube.com/watch?v=<ID>
YOUTUBE_VIDEO_IDS: list[str] = [
    "SC_zdDcYwE8",
    "Lq_sYoZ9zBw",
    "rady1Z9Lwms",
    "dcWh2RmeFkE",
    "1XPy8Y14NE0",
    "AYWh6qfopUM",
    "qP6KkeHwAbk",
]

# ── Scraper limits ─────────────────────────────────────────────────────────────
PLAY_STORE_MAX_REVIEWS: int = 1000
APP_STORE_MAX_REVIEWS:  int = 500
YOUTUBE_MAX_COMMENTS_PER_VIDEO: int = 100   # per video; YouTube API quota-aware
