"""
agent.py — Myntra Wishlist-to-Purchase Behavior Analyzer

Retrieval-Augmented Generation pipeline:
  1. Embed the user's natural-language query via BAAI/bge-large-en-v1.5
  2. Retrieve top-K semantically similar reviews/items from ChromaDB (myntra_reviews)
  3. Pass retrieved context to Groq LLM with a behavior-analysis system prompt
  4. Return grounded, insight-driven analysis — never hallucinated

The agent is designed to answer questions like:
  - "Why do users add X to wishlist but not buy it?"
  - "What are the most common conversion drivers for kurtas?"
  - "Show me reviews where price was the barrier to purchase"
"""

import os
import logging
import requests
import chromadb
from typing import List, Dict, Optional
from dotenv import load_dotenv
from embeddings import EmbeddingService

# Explicit path so .env is always found regardless of working directory
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_FILE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CHROMA_DIR = os.path.join(BASE_DIR, "data", "chroma_db")
COLLECTION = "myntra_reviews"

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a Myntra Wishlist Behavior Analyst. Analyze the retrieved app reviews to surface concise, evidence-based behavioral insights for product managers.

Rules:
1. Only use the provided review data. Never fabricate.
2. Structure: 1-sentence summary, 2-3 bullet insights, 1 PM recommendation.
3. Keep total response to 3-5 sentences / under 120 words.
4. If reviews are irrelevant, say so and suggest rephrasing.
5. Use Rs for Indian Rupee prices."""


def _format_review_context(reviews: List[Dict]) -> str:
    """Format retrieved review records into a numbered list for the LLM prompt."""
    lines = []
    for i, r in enumerate(reviews, 1):
        meta    = r.get("metadata", {})
        source  = meta.get("source",  "Unknown")
        date    = meta.get("date",    "")[:10]   # YYYY-MM-DD
        rating  = meta.get("rating",  "")
        rating_str = f"{rating}/5" if rating else "N/A"
        url     = meta.get("url",     "")
        conf    = r.get("confidence", 0)
        text    = r.get("text", "")[:400]   # LLM context only; UI displays full text from ChromaDB
        lines.append(
            f"{i}. [Source: {source}] [Date: {date}] [Rating: {rating_str}] "
            f"[Similarity: {conf:.2f}]\n   Review: \"{text}\""
        )
    return "\n".join(lines)


class WishlistAnalystAgent:
    """
    Core RAG agent for Myntra wishlist-to-purchase behavior analysis.
    Retrieves semantically relevant reviews and generates behavioral insights.
    """

    def __init__(self, embed_model: str = "BAAI/bge-large-en-v1.5"):
        self.embed_service = EmbeddingService(model_name=embed_model)
        self._chroma_client: Optional[chromadb.PersistentClient] = None
        self._collection = None
        self.groq_api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.groq_model   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        # NOTE: groq_api_key is read lazily in generate_response() so that
        # load_dotenv() always has a chance to run first.

    def _get_collection(self):
        """Lazily initialise the ChromaDB persistent client and collection."""
        if self._collection is None:
            logger.info(f"Connecting to ChromaDB at: {CHROMA_DIR}")
            self._chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
            self._collection = self._chroma_client.get_collection(name=COLLECTION)
            logger.info(
                f"Connected to collection '{COLLECTION}' ({self._collection.count()} records)."
            )
        return self._collection

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Embed the user's query and retrieve top-K most similar review records.
        Returns a list of dicts: id, text, confidence (1 - cosine_dist), metadata.
        """
        query_vector = self.embed_service.embed_query(query)
        collection   = self._get_collection()

        results = collection.query(
            query_embeddings=[query_vector.tolist()],
            n_results=top_k,
        )

        ids       = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]

        retrieved = []
        for i in range(len(ids)):
            # ChromaDB cosine distance → similarity = 1 - distance
            confidence = round(1.0 - distances[i], 4)
            retrieved.append({
                "id":         ids[i],
                "text":       documents[i],
                "confidence": confidence,
                "metadata":   metadatas[i],
            })

        logger.info(f"Retrieved {len(retrieved)} records for query: '{query}'")
        return retrieved

    def _fallback_response(self, query: str, reviews: List[Dict]) -> str:
        """Plain-text fallback when Groq API is unavailable or key is invalid."""
        if not reviews:
            return "No relevant reviews found in the ChromaDB collection for that query."

        lines = ["**Top matching reviews (Groq API unavailable -- raw retrieval results):**\n"]
        for r in reviews[:5]:
            meta   = r.get("metadata", {})
            source = meta.get("source", "?")
            date   = meta.get("date",   "")[:10]
            rating = meta.get("rating", "") or "N/A"
            conf   = r.get("confidence", 0)
            text   = r.get("text", "")[:180]
            lines.append(
                f"  [{source}] [{date}] Rating: {rating} | Sim: {conf:.3f}\n"
                f"  \"{text}\"\n"
            )
        lines.append("_Add a valid GROQ_API_KEY to .env to get AI-generated insights._")
        return "\n".join(lines)

    def generate_response(self, query: str, reviews: List[Dict]) -> str:
        """
        Call Groq LLM with retrieved reviews as grounded context.
        Falls back gracefully if API key is missing or request fails.
        """
        if not reviews:
            return "No matching review data found. Try a different query or check that ingestion has run."

        # Read both lazily so .env changes or Streamlit secrets are picked up at call time
        groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not groq_api_key:
            try:
                import streamlit as st
                if hasattr(st, "secrets"):
                    groq_api_key = str(
                        st.secrets.get("GROQ_API_KEY") or st.secrets.get("groq_api_key") or ""
                    ).strip()
            except Exception:
                pass

        groq_model = os.getenv("GROQ_MODEL", "").strip()
        if not groq_model:
            try:
                import streamlit as st
                if hasattr(st, "secrets"):
                    groq_model = str(
                        st.secrets.get("GROQ_MODEL") or st.secrets.get("groq_model") or ""
                    ).strip()
            except Exception:
                pass
        if not groq_model:
            groq_model = "groq/compound"

        if not groq_api_key:
            logger.warning("GROQ_API_KEY not set — using plain fallback response.")
            return self._fallback_response(query, reviews)

        review_context = _format_review_context(reviews)
        user_prompt = (
            f'Analyst question: "{query}"\n\n'
            f"Retrieved Review Data:\n{review_context}"
        )

        payload = {
            "model": groq_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens":  250,
        }
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type":  "application/json",
        }

        try:
            logger.info(f"Calling Groq API (model: {groq_model}) ...")
            res = requests.post(self.groq_api_url, json=payload, headers=headers, timeout=20)

            if res.status_code == 200:
                answer = res.json()["choices"][0]["message"]["content"].strip()
                logger.info("Groq API response received successfully.")
                return answer
            elif res.status_code == 429:
                # Parse the suggested wait time out of the error message
                import re as _re
                body = res.json()
                msg  = body.get("error", {}).get("message", "")
                wait_match = _re.search(r"try again in (\d+(?:\.\d+)?)s", msg)
                wait_secs  = float(wait_match.group(1)) + 1.0 if wait_match else 30.0
                logger.warning(f"Groq rate limit 429 — waiting {wait_secs:.1f}s then retrying ...")
                import time as _time; _time.sleep(wait_secs)
                # Single retry
                res2 = requests.post(self.groq_api_url, json=payload, headers=headers, timeout=30)
                if res2.status_code == 200:
                    answer = res2.json()["choices"][0]["message"]["content"].strip()
                    logger.info("Groq API response received successfully (after rate-limit retry).")
                    return answer
                else:
                    logger.error(f"Groq retry failed {res2.status_code}: {res2.text}")
                    return self._fallback_response(query, reviews)
            else:
                logger.error(f"Groq API error {res.status_code}: {res.text}")
                return self._fallback_response(query, reviews)

        except requests.exceptions.RequestException as e:
            logger.error(f"Groq API request failed: {e}")
            return self._fallback_response(query, reviews)

    def answer(self, query: str, top_k: int = 8) -> Dict:
        """
        Full pipeline: retrieve → generate.
        Returns: { response: str, reviews: List[Dict] }
        """
        reviews  = self.retrieve(query, top_k=top_k)
        response = self.generate_response(query, reviews)
        return {"response": response, "reviews": reviews}
