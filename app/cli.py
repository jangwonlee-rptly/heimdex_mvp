from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console

from .ingest.asset_id import AssetIdentity, derive_local_asset_identity
from .ingest.ffprobe_parser import SourceContext, parse_ffprobe_json
from .ingest.sidecar_schema import SchemaPath, export_schema
from .ingest.thumbnails import render_thumbnails

console = Console()


def main(argv: Optional[list[str]] = None) -> None:
    """The main entry point for the CLI.

    Args:
        argv: The command-line arguments.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "check", False):
        _run_environment_check()
        return

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI.

    Returns:
        The argument parser.
    """
    parser = argparse.ArgumentParser(description="Heimdex ingest developer CLI")
    parser.add_argument("--check", action="store_true", help="Validate presence of ffmpeg/ffprobe dependencies")

    subparsers = parser.add_subparsers(dest="command")

    probe_parser = subparsers.add_parser("probe", help="Run ffprobe and print the normalised sidecar JSON")
    probe_parser.add_argument("--file", required=True, help="Path to the source media file")
    probe_parser.add_argument(
        "--weak-threshold-bytes",
        type=int,
        default=1_000_000_000,
        help="Use weak hashing when the file exceeds this size (default 1GB).",
    )
    probe_parser.set_defaults(func=_cmd_probe)

    thumbs_parser = subparsers.add_parser("thumbs", help="Generate thumbnails and print updated JSON")
    thumbs_parser.add_argument("--file", required=True, help="Path to the source media file")
    thumbs_parser.add_argument("--asset-id", required=True, help="Asset identifier to use for filesystem layout")
    thumbs_parser.add_argument(
        "--weak-threshold-bytes",
        type=int,
        default=1_000_000_000,
        help="Use weak hashing when the file exceeds this size (default 1GB).",
    )
    thumbs_parser.set_defaults(func=_cmd_thumbs)

    sidecar_parser = subparsers.add_parser("sidecar", help="Parse, generate thumbnails, and write the sidecar")
    sidecar_parser.add_argument("--file", required=True, help="Path to the source media file")
    sidecar_parser.add_argument("--asset-id", required=True, help="Asset identifier to use for filesystem layout")
    sidecar_parser.add_argument(
        "--weak-threshold-bytes",
        type=int,
        default=1_000_000_000,
        help="Use weak hashing when the file exceeds this size (default 1GB).",
    )
    sidecar_parser.add_argument(
        "--derived-root",
        default="derived",
        help="Root directory for derived artefacts (sidecars, thumbnails, schema).",
    )
    sidecar_parser.set_defaults(func=_cmd_sidecar)
    return parser


def _cmd_probe(args: argparse.Namespace) -> None:
    """Run ffprobe and print the normalised sidecar JSON.

    Args:
        args: The command-line arguments.
    """
    media_path = Path(args.file).expanduser().resolve()
    sidecar = _build_sidecar_for_file(media_path, max_bytes_for_strong_hash=args.weak_threshold_bytes)
    console.print_json(data=sidecar)


def _cmd_thumbs(args: argparse.Namespace) -> None:
    """Generate thumbnails and print updated JSON.

    Args:
        args: The command-line arguments.
    """
    media_path = Path(args.file).expanduser().resolve()
    sidecar = _build_sidecar_for_file(
        media_path,
        asset_id_override=args.asset_id,
        max_bytes_for_strong_hash=args.weak_threshold_bytes,
    )
    updated = render_thumbnails(str(media_path), sidecar, Path("derived"))
    console.print_json(data=updated)


