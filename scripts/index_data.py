"""
scripts/index_data.py — Myntra Wishlist-to-Purchase Behavior Analyzer

Indexing pipeline:
  1. Load data/processed/all_reviews.csv
  2. Embed each text with BAAI/bge-large-en-v1.5 (via EmbeddingService in embeddings.py)
  3. Upsert into a persistent ChromaDB collection `myntra_reviews` at data/chroma_db/
  4. Idempotent — deterministic IDs mean re-running skips already-indexed records

Metadata stored per vector:
    source   str    "Play Store" | "App Store" | "YouTube"
    date     str    ISO-8601 UTC
    rating   str    "1.0"–"5.0" or ""
    url      str    direct link or ""

Run:
    python scripts/index_data.py

Options (env vars):
    EMBED_MODEL   override embedding model  (default: BAAI/bge-large-en-v1.5)
    BATCH_SIZE    embedding batch size      (default: 32)
    UPSERT_CHUNK  ChromaDB upsert chunk     (default: 500)
"""

import os
import sys
import csv
import hashlib
import logging
import time
from datetime import datetime, timezone

# ── Project root on path so embeddings.py is importable ───────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from embeddings import EmbeddingService   # reuses the Blinkit-pattern embedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
EMBED_MODEL  = os.getenv("EMBED_MODEL",   "BAAI/bge-large-en-v1.5")
BATCH_SIZE   = int(os.getenv("BATCH_SIZE",   "32"))
UPSERT_CHUNK = int(os.getenv("UPSERT_CHUNK", "500"))

CSV_FILE     = os.path.join(BASE_DIR, "data", "processed", "all_reviews.csv")
CHROMA_DIR   = os.path.join(BASE_DIR, "data", "chroma_db")
COLLECTION   = "myntra_reviews"


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_doc_id(source: str, text: str) -> str:
    """
    Deterministic, stable document ID derived from (source, text).
    Using SHA-256 truncated to 16 hex chars is collision-resistant enough
    for datasets of this size and guarantees idempotent upserts.
    """
    payload = f"{source}||{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def load_csv(path: str) -> list[dict]:
    """Load all_reviews.csv and return a list of row dicts."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    logger.info(f"Loaded {len(rows)} rows from {path}")
    return rows


def already_indexed_ids(collection) -> set[str]:
    """
    Return the set of document IDs already present in the collection.
    Uses collection.get() with no filter to pull all IDs.
    Chunked to handle large collections gracefully.
    """
    total = collection.count()
    if total == 0:
        return set()

    logger.info(f"Collection has {total} existing records — checking for new rows ...")
    existing = set()
    offset = 0
    chunk  = 1000

    while offset < total:
        result = collection.get(limit=chunk, offset=offset, include=[])
        existing.update(result["ids"])
        offset += chunk

    return existing


def upsert_batch(collection, ids, embeddings, documents, metadatas):
    """Upsert one chunk into ChromaDB."""
    collection.upsert(
        ids=ids,
        embeddings=[e.tolist() for e in embeddings],
        documents=documents,
        metadatas=metadatas,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    start_ts = time.time()

    # ── 1. Load CSV ────────────────────────────────────────────────────────────
    if not os.path.exists(CSV_FILE):
        logger.error(
            f"Input file not found: {CSV_FILE}\n"
            "Run `python scrapers/consolidate.py` first."
        )
        sys.exit(1)

    rows = load_csv(CSV_FILE)
    if not rows:
        logger.error("CSV is empty — nothing to index.")
        sys.exit(1)

    # ── 2. Connect to ChromaDB ─────────────────────────────────────────────────
    import chromadb

    os.makedirs(CHROMA_DIR, exist_ok=True)
    logger.info(f"Opening ChromaDB at: {CHROMA_DIR}")
    client     = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(f"Collection '{COLLECTION}' ready.")

    # ── 3. Determine which rows need embedding ─────────────────────────────────
    existing_ids = already_indexed_ids(collection)

    # Build (id, row) pairs, skipping already-indexed
    to_index: list[tuple[str, dict]] = []
    for row in rows:
        doc_id = make_doc_id(row["source"], row["text"])
        if doc_id not in existing_ids:
            to_index.append((doc_id, row))

    n_skip = len(rows) - len(to_index)
    if n_skip:
        logger.info(f"Skipping {n_skip} already-indexed records.")
    if not to_index:
        logger.info("All records already indexed. Nothing to do.")
        _print_summary(collection, rows, n_new=0, elapsed=time.time() - start_ts)
        return

    logger.info(f"Records to embed and index: {len(to_index)}")

    # ── 4. Embed in batches ────────────────────────────────────────────────────
    logger.info(f"Loading embedding model '{EMBED_MODEL}' ...")
    embedder = EmbeddingService(model_name=EMBED_MODEL)
    embedder.load_model()
    logger.info(f"Model loaded — embedding dimension: {embedder.get_dimension()}")

    texts = [row["text"] for _, row in to_index]
    logger.info(f"Embedding {len(texts)} texts (batch_size={BATCH_SIZE}) ...")
    embeddings = embedder.embed_documents(texts, batch_size=BATCH_SIZE)
    logger.info(f"Embeddings shape: {embeddings.shape}")

    # ── 5. Upsert into ChromaDB in chunks ─────────────────────────────────────
    logger.info(f"Upserting into '{COLLECTION}' (chunk={UPSERT_CHUNK}) ...")
    n_upserted = 0

    for chunk_start in range(0, len(to_index), UPSERT_CHUNK):
        chunk_end    = min(chunk_start + UPSERT_CHUNK, len(to_index))
        chunk_pairs  = to_index[chunk_start:chunk_end]
        chunk_embeds = embeddings[chunk_start:chunk_end]

        chunk_ids   = [doc_id for doc_id, _ in chunk_pairs]
        chunk_docs  = [row["text"] for _, row in chunk_pairs]
        chunk_metas = [
            {
                "source": row["source"],
                "date":   row["date"]   or "",
                "rating": row["rating"] or "",
                "url":    row["url"]    or "",
            }
            for _, row in chunk_pairs
        ]

        upsert_batch(collection, chunk_ids, chunk_embeds, chunk_docs, chunk_metas)
        n_upserted += len(chunk_ids)
        logger.info(
            f"  Upserted records {chunk_start + 1}–{chunk_end} "
            f"({n_upserted}/{len(to_index)})"
        )

    logger.info(f"Indexing complete. Total upserted this run: {n_upserted}")
    _print_summary(collection, rows, n_new=n_upserted, elapsed=time.time() - start_ts)


def _print_summary(collection, csv_rows: list[dict], n_new: int, elapsed: float):
    """Print a human-readable summary of the indexed collection."""
    from collections import Counter

    total_indexed = collection.count()
    source_dist   = Counter(r["source"] for r in csv_rows)
    ts_now        = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print()
    print("=" * 62)
    print("  INDEX PIPELINE -- SUMMARY")
    print("=" * 62)
    print(f"  Collection          : {COLLECTION}")
    print(f"  ChromaDB path       : {CHROMA_DIR}")
    print(f"  Embedding model     : {EMBED_MODEL}")
    print(f"  Embedding dim       : 1024")
    print()
    print(f"  CSV rows loaded     : {len(csv_rows)}")
    print(f"  New records indexed : {n_new}")
    print(f"  Total in collection : {total_indexed}")
    print()
    print(f"  Source breakdown (CSV):")
    for src, count in source_dist.most_common():
        print(f"    {src:<20}: {count}")
    print()
    print(f"  Last indexed at     : {ts_now}")
    print(f"  Elapsed             : {elapsed:.1f}s")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
