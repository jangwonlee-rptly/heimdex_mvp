from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.ingest.asset_id import derive_local_asset_identity
from app.ingest.ffprobe_parser import SourceContext, parse_ffprobe_json
from app.ingest.sidecar_schema import SchemaPath, Sidecar, export_schema
from app.ingest.thumbnails import render_thumbnails

MEDIA = Path("tests/fixtures/media")


def _run_ffprobe(target: Path) -> dict:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-print_format",
        "json",
        str(target),
    ]
    proc = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return json.loads(proc.stdout)


def _birthtime(stat_result) -> datetime | None:
    birth = getattr(stat_result, "st_birthtime", None)
    if birth is not None:
        return datetime.fromtimestamp(birth, tz=timezone.utc)
    return None


def _sidecar_for_media(media_path: Path) -> dict:
    identity = derive_local_asset_identity(media_path, max_bytes_for_strong_hash=None)
    stat = media_path.stat()
    ctx = SourceContext(
        type="local",
        uri=media_path.resolve().as_uri(),
        filename=media_path.name,
        size_bytes=stat.st_size,
        asset_id=identity.asset_id,
        created_time=_birthtime(stat),
        modified_time=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        hash=identity.hash,
        hash_quality=identity.hash_quality,
    )
    raw = _run_ffprobe(media_path)
    return parse_ffprobe_json(raw, ctx)


def test_export_schema_matches_model(tmp_path: Path):
    destination = tmp_path / SchemaPath.name
    path = export_schema(destination)
    assert path.exists()

    written = json.loads(path.read_text())
    expected = Sidecar.model_json_schema()
    assert written == expected


def test_sidecar_round_trip_validates(tmp_path: Path):
    media_path = MEDIA / "tiny_h264_aac.mp4"
    sidecar = _sidecar_for_media(media_path)
    enriched = render_thumbnails(str(media_path), sidecar, tmp_path)
    # Should not raise
    Sidecar.model_validate(enriched)
