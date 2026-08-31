"""
app.py — Myntra Wishlist-to-Purchase Behavior Analyzer
Streamlit chat interface  |  run: streamlit run app.py
"""

import os
import logging
import streamlit as st
from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Synchronize Streamlit Secrets to environment variables for Cloud deployments
try:
    import streamlit as _st
    if hasattr(_st, "secrets"):
        for k in ("GROQ_API_KEY", "groq_api_key"):
            if k in _st.secrets and _st.secrets[k]:
                os.environ["GROQ_API_KEY"] = str(_st.secrets[k]).strip()
                break
        for k in ("GROQ_MODEL", "groq_model"):
            if k in _st.secrets and _st.secrets[k]:
                os.environ["GROQ_MODEL"] = str(_st.secrets[k]).strip()
                break
except Exception:
    pass

st.set_page_config(
    page_title="Myntra Wishlist Analyzer",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif !important; }

.stApp {
  background: linear-gradient(135deg, #0d0d1a 0%, #0f0f23 60%, #12091a 100%);
  min-height: 100vh;
}
#MainMenu, footer, header { visibility: hidden; }
.block-container { max-width: 900px !important; padding: 2rem 2rem 5rem !important; }

/* Navbar */
.navbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.9rem 0 1.8rem; border-bottom: 1px solid #1e1030; margin-bottom: 2rem;
}
.navbar-logo { display: flex; align-items: center; gap: 0.6rem; }
.navbar-logo-icon {
  width: 36px; height: 36px;
  background: linear-gradient(135deg, #FF3F6C, #FF6B98);
  border-radius: 10px; display: flex; align-items: center; justify-content: center;
  font-size: 1.1rem; font-weight: 900; color: #fff; letter-spacing: -1px;
  box-shadow: 0 4px 12px rgba(255,63,108,0.35);
}
.navbar-brand { font-size: 1rem; font-weight: 700; color: #fff; letter-spacing: -0.3px; }
.navbar-tag {
  font-size: 0.68rem; color: #FF3F6C; background: #FF3F6C15;
  border: 1px solid #FF3F6C30; border-radius: 20px;
  padding: 0.18rem 0.65rem; font-weight: 600; letter-spacing: 0.3px;
}

/* Hero */
.hero { text-align: center; padding: 2.5rem 1rem 1.5rem; }
.hero-eyebrow {
  display: inline-flex; align-items: center; gap: 0.4rem;
  font-size: 0.72rem; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase;
  color: #FF3F6C; background: #FF3F6C10; border: 1px solid #FF3F6C25;
  border-radius: 30px; padding: 0.3rem 0.9rem; margin-bottom: 1.2rem;
}
.hero-title {
  font-size: clamp(2rem, 5vw, 3rem); font-weight: 900; letter-spacing: -1.5px;
  line-height: 1.1; color: #ffffff; margin: 0 0 0.9rem;
}
.hero-title .accent { color: #FF3F6C; }
.hero-sub {
  font-size: 1rem; color: #6b6b8a; max-width: 540px;
  margin: 0 auto 2rem; line-height: 1.65; font-weight: 400;
}

/* Pills */
.pill-strip { display: flex; flex-wrap: wrap; justify-content: center; gap: 0.45rem; margin-bottom: 2.5rem; }
.pill {
  display: inline-flex; align-items: center; gap: 0.35rem;
  background: #16102a; border: 1px solid #251e40; border-radius: 30px;
  padding: 0.3rem 0.85rem; font-size: 0.78rem; color: #9090b8; font-weight: 500; transition: all 0.2s;
}
.pill:hover { border-color: #FF3F6C55; color: #FF3F6C; background: #FF3F6C08; }

/* Suggestion chips */
div[data-testid="column"] > div > div > div > button {
  background: #13102a !important; border: 1px solid #221d3a !important;
  border-radius: 12px !important; color: #b0acd0 !important;
  font-size: 0.82rem !important; font-weight: 500 !important;
  padding: 0.55rem 0.9rem !important; transition: all 0.2s !important;
  text-align: left !important; height: auto !important;
  min-height: 2.6rem !important; white-space: normal !important; line-height: 1.3 !important;
}
div[data-testid="column"] > div > div > div > button:hover {
  border-color: #FF3F6C55 !important; color: #FF3F6C !important;
  background: #FF3F6C0A !important; transform: translateY(-1px);
}

/* Chat bubbles */
.stChatMessage { background: transparent !important; padding: 0 !important; margin-bottom: 1.25rem !important; }
[data-testid="stChatMessageContent"] { border-radius: 16px !important; }

/* Source citation cards */
.src-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px,1fr)); gap: 0.7rem; margin-top: 0.6rem; }
.src-card {
  background: #110e22; border: 1px solid #1e1830; border-radius: 14px;
  padding: 0.85rem 1rem; position: relative; overflow: hidden;
  transition: all 0.22s cubic-bezier(.25,.8,.25,1);
}
.src-card::before {
  content:''; position:absolute; top:0; left:0; right:0; height:2px;
  background: linear-gradient(90deg,#FF3F6C,#FF6B98); opacity:0; transition:opacity 0.22s;
}
.src-card:hover { border-color:#2e2550; transform:translateY(-3px); box-shadow:0 12px 30px rgba(0,0,0,.5); }
.src-card:hover::before { opacity:1; }

.src-meta {
  display: flex; align-items: center; gap: 0.4rem;
  font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.8px; color: #FF3F6C; margin-bottom: 0.45rem;
}
.src-badge {
  font-size: 0.6rem; background: #FF3F6C18; border: 1px solid #FF3F6C30;
  border-radius: 6px; padding: 0.1rem 0.4rem; color: #FF3F6C;
}
.src-sim {
  font-size: 0.6rem; color: #3d3560; margin-left: auto;
}
.src-text {
  font-size: 0.78rem; color: #c5c0e8; line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;
}
.src-rating {
  font-size: 0.7rem; color: #ffa726; margin-top: 0.5rem; font-weight: 600;
}

/* Divider */
.card-divider { border: none; border-top: 1px solid #1a1530; margin: 1rem 0 0.6rem; }
.section-label {
  font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1.2px; color: #3d3560; margin: 0.2rem 0 0.8rem;
}

/* Chat input */
[data-testid="stChatInput"] {
  background: #110e22 !important; border: 1px solid #221d3a !important; border-radius: 16px !important;
}
[data-testid="stChatInput"]:focus-within { border-color: #FF3F6C55 !important; box-shadow: 0 0 0 3px #FF3F6C10 !important; }
[data-testid="stChatInput"] textarea { color: #e0ddf8 !important; font-size: 0.92rem !important; }

/* Sidebar */
[data-testid="stSidebar"] { background: #0d0b1a !important; border-right: 1px solid #1a1530 !important; }
.stSpinner > div { border-top-color: #FF3F6C !important; }

/* Stat row */
.stat-row { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 1rem; }
.stat-pill {
  background: #16102a; border: 1px solid #251e40; border-radius: 10px;
  padding: 0.35rem 0.75rem; font-size: 0.73rem; color: #9090b8;
}
.stat-pill strong { color: #FF3F6C; }
</style>
""", unsafe_allow_html=True)


# ── Constants ─────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CHROMA_DIR = os.path.join(BASE_DIR, "data", "chroma_db")
COLLECTION = "myntra_reviews"
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-large-en-v1.5")

SOURCE_ICONS = {
    "Play Store": "🤖",
    "App Store":  "🍎",
    "YouTube":    "▶️",
}

SUGGESTIONS = [
    ("💰", "What price-related concerns prevent users from completing a purchase?"),
    ("📏", "What uncertainties do users have about fit, sizing, or product quality?"),
    ("🛑", "What are the most common reasons users abandon their wishlists?"),
    ("🚚", "How do delivery and return issues affect purchase decisions?"),
    ("⭐", "What positive experiences do users highlight about Myntra?"),
    ("🤔", "Why do users postpone buying items they have already wishlisted?"),
]


# ── Cached resource loaders ───────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_agent():
    from agent import WishlistAnalystAgent
    agent = WishlistAnalystAgent(embed_model=EMBED_MODEL)
    agent.embed_service.load_model()
    agent._get_collection()
    return agent


@st.cache_data(show_spinner=False)
def get_collection_count():
    import chromadb
    try:
        col = chromadb.PersistentClient(path=CHROMA_DIR).get_collection(COLLECTION)
        return col.count()
    except Exception:
        return 0


# ── Source citation card renderer ─────────────────────────────────────────────
def render_source_cards(reviews: list):
    if not reviews:
        return
    html = '<div class="src-grid">'
    for r in reviews:
        meta   = r.get("metadata", {})
        source = meta.get("source", "Unknown")
        date   = (meta.get("date") or "")[:10]
        rating = meta.get("rating")
        url    = meta.get("url") or ""
        text   = r.get("text", "")
        sim    = r.get("confidence", 0)
        icon   = SOURCE_ICONS.get(source, "💬")

        rating_html = ""
        if rating:
            try:
                stars = "★" * int(float(rating)) + "☆" * (5 - int(float(rating)))
                rating_html = f'<div class="src-rating">{stars} {float(rating):.1f}/5</div>'
            except Exception:
                pass

        link_open  = f'<a href="{url}" target="_blank" style="text-decoration:none">' if url else ""
        link_close = "</a>" if url else ""

        html += f"""
        <div class="src-card">
          <div class="src-meta">
            {icon} <span class="src-badge">{source}</span>
            <span>{date}</span>
            <span class="src-sim">{sim:.0%} match</span>
          </div>
          {link_open}<p class="src-text">{text}</p>{link_close}
          {rating_html}
        </div>"""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ── Bootstrap ─────────────────────────────────────────────────────────────────
with st.spinner("Loading Myntra Wishlist Analyzer…"):
    record_count = get_collection_count()

if record_count == 0:
    st.error(
        "**ChromaDB collection is empty or not found.**  \n"
        f"Expected at `{CHROMA_DIR}`.  \n"
        "Run `python scripts/index_data.py` first."
    )
    st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")

    groq_key = st.text_input(
        "Groq API Key",
        value=os.getenv("GROQ_API_KEY", ""),
        type="password",
        help="Free key at console.groq.com",
        placeholder="gsk_…",
    )
    if groq_key:
        os.environ["GROQ_API_KEY"] = groq_key

    st.markdown("---")
    st.markdown(
        f'<div class="stat-pill">📦 <strong>{record_count}</strong> reviews indexed</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    top_k = st.slider("Reviews retrieved per query", min_value=3, max_value=10, value=5,
                      help="Higher = more context, more tokens used")

    st.markdown("---")
    st.caption(
        "**Myntra Wishlist Behavior Analyzer**\n\n"
        "Ask any question about why shoppers add items to their wishlist "
        "but don't always convert to purchase.\n\n"
        "Grounded in ~821 real Play Store, App Store & YouTube reviews."
    )
    st.markdown("---")
    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# ── Navbar ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="navbar">
  <div class="navbar-logo">
    <div class="navbar-logo-icon">M</div>
    <span class="navbar-brand">Myntra Wishlist Analyzer</span>
  </div>
  <span class="navbar-tag">PM RESEARCH</span>
</div>
""", unsafe_allow_html=True)


# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <div class="hero-eyebrow">🛍️ Wishlist-to-Purchase Intelligence</div>
  <h1 class="hero-title">Why do shoppers <span class="accent">wish</span> but not buy?</h1>
  <p class="hero-sub">
    Ask any behavior question about Myntra wishlist data — price barriers,
    fit concerns, delivery issues, and more — grounded in real user reviews.
  </p>
</div>

<div class="pill-strip">
  <span class="pill">🤖 Play Store</span>
  <span class="pill">🍎 App Store</span>
  <span class="pill">▶️ YouTube</span>
  <span class="pill">📏 Fit & Sizing</span>
  <span class="pill">💰 Price Sensitivity</span>
  <span class="pill">🚚 Delivery</span>
  <span class="pill">↩️ Returns</span>
  <span class="pill">⭐ Quality</span>
</div>
""", unsafe_allow_html=True)


# ── Suggestion chips ──────────────────────────────────────────────────────────
st.markdown('<p class="section-label">Try a question →</p>', unsafe_allow_html=True)
cols = st.columns(3)
for i, (icon, text) in enumerate(SUGGESTIONS):
    with cols[i % 3]:
        if st.button(f"{icon} {text}", key=f"chip_{i}", use_container_width=True):
            st.session_state.pending_input = text

st.markdown("<div style='margin-top:0.5rem'></div>", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_input" not in st.session_state:
    st.session_state.pending_input = None


# ── Render chat history ───────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("reviews"):
            st.markdown('<hr class="card-divider">', unsafe_allow_html=True)
            st.markdown('<p class="section-label">Source reviews retrieved from ChromaDB</p>',
                        unsafe_allow_html=True)
            render_source_cards(msg["reviews"])


# ── Input handler ─────────────────────────────────────────────────────────────
def handle_input(user_query: str):
    user_query = user_query.strip()
    if not user_query:
        return

    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Searching reviews and generating insight…"):
            try:
                agent   = load_agent()
                result  = agent.answer(user_query, top_k=top_k)
                answer  = result["response"]
                reviews = result["reviews"]
            except Exception as exc:
                answer  = f"⚠️ Something went wrong: {exc}"
                reviews = []

        st.markdown(answer)

        if reviews:
            st.markdown('<hr class="card-divider">', unsafe_allow_html=True)
            st.markdown(
                f'<p class="section-label">{len(reviews)} source reviews from ChromaDB</p>',
                unsafe_allow_html=True,
            )
            render_source_cards(reviews)

    st.session_state.messages.append({
        "role": "assistant", "content": answer, "reviews": reviews,
    })


# ── Chip → pending input ──────────────────────────────────────────────────────
if st.session_state.pending_input:
    pending = st.session_state.pending_input
    st.session_state.pending_input = None
    handle_input(pending)


# ── Chat input ────────────────────────────────────────────────────────────────
if user_input := st.chat_input("Ask about wishlist behavior… e.g. 'Why do users not convert after wishlisting?'"):
    handle_input(user_input)
