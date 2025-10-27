# Heimdex Developer Guide

This guide captures the workflows you will commonly reach for while developing, testing, and validating the Heimdex API and its background workers. All commands assume you are in the repository root unless noted otherwise.

---

## 1. Environment Overview

- **Containers**
  - `vna`: FastAPI server + worker tooling (runs as `appuser`).
  - `postgres`: metadata persistence (default credentials: `heimdex/heimdex`).
  - `redis`: job broker for the optional RQ worker.
- **Volumes**
  - `./derived` – mounted at `/app/derived`; holds sidecars/thumbnails during local testing.
  - `./app`, `./tests` – bind-mounted inside the container for live reload during development.

Bring everything up:

```bash
docker compose up --build
# or run in the background
docker compose up -d --build
```

Stop and clean up:

```bash
docker compose down
```

Whenever you change Python dependencies or migration code, rebuild the image so the container picks up changes:

```bash
docker compose build vna
docker compose up -d --force-recreate vna
```

---

## 2. Database Migrations

Apply migrations against the running Postgres container:

```bash
docker compose exec vna uv run alembic upgrade head
```

Generate a new revision (after editing SQLAlchemy models):

```bash
docker compose exec vna uv run alembic revision -m "describe change"
```

Rollback one revision:

```bash
docker compose exec vna uv run alembic downgrade -1
```

> **Tip:** Alembic is executed from `/app/migrations`, and the `env.py` script adjusts `sys.path` so the `app` package is importable without extra setup.

---

## 3. Running Tests

### 3.1 Inside Docker (recommended)

Leverage the same environment that ships with the service:

```bash
docker compose run --rm vna bash -lc "cd /app && PYTHONPATH=/app uv run --with pytest --with httpx --with fakeredis pytest"
```

- `uv run --with …` pulls test-only dependencies (pytest, httpx, fakeredis) into the container at runtime.
- `PYTHONPATH=/app` exposes the project package to the interpreter.
- Tests create a throwaway SQLite database under `/tmp` and clean up derived artefacts automatically.

### 3.2 Host Environment (optional)

If you prefer to run tests without Docker:

```bash
uv sync  # install dependencies locally
env PYTHONPATH=$(pwd) HEIMDEX_DERIVED_ROOT=$(pwd)/derived pytest
```

Ensure ffmpeg/ffprobe and PySceneDetect are available on your PATH to pass the integration tests.

---

## 4. Working With Local Media Inside Docker

### 4.1 Copying Test Assets

Bind-mount a directory of test videos into the container by editing `docker-compose.yml`:

```yaml
    volumes:
      - ./samples:/app/samples:ro
```

Alternatively, copy individual files into the running container:

```bash
# Copy sample.mov from your host into the derived upload bucket inside the container
docker cp ~/Videos/sample.mov vna-dev:/app/derived/uploads/org-demo/tmp-upload/sample.mov
```

### 4.2 Exercising the API

1. **Init upload**
   ```bash
   curl -s -X POST http://localhost:8000/v1/ingest/init \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"org_id":"org-demo","source_name":"sample.mov","content_length":123456,"content_type":"video/quicktime"}'
   ```
2. **Place the file** into the `asset_uri` returned (for local testing, it will be a `file://` URI under `/app/derived/uploads/...`).
3. **Commit the upload**
   ```bash
   curl -X POST http://localhost:8000/v1/ingest/commit \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"org_id":"org-demo","upload_id":"<from init>","source_uri":"file:///app/derived/uploads/org-demo/..."}'
   ```
4. **Dry-run probe** (sync ffprobe validation)
   ```bash
   curl -X POST http://localhost:8000/v1/ingest/probe \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"org_id":"org-demo","source_uri":"file:///app/derived/uploads/org-demo/..."}'
   ```
5. **Async jobs**
   ```bash
   curl -X POST http://localhost:8000/v1/assets/<asset_id>/sidecar \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Idempotency-Key: test-123' \
     -H 'Content-Type: application/json' \
     -d '{"org_id":"org-demo","source_uri":"file:///app/derived/uploads/org-demo/..."}'
   ```
6. **Poll job status**
   ```bash
   curl -s http://localhost:8000/v1/jobs/<job_id> -H "Authorization: Bearer $TOKEN"
   ```
7. **Fetch artefacts** – once jobs succeed, inspect `/v1/assets/<asset_id>` and `/v1/assets/<asset_id>/sidecar`.

> **JWTs:** The API expects a JWT carrying `org_id` (and optionally scopes). For local smoke tests you can mint a token with `python -c 'import jwt; print(jwt.encode({"org_id": "org-demo", "scopes": ["admin"]}, "change-me", algorithm="HS256"))'`.

---

## 5. Worker Execution Modes

- **Inline (default):** jobs execute synchronously within API requests. Set `HEIMDEX_JOB_QUEUE_BACKEND=immediate` (default in `.env`).
- **Redis/RQ:** set `HEIMDEX_JOB_QUEUE_BACKEND=rq` and run the worker:

  ```bash
  docker compose exec vna uv run rq worker heimdex-jobs
  ```

  Jobs will enqueue instantly; the worker consumes them out-of-band.

Retries and backoff are handled in `app/services/ingest_service.py` – adjust settings via environment variables if you need to tune them.

---

## 6. Structured Logs & Diagnostics

Logs are emitted via `structlog` in JSON format. To tail them:

```bash
docker compose logs -f vna
```

Expect fields like `asset_id`, `job_id`, and `component` for correlation. The same command works for the worker or datastore services (`vna-postgres`, `vna-redis`).

---

## 7. Cleaning Derived Artefacts

During iteration the `derived/` tree can accumulate sidecars and thumbnails. Clean it safely from the host:

```bash
rm -rf derived/*
```

Or inside the container:

```bash
docker compose exec vna bash -lc 'rm -rf /app/derived/*'
```

---

## 8. Quick Reference

| Task | Command |
|------|---------|
| Start stack | `docker compose up -d --build` |
| Rebuild API image | `docker compose build vna` |
| Run migrations | `docker compose exec vna uv run alembic upgrade head` |
| Run tests | `docker compose run --rm vna bash -lc "cd /app && PYTHONPATH=/app uv run --with pytest --with httpx --with fakeredis pytest"` |
| Start worker | `docker compose exec vna uv run rq worker heimdex-jobs` |
| Tail logs | `docker compose logs -f vna` |

Keep this document handy as you experiment with local media and extend the API surface. Contributions and tweaks are welcome—update this guide when you discover new workflows or caveats.
