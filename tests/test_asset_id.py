from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.ingest.asset_id import (
    AssetIdentity,
    HashInfo,
    compose_drive_asset_identity,
    compute_sha256,
    compute_weak_signature,
    derive_local_asset_identity,
)


def test_compute_weak_signature_is_deterministic():
    timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    first = compute_weak_signature("example.mp4", 1024, timestamp)
    second = compute_weak_signature("example.mp4", 1024, timestamp)
    assert first == second


def test_derive_local_asset_identity_strong(tmp_path: Path):
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"hello world")

    identity = derive_local_asset_identity(sample, max_bytes_for_strong_hash=None)
    assert identity.hash is not None
    assert identity.hash.algo == "sha256"
    assert identity.hash_quality == "strong"
    assert identity.asset_id.startswith("sha256:")
    assert identity.hash.value == compute_sha256(sample)


def test_derive_local_asset_identity_weak(tmp_path: Path):
    sample = tmp_path / "large.bin"
    sample.write_bytes(b"x" * 10)

    identity = derive_local_asset_identity(sample, max_bytes_for_strong_hash=1)
    assert identity.hash is not None
    assert identity.hash.algo == "weak"
    assert identity.hash_quality == "weak"
    assert identity.asset_id.startswith("weak:")


def test_compose_drive_asset_identity():
    with_hash = compose_drive_asset_identity("abc123", "md5value")
    assert isinstance(with_hash, AssetIdentity)
    assert with_hash.asset_id == "drive:abc123::md5value"
    assert with_hash.hash == HashInfo(algo="md5", value="md5value")
    assert with_hash.hash_quality == "strong"

    without_hash = compose_drive_asset_identity("abc123", None)
    assert without_hash.asset_id == "drive:abc123"
    assert without_hash.hash is None
    assert without_hash.hash_quality is None
