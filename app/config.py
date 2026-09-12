import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GEMINI_API_KEYS = os.getenv("GOOGLE_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_CLUSTER_ENDPOINT = os.getenv("QDRANT_CLUSTER_ENDPOINT")
    QDRANT_COLLECTION = "enterprise_rag"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    NVIDIA_API_KEY= os.getenv("NVIDIA_API_KEY")
    NVIDIA_EMBEDDING_MODEL= "nvidia/nemotron-3-embed-1b"
    # Use a Groq model that is commonly available on Groq; override with GROQ_MODEL in .env if needed.
    GROQ_MODEL = "qwen/qwen3.8-27b"

setting = Settings()

