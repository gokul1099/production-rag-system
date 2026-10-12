import logfire
from app.agents.state import AgentState
from app.config import setting
from langchain_groq import ChatGroq

llm = ChatGroq(api_key=setting.GROQ_API_KEY, model=setting.GROQ_MODEL)
def generate_node(state: AgentState):
    """
    Synthesizes a response using both Documentation Context and Conversation History
    """
    query = state["current_query"]
    history_str = ""

    for msg in state["messages"]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"

    user_msg = state["messages"][-1]["content"] if state["messages"] else ""

    if query == "CONVERSATIONAL":
        logfire.info("🔵 [RESPONDER] Generating conversational response using memory")
        prompt = f"""
        You are a friendly and helpful Enterprise AI Assistant.
        Answer the user's latest message using the CONVERSATION HISTORY below.

        CONVERSATION HISTORY:
        {history_str}

        LATEST MESSAGE:
        "{user_msg}"
        """

    else:
        logfire.info(f"🔵 [RESPONDER] Generating technical RAG response with {len(state['documents'])} documents")
        max_context_chars = 25000
        full_context = ""

        if not state["documents"]:
            logfire.warning("⚠️ [RESPONDER] No documents provided - generating response without context")

        for idx, doc in enumerate(state["documents"]):
            if len(full_context) + len(doc) < max_context_chars:
                full_context += doc + "\n\n"
            else:
                logfire.info(f"🔵 [RESPONDER] Context truncated at document {idx} to fit token limits")
                break

        logfire.info(f"🔵 [RESPONDER] Context prepared: {len(full_context)} characters from {len(state['documents'])} documents")

        prompt = f"""
        You are a Senior Technical Architect.
        Answer the question using the TECHNICAL CONTEXT provided.

        FULL CONTEXT:
        {full_context}

        CONVERSATION HISTORY:
        {history_str}

        USER QUESTION:
        `{user_msg}`
        """

    with logfire.span("Calling LLM with prompt"):
        try:
            logfire.info(f"🔵 [RESPONDER] Invoking {setting.GROQ_MODEL} LLM")
            content = llm.invoke(prompt).content
            logfire.info(f"✅ [RESPONDER] Response synthesized via LLM ({len(content)} characters)")

            return {
                "final_answer": content,
                "status": "Response generated",
                "plan": state["plan"],
                "messages": [{"role": "assistant", "content": content}]
            }
        except Exception as e:
            logfire.error(f"🔴 [RESPONDER] LLM generation failed: {type(e).__name__}: {str(e)}", exc_info=True)
            return {
                "final_answer": f"I encountered an error while generating a response: {str(e)}",
                "status": "Error in response generation",
                "plan": state["plan"] + ["Error in LLM"],
                "messages": [{"role": "assistant", "content": f"Error: {str(e)}"}]
            }
            


