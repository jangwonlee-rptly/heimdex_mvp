# Technical System Overview

This document provides a detailed, file- and module-level technical overview of the Heimdex Vector-Native Archive API.

## 1. Application Entrypoint (`app/main.py`)

The application is a standard FastAPI service. The entrypoint, `app/main.py`, is responsible for:

-   **Application Factory (`create_app`)**: This function initializes the FastAPI application.
-   **Lifespan Management (`@asynccontextmanager lifespan`)**: On startup, it initializes and attaches core components to the application state (`app.state`):
    -   `settings`: Pydantic settings loaded from `app.core.config`.
    -   `storage`: The storage backend (e.g., local filesystem) from `app.core.storage`.
    -   `engine` and `session_factory`: SQLAlchemy async engine and session factory from `app.core.db`.
-   **Router Inclusion**: It includes the main API router from `app.api.v1` and a legacy router (if `HEIMDEX_ENABLE_LEGACY` is true).

## 2. API Layer (`app/api/v1/`)

The API is versioned under `/v1` and is composed of several modular routers.

-   **`__init__.py`**: The `get_api_router` function aggregates all the individual route modules (`routes_system`, `routes_admin`, `routes_ingest`, `routes_assets`, `routes_jobs`) into a single `APIRouter` with the `/v1` prefix.
-   **`routes_ingest.py`**: Handles the multi-step file ingestion process.
    -   `POST /init`: Calls `service.init_upload` from `app.services.ingest_service` to prepare for a file upload. It returns an `upload_id`.
    -   `POST /commit`: Calls `service.commit_upload`, creating an `Asset` record in the database.
    -   `POST /probe`: Calls `service.probe` to synchronously run `ffprobe` on a source file and return metadata without creating a persistent asset.
-   **`routes_assets.py`**: Manages assets and their derived data.
    -   `POST /{asset_id}/sidecar`: Initiates a background job to generate a sidecar file with detailed metadata. It enqueues a task for the RQ worker.
    -   `GET /{asset_id}/sidecar`: Retrieves the persisted sidecar metadata.
-   **`routes_jobs.py`**:
    -   `GET /{job_id}`: Polls the status of a background job by querying the `Job` table in the database.

## 3. Core Modules (`app/core/`)

This directory contains the cross-cutting concerns of the application.

-   **`auth.py`**: Defines the `AuthContext` and JWT dependency (`AuthDependency`) used to secure endpoints and provide tenant (`org_id`) information.
-   **`config.py`**: Uses `pydantic-settings` to load configuration from environment variables.
-   **`db.py`**: Sets up the asynchronous SQLAlchemy engine (`create_engine`) and session factory (`create_session_factory`).
-   **`jobs.py`**: Provides an abstraction for the job queue. It defines a `JobQueue` protocol and implementations for `ImmediateQueue` (for local development) and `RQQueue` (for production).
-   **`storage.py`**: Provides an abstraction for file storage. It defines a `Storage` protocol and implementations for `LocalStorage` and a stub `GCSStorage`.

## 4. Business Logic (`app/services/ingest_service.py`)

This service contains the core business logic for the ingestion process, separating it from the API layer.

-   **`AuthenticatedService`**: This class is initialized with a database session, a storage backend, a job queue, and an auth context. The API routes use this service to perform their operations.
-   **`init_upload`**: Generates a unique upload ID and a destination URI in the storage backend.
-   **`commit_upload`**: Creates a new `Asset` record in the database, linking it to the organization and the `source_uri` provided by the client.
-   **`probe`**: Downloads the file from the `source_uri` to a temporary location and runs `ffprobe` on it.

## 5. Database Models (`app/db/models.py`)

The database schema is defined using SQLAlchemy ORM.

-   **`Organization`**: Represents a tenant in the system. `org_id` is the primary key and is used as a foreign key in most other tables to enforce data isolation.
-   **`Asset`**: The central model representing a media file. It stores the `source_uri`, size, hash, status (`queued`, `ready`, `processing`, `failed`), and relationships to its organization, sidecar, and thumbnails.
-   **`Sidecar`**: Stores the metadata extracted from an asset by `ffprobe`. It has a one-to-one relationship with `Asset`.
-   **`Thumbnail`**: Stores information about generated thumbnails for an asset. It has a one-to-many relationship with `Asset`.
-   **`Job`**: Represents an asynchronous task (e.g., sidecar generation). It stores the `job_type`, `status` (`queued`, `running`, `succeeded`, `failed`), and any resulting data or errors. It is linked to an `Asset` and `Organization`.

## 6. Asynchronous Workers (`app/workers/tasks.py`)

This module defines the functions that are executed by the RQ background workers.

-   The functions defined here are intended to be called asynchronously via the job queue (e.g., `RQQueue.enqueue`).
-   A typical task function (e.g., `generate_sidecar_task`) would receive an `asset_id` and `org_id`, fetch the corresponding `Asset` from the database, perform the long-running processing (like running `ffprobe`), and update the `Asset` and `Sidecar` tables with the results.

## 7. Technical Data Flow: Sidecar Generation

1.  **Request**: A user sends a `POST` request to `/v1/assets/{asset_id}/sidecar`.
2.  **API Layer (`routes_assets.py`)**:
    -   The endpoint receives the request.
    -   It uses the `AuthenticatedService` to access the job queue.
    -   It calls `job_queue.enqueue("generate_sidecar", asset_id=asset_id, org_id=context.org_id)`.
    -   A new `Job` record is created in the database with `status='queued'`. The API returns the `job_id`.
3.  **Job Queue (`core/jobs.py` -> Redis)**:
    -   The `RQQueue` implementation pushes a job onto the `heimdex-jobs` Redis queue.
4.  **Worker (`workers/tasks.py`)**:
    -   An `rq` worker process, running in the background, pops the job from the queue.
    -   The worker executes the target function (e.g., `generate_sidecar_task`).
5.  **Execution**:
    -   The task function uses a new database session to fetch the `Asset` by its `asset_id`.
    -   It updates the `Job` status to `running`.
    -   It uses the `Storage` interface to get a local handle to the media file.
    -   It runs `ffprobe` on the file.
    -   It creates a new `Sidecar` record with the extracted metadata and associates it with the `Asset`.
    -   It updates the `Asset` status to `ready`.
    -   It updates the `Job` status to `succeeded` and stores the result.
6.  **Polling**:
    -   The user can periodically send `GET` requests to `/v1/jobs/{job_id}`.
    -   The API queries the `Job` table and returns the current status and result.
