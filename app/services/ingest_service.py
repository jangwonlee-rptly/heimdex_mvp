from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.jobs import get_job_backend
from app.core.storage import PresignedURL, Storage
from app.db.models import Asset, AssetStatus, Job, JobStatus, JobType, Organization, Sidecar, Thumbnail
from app.domain import (
    AssetIdentity,
    SourceContext,
    derive_local_asset_identity,
    export_schema,
    parse_ffprobe_json,
    render_thumbnails,
)
from app.core.logging import get_logger


class IngestService:
    def __init__(self, settings: Settings, storage: Storage, session: AsyncSession):
        self.settings = settings
        self.storage = storage
        self.session = session
        self.logger = get_logger(component="ingest_service")

    async def ensure_org(self, org_id: str) -> Organization:
        org = await self.session.get(Organization, org_id)
        if org:
            return org
        org = Organization(org_id=org_id)
        self.session.add(org)
        await self.session.flush()
        return org

    async def init_upload(self, *, org_id: str, source_name: str, content_type: str | None) -> dict[str, Any]:
        await self.ensure_org(org_id)
        upload_id = uuid4().hex
        key = f"uploads/{org_id}/{upload_id}/{source_name}"
        presigned = self.storage.presign_put(key, content_type=content_type)
        return {
            "upload_id": upload_id,
            "presigned": {
                "asset_uri": presigned.url,
            },
        }

    async def commit_upload(
        self,
        *,
        org_id: str,
        source_uri: str,
        upload_id: str,
        weak_threshold_bytes: int | None,
    ) -> dict[str, Any]:
        await self.ensure_org(org_id)
        parsed_uri = urlparse(source_uri)
        if parsed_uri.scheme == "gs":
            raise NotImplementedError("gcs_commit_not_implemented")
        path = self._resolve_local_path(source_uri)
        if not path.exists():
            raise FileNotFoundError(source_uri)

        identity = await asyncio.to_thread(
            derive_local_asset_identity,
            path,
            max_bytes_for_strong_hash=weak_threshold_bytes,
        )

        asset = await self.session.get(Asset, identity.asset_id)
        stat = path.stat()
        created_time = self._stat_birthtime(stat)
        modified_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        if asset is None:
            asset = Asset(
                asset_id=identity.asset_id,
                org_id=org_id,
                source_uri=source_uri,
                size_bytes=stat.st_size,
                hash=identity.hash.value if identity.hash else None,
                hash_quality=identity.hash_quality,
                created_time=created_time,
                modified_time=modified_time,
                status=AssetStatus.ready,
            )
            self.session.add(asset)
        else:
            asset.source_uri = source_uri
            asset.size_bytes = stat.st_size
            asset.hash = identity.hash.value if identity.hash else None
            asset.hash_quality = identity.hash_quality
            asset.modified_time = modified_time
            asset.status = AssetStatus.ready

        await self.session.commit()
        await self.session.refresh(asset)

        return {
            "asset_id": asset.asset_id,
            "source_uri": asset.source_uri,
            "status": asset.status.value,
        }

    async def probe(self, *, org_id: str, source_uri: str, weak_threshold_bytes: int | None) -> dict[str, Any]:
        await self.ensure_org(org_id)
        parsed_uri = urlparse(source_uri)
        if parsed_uri.scheme == "gs":
            raise NotImplementedError("gcs_probe_not_implemented")
        path = self._resolve_local_path(source_uri)
        identity = await asyncio.to_thread(
            derive_local_asset_identity,
            path,
            max_bytes_for_strong_hash=weak_threshold_bytes,
        )
        context = await asyncio.to_thread(
            self._build_source_context,
            path,
            identity,
        )
        raw = await asyncio.to_thread(self._run_ffprobe, path)
        sidecar = parse_ffprobe_json(raw, context)
        return sidecar

    async def enqueue_job(
        self,
        *,
        org_id: str,
        asset_id: str,
        job_type: JobType,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> Job:
        await self.ensure_org(org_id)
        job = await self._upsert_job(org_id, asset_id, job_type, payload, idempotency_key)
        backend = get_job_backend()
        await backend.enqueue(job.job_id, job.job_type)
        return job

    async def _upsert_job(
        self,
        org_id: str,
        asset_id: str,
        job_type: JobType,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> Job:
        if idempotency_key:
            stmt = select(Job).where(Job.org_id == org_id, Job.idempotency_key == idempotency_key)
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                if existing.payload != payload or existing.job_type != job_type:
                    raise ValueError("idempotency_conflict")
                return existing

        job = Job(
            job_id=uuid4().hex,
            job_type=job_type,
            org_id=org_id,
            asset_id=asset_id,
            status=JobStatus.queued,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_job(self, job_id: str) -> Job | None:
        return await self.session.get(Job, job_id)

    async def get_asset_snapshot(self, *, org_id: str, asset_id: str) -> dict[str, Any] | None:
        stmt = select(Asset).where(Asset.asset_id == asset_id, Asset.org_id == org_id)
        result = await self.session.execute(stmt)
        asset = result.scalar_one_or_none()
        if not asset:
            return None

        sidecar_stmt = select(Sidecar).where(Sidecar.asset_id == asset_id)
        sidecar = (await self.session.execute(sidecar_stmt)).scalar_one_or_none()

        thumbs_stmt = select(Thumbnail).where(Thumbnail.asset_id == asset_id).order_by(Thumbnail.idx)
        thumbs = (await self.session.execute(thumbs_stmt)).scalars().all()

        return {
            "asset_id": asset.asset_id,
            "org_id": asset.org_id,
            "source_uri": asset.source_uri,
            "size_bytes": asset.size_bytes,
            "hash": asset.hash,
            "hash_quality": asset.hash_quality,
            "status": asset.status.value,
            "sidecar": {
                "schema_version": sidecar.schema_version if sidecar else None,
                "storage_key": sidecar.storage_key if sidecar else None,
                "etag": sidecar.etag if sidecar else None,
            },
            "thumbnails": [
                {
                    "idx": thumb.idx,
                    "storage_key": thumb.storage_key,
                    "width": thumb.width,
                    "height": thumb.height,
                    "ts_ms": thumb.ts_ms,
                }
                for thumb in thumbs
            ],
        }

    async def persist_sidecar(
        self,
        *,
        org_id: str,
        asset_id: str,
        schema_version: str,
        storage_key: str,
        etag: str | None,
    ) -> Sidecar:
        sidecar = await self.session.get(Sidecar, asset_id)
        if sidecar is None:
            sidecar = Sidecar(
                asset_id=asset_id,
                org_id=org_id,
                schema_version=schema_version,
                storage_key=storage_key,
                etag=etag,
            )
            self.session.add(sidecar)
        else:
            sidecar.schema_version = schema_version
            sidecar.storage_key = storage_key
            sidecar.etag = etag
        await self.session.commit()
        return sidecar

    async def persist_thumbnails(
        self,
        *,
        org_id: str,
        asset_id: str,
        thumbnails: list[dict[str, Any]],
    ) -> None:
        await self.session.execute(
            Thumbnail.__table__.delete().where(Thumbnail.asset_id == asset_id)  # type: ignore[attr-defined]
        )
        for entry in thumbnails:
            thumb = Thumbnail(
                asset_id=asset_id,
                org_id=org_id,
                idx=entry.get("idx", 0),
                ts_ms=entry.get("ts_ms"),
                storage_key=entry["storage_key"],
                width=entry.get("width"),
                height=entry.get("height"),
            )
            self.session.add(thumb)
        await self.session.commit()

    async def update_job_status(
        self,
        job_id: str,
        *,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> Job:
        job = await self.session.get(Job, job_id)
        if not job:
            raise LookupError(job_id)
        job.status = status
        job.result = result
        job.error = error
        if status == JobStatus.running:
            job.started_at = datetime.now(timezone.utc)
        if status in {JobStatus.succeeded, JobStatus.failed}:
            job.finished_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    def _resolve_local_path(self, source_uri: str) -> Path:
        parsed = urlparse(source_uri)
        if parsed.scheme not in {"file", ""}:
            raise ValueError(f"unsupported_uri_scheme:{parsed.scheme}")
        if parsed.scheme == "file":
            return Path(parsed.path)
        return Path(source_uri)

    @staticmethod
    def _stat_birthtime(stat_result: Any) -> datetime | None:
        birth_time = getattr(stat_result, "st_birthtime", None)
        if birth_time is None:
            return None
        return datetime.fromtimestamp(birth_time, tz=timezone.utc)

    @staticmethod
    def _run_ffprobe(target: Path) -> dict[str, Any]:
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
        proc = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(proc.stdout)

    def _build_source_context(self, media_path: Path, identity: AssetIdentity) -> SourceContext:
        stat = media_path.stat()
        created_time = self._stat_birthtime(stat)
        modified_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        return SourceContext(
            type="local",
            uri=media_path.resolve().as_uri(),
            filename=media_path.name,
            size_bytes=stat.st_size,
            asset_id=identity.asset_id,
            created_time=created_time,
            modified_time=modified_time,
            hash=identity.hash,
            hash_quality=identity.hash_quality,
        )


async def process_thumbnails_job(job_id: str, session: AsyncSession, settings: Settings, storage: Storage) -> None:
    logger = get_logger(job_id=job_id, job_type="thumbnails")
    job = await session.get(Job, job_id)
    if not job:
        logger.error("job_not_found")
        return
    service = IngestService(settings, storage, session)
    await service.update_job_status(job_id, status=JobStatus.running)

    payload = job.payload or {}
    org_id = payload["org_id"]
    asset_id = payload["asset_id"]
    source_uri = payload["source_uri"]

    try:
        sidecar = await service.probe(org_id=org_id, source_uri=source_uri, weak_threshold_bytes=payload.get("weak_threshold_bytes"))
        derived_root = Path(settings.derived_root) / org_id
        derived_root.mkdir(parents=True, exist_ok=True)
        source_path = service._resolve_local_path(source_uri)
        updated = await asyncio.to_thread(render_thumbnails, str(source_path), sidecar, derived_root)
        manifest = _normalise_thumbnail_manifest(updated, derived_root, org_id, asset_id)
        await service.persist_thumbnails(org_id=org_id, asset_id=asset_id, thumbnails=manifest)
        asset = await service.session.get(Asset, asset_id)
        if asset:
            asset.status = AssetStatus.ready
            await service.session.commit()
        await service.update_job_status(job_id, status=JobStatus.succeeded, result={"thumbnails": manifest})
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("thumbnail_job_failed")
        await service.update_job_status(job_id, status=JobStatus.failed, error={"message": str(exc)})


async def process_sidecar_job(job_id: str, session: AsyncSession, settings: Settings, storage: Storage) -> None:
    logger = get_logger(job_id=job_id, job_type="sidecar")
    job = await session.get(Job, job_id)
    if not job:
        logger.error("job_not_found")
        return
    service = IngestService(settings, storage, session)
    await service.update_job_status(job_id, status=JobStatus.running)

    payload = job.payload or {}
    org_id = payload["org_id"]
    asset_id = payload["asset_id"]
    source_uri = payload["source_uri"]

    try:
        sidecar = await service.probe(org_id=org_id, source_uri=source_uri, weak_threshold_bytes=payload.get("weak_threshold_bytes"))
        derived_root = Path(settings.derived_root)
        schemas_dir = derived_root / "schemas"
        schemas_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(export_schema, schemas_dir / "sidecar.schema.json")

        org_root = derived_root / org_id
        org_root.mkdir(parents=True, exist_ok=True)
        source_path = service._resolve_local_path(source_uri)
        updated = await asyncio.to_thread(render_thumbnails, str(source_path), sidecar, org_root)
        manifest = _normalise_thumbnail_manifest(updated, org_root, org_id, asset_id)
        await service.persist_thumbnails(org_id=org_id, asset_id=asset_id, thumbnails=manifest)

        sidecars_dir = org_root / "sidecars"
        sidecars_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = sidecars_dir / f"{asset_id}.vna.json"
        sidecar_path.write_text(json.dumps(updated, indent=2, sort_keys=True), encoding="utf-8")

        storage_key = f"sidecars/{asset_id}.vna.json"
        await service.persist_sidecar(
            org_id=org_id,
            asset_id=asset_id,
            schema_version=updated["schema_version"],
            storage_key=storage_key,
            etag=None,
        )
        asset = await service.session.get(Asset, asset_id)
        if asset:
            asset.status = AssetStatus.ready
            await service.session.commit()
        await service.update_job_status(
            job_id,
            status=JobStatus.succeeded,
            result={
                "sidecar_uri": sidecar_path.as_uri(),
                "thumbnails": manifest,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("sidecar_job_failed")
        await service.update_job_status(job_id, status=JobStatus.failed, error={"message": str(exc)})


def _normalise_thumbnail_manifest(
    sidecar: dict[str, Any],
    org_root: Path,
    org_id: str,
    asset_id: str,
) -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []
    manifest = sidecar.get("thumbnails") or {}

    poster = manifest.get("poster")
    thumbs_root = org_root / "thumbs" / asset_id
    final_root = org_root / asset_id / "thumbs"

    if thumbs_root.exists():
        final_root.parent.mkdir(parents=True, exist_ok=True)
        if final_root.exists():
            shutil.rmtree(final_root)
        shutil.move(str(thumbs_root), str(final_root))
        thumbs_parent = org_root / "thumbs"
        if thumbs_parent.exists() and not any(thumbs_parent.iterdir()):
            thumbs_parent.rmdir()

    final_root.mkdir(parents=True, exist_ok=True)

    if poster and poster.get("path"):
        poster_path = final_root / Path(poster["path"]).name
        poster["path"] = f"{org_id}/{asset_id}/thumbs/{poster_path.name}"
        poster_entry = {
            "idx": 0,
            "storage_key": poster["path"],
            "width": poster.get("width_px"),
            "height": poster.get("height_px"),
            "ts_ms": int(poster.get("timestamp_s", 0) * 1000),
        }
        generated.append(poster_entry)

    samples = manifest.get("samples", [])
    for index, sample in enumerate(samples, start=1):
        if not sample.get("path"):
            continue
        sample_path = final_root / Path(sample["path"]).name
        sample["path"] = f"{org_id}/{asset_id}/thumbs/{sample_path.name}"
        entry = {
            "idx": index,
            "storage_key": sample["path"],
            "width": sample.get("width_px"),
            "height": sample.get("height_px"),
            "ts_ms": int(sample.get("timestamp_s", 0) * 1000),
        }
        generated.append(entry)
    return generated


__all__ = [
    "IngestService",
    "process_thumbnails_job",
    "process_sidecar_job",
]
