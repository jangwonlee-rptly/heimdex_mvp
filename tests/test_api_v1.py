from __future__ import annotations

from tests.conftest import uri_to_path


def test_health(client):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"


def test_admin_env_check_requires_scope(client, org_headers):
    resp = client.get("/v1/admin/env-check", headers=org_headers)
    assert resp.status_code == 403


def test_ingest_sidecar_flow(client, admin_headers, generated_video_file):
    # Initialise upload
    init_resp = client.post(
        "/v1/ingest/init",
        json={
            "org_id": "org-test",
            "source_name": "sample.mp4",
            "content_length": generated_video_file.stat().st_size,
            "content_type": "video/mp4",
        },
        headers=admin_headers,
    )
    assert init_resp.status_code == 201, init_resp.text
    init_json = init_resp.json()
    upload_uri = init_json["presigned"]["asset_uri"]

    target_path = uri_to_path(upload_uri)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(generated_video_file.read_bytes())

    commit_resp = client.post(
        "/v1/ingest/commit",
        json={
            "org_id": "org-test",
            "upload_id": init_json["upload_id"],
            "source_uri": upload_uri,
            "weak_threshold_bytes": 100_000_000,
        },
        headers=admin_headers,
    )
    assert commit_resp.status_code == 200, commit_resp.text
    commit_json = commit_resp.json()
    asset_id = commit_json["asset_id"]

    probe_resp = client.post(
        "/v1/ingest/probe",
        json={
            "org_id": "org-test",
            "source_uri": upload_uri,
        },
        headers=admin_headers,
    )
    assert probe_resp.status_code == 200, probe_resp.text
    probe_json = probe_resp.json()
    assert probe_json["asset_id"] == asset_id

    idempotency_key = "test-sidecar-job"
    job_resp = client.post(
        f"/v1/assets/{asset_id}/sidecar",
        json={
            "org_id": "org-test",
            "source_uri": upload_uri,
        },
        headers={**admin_headers, "Idempotency-Key": idempotency_key},
    )
    assert job_resp.status_code == 202, job_resp.text
    job_json = job_resp.json()
    job_id = job_json["job_id"]

    status_resp = client.get(f"/v1/jobs/{job_id}", headers=admin_headers)
    assert status_resp.status_code == 200
    status_json = status_resp.json()
    assert status_json["status"] == "succeeded"
    assert status_json["result"]["sidecar_uri"]

    asset_resp = client.get(f"/v1/assets/{asset_id}", headers=admin_headers)
    assert asset_resp.status_code == 200
    asset_json = asset_resp.json()
    assert asset_json["asset_id"] == asset_id
    assert asset_json["sidecar"]["storage_key"]
    assert asset_json["thumbnails"], "thumbnails should be recorded"

    sidecar_resp = client.get(f"/v1/assets/{asset_id}/sidecar", headers=admin_headers)
    assert sidecar_resp.status_code == 200
    sidecar_json = sidecar_resp.json()
    assert sidecar_json["asset_id"] == asset_id


def test_thumbnail_job_idempotency(client, admin_headers, generated_video_file):
    init_resp = client.post(
        "/v1/ingest/init",
        json={
            "org_id": "org-test",
            "source_name": "thumbs.mp4",
            "content_length": generated_video_file.stat().st_size,
            "content_type": "video/mp4",
        },
        headers=admin_headers,
    )
    upload_uri = init_resp.json()["presigned"]["asset_uri"]
    target_path = uri_to_path(upload_uri)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(generated_video_file.read_bytes())

    commit_resp = client.post(
        "/v1/ingest/commit",
        json={
            "org_id": "org-test",
            "upload_id": init_resp.json()["upload_id"],
            "source_uri": upload_uri,
        },
        headers=admin_headers,
    )
    asset_id = commit_resp.json()["asset_id"]

    key = "thumb-job"
    first_resp = client.post(
        f"/v1/assets/{asset_id}/thumbnails",
        json={"org_id": "org-test", "source_uri": upload_uri},
        headers={**admin_headers, "Idempotency-Key": key},
    )
    assert first_resp.status_code == 202
    job_id = first_resp.json()["job_id"]

    second_resp = client.post(
        f"/v1/assets/{asset_id}/thumbnails",
        json={"org_id": "org-test", "source_uri": upload_uri},
        headers={**admin_headers, "Idempotency-Key": key},
    )
    assert second_resp.status_code == 202
    assert second_resp.json()["job_id"] == job_id

    conflict_resp = client.post(
        f"/v1/assets/{asset_id}/thumbnails",
        json={"org_id": "org-test", "source_uri": upload_uri, "weak_threshold_bytes": 1},
        headers={**admin_headers, "Idempotency-Key": key},
    )
    assert conflict_resp.status_code == 409
