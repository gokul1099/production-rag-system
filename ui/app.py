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
    if token:
        logfire.configure(token=token)
    LOGFIRE_STATUS = "Connected & Tracing"
except Exception as e:
    print(f"Logfire Init error in UI: {e}")
    LOGFIRE_STATUS = f"Standby (Error: {e})"

st.set_page_config(
    page_title="Enterprise Agentic RAG",
    page_icon="🤖",
    layout="wide"
)

AI_AVATAR = "🤖"
USER_AVATAR = "👨🏼‍🦳"

# --- SESSION MANAGEMENT ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

# Auth state
if "access_token" not in st.session_state:
    st.session_state.access_token = None
    st.session_state.user_id = None
    st.session_state.logged_in = False

if "show_auth_modal" not in st.session_state:
    st.session_state.show_auth_modal = False

if "auth_modal_tab" not in st.session_state:
    st.session_state.auth_modal_tab = "Sign In"

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# --- TOP HEADER BAR ---
header_col1, header_col2, header_col3 = st.columns([6, 1, 1])
with header_col1:
    st.markdown("### 🤖 Enterprise Agentic RAG")
with header_col2:
    if not st.session_state.logged_in:
        if st.button("Sign In", use_container_width=True, key="top_signin"):
            st.session_state.show_auth_modal = True
            st.session_state.auth_modal_tab = "Sign In"
            st.rerun()
    else:
        st.markdown(f"👤 **`{str(st.session_state.user_id)[:8]}...`**")
with header_col3:
    if not st.session_state.logged_in:
        if st.button("Sign Up", type="primary", use_container_width=True, key="top_signup"):
            st.session_state.show_auth_modal = True
            st.session_state.auth_modal_tab = "Sign Up"
            st.rerun()
    else:
        if st.button("Logout", use_container_width=True, key="top_logout"):
            st.session_state.access_token = None
            st.session_state.user_id = None
            st.session_state.logged_in = False
            st.session_state.show_auth_modal = False
            st.rerun()

st.markdown("---")

# --- AUTH MODAL ---
if st.session_state.show_auth_modal and not st.session_state.logged_in:
    with st.container(border=True):
        _, modal_col, _ = st.columns([1, 2, 1])
        with modal_col:
            title = "🔐 Sign In to your account" if st.session_state.auth_modal_tab == "Sign In" else "📝 Create a new account"
            st.markdown(f"## {title}")
            st.markdown(" ")

            tab_signin, tab_signup = st.tabs(["Sign In", "Sign Up"])

            with tab_signin:
                signin_email = st.text_input("Email", placeholder="you@example.com", key="modal_signin_email")
                signin_password = st.text_input("Password", type="password", key="modal_signin_password")
                st.markdown(" ")
                col_do_signin, col_cancel1 = st.columns(2)
                if col_do_signin.button("Sign In", type="primary", use_container_width=True, key="modal_do_signin"):
                    if not signin_email or not signin_password:
                        st.error("Please enter your email and password.")
                    else:
                        try:
                            resp = requests.post(
                                f"{BASE_URL}/auth/signin",
                                json={"email": signin_email, "password": signin_password},
                                timeout=15
                            )
                            resp.raise_for_status()
                            data = resp.json()
                            tok = data.get("access_token")
                            if tok:
                                st.session_state.access_token = tok
                                st.session_state.user_id = data.get("user_id")
                                st.session_state.logged_in = True
                                st.session_state.show_auth_modal = False
                                st.success("Signed in successfully!")
                                st.rerun()
                            else:
                                st.error("Sign in failed: no token returned.")
                        except requests.HTTPError as e:
                            err_msg = ""
                            try:
                                err_msg = resp.json().get("detail", "")
                            except Exception:
                                pass
                            st.error(err_msg or f"Invalid email or password. ({e})")
                        except requests.RequestException as e:
                            st.error(f"Sign in failed: {e}")
                if col_cancel1.button("Cancel", use_container_width=True, key="modal_cancel_signin"):
                    st.session_state.show_auth_modal = False
                    st.rerun()

            with tab_signup:
                signup_email = st.text_input("Email", placeholder="you@example.com", key="modal_signup_email")
                signup_password = st.text_input("Password", type="password", placeholder="Min 8 characters", key="modal_signup_password")
                st.markdown(" ")
                col_do_signup, col_cancel2 = st.columns(2)
                if col_do_signup.button("Create Account", type="primary", use_container_width=True, key="modal_do_signup"):
                    if not signup_email or not signup_password:
                        st.error("Please enter your email and password.")
                    else:
                        try:
                            resp = requests.post(
                                f"{BASE_URL}/auth/signup",
                                json={"email": signup_email, "password": signup_password},
                                timeout=15
                            )
                            resp.raise_for_status()
                            data = resp.json()
                            tok = data.get("access_token")
                            if tok:
                                st.session_state.access_token = tok
                                st.session_state.user_id = data.get("user_id")
                                st.session_state.logged_in = True
                                st.session_state.show_auth_modal = False
                                st.success("Account created and signed in!")
                                st.rerun()
                            else:
                                st.success("Account created! Please sign in.")
                        except requests.HTTPError as e:
                            err_msg = ""
                            try:
                                err_msg = resp.json().get("detail", "")
                            except Exception:
                                pass
                            st.error(err_msg or f"Sign up failed: {e}")
                        except requests.RequestException as e:
                            st.error(f"Sign up failed: {e}")

                if col_cancel2.button("Cancel", use_container_width=True, key="modal_cancel_signup"):
                    st.session_state.show_auth_modal = False
                    st.rerun()

    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🧠 Agent OS")
    st.markdown("---")
    st.success(f"Logfire: {LOGFIRE_STATUS}")
    st.info(f"Memory ID: {st.session_state.session_id[:8]}")

    # Auth status in sidebar
    st.subheader("Account")
    if st.session_state.logged_in:
        st.success("✅ Signed in")
        st.caption(f"User ID: {str(st.session_state.user_id)[:16]}...")
    else:
        st.warning("🔒 Not signed in")
        st.caption("Use the Sign In / Sign Up buttons at the top.")

    st.markdown("---")

    st.subheader("Upload Document")
    uploaded_file = st.file_uploader(
        "Choose a document",
        type=["txt", "pdf", "doc", "docx", "ppt", "pptx"],
        accept_multiple_files=False,
    )

    upload_disabled = uploaded_file is None
    if st.button("Upload", use_container_width=True, disabled=upload_disabled):
        if not st.session_state.logged_in:
            st.session_state.show_auth_modal = True
            st.warning("Please sign in to upload documents.")
            st.rerun()
        else:
            upload_session_id = str(uuid.uuid4())
            upload_url = f"{BASE_URL}/upload"
            try:
                file_bytes = uploaded_file.getvalue()
                files = {
                    "file": (
                        uploaded_file.name,
                        file_bytes,
                        uploaded_file.type or "application/octet-stream",
                    )
                }
                headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
                response = requests.post(
                    upload_url,
                    files=files,
                    data={"session_id": upload_session_id},
                    headers=headers,
                    timeout=120,
                )
                response.raise_for_status()
                st.success(f"✅ Uploaded {uploaded_file.name}")
            except requests.RequestException as e:
                logfire.error(f"Document upload failed: {e}")
                st.error(f"Upload failed: {e}")

    if st.button("🗑️ Clear history and memory", use_container_width=True, type="primary"):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# --- MAIN CHAT AREA ---
