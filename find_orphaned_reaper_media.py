#!/usr/bin/env python3
"""Find audio/MIDI files in a directory that are not referenced by Reaper projects."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from tqdm import tqdm
from send2trash import send2trash

DEFAULT_AUDIO_TYPES = {
    ".wav",
    ".mp3",
    ".flac",
    ".aif",
    ".aiff",
    ".ogg",
    ".m4a",
    ".aac",
    ".wma",
    ".opus",
    ".alac",
    ".mid",
    ".midi",
}

REFERENCE_PATTERN = re.compile(r'"([^"\r\n]+)"')
MAX_RECYCLE_BIN_RENAME_ATTEMPTS = 10_000


def parse_audio_types(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set(DEFAULT_AUDIO_TYPES)
    parsed = set()
    for value in raw_value.split(","):
        value = value.strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = f".{value}"
        parsed.add(value)
    return parsed or set(DEFAULT_AUDIO_TYPES)


def collect_audio_files(start_directory: Path, audio_types: set[str]) -> set[Path]:
    files: set[Path] = set()
    for path in start_directory.rglob("*"):
        if path.is_file() and path.suffix.lower() in audio_types:
            files.add(path.resolve())
    return files


def collect_project_files(
    start_directory: Path, ignore_backups: bool, project_file: str | None = None
) -> list[Path]:
    if project_file:
        selected = Path(project_file).expanduser().resolve()
        selected_name = selected.name.lower()
        if not (selected_name.endswith(".rpp") or selected_name.endswith(".rpp-bak")):
            raise ValueError("project_file must be a .rpp or .rpp-bak file")
        if not selected.is_file():
            raise FileNotFoundError(f"project file not found: {selected}")
        if ignore_backups and selected_name.endswith(".rpp-bak"):
            return []
        return [selected]

    project_files = sorted(start_directory.rglob("*.rpp"))
    if not ignore_backups:
        project_files.extend(sorted(start_directory.rglob("*.rpp-bak")))
    return [path.resolve() for path in project_files]


def _normalize_reference_path(value: str, project_dir: Path) -> Path:
    candidate = Path(value.replace("\\", os.sep))
    if candidate.is_absolute():
        return candidate.resolve()
    return (project_dir / candidate).resolve()


def collect_project_audio_references(
    project_files: list[Path], audio_types: set[str]
) -> dict[Path, list[Path]]:
    references: dict[Path, set[Path]] = {}
    for project in tqdm(project_files, desc="Scanning projects for audio/MIDI references", unit="project"):
        project_references: set[Path] = set()
        content = project.read_text(encoding="utf-8", errors="replace")
        for value in REFERENCE_PATTERN.findall(content):
            normalized = _normalize_reference_path(value, project.parent)
            if normalized.suffix.lower() in audio_types:
                project_references.add(normalized)
        references[project] = project_references
    return {project: sorted(paths) for project, paths in references.items()}


def collect_referenced_audio_files(project_files: list[Path], audio_types: set[str]) -> set[Path]:
    referenced: set[Path] = set()
    for paths in tqdm(collect_project_audio_references(project_files, audio_types).values(), desc="Collecting referenced audio/MIDI files", unit="project"):
        referenced.update(paths)
    return referenced


def find_orphaned_audio_files(
    start_directory: str,
    project_file: str | None = None,
    audio_types: str | None = None,
    ignore_backups: bool = False,
) -> tuple[set[Path], list[Path], set[Path], set[Path]]:
    root = Path(start_directory).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"start_directory does not exist: {root}")

    # Display whether we are ignoring backup files or not
    if ignore_backups:
        print("Ignoring backup project files (.rpp-bak)")
    else:
        print("Including backup project files (.rpp-bak)")

    selected_audio_types = parse_audio_types(audio_types)
    audio_files = collect_audio_files(root, selected_audio_types)
    project_files = collect_project_files(root, ignore_backups, project_file)

    # Display the number of *.rpp and the number of *.rpp-bak files found
    rpp_count = sum(1 for p in project_files if p.suffix.lower() == ".rpp")
    bak_count = sum(1 for p in project_files if p.suffix.lower() == ".rpp-bak")
    print(f"Found {rpp_count} .rpp files and {bak_count} .rpp-bak files")

    referenced = collect_referenced_audio_files(project_files, selected_audio_types)
    orphaned = {audio for audio in audio_files if audio not in referenced}
    return audio_files, project_files, referenced, orphaned


def recycle_bin_directory(home_dir: Path | None = None, platform_name: str | None = None) -> Path:
    if platform_name is None:
        if os.name == "nt":
            platform_name = "windows"
        elif sys.platform == "darwin":
            platform_name = "darwin"
        else:
            platform_name = "linux"
    home = home_dir or Path.home()
    platform_name = platform_name.lower()
    if platform_name in {"nt", "windows"}:
        return home / "Recycle.Bin"
    if platform_name in {"darwin", "mac", "macos"}:
        return home / ".Trash"
    return home / ".local" / "share" / "Trash" / "files"


def move_to_recycle_bin(path: Path) -> Path:
    """
    destination_dir = recycle_bin_directory()
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = destination_dir / path.name
    if destination.exists():
        stem = path.stem
        suffix = path.suffix
        for index in range(1, MAX_RECYCLE_BIN_RENAME_ATTEMPTS + 1):
            candidate = destination_dir / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                destination = candidate
                break
        else:
            raise RuntimeError(f"could not find a free recycle bin name for {path}")
    return Path(shutil.move(str(path), str(destination)))
    """
    try:
        send2trash(str(path))
        return path
    except Exception as e:
        print(f"Error moving {path} to recycle bin: {e}")
        raise


def format_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024 or unit == "TB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024


def print_report(
    audio_files: set[Path],
    project_files: list[Path],
    orphaned: set[Path],
    project_references: Mapping[Path, Sequence[Path]] | None = None,
) -> None:
    print(f"Audio/MIDI files found: {len(audio_files)}")
    print(f"Project files scanned: {len(project_files)}")
    print(f"Orphaned files: {len(orphaned)}")
    if project_references is not None:
        for project in project_files:
            print(project)
            references = project_references.get(project, ())
            if references:
                for path in references:
                    print(f"  {path}")
            else:
                print("  (no audio/MIDI files referenced)")
    if orphaned:
        print("---------------\nOrphaned Files\n---------------")
        for path in sorted(orphaned):
            print(path)
        total_size = 0
        for path in orphaned:
            try:
                total_size += path.stat().st_size
            except FileNotFoundError:
                pass
        print(f"Total orphaned files size: {format_size(total_size)}")


def maybe_delete_orphaned(orphaned: set[Path], delete_orphaned_audio_files: bool) -> None:
    if not delete_orphaned_audio_files or not orphaned:
        return
    response = input("Delete orphaned files to recycle bin? [y/N]: ").strip().lower()
    if response not in {"y", "yes"}:
        print("Deletion canceled.")
        return
    for path in sorted(orphaned):
        moved_to = move_to_recycle_bin(path)
        print(f"Moved to recycle bin: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find audio/MIDI files not referenced in Reaper .rpp/.rpp-bak project files."
    )
    parser.add_argument("start_directory", help="Directory to scan recursively for audio/MIDI files.")
    parser.add_argument(
        "--project_file",
        help="Optional single .rpp or .rpp-bak project file to scan for references.",
    )
    parser.add_argument(
        "--audio_types",
        help='Comma-delimited extensions, e.g. "wav,mid". Defaults to common audio + MIDI types.',
    )
    parser.add_argument(
        "--ignore_backups",
        action="store_true",
        help="Ignore .rpp-bak files when finding project files.",
    )
    parser.add_argument(
        "--delete_orphaned_audio_files",
        action="store_true",
        help="Prompt to move orphaned files to the recycle bin.",
    )
    parser.add_argument(
        "--list_referenced_audio_files",
        action="store_true",
        help="List referenced audio/MIDI files for each scanned project file.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    audio_files, project_files, _referenced, orphaned = find_orphaned_audio_files(
        start_directory=args.start_directory,
        project_file=args.project_file,
        audio_types=args.audio_types,
        ignore_backups=args.ignore_backups,
    )
    project_references = None
    if args.list_referenced_audio_files:
        project_references = collect_project_audio_references(
            project_files, parse_audio_types(args.audio_types)
        )
    print_report(audio_files, project_files, orphaned, project_references=project_references)
    maybe_delete_orphaned(orphaned, args.delete_orphaned_audio_files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
