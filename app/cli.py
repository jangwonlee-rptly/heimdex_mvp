from __future__ import annotations
import subprocess
import sys
from rich.console import Console

console = Console()

def check_binary(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def main():
    mode = "--check" if "--check" in sys.argv else None

    if mode == "--check":
        ok_ffmpeg = check_binary(["ffmpeg", "-version"])
        ok_ffprobe = check_binary(["ffprobe", "-version"])
        try:
            import scenedetect  # PySceneDetect
            ok_psd = True
        except Exception:
            ok_psd = False

        console.rule("[bold]Environment Check")
        console.print(f"[bold]ffmpeg[/]:     {'✅' if ok_ffmpeg else '❌'}")
        console.print(f"[bold]ffprobe[/]:    {'✅' if ok_ffprobe else '❌'}")
        console.print(f"[bold]PySceneDetect[/]: {'✅' if ok_psd else '❌'}")

        if not (ok_ffmpeg and ok_ffprobe and ok_psd):
            console.print("[red]One or more tools are missing. See Dockerfile/pyproject.toml.[/]")
            sys.exit(1)
        console.print("[green]Environment looks good![/]")
        return

    console.print("[bold]VNA Dev CLI[/] — add commands here (ingest, detect-scenes, etc.)")

if __name__ == "__main__":
    main()