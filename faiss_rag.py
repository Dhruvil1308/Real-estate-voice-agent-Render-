import json
import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
MODEL_NAME   = 'paraphrase-multilingual-MiniLM-L12-v2'
INDEX_DIR    = 'faiss_index'
INDEX_FILE   = os.path.join(INDEX_DIR, 'index.faiss')
METADATA_FILE = os.path.join(INDEX_DIR, 'metadata.json')

# Minimum cosine similarity score to include a result (range 0-1).
# Hits below this threshold are considered off-topic and are discarded.
SCORE_THRESHOLD = 0.25

# Maximum characters to include from the eligibility field in the embedding
# text and in the voice-context output (keeps token count low).
ELIGIBILITY_MAX_CHARS = 180

# ─────────────────────────────────────────────────────────────────────────────
# Global singletons (lazy-loaded)
# ─────────────────────────────────────────────────────────────────────────────
_model    = None
_index    = None
_metadata = None   # list[dict] — one entry per programme


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading embedding model '{MODEL_NAME}' on {device}…")
        _model = SentenceTransformer(MODEL_NAME, device=device)
        if device == "cuda":
            _model.half()  # Use float16 for maximum GPU speed
    return _model


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────
def _short_eligibility(raw: str | None, max_chars: int = ELIGIBILITY_MAX_CHARS) -> str:
    """Return first sentence (or first max_chars chars) of an eligibility string."""
    if not raw:
        return "N/A"
    # Collapse whitespace / newlines
    clean = " ".join(raw.split())
    # Take up to the first full sentence that fits, otherwise hard-truncate
    if len(clean) <= max_chars:
        return clean
    truncated = clean[:max_chars]
    # Try to end at last period / OR clause boundary
    for sep in (". ", " OR "):
        pos = truncated.rfind(sep)
        if pos > max_chars // 2:
            return truncated[: pos + 1].strip()
    return truncated.rstrip(",; ") + "…"


def format_record(record: dict) -> str:
    """Format a property record into a dense embedding-friendly text chunk."""
    title = record.get('title', 'Unknown Property')
    prop_type = record.get('property_type', 'N/A')
    locality = record.get('locality', 'Unknown Locality')
    city = record.get('city', 'Ahmedabad')
    price = record.get('price_inr', 'Contact for Price')
    if isinstance(price, (int, float)):
        price = f"Rs {price}"
    bhk = record.get('bhk', 'N/A')
    area = record.get('area_sqft', 'N/A')
    furnishing = record.get('furnishing', 'N/A')
    amenities = ", ".join(record.get('amenities', []))
    c_name = record.get('contact_name', 'N/A')
    c_phone = record.get('contact_phone', 'N/A')

    return (
        f"Title: {title} | Type: {prop_type} | Location: {locality}, {city} | "
        f"Price: {price} | BHK: {bhk} | Area: {area} sqft | Furnishing: {furnishing} | "
        f"Amenities: {amenities} | Contact: {c_name} | Phone: {c_phone}"
    )


def format_voice_context(record: dict, score: float) -> str:
    """Compact representation for injecting RAG context into the LLM prompt."""
    title = record.get('title', 'Unknown Property')
    locality = record.get('locality', '')
    city = record.get('city', 'Ahmedabad')
    price = record.get('price_inr', 'Contact for Price')
    if isinstance(price, (int, float)):
        price = f"Rs {price}"
    bhk = record.get('bhk', 'N/A')
    furnishing = record.get('furnishing', 'N/A')
    c_name = record.get('contact_name', '')
    c_phone = record.get('contact_phone', '')

    parts = [f"• {title}"]
    if locality:
        parts[-1] += f" in {locality}, {city}"
    parts.append(f"  Price: {price} | BHK: {bhk} | Furnishing: {furnishing}")
    if c_name or c_phone:
        contact = " | ".join(filter(None, [c_name, c_phone]))
        parts.append(f"  Contact: {contact}")

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Index build / load
# ─────────────────────────────────────────────────────────────────────────────
def build_index_from_json(json_path: str = 'final_dataset.json') -> bool:
    """Build and persist the FAISS index from the programme dataset."""
    logger.info(f"Building FAISS index from '{json_path}'…")

    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Dataset not found: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    if not dataset:
        logger.warning("Dataset is empty — cannot build index.")
        return False

    texts = [format_record(r) for r in dataset]

    model = get_model()
    logger.info(f"Generating {len(texts)} embeddings…")
    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        convert_to_numpy=True,
        batch_size=64,
        normalize_embeddings=True,   # already unit-norm → skip extra L2 step
    )

    # Normalise for cosine similarity via IndexFlatIP
    faiss.normalize_L2(embeddings)

    dim   = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    os.makedirs(INDEX_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_FILE)

    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ FAISS index built: {len(dataset)} vectors → {INDEX_FILE}")
    return True


