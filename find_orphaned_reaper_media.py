#!/usr/bin/env python3
"""Find audio/MIDI files in a directory that are not referenced by Reaper projects."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

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

REFERENCE_PATTERN = re.compile(r'"([^"\r\n]+\.[A-Za-z0-9]+)"')


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
        if not (selected_name.endswith(".rpp") or selected_name.endswith(".rpp.bak")):
            raise ValueError("project_file must be a .rpp or .rpp.bak file")
        if not selected.is_file():
            raise FileNotFoundError(f"project file not found: {selected}")
        if ignore_backups and selected_name.endswith(".rpp.bak"):
            return []
        return [selected]

    project_files = sorted(start_directory.rglob("*.rpp"))
    if not ignore_backups:
        project_files.extend(sorted(start_directory.rglob("*.rpp.bak")))
    return [path.resolve() for path in project_files]


def _normalize_reference_path(value: str, project_dir: Path) -> Path:
    candidate = Path(value.replace("\\", os.sep))
    if candidate.is_absolute():
        return candidate.resolve()
    return (project_dir / candidate).resolve()


def collect_referenced_audio_files(project_files: list[Path], audio_types: set[str]) -> set[Path]:
    referenced: set[Path] = set()
    for project in project_files:
        content = project.read_text(encoding="utf-8", errors="ignore")
        for value in REFERENCE_PATTERN.findall(content):
            normalized = _normalize_reference_path(value, project.parent)
            if normalized.suffix.lower() in audio_types:
                referenced.add(normalized)
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

    selected_audio_types = parse_audio_types(audio_types)
    audio_files = collect_audio_files(root, selected_audio_types)
    project_files = collect_project_files(root, ignore_backups, project_file)
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
    destination_dir = recycle_bin_directory()
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = destination_dir / path.name
    if destination.exists():
        stem = path.stem
        suffix = path.suffix
        index = 1
        while True:
            candidate = destination_dir / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                destination = candidate
                break
            index += 1
    return Path(shutil.move(str(path), str(destination)))


def print_report(audio_files: set[Path], project_files: list[Path], orphaned: set[Path]) -> None:
    print(f"Audio/MIDI files found: {len(audio_files)}")
    print(f"Project files scanned: {len(project_files)}")
    print(f"Orphaned files: {len(orphaned)}")
    if orphaned:
        for path in sorted(orphaned):
            print(path)


def maybe_delete_orphaned(orphaned: set[Path], delete_orphaned_audio_files: bool) -> None:
    if not delete_orphaned_audio_files or not orphaned:
        return
    response = input("Delete orphaned files to recycle bin? [y/N]: ").strip().lower()
    if response not in {"y", "yes"}:
        print("Deletion canceled.")
        return
    for path in sorted(orphaned):
        moved_to = move_to_recycle_bin(path)
        print(f"Moved to recycle bin: {path} -> {moved_to}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find audio/MIDI files not referenced in Reaper .rpp/.rpp.bak project files."
    )
    parser.add_argument("start_directory", help="Directory to scan recursively for audio/MIDI files.")
    parser.add_argument(
        "--project_file",
        help="Optional single .rpp or .rpp.bak project file to scan for references.",
    )
    parser.add_argument(
        "--audio_types",
        help='Comma-delimited extensions, e.g. "wav,mid". Defaults to common audio + MIDI types.',
    )
    parser.add_argument(
        "--ignore_backups",
        action="store_true",
        help="Ignore .rpp.bak files when finding project files.",
    )
    parser.add_argument(
        "--delete_orphaned_audio_files",
        action="store_true",
        help="Prompt to move orphaned files to the recycle bin.",
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
    print_report(audio_files, project_files, orphaned)
    maybe_delete_orphaned(orphaned, args.delete_orphaned_audio_files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
