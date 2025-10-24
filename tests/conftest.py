import pytest
from pathlib import Path
import subprocess

@pytest.fixture(scope="session")
def generated_video_file(tmp_path_factory) -> Path:
    """
    Generates a small, valid MP4 video file for testing in a temporary directory.
    """
    video_path = tmp_path_factory.mktemp("data") / "test_video.mp4"

    # Generate a 1-second video with a solid color
    command = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "color=c=black:s=128x72:r=30",
        "-t", "1",
        "-pix_fmt", "yuv420p",
        str(video_path)
    ]
    subprocess.run(command, check=True, capture_output=True)
    return video_path
