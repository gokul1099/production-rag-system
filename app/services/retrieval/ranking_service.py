import time
import logfire
from flashrank import Ranker, RerankRequest


_ranker =None

def get_ranker() -> Ranker:
    """
    Initializes the flash rank engine lazily.
    Flashrank uses local onnx model (ms-marco-MiniLM-L-6-v2) for ultra-fast reranking
    """
    global _ranker
    if _ranker is None:
        logfire.info("🧠 Initializing Flashrank model")
        try:
            _ranker =Ranker(cache_dir="/tmp/flashrank")
        except Exception:
            _ranker = Ranker()
    return _ranker

def rerank_documents(query:str, documents: list[str], top_n:int =5 ) -> list[str]:
    """
    Refines retrieval results by re-scoring documents against the query semantically.

    Why Flashrank?
    Standard vector search (Cosine Similarity) is fast but mathematically "fuzzt",
    FlashRank uses a Cross-Encoder approach which is much more precise but usually slow.
    FlashRank solves this by using highly optimized, quantized ONNX models locally.
    """

    if not documents:
        return []
    start_time = time.time()
    logfire.info(f"[Reranker] sending {len(documents)} docs to FlashRank CrossEncoder...")

    try:
        ranker = get_ranker()
        passages = [
            {"id":1, "text":doc}
            for i, doc in enumerate(documents)
        ]
        request = RerankRequest(query=query, passages=passages)
        results = ranker.rerank(request)

        reranked_docs = [] 
        for res in results[:top_n]:
            reranked_docs.append(res["text"])

        duration = time.time() - start_time
        top_score = results[0]['score'] if results else 'N/A'
        logfire.info(f"✅ [Reranker] Done in {duration:.2f}s. Top semantic score: {top_score}")
        return reranked_docs
    except Exception as e:
        logfire.error(f"❌ [Reranker] Semantic Reranking failed: {e}")
        #Fallback to original qudrant order to ensure the user still gets an answer
        return documents[:top_n]
    