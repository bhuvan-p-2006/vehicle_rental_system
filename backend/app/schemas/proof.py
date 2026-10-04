from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

# R4 accepted artifacts (SPEC 3.4).
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "application/pdf")
MAX_PROOF_BYTES = 5 * 1024 * 1024

ProofKind = Literal["aadhaar", "licence"]


class UploadUrlRequest(BaseModel):
    """Mint a presigned PUT so the browser can upload a proof directly to MinIO.

    ``draft_id`` namespaces the object key before the rental row exists; the client
    echoes the returned ``object_key`` back in ``POST /rentals``.
    """

    model_config = {"extra": "forbid"}

    kind: ProofKind
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., pattern="|".join(ALLOWED_CONTENT_TYPES))
    size: int = Field(..., gt=0, le=MAX_PROOF_BYTES)
    draft_id: uuid.UUID


class UploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str
    expires_in_seconds: int
