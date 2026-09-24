import logfire
import os
from dotenv import load_dotenv
from pathlib import Path
import tempfile
load_dotenv()
logfire.configure(token=os.getenv("LOGFIRE_TOKEN"), scrubbing=False)

from fastapi import FastAPI, Response, UploadFile, File, Form, HTTPException
from app.agents.graph import rag_agent
from app.models import QueryRequest, UploadRequest
from app.ingestion.processor import process_file
from app.auth import router as auth_router

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

@app.post("/upload")
async def upload_files(file: UploadFile = File(...), session_id: str = Form(...)):
    support_extensions = [".pdf",".docx", ".ppt", ".txt"]
    file_name = Path(file.filename or "").name
    extension = Path(file_name).suffix.lower()
    print(file_name)
    if not file_name or extension not in  support_extensions:
        raise HTTPException(status_code=422, detail="File extension does not found in supported formates")

    if not session_id.strip():
        raise HTTPException(status_code=422, detail="Session id not found")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete= False) as temporary_file:
            temporary_path = temporary_file.name
            while chunk := await file.read(1024 * 1024):
                temporary_file.write(chunk)
        indexed = process_file(temporary_path, file_name, "upload")
        if not indexed:
            raise HTTPException(status_code=422, detail="The document could not be parsed or indexed") 

        return {
            "filename": file_name,
            "session_id": session_id.strip(),
            "status": "indexed"
        }       
    finally:
        await file.close()
        if temporary_path:
            os.unlink(temporary_path)


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

    