import logfire
from app.agents.state import AgentState
from app.services.retrieval.qdrant_service import seaech_enterprice_knowledge
from app.services.retrieval.ranking_service import rerank_documents

def retrieve_node(state: AgentState):
    """
    Perform vector search and semantic reranking for technical queries
    """
    query = state["current_query"]

    with logfire.span("🔎 Knowledge Retrieval"):
        logfire.info(f"🔵 [RETRIEVER] Starting retrieval for query: {query}")
        raw_results = seaech_enterprice_knowledge(query=query, limit=15)
        logfire.info(f"🔵 [RETRIEVER] Retrieved {len(raw_results)} candidates from Qdrant")

        if not raw_results:
            logfire.warning(f"⚠️ [RETRIEVER] No results found in Qdrant for query: {query}")
            return {
                "documents": [],
                "status": "No matching documents found in knowledge base",
                "plan": state["plan"] + ["Context Retrieval: No results"]
            }

        doc_contents = [doc["content"] for doc in raw_results]
        logfire.info(f"🔵 [RETRIEVER] Extracted {len(doc_contents)} document contents for reranking")

        with logfire.span("Semantic Reranking"):
            logfire.info(f"🔵 [RETRIEVER] Starting semantic reranking with top_n=5")
            reranked_contents = rerank_documents(query=query, documents=doc_contents, top_n=5)
            logfire.info(f"✅ [RETRIEVER] Reranking completed with {len(reranked_contents)} results")

        formatted_docs = [f"CONTENT: {doc}" for doc in reranked_contents]
        logfire.info(f"✅ [RETRIEVER] Formatted {len(formatted_docs)} documents for generation")

        return {
            "documents": formatted_docs,
            "status": f"Found {len(formatted_docs)} relevant technical content",
            "plan": state["plan"] + ["Context Retrieved"]
        }

    