import logfire
from fastembed.sparse_embedding import SparseTextEmbedding
from qdrant_client.http import models

_sparse_model = None

def _init_sparse_model():
    """Initialise Sparse Model lazily"""
    global _sparse_model
    if _sparse_model is None:
        logfire.info("🧠[SPARSE] Initializing sparse embedding models for BM25")
        _sparse_model = SparseTextEmbedding(model_name="Qdrant/bm42-all-minilm-l6-v2-attentions")
    return _sparse_model

def compute_sparse_vectors(chunks: list[str]) -> list[models.SparseVector]:
    """
    Computer sparse vectors (BM25-style) from text chunks for hybrid search
    """
    try:
        logfire.info(f"[SPARSE] Computing sparse vectors for {len(chunks)} chunks")
        model = _init_sparse_model()

        sparse_vectors = []
        sparse_embeddings = list(model.embed_documents(chunks))

        for idx, sparse_embeddings in enumerate(sparse_embeddings):
            indices, values = sparse_embeddings
            sparse_vec = models.SparseVector(
                indices=indices,
                values=values
            )
            sparse_vectors.append(sparse_vec)

        logfire.info(f"✅ [SPARSE] Computed Sparse vectors for {len(sparse_vectors)} chunks")
        return sparse_vectors
    except Exception as e:
        logfire.error(f"🛑 [SPARSE] Failed to compute sparse vectors: {type(e).__name__}: {str(e)}", exc_info=True)
        return [models.SparseVector(indices=[], values=[]) for _ in chunks]