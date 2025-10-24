from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import md5, sha256
from pathlib import Path
from typing import Literal, Optional

__all__ = [
    "HashInfo",
    "AssetIdentity",
    "compute_sha256",
    "compute_weak_signature",
    "derive_local_asset_identity",
    "compose_drive_asset_identity",
]

WeakOrStrong = Literal["weak", "strong"]
HashAlgo = Literal["sha256", "md5", "weak"]


@dataclass(slots=True)
class HashInfo:
    """A dataclass to store hash information."""

    algo: HashAlgo
    value: str


@dataclass(slots=True)
class AssetIdentity:
    """A dataclass to store asset identity information."""

    asset_id: str
    hash: Optional[HashInfo]
    hash_quality: Optional[WeakOrStrong]


def compute_sha256(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Return a hexadecimal SHA256 digest for the file.

    Args:
        path: The path to the file.
        chunk_size: The chunk size to use when reading the file.

    Returns:
        The hexadecimal SHA256 digest.
    """
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def compute_weak_signature(
    filename: str,
    size_bytes: Optional[int],
    modified_time: Optional[datetime],
) -> str:
    """Return a deterministic weak fingerprint for the supplied metadata.

    Args:
        filename: The filename.
        size_bytes: The file size in bytes.
        modified_time: The last modified time.

    Returns:
        The weak signature.
    """
    size_component = str(size_bytes) if size_bytes is not None else "unknown"
    if modified_time is not None:
        # Normalise to UTC, ignoring sub-second noise.
        if modified_time.tzinfo is None:
            modified_time = modified_time.replace(tzinfo=timezone.utc)
        modified_component = modified_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        modified_component = "missing"
    payload = f"{filename}|{size_component}|{modified_component}"
    return md5(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


def derive_local_asset_identity(
    path: Path,
    *,
    max_bytes_for_strong_hash: Optional[int] = 1_000_000_000,
) -> AssetIdentity:
    """Return the canonical local asset identifier and hash metadata.

    Args:
        path: The path to the file.
        max_bytes_for_strong_hash: The maximum file size for which to compute a strong hash.

    Returns:
        The asset identity.
    """
    stat = path.stat()
    size_bytes = stat.st_size
    modified_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    do_strong = max_bytes_for_strong_hash is None or size_bytes <= max_bytes_for_strong_hash

    if do_strong:
        sha = compute_sha256(path)
        return AssetIdentity(
            asset_id=f"sha256:{sha}",
            hash=HashInfo(algo="sha256", value=sha),
            hash_quality="strong",
        )

    weak = compute_weak_signature(path.name, size_bytes, modified_time)
    return AssetIdentity(
        asset_id=f"weak:{weak}",
        hash=HashInfo(algo="weak", value=weak),
        hash_quality="weak",
    )


def compose_drive_asset_identity(file_id: str, md5_checksum: Optional[str]) -> AssetIdentity:
    """Compose the canonical Google Drive asset identifier.

    Args:
        file_id: The Google Drive file ID.
        md5_checksum: The MD5 checksum of the file.

    Returns:
        The asset identity.
    """
    if md5_checksum:
        return AssetIdentity(
            asset_id=f"drive:{file_id}::{md5_checksum}",
            hash=HashInfo(algo="md5", value=md5_checksum),
            hash_quality="strong",
        )
    return AssetIdentity(asset_id=f"drive:{file_id}", hash=None, hash_quality=None)
