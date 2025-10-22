from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Health status indicator.")


class StreamMetadata(BaseModel):
    index: int = Field(..., description="Stream index as reported by ffprobe.")
    codec_type: str = Field(..., description="Stream media type (e.g. video, audio).")
    codec_name: Optional[str] = Field(default=None, description="Codec name reported by ffprobe.")
    width: Optional[int] = Field(default=None, description="Frame width in pixels for video streams.")
    height: Optional[int] = Field(default=None, description="Frame height in pixels for video streams.")
    bitrate_kbps: Optional[float] = Field(
        default=None,
        description="Per-stream bitrate in kilobits per second when available.",
    )
    frame_rate: Optional[float] = Field(
        default=None,
        description="Average frame rate calculated from ffprobe's avg_frame_rate.",
    )


class MetadataResponse(BaseModel):
    filename: str = Field(..., description="Original filename supplied by the client.")
    format_name: Optional[str] = Field(default=None, description="Container format reported by ffprobe.")
    duration_seconds: Optional[float] = Field(default=None, description="Media duration in seconds.")
    bitrate_kbps: Optional[float] = Field(default=None, description="Overall bitrate in kilobits per second.")
    size_bytes: Optional[int] = Field(default=None, description="File size in bytes as reported by ffprobe.")
    streams: List[StreamMetadata] = Field(default_factory=list, description="List of individual stream metadata.")
