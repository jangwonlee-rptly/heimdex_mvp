from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

from . import SCHEMA_VERSION
from .asset_id import AssetIdentity, HashInfo

SidecarDict = Dict[str, Any]
StreamType = Literal["video", "audio", "data", "subtitle", "other"]

PARSER_VERSION = "heimdex.ingest/0.1.0"


@dataclass(slots=True)
class SourceContext:
    type: Literal["local", "gdrive"]
    uri: str
    filename: str
    size_bytes: Optional[int]
    asset_id: str
    created_time: Optional[datetime]
    modified_time: Optional[datetime]
    hash: Optional[HashInfo]
    hash_quality: Optional[Literal["strong", "weak"]]
    source_etag: Optional[str] = None
    drive_md5: Optional[str] = None


def parse_ffprobe_json(raw: Dict[str, Any], source_ctx: SourceContext) -> SidecarDict:
    """Normalise ffprobe JSON into the canonical sidecar representation."""
    ingested_at = datetime.now(timezone.utc)
    warnings: List[str] = []
    errors: List[str] = []

    format_info = raw.get("format") or {}
    format_tags = _normalise_tags(format_info.get("tags"))

    duration_s, duration_warning = _parse_duration(format_info.get("duration"))
    if duration_warning:
        warnings.append(duration_warning)

    bitrate_kbps = _parse_bitrate_kbps(format_info.get("bit_rate"))

    streams_payload, video_streams, audio_streams = _parse_streams(raw.get("streams") or [])

    video_summary, video_warning = _summarise_video_stream(video_streams)
    if video_warning:
        warnings.append(video_warning)

    audio_summary, audio_warning = _summarise_audio_stream(audio_streams)
    if audio_warning:
        warnings.append(audio_warning)

    created_time = _determine_created_time(
        source_ctx=source_ctx,
        format_tags=format_tags,
        streams=video_streams + audio_streams,
        default_fallback=ingested_at,
    )
    modified_time_iso = _format_datetime(source_ctx.modified_time) if source_ctx.modified_time else None

    sidecar: SidecarDict = {
        "schema_version": SCHEMA_VERSION,
        "asset_id": source_ctx.asset_id,
        "source": {
            "type": source_ctx.type,
            "uri": source_ctx.uri,
            "filename": source_ctx.filename,
            "size_bytes": source_ctx.size_bytes,
            "created_time": _format_datetime(created_time),
            "modified_time": modified_time_iso,
            "hash": _hash_dict(source_ctx.hash),
        },
        "format": {
            "container": format_info.get("format_name") or format_info.get("format_long_name") or "unknown",
            "duration_s": duration_s,
            "bitrate_kbps": bitrate_kbps,
            "tags": format_tags,
        },
        "video": video_summary,
        "audio": audio_summary,
        "streams": streams_payload,
        "thumbnails": _initial_thumbnail_manifest(duration_s),
        "provenance": {
            "ingested_at": _format_datetime(ingested_at),
            "tools": {
                "ffprobe": _binary_version(("ffprobe", "-version")),
                "ffmpeg": _binary_version(("ffmpeg", "-version")),
                "parser": PARSER_VERSION,
            },
            "selection_policy": {
                "video": "first_default_or_highest_resolution",
                "audio": "first_default_or_highest_channels",
            },
            "hash_quality": source_ctx.hash_quality,
            "source_etag": source_ctx.source_etag,
            "drive_md5": source_ctx.drive_md5,
        },
        "warnings": sorted(set(warnings)),
        "errors": errors,
    }

    # Validate against the schema to catch accidental drift early.
    _validate_against_schema(sidecar)
    return sidecar


def _initial_thumbnail_manifest(duration_s: float) -> Dict[str, Any]:
    poster_time = 0.0
    if duration_s and duration_s > 0:
        poster_time = duration_s / 2.0

    manifest = {
        "poster": {"timestamp_s": round(poster_time, 3), "path": "", "width_px": 0, "height_px": 0},
        "samples": [],
    }
    if duration_s >= 60.0:
        for ratio in (0.2, 0.8):
            manifest["samples"].append(
                {
                    "timestamp_s": round(duration_s * ratio, 3),
                    "path": "",
                    "width_px": 0,
                    "height_px": 0,
                }
            )
    return manifest


