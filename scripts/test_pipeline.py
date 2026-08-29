"""
scripts/test_pipeline.py — Myntra Wishlist-to-Purchase Behavior Analyzer

End-to-end validation of the RAG pipeline:
  1. Load EmbeddingService (BAAI/bge-large-en-v1.5)
  2. Connect to the `myntra_reviews` ChromaDB collection
  3. Set up WishlistAnalystAgent (top_k=8)
  4. Run 3 behavioral questions through retrieve → generate
  5. Print retrieved chunks + LLM answer for each

Run:
    python scripts/test_pipeline.py
"""

import os
import sys
import time
import textwrap

# ── Project root on path ───────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Load .env so GROQ_API_KEY is available
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from agent import WishlistAnalystAgent

# ── Validation questions ───────────────────────────────────────────────────────
QUESTIONS = [
    "Why do users add fashion products to their wishlist?",
    "What prevents wishlisted products from eventually being purchased?",
    "What causes users to postpone a purchase?",
]

DIVIDER     = "=" * 72
SUB_DIVIDER = "-" * 72
WRAP_WIDTH  = 70


def fmt(text: str, indent: int = 4) -> str:
    """Wrap and indent long text for terminal display."""
    prefix = " " * indent
    return textwrap.fill(text, width=WRAP_WIDTH, initial_indent=prefix,
                         subsequent_indent=prefix)


def print_chunks(reviews: list[dict]) -> None:
    """Print the retrieved review chunks with metadata."""
    for i, r in enumerate(reviews, 1):
        meta     = r.get("metadata", {})
        source   = meta.get("source",  "?")
        date     = meta.get("date",    "")[:10]
        rating   = meta.get("rating",  "") or "N/A"
        conf     = r.get("confidence", 0)
        text     = r.get("text", "")

        print(f"  Chunk {i}  |  {source}  |  {date}  |  "
              f"Rating: {rating}  |  Similarity: {conf:.4f}")
        print(fmt(f'"{text}"', indent=6))
        print()


def run_question(agent: WishlistAnalystAgent, q: str, idx: int) -> None:
    """Run one question through the full pipeline and pretty-print results."""
    print(DIVIDER)
    print(f"  Q{idx}: {q}")
    print(DIVIDER)

    t0     = time.time()
    result = agent.answer(q, top_k=5)
    elapsed = time.time() - t0

    reviews  = result["reviews"]
    response = result["response"]

    # ── Retrieved chunks ───────────────────────────────────────────────────────
    print(f"\n  [{len(reviews)} RETRIEVED CHUNKS -- top_k=8]\n")
    print_chunks(reviews)

    # ── LLM answer ────────────────────────────────────────────────────────────
    print(SUB_DIVIDER)
    print("  LLM ANSWER")
    print(SUB_DIVIDER)
    for line in response.splitlines():
        safe = line.encode("ascii", "replace").decode("ascii")
        print(f"  {safe}")
    print()
    print(f"  [Pipeline elapsed: {elapsed:.2f}s]")
    print()


def main():
    print()
    print(DIVIDER)
    print("  MYNTRA RAG PIPELINE -- VALIDATION TEST")
    print(DIVIDER)

    # ── Instantiate agent (lazy model load) ────────────────────────────────────
    print("\n  Initialising WishlistAnalystAgent ...")
    agent = WishlistAnalystAgent(embed_model="BAAI/bge-large-en-v1.5")

    # Force model + collection load upfront so timing is accurate per question
    _ = agent.embed_service.load_model()
    col = agent._get_collection()
    print(f"  ChromaDB collection '{col.name}': {col.count()} records")
    groq_key = os.getenv("GROQ_API_KEY", "")
    print(f"  GROQ_API_KEY       : {'SET (' + groq_key[:12] + '...)' if groq_key else 'NOT SET -- fallback mode'}")
    print(f"  GROQ_MODEL         : {agent.groq_model}")
    print()

    # ── Run 3 validation questions ─────────────────────────────────────────────
    for i, question in enumerate(QUESTIONS, 1):
        run_question(agent, question, i)
        if i < len(QUESTIONS):
            print("  [Pausing 5s to stay within Groq TPM rate limit...]\n")
            time.sleep(5)

    print(DIVIDER)
    print("  ALL 3 VALIDATION QUESTIONS COMPLETE")
    print(DIVIDER)
    print()


if __name__ == "__main__":
    main()
