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
        logfire.info(f"Searching Qdrant for: {query}")
        raw_results = seaech_enterprice_knowledge(query=query, limit=15)
        logfire.info(f"Retrived {len(raw_results)} candidates from vector DB")

        doc_contents = [doc["content"] for doc in raw_results]

        with logfire.span("Semantic Reranking"):
            renranked_contents = rerank_documents(query=query, documents=doc_contents, top_n=5)
            logfire.info("Reranking completed ")

        formatted_docs = [f"CONTENT: {doc}" for doc in renranked_contents]
        return{
            "documents": formatted_docs,
            "status": f"Found technical content",
            "plan": state["plan"] + ["Context Retrieved"]
        }

    