from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import AnyUrl, BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Health status indicator.")
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EnvCheckResponse(BaseModel):
    ffmpeg: bool
    ffprobe: bool
    pyscenedetect: bool


class IngestInitRequest(BaseModel):
    org_id: str = Field(..., json_schema_extra={"example": "org-demo01"})
    source_name: str = Field(..., json_schema_extra={"example": "clip.mov"})
    content_length: int = Field(..., ge=0, json_schema_extra={"example": 1717986918})
    content_type: Optional[str] = Field(default=None, json_schema_extra={"example": "video/quicktime"})


class PresignedPayload(BaseModel):
    asset_uri: AnyUrl
    metadata_uri: Optional[AnyUrl] = None


class IngestInitResponse(BaseModel):
    upload_id: str = Field(..., json_schema_extra={"example": "1f2d3c4b5a"})
    presigned: PresignedPayload


class IngestCommitRequest(BaseModel):
    org_id: str
    upload_id: str
    source_uri: AnyUrl | str
    weak_threshold_bytes: Optional[int] = Field(default=1_000_000_000, ge=0)


class IngestCommitResponse(BaseModel):
    asset_id: str
    source_uri: str
    status: str = Field(description="queued | ready")


class ProbeRequest(BaseModel):
    org_id: str
    source_uri: AnyUrl | str
    weak_threshold_bytes: Optional[int] = Field(default=1_000_000_000, ge=0)


class SidecarModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ThumbnailPolicy(BaseModel):
    interval_s: Optional[float] = Field(default=None, ge=0)
    max_count: Optional[int] = Field(default=None, ge=1, le=50)
    max_height: Optional[int] = Field(default=None, ge=64)


class ThumbnailJobRequest(BaseModel):
    org_id: str
    source_uri: AnyUrl | str
    policy: Optional[ThumbnailPolicy] = None
    weak_threshold_bytes: Optional[int] = Field(default=None, ge=0)


class SidecarJobRequest(BaseModel):
    org_id: str
    source_uri: AnyUrl | str
    weak_threshold_bytes: Optional[int] = Field(default=None, ge=0)


class JobAcceptedResponse(BaseModel):
    job_id: str
    location: str


class AssetSidecarPointer(BaseModel):
    schema_version: Optional[str]
    storage_key: Optional[str]
    etag: Optional[str]


class AssetThumbnailPointer(BaseModel):
    idx: int
    storage_key: str
    width: Optional[int]
    height: Optional[int]
    ts_ms: Optional[int]


class AssetResponse(BaseModel):
    asset_id: str
    org_id: str
    source_uri: str
    size_bytes: Optional[int]
    hash: Optional[str]
    hash_quality: Optional[str]
    status: str
    sidecar: AssetSidecarPointer
    thumbnails: List[AssetThumbnailPointer]


class JobResultSidecar(BaseModel):
    sidecar_uri: Optional[str]
    thumbnails: Optional[List[Dict[str, Any]]]


class JobError(BaseModel):
    code: Optional[str] = None
    message: str


class JobResponse(BaseModel):
    job_id: str
    type: str
    asset_id: Optional[str]
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    result: Optional[JobResultSidecar]
    error: Optional[JobError]


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[Any] = None


__all__ = [
    "HealthResponse",
    "EnvCheckResponse",
    "IngestInitRequest",
    "IngestInitResponse",
    "IngestCommitRequest",
    "IngestCommitResponse",
    "ProbeRequest",
    "SidecarModel",
    "ThumbnailJobRequest",
    "SidecarJobRequest",
    "JobAcceptedResponse",
    "AssetResponse",
    "JobResponse",
    "ErrorResponse",
]
