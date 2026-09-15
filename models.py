from pydantic import BaseModel
from typing import Optional

class QueryRequest(BaseModel):
    q: str
    thread_id: Optional[str] = "default_user"

class UploadRequest(BaseModel):
    session_id: str