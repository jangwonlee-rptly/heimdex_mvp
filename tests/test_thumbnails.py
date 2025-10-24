from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.ingest.asset_id import derive_local_asset_identity
from app.ingest.ffprobe_parser import SourceContext, parse_ffprobe_json
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


def test_render_thumbnails_poster_only(tmp_path: Path):
    media_path = MEDIA / "tiny_h264_aac.mp4"
    sidecar = _sidecar_for_media(media_path)

    updated = render_thumbnails(str(media_path), sidecar, tmp_path)

    poster = updated["thumbnails"]["poster"]
    assert poster["path"].startswith("thumbs/")
    poster_path = tmp_path / poster["path"]
    assert poster_path.exists()
    assert poster["width_px"] == 320
    assert poster["height_px"] > 0
    assert updated["thumbnails"]["samples"] == []


def test_render_thumbnails_with_samples(tmp_path: Path):
    media_path = MEDIA / "long_h264_aac.mp4"
    sidecar = _sidecar_for_media(media_path)

    updated = render_thumbnails(str(media_path), sidecar, tmp_path)

    samples = updated["thumbnails"]["samples"]
    assert len(samples) == 2
    for sample in samples:
        sample_path = tmp_path / sample["path"]
        assert sample_path.exists()
        assert sample["width_px"] == 320
        assert sample["height_px"] > 0
        timestamp = sample["timestamp_s"]
        expected_name = f"t{int(round(timestamp * 100)):04d}.jpg"
        assert sample_path.name == expected_name