def _cmd_sidecar(args: argparse.Namespace) -> None:
    """Parse, generate thumbnails, and write the sidecar.

    Args:
        args: The command-line arguments.
    """
    media_path = Path(args.file).expanduser().resolve()
    derived_root = Path(args.derived_root).expanduser().resolve()

    derived_root.mkdir(parents=True, exist_ok=True)
    schema_path = export_schema(derived_root / SchemaPath.relative_to("derived"))

    console.print(f"[dim]Schema ensured at {schema_path}[/]")

    sidecar = _build_sidecar_for_file(
        media_path,
        asset_id_override=args.asset_id,
        max_bytes_for_strong_hash=args.weak_threshold_bytes,
    )
    updated = render_thumbnails(str(media_path), sidecar, derived_root)

    sidecars_dir = derived_root / "sidecars"
    sidecars_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = sidecars_dir / f"{updated['asset_id']}.vna.json"
    sidecar_path.write_text(json.dumps(updated, indent=2, sort_keys=True))

    console.print_json(data=updated)
    console.print(f"[green]Sidecar written to {sidecar_path}[/]")


def _build_sidecar_for_file(
    media_path: Path,
    *,
    asset_id_override: Optional[str] = None,
    max_bytes_for_strong_hash: Optional[int] = None,
):
    """Build the sidecar for a given media file.

    Args:
        media_path: The path to the media file.
        asset_id_override: An optional asset ID to override the derived one.
        max_bytes_for_strong_hash: The maximum file size for which to compute a strong hash.

    Returns:
        The sidecar dictionary.
    """
    if not media_path.exists():
        console.print(f"[red]File not found: {media_path}[/]")
        sys.exit(2)

    identity = derive_local_asset_identity(media_path, max_bytes_for_strong_hash=max_bytes_for_strong_hash)
    asset_id = asset_id_override or identity.asset_id
    source_ctx = _build_local_source_context(media_path, identity, asset_id_override=asset_id)

    raw = _run_ffprobe(media_path)
    sidecar = parse_ffprobe_json(raw, source_ctx)
    if asset_id_override and sidecar["asset_id"] != asset_id_override:
        sidecar["asset_id"] = asset_id_override
    return sidecar


def _build_local_source_context(
    media_path: Path,
    identity: AssetIdentity,
    *,
    asset_id_override: Optional[str] = None,
) -> SourceContext:
    """Build the source context for a local media file.

    Args:
        media_path: The path to the media file.
        identity: The asset identity.
        asset_id_override: An optional asset ID to override the derived one.

    Returns:
        The source context.
    """
    stat = media_path.stat()
    created_time = _stat_birthtime(stat)
    modified_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    return SourceContext(
        type="local",
        uri=media_path.resolve().as_uri(),
        filename=media_path.name,
        size_bytes=stat.st_size,
        asset_id=asset_id_override or identity.asset_id,
        created_time=created_time,
        modified_time=modified_time,
        hash=identity.hash,
        hash_quality=identity.hash_quality,
    )


def _stat_birthtime(stat_result: os.stat_result) -> Optional[datetime]:
    """Get the birth time of a file from a stat result.

    Args:
        stat_result: The stat result.

    Returns:
        The birth time, or None if it's not available.
    """
    birth_time = getattr(stat_result, "st_birthtime", None)
    if birth_time is not None:
        return datetime.fromtimestamp(birth_time, tz=timezone.utc)
    return None


def _run_ffprobe(target: Path) -> dict:
    """Run ffprobe on a media file.

    Args:
        target: The path to the media file.

    Returns:
        The ffprobe output as a dictionary.
    """
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
    try:
        proc = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]ffprobe failed:[/] {exc.stderr.strip()}")
        sys.exit(3)
    return json.loads(proc.stdout)


def _run_environment_check() -> None:
    """Check for the presence of required external dependencies."""
    checks = {
        "ffmpeg": ["ffmpeg", "-version"],
        "ffprobe": ["ffprobe", "-version"],
        "PySceneDetect": ["python", "-m", "scenedetect", "--version"],
    }
    results = {}
    for label, cmd in checks.items():
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            results[label] = True
        except Exception:
            results[label] = False

    console.rule("[bold]Environment Check")
    for label, ok in results.items():
        console.print(f"[bold]{label}[/]: {'✅' if ok else '❌'}")

    if not all(results.values()):
        console.print("[red]Missing dependencies detected. Consult Dockerfile/pyproject.toml.[/]")
        sys.exit(1)
    console.print("[green]Environment looks good![/]")


if __name__ == "__main__":
    main()
