"""
embeddings.py — Myntra Wishlist Discovery
Wraps BAAI/bge-large-en-v1.5 via sentence-transformers for CPU-optimized
1024-dim dense embeddings suitable for cosine similarity in ChromaDB.
"""

import os
import logging
import torch
import numpy as np
from typing import List
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Minimize CPU thread count to reduce memory pressure
try:
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
except Exception as e:
    logger.warning(f"Could not configure PyTorch thread limits: {e}")

# BGE instruction prefix for query-side encoding
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingService:
    """
    CPU-optimized embedding service using BAAI/bge-large-en-v1.5.
    Produces normalized 1024-dim dense vectors suitable for cosine similarity.

    Document embeddings (reviews, wishlist items) do NOT need a prefix.
    Query embeddings (user chat input) use BGE's recommended instruction prefix.
    """

    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5"):
        self.model_name = model_name
        self.model = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def load_model(self):
        """Lazy-load the embedding model on first use."""
        if self.model is None:
            logger.info(f"Loading embedding model '{self.model_name}' on CPU ...")
            self.model = SentenceTransformer(self.model_name, device="cpu")
            logger.info(
                f"Embedding model loaded -- dim={self.model.get_embedding_dimension()}"
            )

    def get_dimension(self) -> int:
        """Return the embedding vector dimensionality (1024 for bge-large)."""
        self.load_model()
        return self.model.get_embedding_dimension()

    # ── Encoding ───────────────────────────────────────────────────────────────

    def embed_documents(self, texts: List[str], batch_size: int = 16) -> np.ndarray:
        """
        Embed a list of document/passage strings (reviews, wishlist items, etc.).
        BGE passage embedding does NOT require an instruction prefix.
        Returns: float32 numpy array of shape (N, dim), L2-normalized.
        """
        self.load_model()
        if not texts:
            return np.empty((0, self.get_dimension()), dtype=np.float32)

        logger.info(f"Embedding {len(texts)} document(s) with batch_size={batch_size} ...")
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,   # L2-normalize -> cosine similarity
        )
        return embeddings.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single user query (chat input).
        BGE v1.5 recommends prepending an instruction prefix to queries only.
        Returns: float32 numpy array of shape (dim,), L2-normalized.
        """
        self.load_model()
        prefixed = f"{BGE_QUERY_PREFIX}{query}"
        embedding = self.model.encode(
            [prefixed],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embedding[0].astype(np.float32)
