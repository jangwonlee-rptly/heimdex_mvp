from __future__ import annotations

import enum
from datetime import datetime

from typing import List, Optional

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class AssetStatus(str, enum.Enum):
    queued = "queued"
    ready = "ready"
    processing = "processing"
    failed = "failed"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class JobType(str, enum.Enum):
    thumbnails = "thumbnails"
    sidecar = "sidecar"


class Organization(Base):
    __tablename__ = "organizations"

    org_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    limits_jsonb: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    assets: Mapped[List["Asset"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Asset(Base):
    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hash_quality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    modified_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), default=AssetStatus.queued, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="assets")
    sidecar: Mapped[Optional["Sidecar"]] = relationship(back_populates="asset", uselist=False)
    thumbnails: Mapped[List["Thumbnail"]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class Sidecar(Base):
    __tablename__ = "sidecars"

    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(2048), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="sidecar")


class Thumbnail(Base):
    __tablename__ = "thumbnails"
    __table_args__ = (UniqueConstraint("asset_id", "idx", name="uq_thumbnails_asset_idx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    ts_ms: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(2048), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="thumbnails")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_org_id_asset_id", "org_id", "asset_id"),
        UniqueConstraint("org_id", "idempotency_key", name="uq_jobs_org_idempotency"),
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[JobType] = mapped_column(Enum(JobType), nullable=False)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.asset_id", ondelete="SET NULL"), nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    meta_jsonb: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


__all__ = [
    "Organization",
    "Asset",
    "Sidecar",
    "Thumbnail",
    "Job",
    "AuditEvent",
    "AssetStatus",
    "JobStatus",
    "JobType",
]
