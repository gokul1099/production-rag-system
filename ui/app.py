import os
import streamlit as st
import requests
import time
import uuid
import logfire
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=env_path)

try:
    token = os.getenv("LOGFIRE_TOKEN")
    if not token:
        print("Error: LoGFIRE_TOKEN is empty or None!")
    logfire.configure(token=token)

    LOGFIRE_STATUS = "Conncted & Tracing"
except Exception as e:
    print(f"Logfire Inint error in UI: {e}")
    LOGFIRE_STATUS = f"standby (Error: {e})"

st.set_page_config(
    page_title="Enterprise Agentic RAG",
    page_icon="🤖",
    layout="wide"
)

AI_AVATAR="🤖"
USER_AVATAR="👨🏼‍🦳"

# --- SESSION MANAGEMENT ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    logfire.info(f"✨ New User Session Created: {st.session_state.session_id}")

if "messages" not in st.session_state:
    st.session_state.messages = []


with st.sidebar:
    st.title("🧠 Agent OS")
    st.markdown("---")
    st.success(f"Logfire: {LOGFIRE_STATUS}")
    st.info(f"Memory ID: {st.session_state.session_id[:8]}")
    if st.button("🗑️ Clear history and memory", width="stretch", type="primary"):
        logfire.warn(f"🗑️ Memory wipe triggered for session: {st.session_state.session_id[:8]}")
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

st.title("Enterprise agentic assistant")

for message in st.session_state.messages:
    avatar = AI_AVATAR if message["role"] == "assistant" else USER_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about your documents"):
    with logfire.span("💬 User chat interaction", user_query=prompt, session_id=st.session_state.session_id):
        st.session_state.messages.append({"role":"user", "content": prompt})
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar=AI_AVATAR):
            with st.status("🔎 Agent is thinking...", expanded=True) as status:
                try:
                    with logfire.span("Calling RAG backend"):
                        base_url = os.getenv("BACKEND_URL", "http://localhost:8000")
                        url = f"{base_url}/query"
                        payload = {"q": prompt, "thread_id": st.session_state.session_id}
                        response = requests.post(url, json=payload, timeout=60)
                        data = response.json()

                    steps = data.get("thought_process", [])
                    for step in steps:
                        st.write(f"⚙️ {steps}")
                    status.update(label="Answer Sysnthesized", state="complete", expanded=False)

                    sources = data.get("sources", [])
                    if sources:
                        with st.expander("📄 View Retrieved Context (Sources)"):
                            for i, source in enumerate(sources):
                                preview = sources[:100].replace("\n", " ")+ "..."
                                with st.expander(f"Chunk {i+1}: {preview}"):
                                    st.info(source)
                except Exception as e:
                    logfire.error(f"UI Backend connection failed: {e}")
                    status.update(label="conntection Failed", state="error")
                    st.error("Backend offine")
                    st.stop()

            answer_placeholder = st.empty()
            full_answer = data.get("answer", "No response")
            curr_text = ""
            for char in full_answer:
                curr_text+= char
                answer_placeholder.markdown(curr_text + "▌")
                time.sleep(0.005)

            answer_placeholder.markdown(full_answer)
            st.session_state.messages.append({"role":"assistant", "content": full_answer})
            logfire.info("Chat cycle completed successfully")