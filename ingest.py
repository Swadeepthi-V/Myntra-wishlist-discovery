"""
ingest.py — Myntra Wishlist Discovery · One-shot ingestion script

Reads scraped/processed review & wishlist data from data/processed/,
embeds each record using BAAI/bge-large-en-v1.5, and upserts all
vectors into a persistent ChromaDB collection named `myntra_reviews`.

Usage:
    python ingest.py

Safe to re-run; existing documents with the same ID will be updated.

Expected input file: data/processed/reviews_clean.json
Each record must have at minimum: product_id, product_name, category,
rating (str), review_text, brand.
Optional: price_inr, color, size, wishlist_to_purchase (bool-ish).
"""

import os
import json
import logging
import chromadb
from embeddings import EmbeddingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR  = os.path.join(BASE_DIR, "data", "processed")
REVIEWS_FILE   = os.path.join(PROCESSED_DIR, "reviews_clean.json")
CHROMA_DIR     = os.path.join(BASE_DIR, "chroma_db")
COLLECTION     = "myntra_reviews"
EMBED_MODEL    = os.getenv("EMBED_MODEL", "BAAI/bge-large-en-v1.5")


def load_reviews(path: str) -> list[dict]:
    """Load cleaned review records from JSON file."""
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    logger.info(f"Loaded {len(records)} review records from {path}")
    return records


def build_document_text(record: dict) -> str:
    """
    Combine key fields into a single searchable text string for embedding.
    Optimized for wishlist-to-purchase behavior signals.
    """
    parts = [
        f"Product: {record.get('product_name', 'Unknown')}",
        f"Brand: {record.get('brand', 'Unknown')}",
        f"Category: {record.get('category', 'Unknown')}",
        f"Rating: {record.get('rating', 'N/A')}/5",
    ]
    if record.get("review_text"):
        parts.append(f"Review: {record['review_text']}")
    if record.get("color"):
        parts.append(f"Color/Variant: {record['color']}")
    if record.get("size"):
        parts.append(f"Size: {record['size']}")
    converted = record.get("wishlist_to_purchase")
    if converted is not None:
        label = "Yes" if str(converted).lower() in ("true", "1", "yes") else "No"
        parts.append(f"Wishlist-to-Purchase Conversion: {label}")
    return " | ".join(parts)


def build_metadata(record: dict) -> dict:
    """Extract flat metadata dict for ChromaDB (string / int / float values only)."""
    return {
        "product_id":             str(record.get("product_id", "")),
        "product_name":           str(record.get("product_name", "")),
        "brand":                  str(record.get("brand", "")),
        "category":               str(record.get("category", "")),
        "rating":                 str(record.get("rating", "")),
        "price_inr":              str(record.get("price_inr", "")),
        "color":                  str(record.get("color", "")),
        "size":                   str(record.get("size", "")),
        "wishlist_to_purchase":   str(record.get("wishlist_to_purchase", "")),
        "source_url":             str(record.get("source_url", "")),
    }


def main():
    # ── 1. Load processed reviews ──────────────────────────────────────────────
    if not os.path.exists(REVIEWS_FILE):
        logger.error(
            f"Processed data file not found: {REVIEWS_FILE}\n"
            "Run the scraper first: python scrapers/myntra_scraper.py"
        )
        raise FileNotFoundError(REVIEWS_FILE)

    records = load_reviews(REVIEWS_FILE)

    # ── 2. Prepare texts, IDs, and metadata ───────────────────────────────────
    texts     = [build_document_text(r) for r in records]
    ids       = [f"review_{i:05d}" for i in range(len(records))]
    metadatas = [build_metadata(r) for r in records]

    # ── 3. Embed documents ─────────────────────────────────────────────────────
    logger.info(f"Initializing EmbeddingService (model={EMBED_MODEL}) ...")
    embed_service = EmbeddingService(model_name=EMBED_MODEL)
    embeddings = embed_service.embed_documents(texts)
    logger.info(f"Embedding shape: {embeddings.shape}")

    # ── 4. Upsert into ChromaDB ────────────────────────────────────────────────
    logger.info(f"Opening persistent ChromaDB at: {CHROMA_DIR}")
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # get_or_create makes this idempotent across re-runs
    collection = client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    logger.info(f"Upserting {len(ids)} records into '{COLLECTION}' collection ...")
    # ChromaDB upsert in chunks of 500 to avoid memory spikes
    chunk_size = 500
    for start in range(0, len(ids), chunk_size):
        end = start + chunk_size
        collection.upsert(
            ids=ids[start:end],
            embeddings=[e.tolist() for e in embeddings[start:end]],
            documents=texts[start:end],
            metadatas=metadatas[start:end],
        )
        logger.info(f"  Upserted records {start}–{min(end, len(ids)) - 1}")

    count = collection.count()
    logger.info(f"Ingestion complete. Collection '{COLLECTION}' now has {count} documents.")
    print(f"\nIngestion complete — {count} review records indexed in ChromaDB.")


if __name__ == "__main__":
    main()
