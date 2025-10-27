"""Domain entities and ingest utilities reused by the API."""

# Re-export legacy ingest helpers for compatibility and clarity.
from app.ingest.asset_id import AssetIdentity, HashInfo, derive_local_asset_identity
from app.ingest.ffprobe_parser import SourceContext, parse_ffprobe_json
from app.ingest.sidecar_schema import SchemaPath, Sidecar, export_schema
from app.ingest.thumbnails import render_thumbnails

__all__ = [
    "AssetIdentity",
    "HashInfo",
    "SourceContext",
    "parse_ffprobe_json",
    "SchemaPath",
    "Sidecar",
    "export_schema",
    "render_thumbnails",
    "derive_local_asset_identity",
]

