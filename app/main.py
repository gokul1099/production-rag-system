import logfire
import os
from dotenv import load_dotenv
from pathlib import Path
import tempfile
load_dotenv()
logfire_token = os.getenv("LOGFIRE_TOKEN")
if logfire_token:
    logfire.configure(token=logfire_token, scrubbing=False)
import asyncio
from fastapi import FastAPI, Response, UploadFile, File, Form, HTTPException, Request
from app.agents.graph import rag_agent
from app.models import QueryRequest, UploadRequest
from app.auth import router as auth_router
from app.ingestion.processor import process_gcs_file
from app.services.gcp.gcs_utils import gcs_service
import base64
import json


app = FastAPI(title="Enterprise Agentic RAG API")

# Authentication routes (signup/signin)
app.include_router(auth_router, prefix="/auth")

@app.get("/")
def home():
    return {"message": "Enterprise langrapg RAG api is live"}

@app.get("/graph")
def get_graph_images():
    """
    Return the mermaid image of the agent's workflow
    """

    try:
        png_bytes = rag_agent.get_graph().draw_mermaid_png()
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        return {"error": f"Could not generate graph image: {e}"}

@app.post("/pubsub/ingest")
async def handle_pubsub_ingest(request: Request):
    """
    HTTP push endpoint triggered automatically by google pub/sub event
    triggered when OBJECT_FINALIZE upload event is triggered
    """
    file_name = "unknown"
    try:
        logfire.info("🔵 [PUBSUB] Endpoint called - Starting pub/sub ingestion handler")

        body = await request.json()
        logfire.info(f"🔵 [PUBSUB] Request body received: {body}")
        message = body.get("message", {})

        if not message or "data" not in message:
            logfire.error("🔴 [PUBSUB] Invalid pub/sub payload: missing message.data")
            raise HTTPException(status_code=400, detail="Invalid pub/sub payload: missing message.data")

        decoded_bytes = base64.b64decode(message["data"])
        event_info = json.loads(decoded_bytes.decode("utf-8"))
        bucket_name = event_info.get("bucket")
        file_name = event_info.get("name")

        logfire.info(f"🔵 [PUBSUB] Event parsed - Bucket: {bucket_name}, File: {file_name}")

        if not file_name or file_name.endswith("/"):
            logfire.info(f"⚠️ [PUBSUB] Skipping directory object: {file_name}")
            return {"status": "ignored", "reason": "Directory object"}

        parts = file_name.split("/")
        source_type = parts[0] if len(parts) > 1 else "upload"
        logfire.info(f"🔵 [PUBSUB] Source type detected: {source_type}")

        logfire.info(f"🔵 [PUBSUB] Starting file ingestion for: {file_name}")
        ingestion_success = await asyncio.to_thread(process_gcs_file, file_name, source_type)
        logfire.info(f"🔵 [PUBSUB] File ingestion completed. Success: {ingestion_success}")

        if not ingestion_success:
            logfire.error(f"🔴 [PUBSUB] Ingestion failed for file: {file_name}")
            raise HTTPException(status_code=500, detail=f"Failed to ingest file from GCS due to: {file_name}")

        logfire.info(f"✅ [PUBSUB] Successfully ingested file: {file_name}")
        return {
            "status": "success",
            "file_name": file_name
        }
    except HTTPException as he:
        logfire.error(f"🔴 [PUBSUB] HTTPException for file {file_name}: {he.detail}")
        raise he
    except Exception as e:
        logfire.error(f"🔴 [PUBSUB] Unexpected error processing file {file_name}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload")
async def upload_files(file: UploadFile = File(...), session_id: str = Form(...)):
    support_extensions = [".pdf", ".docx", ".ppt", ".txt"]
    file_name = Path(file.filename or "").name
    extension = Path(file_name).suffix.lower()

    logfire.info(f"🔵 [UPLOAD] Upload request received - File: {file_name}, Session: {session_id}")

    if not file_name or extension not in support_extensions:
        logfire.error(f"🔴 [UPLOAD] Invalid file extension for {file_name}. Extension: {extension}, Supported: {support_extensions}")
        raise HTTPException(status_code=422, detail="File extension does not found in supported formates")

    if not session_id.strip():
        logfire.error("[UPLOAD] Invalid session_id provided")
        raise HTTPException(status_code=422, detail="Session id not found")

    try:
        file_bytes = await file.read()
        logfire.info(f"🔵 [UPLOAD] File read successfully - File: {file_name}, Size: {len(file_bytes)} bytes")

        destination_path = f"uploads/{file_name}"
        logfire.info(f"🔵 [UPLOAD] Starting GCS upload to {destination_path}")

        gcs_uri = await asyncio.to_thread(
            gcs_service.upload_file,
            source=file_bytes,
            destination_blob_name=destination_path,
            content_type=file.content_type
        )
        logfire.info(f"✅ [UPLOAD] File uploaded successfully to GCS: {gcs_uri}")

        return {
            "filename": file_name,
            "session_id": session_id.strip(),
            "gcs_uri": gcs_uri,
            "status": "uploaded_to_gcs"
        }
    except Exception as e:
        logfire.error(f"🔴 [UPLOAD] Failed to upload file {file_name}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@app.post("/query")
def query(request: QueryRequest):
     """
     Excute the Langraph RAG flow with memory using a POST request
     """
     q = request.q
     thread_id = request.thread_id

     initial_state = {
         "messages": [{"role": "user", "content": q}],
         "current_query": q,
         "documents": [],
         "plan":["start"],
         "status":"Initializing Graph ..."
     }

     config = {"configurable": {"thread_id": thread_id}}
     try:
         final_output = rag_agent.invoke(initial_state, config=config)

         return {
             "question": q,
             "answer": final_output.get("final_answer"),
             "thought_process": final_output.get("plan"),
             "status": final_output.get("status"),
             "sources": final_output.get("documents", [])
         }
     except Exception as e:
        logfire.error(f"❌ Backend execution failed: {e}")
        return {
            "question": q,
            "answer": "I apologize, but I encountered an internal error while procession your request",
            "thought_process": ["Error encountered during execution"],
            "status": "error",
            "sources": []
        }

    