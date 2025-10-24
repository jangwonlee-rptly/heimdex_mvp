from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.ingest.asset_id import HashInfo, derive_local_asset_identity
from app.ingest.ffprobe_parser import SourceContext, parse_ffprobe_json

FIXTURES = Path("tests/fixtures/ffprobe_json")
MEDIA = Path("tests/fixtures/media")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_parse_mp4_with_audio():
    raw = _load_fixture("mp4_h264_aac.json")
    media_path = MEDIA / "tiny_h264_aac.mp4"
    identity = derive_local_asset_identity(media_path, max_bytes_for_strong_hash=None)
    stat = media_path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    ctx = SourceContext(
        type="local",
        uri=media_path.resolve().as_uri(),
        filename=media_path.name,
        size_bytes=stat.st_size,
        asset_id=identity.asset_id,
        created_time=None,
        modified_time=modified,
        hash=identity.hash,
        hash_quality=identity.hash_quality,
    )

    sidecar = parse_ffprobe_json(raw, ctx)

    assert sidecar["schema_version"] == "0.1.0"
    assert sidecar["format"]["duration_s"] == pytest.approx(2.0)
    assert sidecar["video"]["frame_rate_fps"] == pytest.approx(30.0)
    assert sidecar["audio"]["channels"] == 1
    assert sidecar["thumbnails"]["samples"] == []
    assert sidecar["warnings"] == []
    assert sidecar["source"]["created_time"] == _iso(modified)
    assert sidecar["source"]["hash"]["algo"] == "sha256"


def test_parse_mp4_without_audio():
    raw = _load_fixture("mp4_h264_no_audio.json")
    media_path = MEDIA / "tiny_noaudio.mp4"
    identity = derive_local_asset_identity(media_path, max_bytes_for_strong_hash=None)
    stat = media_path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    ctx = SourceContext(
        type="local",
        uri=media_path.resolve().as_uri(),
        filename=media_path.name,
        size_bytes=stat.st_size,
        asset_id=identity.asset_id,
        created_time=None,
        modified_time=modified,
        hash=identity.hash,
        hash_quality=identity.hash_quality,
    )

    sidecar = parse_ffprobe_json(raw, ctx)

    assert sidecar["audio"] is None
    assert "no_audio_stream" in sidecar["warnings"]
    assert sidecar["thumbnails"]["samples"] == []
    assert sidecar["video"]["frame_rate_fps"] == pytest.approx(30.0)


def test_parse_mkv_vfr_uses_r_frame_rate_and_tags():
    raw = _load_fixture("mkv_vfr.json")
    modified = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    ctx = SourceContext(
        type="local",
        uri="file:///sample.mkv",
        filename="sample.mkv",
        size_bytes=2048,
        asset_id="sha256:test",
        created_time=None,
        modified_time=modified,
        hash=HashInfo(algo="weak", value="deadbeef"),
        hash_quality="weak",
    )

    sidecar = parse_ffprobe_json(raw, ctx)

    assert sidecar["format"]["duration_s"] == 0.0
    assert "duration_unavailable" in sidecar["warnings"]
    assert sidecar["video"]["frame_rate_fps"] == pytest.approx(29.97, rel=0.001)
    assert sidecar["source"]["created_time"] == "2023-10-04T09:03:02Z"
    assert sidecar["thumbnails"]["poster"]["timestamp_s"] == 0.0


def test_parse_weird_tags_prioritises_quicktime_creation_date():
    raw = _load_fixture("weird_tags.json")
    modified = datetime(2024, 2, 2, 2, 2, tzinfo=timezone.utc)

    ctx = SourceContext(
        type="local",
        uri="file:///sample.mov",
        filename="sample.mov",
        size_bytes=5120000,
        asset_id="sha256:abc123",
        created_time=None,
        modified_time=modified,
        hash=HashInfo(algo="sha256", value="abc123"),
        hash_quality="strong",
    )

    sidecar = parse_ffprobe_json(raw, ctx)

    assert sidecar["source"]["created_time"] == "2020-05-01T17:34:56Z"
    assert sidecar["video"]["pixel_aspect_ratio"] == 1.0
    assert sidecar["video"]["color_space"] == "bt709"
    assert sidecar["audio"]["channels"] == 6
    assert sidecar["audio"]["bitrate_kbps"] == 4608
    assert sidecar["format"]["bitrate_kbps"] == 1000
    assert sidecar["thumbnails"]["poster"]["timestamp_s"] == pytest.approx(2.5)
