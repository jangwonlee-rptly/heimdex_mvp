import pytest
from app.main import _parse_frame_rate, _bitrate_to_kbps

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("30000/1001", 29.97),
        ("24/1", 24.0),
        ("0/0", None),
        ("N/A", None),
        (None, None),
        ("30/0", None),
        ("abc", None),
    ],
)
def test_parse_frame_rate(raw, expected):
    assert _parse_frame_rate(raw) == expected

@pytest.mark.parametrize(
    "value, expected",
    [
        ("1000", 1.0),
        ("2500000", 2500.0),
        ("0", 0.0),
        ("N/A", None),
        (None, None),
        ("abc", None),
    ],
)
def test_bitrate_to_kbps(value, expected):
    assert _bitrate_to_kbps(value) == expected

from app.main import _build_response
from app.schemas import MetadataResponse, StreamMetadata

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("app.main._run_ffprobe")
def test_extract_metadata_success(mock_run_ffprobe):
    mock_run_ffprobe.return_value = {
        "format": {
            "format_long_name": "QuickTime / MOV",
            "duration": "10.0",
            "bit_rate": "2000000",
            "size": "2500000",
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "bit_rate": "1800000",
                "avg_frame_rate": "30/1",
            }
        ],
    }
    with open("test.mov", "wb") as f:
        f.write(b"test")
    with open("test.mov", "rb") as f:
        response = client.post("/metadata", files={"file": ("test.mov", f, "video/quicktime")})
    assert response.status_code == 200
    assert response.json()["filename"] == "test.mov"


def test_build_response():
    ffprobe_data = {
        "format": {
            "format_long_name": "QuickTime / MOV",
            "duration": "10.0",
            "bit_rate": "2000000",
            "size": "2500000",
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "bit_rate": "1800000",
                "avg_frame_rate": "30/1",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
            },
        ],
    }
    expected = MetadataResponse(
        filename="test.mov",
        format_name="QuickTime / MOV",
        duration_seconds=10.0,
        bitrate_kbps=2000.0,
        size_bytes=2500000,
        streams=[
            StreamMetadata(
                index=0,
                codec_type="video",
                codec_name="h264",
                width=1920,
                height=1080,
                bitrate_kbps=1800.0,
                frame_rate=30.0,
            ),
            StreamMetadata(
                index=1,
                codec_type="audio",
                codec_name="aac",
                width=None,
                height=None,
                bitrate_kbps=None,
                frame_rate=None,
            ),
        ],
    )
    assert _build_response(ffprobe_data, "test.mov") == expected
