# Enterprise Agentic RAG System

A production-oriented Retrieval-Augmented Generation (RAG) system. Users sign up, upload documents, and ask questions. Uploads are stored in Google Cloud Storage, indexed automatically through a Pub/Sub event pipeline into Qdrant, and answered by a LangGraph agent that plans, retrieves, reranks, and generates a grounded response.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Running the Services](#running-the-services)
- [Ingesting Documents](#ingesting-documents)
- [API Reference](#api-reference)
- [Retrieval Pipeline](#retrieval-pipeline)
- [Observability](#observability)
- [Deployment](#deployment)
- [Status and Roadmap](#status-and-roadmap)

---

## Features

### Authentication and Access Control
- **User signup and signin** (`/auth/signup`, `/auth/signin`) with bcrypt password hashing (passwords are truncated to bcrypt's 72-byte limit).
- **JWT access tokens** issued on signup and signin, configurable algorithm and expiry (`JWT_ALGORITHM`, `JWT_EXP_SECONDS`).
- **User storage** via SQLModel: PostgreSQL when `DATABASE_URL` is set, otherwise a local SQLite file (`processed_data/users.db`).
- **API Gateway authentication**: every request except public and auth routes must carry `Authorization: Bearer <token>`, either a static API key from `GATEWAY_API_KEYS` or a valid JWT.
- **Rate limiting** in the gateway: sliding window per token (or per client IP for anonymous requests), configured by `GATEWAY_RATE_LIMIT_REQUESTS` and `GATE_LIMIT_WINDOW_SECONDS`.

### Document Upload and Storage
- **Upload endpoint** (`POST /upload`) accepts `.pdf`, `.docx`, `.ppt`, and `.txt` files with a `session_id` form field.
- Files are validated (extension, session ID), read into memory, and written to Google Cloud Storage under `uploads/<filename>`.
- GCS object finalization triggers the ingestion pipeline automatically (see below).

### Event-Driven Ingestion
- **GCS to Pub/Sub to Cloud Run**: a GCS bucket notification publishes an `OBJECT_FINALIZE` event to a Pub/Sub topic. A push subscription delivers it to `POST /pubsub/ingest`.
- The handler decodes the event, skips directory objects, derives the source type from the object path, and runs ingestion in a worker thread so the event loop is not blocked.
- Failures return HTTP 500 so Pub/Sub retries the delivery.

### Document Processing
- **Multi-format loaders**: PDF (`pypdf` / `pdfplumber`), HTML (`beautifulsoup4`), plain text, and Office documents (`python-docx`, `python-pptx`).
- Files are downloaded from GCS to a temporary file, parsed, and the temporary file is removed afterwards.
- Extracted text is saved as JSON under `processed_data/<source_type>/` for inspection and reuse.
- **Paragraph-aware chunking**: text is split on blank lines into chunks of roughly 1500 characters.
- **Source typing**: documents are tagged `true`, `noisy`, or `general` from their folder name during bulk ingestion.

### Dense Embeddings (Semantic Search)
- **Primary model**: NVIDIA embeddings (`nvidia/nemotron-3-embed-1b`, 2048-dimensional).
- **Automatic fallback**: if the NVIDIA probe fails at startup, the system loads `sentence-transformers/all-mpnet-base-v2` (768-dimensional).
- Embeddings are generated in batches of 50 with exponential backoff on rate-limit errors.

### Sparse Embeddings (BM25-style, for Hybrid Search)
- During ingestion, each chunk also receives a **sparse vector** computed with FastEmbed (`Qdrant/bm42-all-minilm-l6-v2-attentions`) through `app/services/retrieval/sparse_embedding.py`.
- The Qdrant collection is created with a named sparse vector configuration, so each point stores both a dense and a sparse vector.
- Query-side hybrid fusion is not wired yet (see [Status and Roadmap](#status-and-roadmap)).

### Vector Database
- **Qdrant** (cloud or self-hosted) stores one point per chunk with `text`, `source`, and `source_type` in the payload.
- The collection (`enterprise_rag`) is created automatically on first ingestion with cosine distance.
- Search uses `client.search()` for cosine similarity over the dense vector.

### Agentic Query Processing
The question-answering flow is a LangGraph state machine with per-thread memory:

1. **Planner** (`app/agents/nodes/planner.py`): an LLM decides whether the latest message can be answered from conversation history (`CONVERSATIONAL`) or needs a refined search query for technical retrieval.
2. **Retriever** (`app/agents/nodes/retriever.py`): searches Qdrant for the top 15 candidates, then reranks them and keeps the top 5.
3. **Responder** (`app/agents/nodes/responder.py`): builds a prompt from the retrieved context (capped at 25,000 characters) and conversation history, then calls the LLM. Conversational turns skip retrieval entirely.

- **Conversation memory**: `MemorySaver` keeps state per `thread_id`. Memory is in-process and is lost on restart.
- **Graceful errors**: LLM and search failures return a structured error response instead of crashing the request.

### Reranking
- **FlashRank** cross-encoder (`ms-marco-MiniLM-L-6-v2`, local ONNX) rescores the Qdrant candidates against the query.
- If reranking fails, the original Qdrant order is used as a fallback.

### Web Interface
- **Streamlit UI** (`ui/app.py`) with sign-in and sign-up tabs, a chat interface, and document upload.
- The UI talks only to the gateway, using the `BACKEND_URL` environment variable.

### Observability
- **Logfire** tracing across every layer: gateway, API, ingestion, embeddings, Qdrant search, reranking, and LLM calls.
- Structured log prefixes make pipeline stages easy to filter: `[PUBSUB]`, `[UPLOAD]`, `[GCS_INGEST]`, `[FILE_PROCESS]`, `[SPARSE]`, `[QDRANT]`, `[RETRIEVER]`, `[PLANNER]`, `[RESPONDER]`, `[QUERY]`.
- Tracing is enabled only when `LOGFIRE_TOKEN` is set.

### Deployment and CI/CD
- **Three Dockerfiles** (API, gateway, Streamlit) and a **docker-compose.yml** that runs all three on a shared network.
- **GitHub Actions** (`.github/workflows/deploy.yml`) builds only the services whose files changed, pushes images to Google Artifact Registry, and deploys to Cloud Run in `asia-east1`.
- **Local dev helpers** (`app/cli.py`) start the services with uvicorn and Streamlit, or via Docker Compose.

---

## Architecture

### Upload and Ingestion Flow

```
 Streamlit UI
      │  POST /upload (multipart: file + session_id)
      ▼
 Gateway :8001  ── auth (API key / JWT) + rate limit ──▶  API :8000
                                                              │
                                                              ▼
                                                     Google Cloud Storage
                                                     bucket: uploads/<file>
                                                              │ OBJECT_FINALIZE
                                                              ▼
                                                        Pub/Sub topic
                                                              │ push subscription
                                                              ▼
                                              POST /pubsub/ingest (API :8000)
                                                              │
                  ┌───────────────────────────────────────────┴──────────────┐
                  ▼                    ▼                    ▼                ▼
          Download from GCS     Parse & chunk      Dense + sparse       Upsert points
                                                    embeddings          to Qdrant
```

### Query Flow

```
 Streamlit UI
      │  POST /query  {q, thread_id}
      ▼
 Gateway :8001  ── auth + rate limit ──▶  API :8000  /query
                                              │
                                              ▼
                              ┌──────────── LangGraph ────────────┐
                              │  Planner ──┬─▶ Responder (chat)   │
                              │            └─▶ Retriever           │
                              │                  │ Qdrant search   │
                              │                  │ FlashRank rerank│
                              │                  ▼                 │
                              │              Responder (RAG)       │
                              └──────────────────┬─────────────────┘
                                                 ▼
                                      answer + sources + plan
```

### Services

| Service | Port | Entry point | Responsibility |
|---|---|---|---|
| `api` | 8000 | `app.main:app` | Upload, Pub/Sub ingestion, query, auth routes |
| `gateway` | 8001 | `gateway.main:app` | Authentication, rate limiting, reverse proxy to `api` |
| `streamlit` | 8501 | `ui/app.py` | Chat and upload interface |

Clients only reach the gateway. Only the gateway forwards traffic to the API.

---

## Project Structure

```
production-rag-system/
├── app/                          # Backend API service
│   ├── main.py                   # FastAPI routes: /upload, /pubsub/ingest, /query
│   ├── auth.py                   # /auth/signup, /auth/signin, JWT and bcrypt helpers
│   ├── db.py                     # SQLModel engine (PostgreSQL or SQLite), session helper
│   ├── models.py                 # Request models (QueryRequest, UploadRequest)
│   ├── models_auth.py            # User table
│   ├── config.py                 # Environment-driven settings
│   ├── cli.py                    # Local dev runners (api, gateway, ui, all, docker)
│   ├── agents/
│   │   ├── graph.py              # LangGraph workflow and compiled rag_agent
│   │   ├── state.py              # AgentState
│   │   └── nodes/
│   │       ├── planner.py        # Conversational vs technical routing
│   │       ├── retriever.py      # Qdrant search and reranking
│   │       └── responder.py      # LLM response generation
│   ├── ingestion/
│   │   ├── processor.py          # GCS download, parse, chunk, embed, index
│   │   ├── loaders/              # pdf.py, html.py, text.py, office.py
│   │   └── chunking/splitter.py  # Paragraph-based chunker
│   ├── gateway/client.py         # Portkey / LLM client helper
│   └── services/
│       ├── gcp/gcs_utils.py      # GCS upload, download, delete
│       └── retrieval/
│           ├── embedding.py      # NVIDIA embeddings with sentence-transformers fallback
│           ├── sparse_embedding.py  # FastEmbed sparse vectors for BM25-style search
│           ├── qdrant_service.py # Collection setup and vector search
│           └── ranking_service.py   # FlashRank reranking
├── gateway/                      # API gateway service
│   ├── main.py                   # Reverse proxy with streaming and header handling
│   ├── config.py
│   └── middlewares/
│       ├── auth.py               # API key and JWT validation
│       └── rate_limit.py         # Sliding-window rate limiter
├── ui/
│   └── app.py                    # Streamlit chat and upload interface
├── DATA/                         # Sample documents for bulk ingestion
│   ├── true_data/
│   └── noisy_data/
├── processed_data/               # Parsed chunk JSON and SQLite user DB (generated)
├── .github/workflows/deploy.yml  # Path-filtered build and Cloud Run deploy
├── Dockerfile                    # API image
├── Dockerfile.gateway            # Gateway image
├── Dockerfile.streamlit          # UI image
├── docker-compose.yml
├── requirements.txt              # API dependencies
├── requirements-gateway.txt      # Gateway dependencies
├── requirements-ui.txt           # UI dependencies
└── pyproject.toml                # Project metadata and dev scripts
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API and gateway | FastAPI, Uvicorn, httpx |
| UI | Streamlit |
| Agent orchestration | LangGraph (with `MemorySaver` checkpointing) |
| LLM | Groq (Qwen model, configurable via `GROQ_MODEL`) |
| Dense embeddings | NVIDIA Embeddings, sentence-transformers (fallback) |
| Sparse embeddings | FastEmbed (BM42 model) |
| Vector database | Qdrant |
| Reranking | FlashRank |
| Object storage | Google Cloud Storage |
| Event bus | Google Cloud Pub/Sub (push subscription) |
| Relational storage | SQLModel with PostgreSQL or SQLite |
| Auth | bcrypt, PyJWT, API keys |
| Observability | Logfire |
| Hosting | Google Cloud Run, Docker, GitHub Actions |

---

## Getting Started

### Prerequisites
- Python 3.13 or newer (per `pyproject.toml`)
- Docker and Docker Compose (for the containerized setup)
- A Qdrant instance (Qdrant Cloud or self-hosted)
- A Google Cloud project with a GCS bucket and Pub/Sub topic (for the event-driven ingestion path)
- API keys for Groq and NVIDIA (and optionally Google, OpenAI, Portkey)

### Local Setup

```bash
git clone <repository-url>
cd production-rag-system

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-gateway.txt
pip install -r requirements-ui.txt
```

Create a `.env` file in the project root. See [Configuration](#configuration).

### Docker Setup

```bash
docker compose up --build
```

This starts the API (internal port 8000), the gateway (port 8001), and the Streamlit UI (port 8501).

---

## Configuration

Set these in `.env` or as environment variables. Never commit real values.

### Model and Vector Database

| Variable | Used by | Purpose |
|---|---|---|
| `GROQ_API_KEY` | API | Groq LLM access |
| `GOOGLE_API_KEY` | API | Google services |
| `NVIDIA_API_KEY` | API | NVIDIA embedding endpoint |
| `OPENAI_API_KEY` | API | Optional OpenAI access |
| `GROQ_MODEL` | API | Optional model override |
| `QDRANT_CLUSTER_ENDPOINT` | API | Qdrant URL |
| `QDRANT_API_KEY` | API | Qdrant key |

The Qdrant collection name is fixed to `enterprise_rag` in `app/config.py`.

### Google Cloud

| Variable | Used by | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | API | GCP project |
| `GCS_BUCKET_NAME` | API | Upload bucket |
| `GOOGLE_APPLICATION_CREDENTIALS` | API | Path to service account or ADC JSON |

### Authentication and Gateway

| Variable | Used by | Purpose |
|---|---|---|
| `JWT_SECRET` | API, gateway, UI | Signing and verification key |
| `JWT_ALGORITHM` | API, gateway, UI | Defaults to `HS256` |
| `JWT_EXP_SECONDS` | API | Token lifetime, defaults to 3600 |
| `GATEWAY_API_KEYS` | Gateway, UI | Comma-separated static API keys |
| `GATEWAY_RATE_LIMIT_REQUESTS` | Gateway | Requests per window, defaults to 100 |
| `GATE_LIMIT_WINDOW_SECONDS` | Gateway | Window length, defaults to 60 |
| `GATEWAY_HTTP_TIMEOUT` | Gateway | Upstream timeout in seconds, defaults to 30 |
| `BACKEND_API_URL` | Gateway | API base URL, defaults to `http://api:8000` |
| `BACKEND_URL` | UI | Gateway base URL, defaults to `http://localhost:8000` |

### Storage and Observability

| Variable | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | API, UI | PostgreSQL URL. Falls back to SQLite when unset |
| `USER_DB_PATH` | API | SQLite path, defaults to `processed_data/users.db` |
| `LOGFIRE_TOKEN` | All services | Enables Logfire tracing |

---

## Running the Services

### Option 1: Local Processes

```bash
dev-all                     # script defined in pyproject.toml
```

`run_all` starts the API on port 8000, the gateway on 8001, and Streamlit on 8501.

Individual services:

```bash
uvicorn app.main:app --port 8000 --reload
uvicorn gateway.main:app --port 8001 --reload
streamlit run ui/app.py --server.port 8501
```

### Option 2: Docker Compose

```bash
docker compose up --build
```

Open the UI at `http://localhost:8501`.

---

## Ingesting Documents

There are two ways to get documents into Qdrant.

### 1. Through the Application (Production Path)

1. Sign in through the UI or call `/auth/signin`.
2. Upload a file through the UI or call `POST /upload`.
3. The file lands in GCS, and the bucket notification triggers `/pubsub/ingest`.
4. The API downloads, parses, chunks, embeds, and indexes the file.

Watch the Logfire or Cloud Run logs for `[UPLOAD]`, `[PUBSUB]`, `[GCS_INGEST]`, and `[FILE_PROCESS]`.

### 2. Bulk Ingestion From Local Folders

```bash
python -m app.ingestion.processor DATA
python -m app.ingestion.processor DATA/true_data true
```

- The first argument is the folder to scan, defaulting to `DATA`.
- The optional second argument forces a source type for the top-level folder.
- Sub-folders are classified as `true`, `noisy`, or `general` from their names.
- The `--wipe` flag is parsed, but dropping the collection is not implemented yet.

Each processed file is also saved as JSON in `processed_data/<source_type>/`.

---

## API Reference

All routes except `/`, `/docs`, `/redoc`, `/openapi.json`, `/auth/signup`, and `/auth/signin` require `Authorization: Bearer <token>` when called through the gateway. The token can be a static API key or a JWT.

### Authentication

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/signup` | `{"email": "...", "password": "..."}` | `access_token`, `token_type`, `user_id` (201) |
| POST | `/auth/signin` | `{"email": "...", "password": "..."}` | `access_token`, `token_type`, `user_id` |

Errors: `400` if the user exists, `401` for invalid credentials.

### Documents

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/upload` | multipart: `file`, `session_id` | `filename`, `session_id`, `gcs_uri`, `status` |
| POST | `/pubsub/ingest` | Pub/Sub push envelope | `status`, `file_name` |

`/upload` returns `422` for unsupported extensions or an empty session ID. `/pubsub/ingest` is called by Google Pub/Sub, not by clients.

### Query

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/query` | `{"q": "...", "thread_id": "..."}` | `question`, `answer`, `thought_process`, `status`, `sources` |

`thread_id` defaults to `default_user` and keeps conversation memory separate per user.

### Utility

| Method | Path | Response |
|---|---|---|
| GET | `/` | Liveness message |
| GET | `/graph` | PNG diagram of the LangGraph workflow |

### Example

```bash
# Sign up
curl -X POST http://localhost:8001/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret"}'

# Upload a document
curl -X POST http://localhost:8001/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@report.pdf" -F "session_id=abc123"

# Ask a question
curl -X POST http://localhost:8001/query \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"q": "What does the report say about latency?", "thread_id": "user-1"}'
```

---

## Retrieval Pipeline

| Stage | Component | Detail |
|---|---|---|
| 1. Plan | Planner node | Classifies the message as conversational or technical and writes a refined search query |
| 2. Embed | `embedding.py` | Embeds the query with the same model used at ingestion |
| 3. Search | `qdrant_service.py` | Cosine search over the dense vector, top 15 candidates |
| 4. Rerank | `ranking_service.py` | FlashRank cross-encoder, keeps top 5 |
| 5. Generate | Responder node | Builds a prompt capped at 25,000 characters and calls the LLM |

Chunks are 1500 characters or less, so each candidate fits comfortably in the context budget.

### Troubleshooting Empty Answers

| Log line | Meaning |
|---|---|
| `[QDRANT] Search returned 0 results` | Nothing is indexed, or the query has no close match. Check ingestion logs. |
| `[RETRIEVER] Reranking completed with 0 results` | Candidates were found but reranking removed them |
| `[RESPONDER] Context prepared: 0 characters` | No documents reached the LLM |

---

## Observability

- **Logfire** receives spans and logs from every service when `LOGFIRE_TOKEN` is set.
- Each pipeline stage logs with a bracketed prefix so one document's journey can be traced from upload to indexing.
- Errors are logged with full stack traces (`exc_info=True`).
- The gateway logs authentication outcomes, proxy status, and timeouts.

---

## Deployment

### Google Cloud Run (CI/CD)

On every push to `main`, the GitHub Actions workflow:

1. Detects which services changed (`app/**`, `gateway/**`, `ui/**`, and their Dockerfiles or requirements).
2. Builds and pushes only the affected images to Google Artifact Registry (`rag-repo`).
3. Deploys them to Cloud Run in `asia-east1`.

Required GitHub secrets include `GCP_PROJECT_ID` and the Google Cloud authentication settings used by the workflow.

### Pub/Sub Configuration

The push subscription must point at the current API service URL:

```
https://<api-service-url>/pubsub/ingest
```

If the Cloud Run URL changes, update the subscription with `gcloud pubsub subscriptions update`. Ingestion stops silently when the endpoint is stale.

---

## Status and Roadmap

| Feature | Status |
|---|---|
| User signup, signin, JWT | Implemented |
| Gateway auth and rate limiting | Implemented |
| GCS upload and Pub/Sub ingestion | Implemented |
| Multi-format parsing and chunking | Implemented |
| Dense embeddings with fallback | Implemented |
| Sparse (BM42) vectors at ingestion | Implemented |
| Qdrant search and FlashRank reranking | Implemented |
| LangGraph planner, retriever, responder | Implemented |
| Streamlit UI | Implemented |
| Logfire observability | Implemented |
| Cloud Run CI/CD | Implemented |
| **Hybrid search (dense + sparse fusion at query time)** | **Planned** |
| `--wipe` collection reset for bulk ingestion | Planned |

---

## Notes

- The Qdrant collection stores its vector configuration when created. If it was created before sparse vectors were added, delete and re-create it, then re-ingest documents.
- Keep `.env` and service account keys out of version control.
