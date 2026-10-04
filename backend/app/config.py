from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of configuration truth (SPEC §13.5).

    Nothing else in the codebase may read os.environ directly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    PROJECT_NAME: str = "Vehicle Rental System"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@db:5432/vehicle_rental"
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    MINIO_ENDPOINT: str = "minio:9000"
    # Browser-reachable endpoint used when minting presigned URLs. Inside Docker
    # the backend talks to `minio:9000`, but that hostname does not resolve for the
    # browser, so presigned URLs must be signed against a public host. SigV4 signs
    # the Host header per request, so signing against the public endpoint is valid.
    # Leave empty to reuse MINIO_ENDPOINT (single-host deployments).
    MINIO_PUBLIC_ENDPOINT: str = ""
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "vehicle-rental"
    MINIO_SECURE: bool = False
    # Setting a region explicitly skips the S3 bucket-location lookup that the
    # client would otherwise perform on every presign request.
    MINIO_REGION: str = "us-east-1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
