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

# Auth state
if "access_token" not in st.session_state:
    st.session_state.access_token = None
    st.session_state.user_id = None
    st.session_state.logged_in = False


with st.sidebar:
    st.title("🧠 Agent OS")
    st.markdown("---")
    st.success(f"Logfire: {LOGFIRE_STATUS}")
    st.info(f"Memory ID: {st.session_state.session_id[:8]}")

    # --- Authentication ---
    st.subheader("Account")
    base_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    if not st.session_state.access_token:
        email = st.text_input("Email", key="auth_email")
        password = st.text_input("Password", type="password", key="auth_password")
        col1, col2 = st.columns(2)
        if col1.button("Sign In"):
            try:
                url = f"{base_url}/auth/signin"
                resp = requests.post(url, json={"email": email, "password": password}, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                token = data.get("access_token")
                if token:
                    st.session_state.access_token = token
                    st.session_state.user_id = data.get("user_id")
                    st.session_state.logged_in = True
                    st.success("Signed in successfully")
                else:
                    st.error("Signin failed: no token returned")
            except requests.RequestException as e:
                logfire.error(f"Signin failed: {e}")
                st.error(f"Signin failed: {e}")

        if col2.button("Sign Up"):
            try:
                url = f"{base_url}/auth/signup"
                resp = requests.post(url, json={"email": email, "password": password}, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                token = data.get("access_token")
                if token:
                    st.session_state.access_token = token
                    st.session_state.user_id = data.get("user_id")
                    st.session_state.logged_in = True
                    st.success("Account created and signed in")
                else:
                    st.success("Account created")
            except requests.RequestException as e:
                logfire.error(f"Signup failed: {e}")
                st.error(f"Signup failed: {e}")
    else:
        st.success(f"Logged in (id: {st.session_state.user_id})")
        if st.button("Logout"):
            st.session_state.access_token = None
            st.session_state.user_id = None
            st.session_state.logged_in = False

    st.subheader("Upload document")
    uploaded_file = st.file_uploader(
        "Choose a document",
        type=["txt", "pdf", "doc", "docx", "ppt", "pptx"],
        accept_multiple_files=False,
    )
    if st.button("Upload", width="stretch", disabled=uploaded_file is None):
        upload_session_id = str(uuid.uuid4())
        base_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        upload_url = f"{base_url}/upload"

        try:
            file_bytes = uploaded_file.getvalue()
            files = {
                "file": (
                    uploaded_file.name,
                    file_bytes,
                    uploaded_file.type or "application/octet-stream",
                )
            }
            headers = {}
            if st.session_state.access_token:
                headers["Authorization"] = f"Bearer {st.session_state.access_token}"

            response = requests.post(
                upload_url,
                files=files,
                data={"session_id": upload_session_id},
                headers=headers,
                timeout=120,
            )
            response.raise_for_status()
            st.success(f"Uploaded {uploaded_file.name}")
        except requests.RequestException as e:
            print(e,"error during uploading")
            logfire.error(f"Document upload failed: {e}")
            st.error(f"Upload failed. Check that the backend is running. {e}")

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
                        headers = {}
                        if st.session_state.access_token:
                            headers["Authorization"] = f"Bearer {st.session_state.access_token}"
                        response = requests.post(url, json=payload, headers=headers, timeout=60)
                        data = response.json()

                    steps = data.get("thought_process", [])
                    for step in steps:
                        st.write(f"⚙️ {steps}")
                    status.update(label="Answer Sysnthesized", state="complete", expanded=False)

                    sources = data.get("sources", [])
                    if sources:
                        with st.expander("📄 View Retrieved Context (Sources)"):
                            for i, source in enumerate(sources):
                                preview = str(source)[:100].replace("\n", " ") + "..."
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