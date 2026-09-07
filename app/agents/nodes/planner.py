from app.agents.state import AgentState
from app.config import setting
from langchain_groq import ChatGroq
import logfire

llm = ChatGroq(api_key=setting.GROQ_API_KEY, model=setting.GROQ_MODEL)

def planner_node(state: AgentState):
    """
    The planner determines if a search is needed based on the ENTIRE conversation
    """
    #Get the conversation history (excluding the latest message)

    history = ""
    for msg in state['messages'][:-1]:
        role = 'User' if msg["role"] == "user" else "Assistant"
        history += f"{role}: {msg['content']}\n"

    user_message = state['messages'][-1]['content'] if state['messages'] else ""

    prompt=f"""
    You are a intelligent Assistant Planner.
    Analyse the conversation history and the latest user message,

    CONVERSATION HISTORY:
    {history}

    LATEST MESSAGE:
    "{user_message}"

    Task:
    1. If the latest message is a greeting (hi, hello) or a question that can be answered using the ONLY the conversation history above (e.g., 'What is my name'), respond with 'CONVERSATIONAL'
    2. If it is technical question about Kubernetes, Intel or networking that requires fresh documentation, output a refined search query
    """

    with logfire.span("Planner Decision"):
        decision = llm.invoke(prompt).content.strip()
        logfire.info(f"Intent identifier: {decision}")

    if decision == "CONVERSATIONAL":
        return {
            "current_query": "CONVERSATIONAL",
            "status": "Handling Conversationaly using memory",
            "plan":["Intent: Conversational/Memory", "Retrieval: Skipped"]
        }
    return{
        "current_query": decision,
        "status":f"Technical research needed. Searching for: {decision}",
        "plan": ["Intent: Technical", f"Search Term: {decision}"]
    }
