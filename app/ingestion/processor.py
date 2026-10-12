import os
import sys
import uuid
import json
import logfire
from pathlib import Path
from app.services.retrieval.qdrant_service import client as qdrant_client, ensure_collection_exists
from qdrant_client.http import models
import tempfile
from app.config import setting
from app.services.retrieval.embedding import _embed_texts, get_embedding_dim
from app.ingestion.loaders.pdf import parse_pdf
from app.ingestion.loaders.text import parse_text
from app.ingestion.loaders.html import parse_html
from app.ingestion.loaders.office import parse_office
from app.ingestion.chunking.splitter import chunk_text
from app.services.gcp.gcs_utils import gcs_service
from app.services.retrieval.sparse_embedding import compute_sparse_vectors

logfire.configure(service_name="enterprice-ingestion-service")

clean_args = sys.argv[1:]

PROCESSED_DATA_DIR = "processed_data"


def save_processed_locally(data: dict, source_type: str, filename: str) -> str:
    """Save parsed chunk metadata as JSON in processed_data/<source_type>/"""
    folder = os.path.join(PROCESSED_DATA_DIR, source_type)
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder,f"{filename}.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data,f, ensure_ascii=False, indent=2)
    return dest

def process_file(file_path: str, filename: str, source_type: str):
    """Process every file in a directory"""
    with logfire.span("Processing file", file=filename, source=source_type):
        try:
            ext = filename.lower().rsplit(".", 1)[-1]
            logfire.info(f"🔵 [FILE_PROCESS] File extension detected: .{ext}")

            if ext == "pdf":
                logfire.info(f"🔵 [FILE_PROCESS] Parsing PDF file: {filename}")
                full_text = parse_pdf(file_path)
            elif ext in ('html', 'htm'):
                logfire.info(f"🔵 [FILE_PROCESS] Parsing HTML file: {filename}")
                full_text = parse_html(file_path)
            elif ext == "txt":
                logfire.info(f"🔵 [FILE_PROCESS] Parsing text file: {filename}")
                full_text = parse_text(file_path)
            elif ext in ("docx", "pptx"):
                logfire.info(f"🔵 [FILE_PROCESS] Parsing Office document: {filename}")
                full_text = parse_office(file_path)
            else:
                logfire.warning(f"⚠️ [FILE_PROCESS] Skipping unsupported file type: {filename} (.{ext})")
                return False

            if not full_text or not full_text.strip():
                logfire.warning(f"⚠️ [FILE_PROCESS] No text extracted from {filename} - skipping")
                return False

            logfire.info(f"🔵 [FILE_PROCESS] Extracted text length: {len(full_text)} characters from {filename}")
            chunks = chunk_text(full_text)
            logfire.info(f"🔵 [FILE_PROCESS] Text chunked into {len(chunks)} chunks")

            if not chunks:
                logfire.warning(f"⚠️ [FILE_PROCESS] No chunks generated from {filename}")
                return False

            processed_data = {
                "filename": filename,
                "source_type": source_type,
                "chunks": chunks
            }

            local_path = save_processed_locally(processed_data, source_type, filename)
            logfire.info(f"🔵 [FILE_PROCESS] Saved processed data -> {local_path}")

            with logfire.span("Vectorizing & Indexing"):
                logfire.info(f"🔵 [FILE_PROCESS] Ensuring Qdrant collection exists: {setting.QDRANT_COLLECTION}")
                ensure_collection_exists(setting.QDRANT_COLLECTION)

                logfire.info(f"🔵 [FILE_PROCESS] Generating embeddings for {len(chunks)} chunks")
                embeddings = _embed_texts(chunks)
                logfire.info(f"🔵 [FILE_PROCESS] Generated {len(embeddings)} embeddings")

                logfire.info(f"🔵 [FILE_PROCESS] Generating sparse vectors for BM25")
                sparse_vectors = compute_sparse_vectors(chunks)
                logfire.info(f"🔵 [FILE_PROCESS] Generated {len(sparse_vectors)} sparse vectors")
            
                points = [
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        sparse_vector=sparse_vec,
                        payload={
                            "text": chunk,
                            "source": filename,
                            "source_type": source_type,
                        },
                    )
                    for chunk, vector, sparse_vec in zip(chunks, embeddings, sparse_vectors)
                ]

                logfire.info(f"🔵 [FILE_PROCESS] Upserting {len(points)} points to Qdrant")
                qdrant_client.upsert(
                    collection_name=setting.QDRANT_COLLECTION,
                    points=points
                )
                logfire.info(f"✅ [FILE_PROCESS] Successfully indexed {len(points)} points to Qdrant from {filename}")
            return True

        except Exception as e:
            logfire.error(f"🔴 [FILE_PROCESS] Error during processing file {file_path}: {type(e).__name__}: {str(e)}", exc_info=True)
            return False

