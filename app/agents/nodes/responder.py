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
        logfire.info("Generating conversational response using memory")
        prompt = f"""
        You are a friendly and helpful Enterprise AI Assistant.
        Answer the user's latest message using the CONVERSATION HISTORY below.

        CONVERSATION HISTORY:
        {history_str}

        LATEST MESSAGE:
        "{user_msg}"
        """
       
    else:
        logfire.info("Generating technical RAG response")
        max_context_chars = 25000
        full_context = ""

        for doc in state["documents"]:
            if len(full_context) + len(doc) < max_context_chars:
                full_context+=doc + "\n\n"
            else:
                logfire.info("Context truncated to fit groq TPM limits")
                break
        
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
            content = llm.invoke(prompt).content
            logfire.info("✅Response Synthesised via LLM")

            return {
                "final_answer": content,
                "status": "Response generated",
                "plan": state["plan"],
                "messages": [{"role": "assistant", "content": content}]
            }
        except Exception as e:
            logfire.error(f"LLM Generation failed: {e}")
            


