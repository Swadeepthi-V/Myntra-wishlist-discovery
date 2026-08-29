# Myntra Wishlist-to-Purchase Behavior Analyzer

A RAG-based research tool for understanding **why Myntra shoppers add items to their wishlist but may or may not convert to purchase**. Built for PM research.

## Architecture

Mirrors the [Blinkit Discovery Agent](../Blinkit%20discovery%20agent/) pattern:

| Layer | Tech |
|---|---|
| Embeddings | `BAAI/bge-large-en-v1.5` via `sentence-transformers` (1024-dim, L2-normalized) |
| Vector Store | ChromaDB — local persistent (`chroma_db/`, cosine space) |
| LLM | Groq API (`llama-3.3-70b-versatile`) — behavioral insight generation |
| UI | Streamlit chat interface |

## Folder Structure

```
Myntra-wishlist-discovery/
├── app.py                        # Streamlit chat UI (main entry point)
├── agent.py                      # RAG pipeline: retrieve → generate
├── embeddings.py                 # EmbeddingService wrapping BGE-large
├── ingest.py                     # One-shot ChromaDB ingestion script
├── requirements.txt
├── .env.example
├── .gitignore
│
├── scrapers/
│   ├── myntra_scraper.py         # Scraper scaffold + synthetic data generator
│   └── preprocess.py             # Raw → clean data normalization pipeline
│
├── data/
│   ├── raw/                      # Output of myntra_scraper.py (gitignored)
│   └── processed/                # Output of preprocess.py   (gitignored)
│
├── analysis/
│   └── wishlist_stats.py         # Standalone stats script (no UI needed)
│
└── chroma_db/                    # ChromaDB vector store (auto-created, gitignored)
```

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up environment
```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 3. Generate / collect data

**Option A — Synthetic data (for dev/testing):**
```bash
python scrapers/myntra_scraper.py --mode synthetic --n 500
```

**Option B — From a CSV export (Octoparse / ParseHub / manual):**
```bash
python scrapers/myntra_scraper.py --mode csv --input path/to/your_export.csv
```

### 4. Preprocess
```bash
python scrapers/preprocess.py
```

### 5. Ingest into ChromaDB
```bash
python ingest.py
```

### 6. Run the app
```bash
streamlit run app.py
```

## Embedding Model

This project uses **`BAAI/bge-large-en-v1.5`** (1024-dim) — the large variant of the BGE family, suited for semantic similarity on fashion review text. The model is downloaded automatically from HuggingFace on first run (~1.3 GB).

To use the smaller/faster variant instead:
```bash
EMBED_MODEL=BAAI/bge-small-en-v1.5 streamlit run app.py
```

## Standalone Analysis (No UI)

```bash
python analysis/wishlist_stats.py
```

Outputs a console summary + `analysis/conversion_summary.json` with:
- Overall conversion rate
- Per-category conversion rates & average prices
- Per-brand conversion rates
- Price-band conversion analysis

## Data Schema

Each review record (in `data/processed/reviews_clean.json`) must contain:

| Field | Type | Description |
|---|---|---|
| `product_id` | str | Myntra product ID |
| `product_name` | str | Full product name |
| `brand` | str | Brand name |
| `category` | str | e.g. "Kurtas & Suits", "Dresses" |
| `rating` | str | "1"–"5" |
| `review_text` | str | Full review body |
| `price_inr` | str | Listed price |
| `color` | str | Selected color/variant |
| `size` | str | Selected size |
| `wishlist_to_purchase` | bool | True if item was purchased after wishlisting |
| `source_url` | str | Product URL |
| `scraped_at` | str | ISO-8601 timestamp |

## Notes on Scraping Myntra

Myntra is a JavaScript-rendered SPA. Options for real data:
1. **Playwright/Selenium** — automate a real browser session
2. **API interception** — use browser DevTools to capture and replay authenticated API calls
3. **Third-party tools** — Octoparse, ParseHub, Bright Data
4. **Kaggle datasets** — several Myntra review datasets exist publicly

---
*PM Research Project · Myntra Wishlist Discovery*