st.title("Enterprise Agentic Assistant")

if not st.session_state.logged_in:
    st.info("👆 Please **Sign In** or **Sign Up** using the buttons at the top to start chatting and uploading documents.")

for message in st.session_state.messages:
    avatar = AI_AVATAR if message["role"] == "assistant" else USER_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

chat_placeholder = "Ask about your documents..." if st.session_state.logged_in else "Sign in to start chatting..."
if prompt := st.chat_input(chat_placeholder, disabled=not st.session_state.logged_in):
    if not st.session_state.logged_in:
        st.session_state.show_auth_modal = True
        st.rerun()

    with logfire.span("💬 User chat interaction", user_query=prompt, session_id=st.session_state.session_id):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar=AI_AVATAR):
            with st.status("🔎 Agent is thinking...", expanded=True) as status:
                try:
                    with logfire.span("Calling RAG backend"):
                        url = f"{BASE_URL}/query"
                        payload = {"q": prompt, "thread_id": st.session_state.session_id}
                        headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
                        response = requests.post(url, json=payload, headers=headers, timeout=60)
                        data = response.json()

                    steps = data.get("thought_process", [])
                    for step in steps:
                        st.write(f"⚙️ {step}")
                    status.update(label="Answer Synthesized", state="complete", expanded=False)

                    sources = data.get("sources", [])
                    if sources:
                        with st.expander("📄 View Retrieved Context (Sources)"):
                            for i, source in enumerate(sources):
                                preview = str(source)[:100].replace("\n", " ") + "..."
                                with st.expander(f"Chunk {i+1}: {preview}"):
                                    st.info(source)
                except Exception as e:
                    logfire.error(f"UI Backend connection failed: {e}")
                    status.update(label="Connection Failed", state="error")
                    st.error("Backend offline or error occurred.")
                    st.stop()

            answer_placeholder = st.empty()
            full_answer = data.get("answer", "No response")
            curr_text = ""
            for char in full_answer:
                curr_text += char
                answer_placeholder.markdown(curr_text + "▌")
                time.sleep(0.005)

            answer_placeholder.markdown(full_answer)
            st.session_state.messages.append({"role": "assistant", "content": full_answer})
            logfire.info("Chat cycle completed successfully")