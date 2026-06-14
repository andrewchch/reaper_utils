"""
reaper_media.py - Utilities for working with media files in Reaper projects.

Provides functions to:
- List all media files referenced by a project
- Check which files are present or missing on disk
- Copy or move media files alongside a project
- Generate a report of media usage
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from reaper_project import ReaperProject, MediaSource, load_project


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MediaFileInfo:
    """Information about a single media file referenced in a project."""

    path: str              # Absolute path (resolved against project dir)
    raw_path: str          # Path as stored in the project file
    source_type: str       # e.g. 'WAVE', 'MIDI', 'VORBIS', 'FLAC'
    exists: bool           # Whether the file exists on disk
    size_bytes: Optional[int]  # File size, or None if file does not exist
    track_names: List[str]     # Names of tracks that reference this file


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def list_media_files(project: ReaperProject) -> List[MediaFileInfo]:
    """
    Return a list of :class:`MediaFileInfo` for every external media file
    referenced in *project*.

    Files referenced by more than one item are deduplicated; the
    ``track_names`` field will contain all referencing track names.

    Args:
        project: A loaded :class:`~reaper_project.ReaperProject`.

    Returns:
        A list of :class:`MediaFileInfo` sorted by resolved absolute path.
    """
    if project.source_path is None:
        raise ValueError("project.source_path must be set to resolve media paths")

    project_dir = os.path.dirname(os.path.abspath(project.source_path))

    # Build a mapping: resolved_path -> (raw_path, source_type, set of track names)
    info_map: Dict[str, Tuple[str, str, set]] = {}

    for track in project.tracks:
        for item in track.items:
            for src in item.sources:
                if src.file_path is None:
                    continue  # Skip embedded/inline sources
                raw = src.file_path
                if os.path.isabs(raw):
                    resolved = raw
                else:
                    resolved = os.path.normpath(os.path.join(project_dir, raw))

                if resolved not in info_map:
                    info_map[resolved] = (raw, src.source_type, set())
                info_map[resolved][2].add(track.name)

    results: List[MediaFileInfo] = []
    for resolved, (raw, src_type, track_names) in sorted(info_map.items()):
        exists = os.path.isfile(resolved)
        size = os.path.getsize(resolved) if exists else None
        results.append(MediaFileInfo(
            path=resolved,
            raw_path=raw,
            source_type=src_type,
            exists=exists,
            size_bytes=size,
            track_names=sorted(track_names),
        ))

    return results


def check_missing_media(project: ReaperProject) -> List[MediaFileInfo]:
    """
    Return only the :class:`MediaFileInfo` entries for files that are
    referenced in the project but do not exist on disk.

    Args:
        project: A loaded :class:`~reaper_project.ReaperProject`.

    Returns:
        A list of missing :class:`MediaFileInfo` objects.
    """
    return [info for info in list_media_files(project) if not info.exists]


def copy_media_to_directory(
    project: ReaperProject,
    dest_dir: str,
    *,
    skip_missing: bool = False,
    overwrite: bool = False,
) -> List[str]:
    """
    Copy all external media files referenced in *project* into *dest_dir*.

    Flat copy: all files are placed directly in *dest_dir* (sub-directory
    structure is not preserved).

    Args:
        project:      A loaded :class:`~reaper_project.ReaperProject`.
        dest_dir:     Destination directory (created if it does not exist).
        skip_missing: If True, silently skip files that do not exist on disk.
                      If False (default), raise :class:`FileNotFoundError`.
        overwrite:    If True, overwrite existing files in *dest_dir*.
                      If False (default), skip files that already exist there.

    Returns:
        A list of destination file paths that were actually copied.

    Raises:
        FileNotFoundError: If a referenced file is missing and *skip_missing*
                           is False.
    """
    os.makedirs(dest_dir, exist_ok=True)
    media = list_media_files(project)
    copied: List[str] = []

    for info in media:
        if not info.exists:
            if skip_missing:
                continue
            raise FileNotFoundError(
                f"Media file not found: {info.path!r} "
                f"(referenced as {info.raw_path!r})"
            )
        dest = os.path.join(dest_dir, os.path.basename(info.path))
        if os.path.exists(dest) and not overwrite:
            continue
        shutil.copy2(info.path, dest)
        copied.append(dest)

    return copied


def media_report(project: ReaperProject) -> str:
    """
    Generate a human-readable text report of media file usage for *project*.

    Args:
        project: A loaded :class:`~reaper_project.ReaperProject`.

    Returns:
        A formatted multi-line string.
    """
    media = list_media_files(project)
    if not media:
        return "No external media files referenced in this project.\n"

    lines: List[str] = []
    lines.append(f"Media files in project: {project.source_path or '(unknown)'}")
    lines.append(f"Total: {len(media)} file(s)")
    lines.append("")

    present = [m for m in media if m.exists]
    missing = [m for m in media if not m.exists]

    lines.append(f"  Present: {len(present)}")
    lines.append(f"  Missing: {len(missing)}")
    lines.append("")

    if present:
        lines.append("Present files:")
        for info in present:
            size_str = f"{info.size_bytes:,} bytes" if info.size_bytes is not None else "?"
            lines.append(f"  [{info.source_type:5s}] {info.path}")
            lines.append(f"         Size: {size_str}")
            lines.append(f"         Tracks: {', '.join(info.track_names)}")
        lines.append("")

    if missing:
        lines.append("Missing files:")
        for info in missing:
            lines.append(f"  [{info.source_type:5s}] {info.path}")
            lines.append(f"         Raw path: {info.raw_path!r}")
            lines.append(f"         Tracks: {', '.join(info.track_names)}")
        lines.append("")

    return "\n".join(lines)
