import os
from io import BytesIO
from pathlib import Path
import logfire
from google.cloud import storage
from app.config import setting


class GCSService:
    """
    Production-ready Google Cloud Storage service manager.
    Handles file uploads, streaming downloads, and blob operations.
    """

    def __init__(self, bucket_name: str | None = None):
        self._bucket_name = bucket_name
        self._client = None
        self._bucket = None

    @property
    def bucket_name(self) -> str:
        name = self._bucket_name or setting.GCS_BUCKET_NAME or os.getenv("GCS_BUCKET_NAME")
        if not name:
            raise ValueError("GCS_BUCKET_NAME is not configured in settings or environment.")
        return name

    @property
    def client(self) -> storage.Client:
        if self._client is None:
            project_id = setting.GCP_PROJECT_ID or os.getenv("GCP_PROJECT_ID")
            self._client = storage.Client(project=project_id)
        return self._client

    @property
    def bucket(self) -> storage.Bucket:
        if self._bucket is None:
            self._bucket = self.client.bucket(self.bucket_name)
            logfire.info(f"Initialized GCSService for bucket: {self.bucket_name}")
        return self._bucket

    def upload_file(
        self,
        source: str | Path | bytes | BytesIO,
        destination_blob_name: str,
        content_type: str | None = None
    ) -> str:
        """
        Uploads a file, bytes string, or BytesIO stream to GCS.

        :param source: Local file path (str/Path) OR in-memory bytes/BytesIO.
        :param destination_blob_name: Target blob name in GCS (e.g. 'uploads/doc.pdf').
        :param content_type: Optional MIME type string (e.g. 'application/pdf').
        :return: GCS URI string ('gs://bucket/destination_blob_name').
        """
        try:
            blob = self.bucket.blob(destination_blob_name)

            if isinstance(source, (str, Path)):
                file_path = Path(source)
                if not file_path.exists():
                    raise FileNotFoundError(f"Local file not found: {file_path}")
                blob.upload_from_filename(str(file_path), content_type=content_type)
            elif isinstance(source, bytes):
                blob.upload_from_string(source, content_type=content_type)
            elif isinstance(source, BytesIO):
                source.seek(0)
                blob.upload_from_file(source, content_type=content_type)
            else:
                raise ValueError("Unsupported source type for GCS upload.")

            gcs_uri = f"gs://{self.bucket_name}/{destination_blob_name}"
            logfire.info(f"✅ Uploaded {destination_blob_name} to {gcs_uri}")
            return gcs_uri

        except Exception as e:
            logfire.error(f"❌ Failed to upload {destination_blob_name} to GCS: {e}")
            raise e

    def download_file_bytes(self, source_blob_name: str) -> bytes:
        """
        Downloads a blob from GCS as raw bytes.

        :param source_blob_name: Path of blob in GCS.
        :return: Raw byte string content.
        """
        try:
            blob = self.bucket.blob(source_blob_name)
            data = blob.download_as_bytes()
            logfire.info(f"Downloaded {len(data)} bytes from gs://{self.bucket_name}/{source_blob_name}")
            return data
        except Exception as e:
            logfire.error(f"❌ Failed to download {source_blob_name} from GCS: {e}")
            raise e

    def delete_file(self, blob_name: str) -> bool:
        """
        Deletes a blob from the GCS bucket.

        :param blob_name: Target blob path in GCS.
        :return: True if successful, False otherwise.
        """
        try:
            blob = self.bucket.blob(blob_name)
            blob.delete()
            logfire.info(f"Deleted gs://{self.bucket_name}/{blob_name} from GCS")
            return True
        except Exception as e:
            logfire.error(f"❌ Failed to delete {blob_name} from GCS: {e}")
            return False


# Singleton instance for easy import throughout the application
gcs_service = GCSService()

