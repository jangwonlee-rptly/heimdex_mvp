import os
import subprocess
from pathlib import Path

def run(cmd):
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8", errors="ignore")
        return 0, out
    except subprocess.CalledProcessError as e:
        return e.returncode, e.output.decode("utf-8", errors="ignore")

def print_first_line(label, text):
    first = text.splitlines()[0] if text.strip() else "(no output)"
    print(f"{label}: {first}")

# Check ffmpeg
code, out = run(["ffmpeg", "-version"])
print_first_line("ffmpeg", out)

# Check ffprobe
code_p, out_p = run(["ffprobe", "-version"])
print_first_line("ffprobe", out_p)

sample = os.getenv("SAMPLE_MEDIA")
if sample and Path(sample).exists():
    print(f"\nInspecting sample: {sample}")
    # Quick probe
    code3, out3 = run(["ffprobe", "-hide_banner", "-v", "error", "-show_format", "-show_streams", sample])
    print(out3[:1000])
else:
    print("\nNo SAMPLE_MEDIA provided or file not found. Set SAMPLE_MEDIA in .env to a valid path under /workspace.")