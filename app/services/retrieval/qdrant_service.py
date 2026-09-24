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
        raise RuntimeError(f"Qdrant is not reachable at localhost:6333: {exc}") from exc

    if exists:
        return

    dim = get_embedding_dim()
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=dim,
            distance=models.Distance.COSINE,
        ),
    )
    logfire.info(f"Created missing Qdrant collection '{collection_name}' ({dim}-dim, Cosine)")


def seaech_enterprice_knowledge(query:str, limit: int= 8):
    """
    Performs a high-precision search in the enterprise knowledge bases.
    uses the model query-points interface
    """
    try:
        query_vector = embed_query(query)

        response = client.query_points(
            collection_name=setting.QDRANT_COLLECTION,
            query=query_vector,
            limit=limit,
            with_payload=True
        )

        results = []
        for res in response.points:
            results.append({
                "content": res.payload.get("text", ""),
                "source": res.payload.get("source","Unkown"),
                "score": res.score
            })

        return results
    except Exception as e:
        logfire.error(f"❌ Qdrant search failed: {e}")
        return []