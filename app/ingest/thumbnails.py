from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2  # type: ignore

THUMB_WIDTH = 320


def render_thumbnails(video_path: str, sidecar: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    """Generate poster and sample thumbnails according to policy."""
    manifest = sidecar.get("thumbnails") or {}
    asset_id = sidecar.get("asset_id")
    if not asset_id:
        raise ValueError("sidecar missing asset_id")

    thumbs_root = out_dir / "thumbs" / asset_id
    thumbs_root.mkdir(parents=True, exist_ok=True)

    warnings = set(sidecar.get("warnings") or [])

    poster_info = manifest.get("poster")
    if poster_info:
        poster_path = thumbs_root / "poster.jpg"
        success = _extract_and_measure(video_path, poster_info["timestamp_s"], poster_path)
        if success:
            width, height = success
            poster_info["path"] = (Path("thumbs") / asset_id / "poster.jpg").as_posix()
            poster_info["width_px"] = width
            poster_info["height_px"] = height
        else:
            warnings.add("thumbnail_generation_failed")
            poster_info.update({"path": "", "width_px": 0, "height_px": 0})

    samples_info = manifest.get("samples", [])
    generated_samples: List[Dict[str, Any]] = []
    for sample in samples_info:
        timestamp = sample.get("timestamp_s", 0.0)
        filename = f"t{_timestamp_to_centiseconds(timestamp):04d}.jpg"
        sample_path = thumbs_root / filename
        success = _extract_and_measure(video_path, timestamp, sample_path)
        if success:
            width, height = success
            sample["path"] = (Path("thumbs") / asset_id / filename).as_posix()
            sample["width_px"] = width
            sample["height_px"] = height
            generated_samples.append(sample)
        else:
            warnings.add("thumbnail_generation_failed")
    manifest["samples"] = generated_samples

    sidecar["thumbnails"] = manifest
    sidecar["warnings"] = sorted(warnings)
    return sidecar


def _timestamp_to_centiseconds(timestamp_s: float) -> int:
    return int(round(max(timestamp_s, 0.0) * 100))


def _extract_and_measure(video_path: str, timestamp: float, output_path: Path) -> Tuple[int, int] | None:
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-ss",
        f"{max(timestamp, 0.0):.3f}",
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-vf",
        f"scale={THUMB_WIDTH}:-2",
        "-q:v",
        "2",
        "-y",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (subprocess.CalledProcessError, FileNotFoundError):
        if output_path.exists():
            output_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
        return None

    try:
        return _image_dimensions(output_path)
    except RuntimeError:
        output_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
        return None


def _image_dimensions(image_path: Path) -> Tuple[int, int]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Failed to read generated thumbnail at {image_path}")
    height, width = image.shape[:2]
    return width, height