def _hash_dict(hash_info: Optional[HashInfo]) -> Optional[Dict[str, str]]:
    if not hash_info:
        return None
    return {"algo": hash_info.algo, "value": hash_info.value}


def _normalise_tags(tags: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not tags:
        return {}
    normalised: Dict[str, str] = {}
    for key, value in tags.items():
        if value is None:
            continue
        if isinstance(value, str):
            normalised[key] = value
        else:
            normalised[key] = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    return normalised


def _parse_duration(raw_value: Any) -> Tuple[float, Optional[str]]:
    if raw_value in (None, "N/A", ""):
        return 0.0, "duration_unavailable"
    try:
        return float(raw_value), None
    except (TypeError, ValueError):
        return 0.0, "duration_unavailable"


def _parse_bitrate_kbps(raw_value: Any) -> Optional[int]:
    if raw_value in (None, "N/A", ""):
        return None
    try:
        return int(round(int(raw_value) / 1000))
    except (TypeError, ValueError):
        return None


def _parse_streams(streams: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    payload: List[Dict[str, Any]] = []
    video_streams: List[Dict[str, Any]] = []
    audio_streams: List[Dict[str, Any]] = []

    for stream in streams:
        stream_type = _normalise_stream_type(stream.get("codec_type"))
        avg_frame_rate = _rational_string(stream.get("avg_frame_rate"))
        r_frame_rate = _rational_string(stream.get("r_frame_rate"))
        entry = {
            "index": stream.get("index", 0),
            "type": stream_type,
            "codec": stream.get("codec_name") or "unknown",
            "avg_frame_rate": avg_frame_rate,
            "r_frame_rate": r_frame_rate,
            "width_px": _int_or_none(stream.get("width")),
            "height_px": _int_or_none(stream.get("height")),
            "channels": _int_or_none(stream.get("channels")),
            "sample_rate_hz": _int_or_none(stream.get("sample_rate")),
            "bitrate_kbps": _parse_bitrate_kbps(stream.get("bit_rate")),
            "disposition_default": _disposition_default(stream.get("disposition")),
            "tags": _normalise_tags(stream.get("tags")),
        }
        payload.append(entry)
        if stream_type == "video":
            video_streams.append({**stream, "__payload": entry})
        elif stream_type == "audio":
            audio_streams.append({**stream, "__payload": entry})
    payload.sort(key=lambda item: item["index"])
    return payload, video_streams, audio_streams


def _normalise_stream_type(value: Any) -> StreamType:
    if not isinstance(value, str):
        return "other"
    value_lower = value.lower()
    if value_lower in {"video", "audio", "data", "subtitle"}:
        return value_lower  # type: ignore[return-value]
    return "other"


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, "N/A", ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _disposition_default(disposition: Any) -> Optional[bool]:
    if not isinstance(disposition, dict):
        return None
    default_value = disposition.get("default")
    if default_value is None:
        return None
    return bool(default_value)


def _rational_string(value: Any) -> Optional[str]:
    if not value or value in {"N/A"}:
        return None
    return str(value)


def _summarise_video_stream(streams: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not streams:
        return None, None

    selected = _select_video_stream(streams)
    payload = selected["__payload"]
    sample_aspect_ratio = selected.get("sample_aspect_ratio")

    frame_rate = _frame_rate_from_stream(payload)
    warning = "frame_rate_unavailable" if frame_rate is None else None
    pixel_aspect_ratio = _parse_sample_aspect_ratio(sample_aspect_ratio)

    summary = {
        "codec": payload["codec"],
        "profile": selected.get("profile"),
        "width_px": payload["width_px"] or 0,
        "height_px": payload["height_px"] or 0,
        "pixel_aspect_ratio": pixel_aspect_ratio,
        "frame_rate_fps": frame_rate,
        "color_space": selected.get("color_space"),
        "color_transfer": selected.get("color_transfer"),
        "color_primaries": selected.get("color_primaries"),
    }
    return summary, warning


def _select_video_stream(streams: List[Dict[str, Any]]) -> Dict[str, Any]:
    default_streams = [
        stream for stream in streams if _disposition_default(stream.get("disposition")) is True
    ]
    if default_streams:
        return default_streams[0]

    def score(item: Dict[str, Any]) -> int:
        payload = item["__payload"]
        width = payload["width_px"] or 0
        height = payload["height_px"] or 0
        return width * height

    return max(streams, key=score)


def _summarise_audio_stream(streams: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not streams:
        return None, "no_audio_stream"

    selected = _select_audio_stream(streams)
    payload = selected["__payload"]

    summary = {
        "codec": payload["codec"],
        "channels": payload["channels"] or 0,
        "sample_rate_hz": payload["sample_rate_hz"] or 0,
        "bitrate_kbps": payload["bitrate_kbps"],
    }
    return summary, None


def _select_audio_stream(streams: List[Dict[str, Any]]) -> Dict[str, Any]:
    default_streams = [
        stream for stream in streams if _disposition_default(stream.get("disposition")) is True
    ]
    if default_streams:
        return default_streams[0]

    def score(item: Dict[str, Any]) -> Tuple[int, int]:
        payload = item["__payload"]
        channels = payload["channels"] or 0
        sample_rate = payload["sample_rate_hz"] or 0
        return channels, sample_rate

    return max(streams, key=score)


def _frame_rate_from_stream(payload: Dict[str, Any]) -> Optional[float]:
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = payload.get(key)
        rate = _parse_rational(value)
        if rate is not None:
            return rate
    return None


def _parse_rational(value: Optional[str]) -> Optional[float]:
    if not value or value in {"0/0", "N/A"}:
        return None
    if "/" not in value:
        # Already a float string.
        try:
            return round(float(value), 2)
        except ValueError:
            return None
    numerator_str, denominator_str = value.split("/", 1)
    try:
        numerator = float(numerator_str)
        denominator = float(denominator_str)
    except ValueError:
        return None
    if math.isclose(denominator, 0.0):
        return None
    return round(numerator / denominator, 2)


def _parse_sample_aspect_ratio(value: Any) -> float:
    if not value or value in {"0:1", "N/A"}:
        return 1.0
    if isinstance(value, (int, float)):
        return float(value) or 1.0
    if isinstance(value, str) and ":" in value:
        num_str, den_str = value.split(":", 1)
        try:
            num = float(num_str)
            den = float(den_str)
            if math.isclose(den, 0.0):
                return 1.0
            ratio = num / den
            return ratio if ratio > 0 else 1.0
        except ValueError:
            return 1.0
    return 1.0


def _determine_created_time(
    *,
    source_ctx: SourceContext,
    format_tags: Dict[str, str],
    streams: List[Dict[str, Any]],
    default_fallback: datetime,
) -> datetime:
    if source_ctx.created_time:
        return source_ctx.created_time.astimezone(timezone.utc)

    tag_keys = [
        "com.apple.quicktime.creationdate",
        "creation_time",
        "date",
    ]
    candidates: List[datetime] = []
    for key in tag_keys:
        value = format_tags.get(key)
        if value:
            candidate = _parse_datetime(value)
            if candidate:
                candidates.append(candidate)

    for stream in streams:
        tags = _normalise_tags(stream.get("tags"))
        for key in tag_keys:
            value = tags.get(key)
            if value:
                candidate = _parse_datetime(value)
                if candidate:
                    candidates.append(candidate)

    if candidates:
        return sorted(candidates)[0]

    if source_ctx.modified_time:
        return source_ctx.modified_time.astimezone(timezone.utc)

    return default_fallback


def _parse_datetime(value: str) -> Optional[datetime]:
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    known_formats = [
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]
    for fmt in known_formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@lru_cache(maxsize=4)
def _binary_version(cmd: Sequence[str]) -> str:
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    output = proc.stdout.strip() or proc.stderr.strip()
    if not output:
        return "unknown"
    first_line = output.splitlines()[0]
    return first_line.strip()


def _validate_against_schema(payload: SidecarDict) -> None:
    try:
        from .sidecar_schema import Sidecar
    except ImportError:
        return

    # raises ValidationError on mismatch
    Sidecar.model_validate(payload)
