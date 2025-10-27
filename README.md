# Heimdex Vector-Native Archive API

Heimdex transforms raw video into structured, queryable metadata. This repository promotes the original CLI ingest tool to a FastAPI service with multi-tenant awareness, asynchronous job orchestration, and pluggable storage.

## Project Overview

The API accepts direct-uploaded media, orchestrates validation plus sidecar generation (thumbnails + schema), and surfaces job status and derived artifacts through a `/v1` surface. It is designed to slot into larger media-processing pipelines that need deterministic asset metadata with org-scoped isolation.

## Features
- FastAPI `/v1` surface covering ingest init/commit, ffprobe probing, thumbnail + sidecar generation, asset metadata, job tracking, and admin health checks.
- Async job runner abstraction with inline (development) execution and Redis/RQ support for production workers.
- Storage abstraction (local filesystem today, S3 stub for later) that preserves the derived layout (`derived/{org_id}/sidecars`, `derived/{org_id}/{asset_id}/thumbs`).
- Postgres schema with Alembic migrations and org-scoped row-level safety primitives.
- JWT guard stub that extracts `org_id` (and optionally scopes) for tenancy enforcement.
- Structured logging via `structlog`, ready for enrichment with metrics hooks.

## Getting Started

```bash
# Build and launch Postgres, Redis, and the API
docker compose up --build

# Apply migrations (executed once per environment)
docker compose exec vna uv run alembic upgrade head

# (Optional) run the async worker with RQ backend
docker compose exec vna uv run rq worker heimdex-jobs
```

Environment defaults (override via `.env`):

```
HEIMDEX_DATABASE_URL=postgresql+asyncpg://heimdex:heimdex@postgres:5432/heimdex
HEIMDEX_REDIS_URL=redis://redis:6379/0
HEIMDEX_STORAGE_BACKEND=local
HEIMDEX_DERIVED_ROOT=/app/derived
HEIMDEX_JOB_QUEUE_BACKEND=immediate  # set to "rq" for Redis-backed jobs
HEIMDEX_JWT_SECRET=change-me
HEIMDEX_MAX_UPLOAD_SIZE_BYTES=536870912
```

## API Walkthrough (curl)

All mutating requests accept an `Idempotency-Key` header. JWTs must carry an `org_id` claim.

```bash
TOKEN=$(python - <<'PY'
import jwt
print(jwt.encode({"org_id": "org-demo", "scopes": ["admin"]}, "change-me", algorithm="HS256"))
PY
)

AUTH="Authorization: Bearer ${TOKEN}"

# 1. Prepare an upload location (client uploads directly to storage)
curl -s -X POST http://localhost:8000/v1/ingest/init \
  -H "${AUTH}" \
  -H 'Content-Type: application/json' \
  -d '{"org_id":"org-demo","source_name":"clip.mp4","content_length":123456,"content_type":"video/mp4"}'

# 2. After the client uploads the file, commit it for tracking
curl -s -X POST http://localhost:8000/v1/ingest/commit \
  -H "${AUTH}" -H 'Content-Type: application/json' \
  -d '{"org_id":"org-demo","upload_id":"<from init>","source_uri":"file:///app/derived/uploads/..."}'

# 3. Run a synchronous ffprobe-based validation
curl -s -X POST http://localhost:8000/v1/ingest/probe \
  -H "${AUTH}" -H 'Content-Type: application/json' \
  -d '{"org_id":"org-demo","source_uri":"file:///app/derived/uploads/..."}'

# 4. Kick off full sidecar generation (thumbnails + schema write)
curl -i -X POST http://localhost:8000/v1/assets/<asset_id>/sidecar \
  -H "${AUTH}" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: 123e4567' \
  -d '{"org_id":"org-demo","source_uri":"file:///app/derived/uploads/..."}'

# 5. Poll job status
curl -s http://localhost:8000/v1/jobs/<job_id> -H "${AUTH}"

# 6. Retrieve the persisted sidecar once ready
curl -s http://localhost:8000/v1/assets/<asset_id>/sidecar -H "${AUTH}"
```

## Development

- **Tests**: `uv run pytest` (Docker image installs test extras and sets `PYTHONPATH=/app`, so imports resolve out of the box).
- **Formatting/Linting**: managed via `uv` (add tools as needed).
- **OpenAPI**: regenerate with `uv run python -c "from app.main import app; import json, pathlib; pathlib.Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2))"`.

## Simple Metadata Endpoint

The upload-based `/metadata` route is considered legacy and is **disabled by default**. Set
`HEIMDEX_ENABLE_LEGACY=true` at process start if you need to re-enable it temporarily for migration period.

If you only need synchronous metadata extraction, the service exposes this thin wrapper around `ffprobe` when enabled:

- `POST /metadata`: Accepts a video upload and returns structured metadata.
- `GET /health`: Basic liveness probe.

Pair the API with the CLI below for quick checks during development.

## Command-Line Interface (CLI)

The project still ships with the original CLI for local workflows and scripts.

```bash
uv run python -m app.cli --help
```

### Worker & Queue

Set `HEIMDEX_JOB_QUEUE_BACKEND=rq` to use Redis-backed background workers. Launch with:

```bash
uv run rq worker --url ${HEIMDEX_REDIS_URL} heimdex-jobs
```

Inline jobs (default) are convenient for local testing but should be avoided in production.

### Migrations

Create new revisions with:

```bash
uv run alembic revision -m "describe change"
```

Apply with `uv run alembic upgrade head`. Migrations target the metadata defined in `app/db/models.py`.

---

For further roadmap items (thumbnail listing endpoint, CDN signing, replay tooling), see the TODO comments sprinkled throughout the service modules.
