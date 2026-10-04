from __future__ import annotations

import uuid
from datetime import timedelta
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from app.config import get_settings

# Presigned URLs are deliberately short-lived (SPEC 3.4): they grant direct access
# to PII, so they expire quickly and are only minted after an authorization check.
PRESIGN_EXPIRY_SECONDS = 15 * 60


class StorageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@lru_cache(maxsize=1)
def get_storage() -> StorageService:
    return StorageService()


class StorageService:
    """Thin S3 wrapper. The database only ever stores object keys.

    Two clients are kept: one for the backend's own API calls (internal endpoint)
    and one used only for presigning (browser-reachable endpoint). They differ
    inside container networks where `storage:9000` does not resolve client-side.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.MINIO_BUCKET
        self.client = self._make_client(settings.MINIO_ENDPOINT, settings.MINIO_SECURE)

        public_endpoint = settings.MINIO_PUBLIC_ENDPOINT or settings.MINIO_ENDPOINT
        if public_endpoint != settings.MINIO_ENDPOINT:
            self._presign_client = self._make_client(public_endpoint, settings.MINIO_SECURE)
        else:
            self._presign_client = self.client

        self.ensure_bucket()

    def _make_client(self, endpoint: str, secure: bool) -> Minio:
        settings = get_settings()
        return Minio(
            endpoint,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=secure,
            region=settings.MINIO_REGION,
        )

    def ensure_bucket(self) -> None:
        """Create the private bucket on boot if it does not exist yet."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error as exc:  # pragma: no cover - infrastructure failure path
            raise StorageError("STORAGE_UNAVAILABLE", f"Object storage error: {exc}") from exc

    @staticmethod
    def build_object_key(draft_id: uuid.UUID, kind: str, filename: str) -> str:
        suffix = ""
        if "." in filename:
            suffix = "." + filename.rsplit(".", 1)[-1].lower()[:10]
        # Namespace under the draft id; the client echoes this key back on submit.
        return f"rentals/{draft_id}/{kind}{suffix}"

    def presigned_put(self, object_key: str) -> str:
        try:
            return self._presign_client.presigned_put_object(
                self.bucket,
                object_key,
                expires=timedelta(seconds=PRESIGN_EXPIRY_SECONDS),
            )
        except S3Error as exc:
            raise StorageError("STORAGE_UNAVAILABLE", f"Could not sign upload: {exc}") from exc

    def presigned_get(self, object_key: str) -> str:
        try:
            return self._presign_client.presigned_get_object(
                self.bucket,
                object_key,
                expires=timedelta(seconds=PRESIGN_EXPIRY_SECONDS),
            )
        except S3Error as exc:
            raise StorageError("STORAGE_UNAVAILABLE", f"Could not sign download: {exc}") from exc

    def object_exists(self, object_key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, object_key)
            return True
        except S3Error:
            return False
