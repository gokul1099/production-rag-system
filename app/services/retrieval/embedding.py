import time
import logfire
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_openai import OpenAI
from app.config import setting
from sentence_transformers import SentenceTransformer

BATCH_SIZE = 50
_GEMINI_DIM = 3072
_FALLBACK_DIM = 768

_active_model = None
_model_type = None

def _probe_gemini():
    """Try one embed call to verfiy Gemini is reachable. Returns model or None"""
    try:
        model = NVIDIAEmbeddings(
            model="nemotron-3-embed-1b",
        )
        model.embed_query("probe")
        logfire.info("Gemini embeddings ready (gemini-embedding-2-preview, 3072-dim)")
        return model
    except Exception as e:
        logfire.warning(f"Gemini probe failed: {e}. Will use sentence-transformers fallback")
        return None

def __load_fallback():
    from sentence_transformers import SentenceTransformer
    logfire.info("Loading sentence-transformers fallback (all-mpnet-base-v2, 768-dim)")
    return SentenceTransformer("all-mpnet-base-v2")

def _init():
    global _active_model, _model_type

    if _active_model is not None:
        return
    gemini = _probe_gemini()
    if gemini:
        _active_model = gemini
        _model_type = "gemini"
    else:
        _active_model=__load_fallback()
        _model_type="fallback"

def get_embedding_dim()-> int:
    """Return the vector dimension for the active model. Call after _init()"""
    _init()
    return _GEMINI_DIM if _model_type == "gemini" else _FALLBACK_DIM

def _embed_bacth(batch: list[str]) -> list[list[float]]:
    if _model_type == "gemini":
        for attempt in range(4):
            try:
                 return _active_model.embed_documents(batch)
            except Exception as e:
                err = str(e).lower()
                is_rate_limit = any(x in err for x in ("429", "rate", "qouta", "resource_exhausted"))
                if is_rate_limit and attempt <3:
                    wait = 2 ** attempt
                    logfire.warning(
                        f"Gemini rate limit hit - retrying in {wait}s"
                        f"(attempt {attempt + 1}/4)"
                    )
                    time.sleep(wait)
                else:
                    logfire.error("Gemini embedding failed: {e}")
                    raise
        raise RuntimeError("Gemini rate limit persisted after 4 attempts")
    else:
        return _active_model.encode(batch, show_progress_bar=False).tolist()

def embed_query(query: str)-> list[float]:
    _init()
    if _model_type == "gemini":
        return _active_model.embed_query(query)
    return _active_model.encode([query])[0].tolist()

def _embed_texts(texts: list[str]) -> list[float]:
    _init()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i: i+ BATCH_SIZE]
        with logfire.span("Embed batch", model=_model_type, start=i, size=len(batch)):
            all_embeddings.extend(_embed_bacth(batch))
    return all_embeddings