def process_gcs_file(blob_name: str, source_type: str = "upload"):
    with logfire.span(f"Processing uploaded file from GCS for ingestion: {blob_name} - {source_type}"):
        filename = Path(blob_name).name
        ext = Path(filename).suffix.lower()
        try:
            logfire.info(f"🔵 [GCS_INGEST] Downloading file from GCS: {blob_name}")
            file_bytes = gcs_service.download_file_bytes(blob_name)
            logfire.info(f"🔵 [GCS_INGEST] Downloaded {len(file_bytes)} bytes from GCS")

            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_blob_bytes:
                temp_blob_bytes.write(file_bytes)
                temp_blob_bytes.flush()
                temp_blob_path = temp_blob_bytes.name

            logfire.info(f"🔵 [GCS_INGEST] Created temp file at {temp_blob_path}")
            try:
                logfire.info(f"🔵 [GCS_INGEST] Starting file processing for {filename}")
                processed = process_file(temp_blob_path, filename, source_type)
                logfire.info(f"✅ [GCS_INGEST] File processing completed. Result: {processed}")
                return processed
            finally:
                if os.path.exists(temp_blob_path):
                    os.unlink(temp_blob_path)
                    logfire.info(f"🔵 [GCS_INGEST] Cleaned up temp file: {temp_blob_path}")
        except Exception as e:
            logfire.error(f"🔴 [GCS_INGEST] process_gcs_file failed for {blob_name}: {type(e).__name__}: {str(e)}", exc_info=True)
            return False


def process_directory(dir_path: str, source_type: str):
    """Process every file in a directory"""
    with logfire.span("Scanning directory", path=dir_path, source=source_type):
        files = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]
        logfire.info(f"Found {len(files)} files in {dir_path}")
        for filename in files:
            process_file(os.path.join(dir_path, filename), filename, source_type)

def run_universal_ingestion(base_dir: str, explicit_source_type: str= None, wipe=bool):
    """
    Scan base dir, map sub-folders to source types, and ingest all documents.
    pass -wipe to drop and recreate the Qdrant collection before ingestion
    """
    with logfire.span("Universal ingestion started", base_directory=base_dir):
        if not qdrant_client.collection_exists(setting.QDRANT_COLLECTION):
            dim = get_embedding_dim()
            qdrant_client.create_collection(
                collection_name=setting.QDRANT_COLLECTION,
                vectors_config=models.VectorParams(
                    size=dim,
                    distance=models.Distance.COSINE
                ),
            )
            logfire.info(
                f"Created collection `{setting.QDRANT_COLLECTION}"
                f"({dim}-dim, Cosine)"
            )

        subdirs = [
            d for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))
        ]

        if not subdirs:
            if explicit_source_type:
                source_type=explicit_source_type
            else:
                base_name= os.path.basename(os.path.normpath(base_dir)).lower()
                source_type = (
                    "true" if "true" in base_name
                    else "noisy" if "noisy" in base_name
                    else "general"
                )
            logfire.info(f"No sub-folders found - processing {base_dir} as {source_type}")
            process_directory(base_dir, source_type)
        else:
            for subdir in subdirs:
                source_type = (
                    "true" if "true" in subdir.lower()
                    else "noisy" if "noisy" in subdir.lower()
                    else "general"
                )
                process_directory(subdir, source_type)


if __name__ == "__main__":
    wipe_requested = "--wipe" in sys.argv
    clean_args = [a for a in sys.argv if a!="--wipe"]
    target_dir = clean_args[1] if len(clean_args) > 1 else "DATA"
    explicit_type = clean_args[2] if len(clean_args) >2 else None

    if not os.path.exists(target_dir):
        print(f"Error: path `{target_dir}` does not exist")
        sys.exit(1)
    run_universal_ingestion(target_dir, explicit_source_type=explicit_type, wipe=wipe_requested)