def load_index(force_rebuild: bool = False, json_path: str = 'final_dataset.json') -> None:
    """Load (or build) the FAISS index into global singletons."""
    global _index, _metadata

    needs_build = (
        force_rebuild
        or not os.path.exists(INDEX_FILE)
        or not os.path.exists(METADATA_FILE)
    )

    if needs_build:
        logger.info("Index not found or rebuild requested — building now…")
        success = build_index_from_json(json_path)
        if not success:
            logger.error("Failed to build index. Ensure dataset is not empty.")
            return

    logger.info("Loading FAISS index from disk…")
    _index = faiss.read_index(INDEX_FILE)

    with open(METADATA_FILE, 'r', encoding='utf-8') as f:
        _metadata = json.load(f)

    logger.info(f"✅ FAISS index ready: {_index.ntotal} vectors | {len(_metadata)} records")




ACRONYM_MAP = {
    "બીએચકે": "BHK", "बीएचके": "BHK", "bhk": "BHK",
    "ફ્લેટ": "Flat", "फ्लैट": "Flat", "flat": "Flat",
    "વિલા": "Villa", "विला": "Villa", "villa": "Villa",
    "એપાર્ટમેન્ટ": "Apartment", "अपार्टमेंट": "Apartment", "apartment": "Apartment",
    "ભાડે": "Rent", "किराए": "Rent", "rent": "Rent",
    "વેચાણ": "Sale", "बिक्री": "Sale", "sale": "Sale",
}

def _clean_multilingual_query(q: str) -> str:
    res = q.lower()
    for k, v in ACRONYM_MAP.items():
        res = res.replace(k, v)
    for k, v in ACRONYM_MAP.items():
        # check original cases incase keys had upper (they don't, but still)
        pass 
    
    # Simple substitution
    res = q
    for k, v in ACRONYM_MAP.items():
        # case insensitive replacement
        import re
        ins_regex = re.compile(re.escape(k), re.IGNORECASE)
        res = ins_regex.sub(v, res)
    return res

# ─────────────────────────────────────────────────────────────────────────────
# Search

# ─────────────────────────────────────────────────────────────────────────────
def search(query: str, top_k: int = 3, score_threshold: float = SCORE_THRESHOLD) -> list[dict]:
    query = _clean_multilingual_query(query)
    """
    Semantic search over the programme index.

    Returns a list of result dicts, each with:
      - score (float):          cosine similarity (0–1)
      - record (dict):          raw programme record from metadata
      - text (str):             dense embedding-chunk representation
      - voice_context (str):    compact phone-call-friendly representation

    Results are:
      • Filtered by score_threshold (low-relevance hits are dropped)
      • Deduplicated by programme name (keeps highest-scoring hit)
      • Sorted by score descending
    """
    global _index, _metadata

    if _index is None or _metadata is None:
        logger.warning("FAISS index not loaded — loading now…")
        load_index()

    model     = get_model()
    query_emb = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    faiss.normalize_L2(query_emb)

    # Fetch more candidates so deduplication doesn't deplete top_k results
    fetch_k = min(top_k * 3, _index.ntotal)
    distances, indices = _index.search(query_emb, fetch_k)

    seen_programs: set[str] = set()
    results: list[dict]    = []

    for i, idx in enumerate(indices[0]):
        if idx < 0 or idx >= len(_metadata):
            continue

        score = float(distances[0][i])
        if score < score_threshold:
            continue                      # below relevance threshold

        record   = _metadata[idx]
        prog_key = record.get('id', '').strip().lower()

        if prog_key in seen_programs:
            continue                      # deduplicate same property id
        seen_programs.add(prog_key)

        results.append({
            'score':         score,
            'record':        record,
            'text':          format_record(record),
            'voice_context': format_voice_context(record, score),
        })

        if len(results) >= top_k:
            break

    return results
# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────
def is_ready() -> bool:
    """Return True if the index is loaded and ready to serve queries."""
    return _index is not None and _metadata is not None


def stats() -> dict:
    """Return basic statistics about the loaded index."""
    return {
        "ready":        is_ready(),
        "total_vectors": _index.ntotal if _index else 0,
        "total_records": len(_metadata) if _metadata else 0,
        "model":        MODEL_NAME,
        "index_file":   INDEX_FILE,
        "score_threshold": SCORE_THRESHOLD,
    }
