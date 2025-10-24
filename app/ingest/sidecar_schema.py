from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import SCHEMA_VERSION

SchemaPath = Path("derived/schema/vna_sidecar_v0.1.0.json")


class HashModel(BaseModel):
    """Schema for hash information."""

    model_config = ConfigDict(extra="forbid")

    algo: Literal["sha256", "md5", "weak"]
    value: str


class SourceModel(BaseModel):
    """Schema for source information."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["local", "gdrive"]
    uri: str
    filename: str
    size_bytes: Optional[int]
    created_time: str
    modified_time: Optional[str]
    hash: Optional[HashModel]


class FormatModel(BaseModel):
    """Schema for format information."""

    model_config = ConfigDict(extra="forbid")

    container: str
    duration_s: float
    bitrate_kbps: Optional[int]
    tags: Dict[str, str]


class VideoModel(BaseModel):
    """Schema for video information."""

    model_config = ConfigDict(extra="forbid")

    codec: str
    profile: Optional[str]
    width_px: int
    height_px: int
    pixel_aspect_ratio: float
    frame_rate_fps: Optional[float]
    color_space: Optional[str]
    color_transfer: Optional[str]
    color_primaries: Optional[str]


class AudioModel(BaseModel):
    """Schema for audio information."""

    model_config = ConfigDict(extra="forbid")

    codec: str
    channels: int
    sample_rate_hz: int
    bitrate_kbps: Optional[int]


class StreamModel(BaseModel):
    """Schema for stream information."""

    model_config = ConfigDict(extra="forbid")

    index: int
    type: Literal["video", "audio", "data", "subtitle", "other"]
    codec: str
    avg_frame_rate: Optional[str]
    r_frame_rate: Optional[str]
    width_px: Optional[int]
    height_px: Optional[int]
    channels: Optional[int]
    sample_rate_hz: Optional[int]
    bitrate_kbps: Optional[int]
    disposition_default: Optional[bool]
    tags: Optional[Dict[str, str]]


class ThumbnailModel(BaseModel):
    """Schema for a single thumbnail."""

    model_config = ConfigDict(extra="forbid")

    timestamp_s: float
    path: str
    width_px: int
    height_px: int


class ThumbnailsModel(BaseModel):
    """Schema for a set of thumbnails."""

    model_config = ConfigDict(extra="forbid")

    poster: ThumbnailModel
    samples: List[ThumbnailModel]


class ToolsModel(BaseModel):
    """Schema for tool information."""

    model_config = ConfigDict(extra="forbid")

    ffprobe: str
    ffmpeg: str
    parser: str


class SelectionPolicyModel(BaseModel):
    """Schema for the selection policy."""

    model_config = ConfigDict(extra="forbid")

    video: Literal["first_default_or_highest_resolution"]
    audio: Literal["first_default_or_highest_channels"]


class ProvenanceModel(BaseModel):
    """Schema for provenance information."""

    model_config = ConfigDict(extra="forbid")

    ingested_at: str
    tools: ToolsModel
    selection_policy: SelectionPolicyModel
    hash_quality: Optional[Literal["strong", "weak"]]
    source_etag: Optional[str]
    drive_md5: Optional[str]


class Sidecar(BaseModel):
    """The root schema for the sidecar file."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SCHEMA_VERSION] = Field(default=SCHEMA_VERSION)
    asset_id: str
    source: SourceModel
    format: FormatModel
    video: Optional[VideoModel]
    audio: Optional[AudioModel]
    streams: List[StreamModel]
    thumbnails: ThumbnailsModel
    provenance: ProvenanceModel
    warnings: List[str]
    errors: List[str]


def export_schema(output_path: Path = SchemaPath) -> Path:
    """Serialise the current schema to disk.

    Args:
        output_path: The path to write the schema to.

    Returns:
        The path the schema was written to.
    """
    schema = Sidecar.model_json_schema()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True))
    return output_path


__all__ = [
    "Sidecar",
    "export_schema",
    "SchemaPath",
]
