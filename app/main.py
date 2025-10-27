from __future__ import annotations

import json
import os
import subprocess
import tempfile
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile

from app.api.v1 import get_api_router
from app.core.config import get_settings
from app.core.db import create_engine, create_session_factory
from app.core.logging import configure_logging, get_logger
from app.core.storage import get_storage

from . import schemas

legacy_logger = get_logger(component="legacy_metadata")
legacy_router = APIRouter()


def _parse_frame_rate(raw: Optional[str]) -> Optional[float]:
    """Convert ffprobe's fractional frame rate string (e.g. '30000/1001') into a float."""
    if not raw or raw in {"0/0", "N/A"}:
        return None
    try:
        numerator, denominator = raw.split("/")
        num = float(numerator)
        den = float(denominator)
        if den == 0:
            return None
        return round(num / den, 3)
    except (ValueError, ZeroDivisionError):
        return None


def _bitrate_to_kbps(value: Optional[str]) -> Optional[float]:
    """Convert bit rate reported in bits/second to kilobits/second."""
    if not value or value == "N/A":
        return None
    try:
        return round(int(value) / 1000.0, 2)
    except ValueError:
        return None


def _build_response(data: Dict[str, Any], filename: str) -> schemas.MetadataResponse:
    """Transform raw ffprobe JSON into the response schema."""
    format_info: Dict[str, Any] = data.get("format", {})
    stream_payload = []
    for stream in data.get("streams", []):
        stream_payload.append(
            schemas.StreamMetadata(
                index=stream.get("index", 0),
                codec_type=stream.get("codec_type", "unknown"),
                codec_name=stream.get("codec_name"),
                width=stream.get("width"),
                height=stream.get("height"),
                bitrate_kbps=_bitrate_to_kbps(stream.get("bit_rate")),
                frame_rate=_parse_frame_rate(stream.get("avg_frame_rate")),
            )
        )

    duration_raw = format_info.get("duration")
    duration = float(duration_raw) if duration_raw and duration_raw != "N/A" else None

    return schemas.MetadataResponse(
        filename=filename,
        format_name=format_info.get("format_long_name") or format_info.get("format_name"),
        duration_seconds=duration,
        bitrate_kbps=_bitrate_to_kbps(format_info.get("bit_rate")),
        size_bytes=int(format_info["size"]) if format_info.get("size") else None,
        streams=stream_payload,
    )


def _run_ffprobe(target: Path) -> Dict[str, Any]:
    """Execute ffprobe and return parsed JSON metadata for the supplied file."""
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
    legacy_logger.info("legacy_ffprobe_run", command=command)

    proc = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(proc.stdout)


@legacy_router.get("/health", response_model=schemas.HealthResponse)
def legacy_health_check() -> schemas.HealthResponse:
    """Simple liveness probe kept for backwards compatibility when legacy routes are enabled."""
    return schemas.HealthResponse()


@legacy_router.post("/metadata", response_model=schemas.MetadataResponse)
async def extract_metadata(file: UploadFile = File(...)) -> schemas.MetadataResponse:
    """Accept a video upload, persist it temporarily, run ffprobe, and return structured metadata."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must include a filename.")

    suffix = Path(file.filename).suffix or ".bin"
    tmp_path: Optional[Path] = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            legacy_logger.info("legacy_metadata_tempfile_created", path=str(tmp_path))

            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)

        await file.close()

        try:
            metadata = _run_ffprobe(tmp_path)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr
            legacy_logger.error("legacy_ffprobe_failed", stderr=stderr)
            raise HTTPException(status_code=422, detail=f"ffprobe failed: {stderr.strip()}") from exc

        response = _build_response(metadata, file.filename)
        legacy_logger.info("legacy_metadata_extracted", filename=file.filename)
        return response
    finally:
        if tmp_path and tmp_path.exists():
            try:
                os.remove(tmp_path)
                legacy_logger.info("legacy_metadata_tempfile_removed", path=str(tmp_path))
            except OSError as cleanup_error:
                legacy_logger.warning(
                    "legacy_metadata_tempfile_cleanup_failed",
                    path=str(tmp_path),
                    error=str(cleanup_error),
                )


def create_app() -> FastAPI:
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    configure_logging(level=log_level)
    storage = get_storage(settings)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.storage = storage
        app.state.engine = engine
        app.state.session_factory = session_factory
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
    )

    app.include_router(get_api_router())
    if settings.enable_legacy:
        app.include_router(legacy_router)
    return app


app = create_app()


__all__ = ["app", "create_app"]
