import logfire
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import setting
from app.services.retrieval.embedding import embed_query, get_embedding_dim

client = QdrantClient(
    url=setting.QDRANT_CLUSTER_ENDPOINT,
    api_key=setting.QDRANT_API_KEY,
    check_compatibility=False
)


def ensure_collection_exists(collection_name: str) -> None:
    """Create the collection if it does not already exist."""
    try:
        exists = client.collection_exists(collection_name)
    except Exception as exc:
        raise RuntimeError(f"Qdrant is not reachable at {setting.QDRANT_CLUSTER_ENDPOINT}: {exc}") from exc

    if exists:
        return

    dim = get_embedding_dim()
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=dim,
            distance=models.Distance.COSINE,
        ),
        sparse_vectors_config=models.SparseVectorParams(
            index=models.SparseIndexParams()
        )
    )
    logfire.info(f"Created missing Qdrant collection '{collection_name}' ({dim}-dim dense + sparse BM25)")


def seaech_enterprice_knowledge(query: str, limit: int = 8):
    """
    Performs a high-precision semantic search in the enterprise knowledge bases.
    Uses vector similarity search (cosine distance) to find relevant documents.
    """
    try:
        logfire.info(f"🔵 [QDRANT] Starting semantic search for query: {query[:100]}...")

        logfire.info(f"🔵 [QDRANT] Embedding query using active model")
        query_vector = embed_query(query)
        logfire.info(f"🔵 [QDRANT] Query vector generated with {len(query_vector)} dimensions")

        logfire.info(f"🔵 [QDRANT] Searching collection '{setting.QDRANT_COLLECTION}' with limit={limit}")
        response = client.search(
            collection_name=setting.QDRANT_COLLECTION,
            query_vector=query_vector,
            limit=limit,
            with_payload=True,

        )

        logfire.info(f"🔵 [QDRANT] Search returned {len(response)} results")

        results = []
        for idx, res in enumerate(response):
            score = res.score if hasattr(res, 'score') else 'N/A'
            source = res.payload.get("source", "Unknown") if hasattr(res, 'payload') else "Unknown"
            logfire.info(f"🔵 [QDRANT] Result {idx + 1}: source={source}, score={score}")

            results.append({
                "content": res.payload.get("text", "") if hasattr(res, 'payload') else "",
                "source": source,
                "score": score
            })

        logfire.info(f"✅ [QDRANT] Successfully retrieved {len(results)} documents from Qdrant")
        return results
    except Exception as e:
        logfire.error(f"🔴 [QDRANT] Semantic search failed: {type(e).__name__}: {str(e)}", exc_info=True)
        return []