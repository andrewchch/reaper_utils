"""
reaper_project.py - High-level model for Reaper project files.

Provides dataclasses that represent the logical structure of a Reaper project
(tracks, items, media sources) built on top of the raw RppNode tree produced
by reaper_parser.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from reaper_parser import RppNode, parse_rpp, parse_rpp_file


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MediaSource:
    """Represents a <SOURCE> block (audio or MIDI)."""

    source_type: str          # e.g. 'WAVE', 'MIDI', 'VORBIS', 'FLAC', ...
    file_path: Optional[str]  # Absolute or relative file path, or None for inline MIDI
    is_embedded: bool         # True when data is inline (no FILE attribute)
    node: RppNode             # Raw node for advanced access


@dataclass
class MediaItem:
    """Represents an <ITEM> block inside a track."""

    position: float       # Start position in seconds
    length: float         # Length in seconds
    name: Optional[str]   # Item name (SOFFS / NAME param)
    sources: List[MediaSource] = field(default_factory=list)
    node: RppNode = field(repr=False, default=None)


@dataclass
class Track:
    """Represents a <TRACK> block in the project."""

    name: str
    index: int                         # 0-based track index
    items: List[MediaItem] = field(default_factory=list)
    children: List["Track"] = field(default_factory=list)   # folder children
    node: RppNode = field(repr=False, default=None)


@dataclass
class ReaperProject:
    """Top-level representation of a Reaper project."""

    version: str                    # e.g. '0.1'
    app_version: str                # e.g. '6.80/win64'
    tracks: List[Track] = field(default_factory=list)
    source_path: Optional[str] = None   # path to the .rpp file, if loaded from disk
    node: RppNode = field(repr=False, default=None)

    # -----------------------------------------------------------------------
    # Convenience helpers
    # -----------------------------------------------------------------------

    def all_items(self) -> List[MediaItem]:
        """Return every MediaItem from every track (flat list)."""
        items: List[MediaItem] = []
        for track in self.tracks:
            items.extend(track.items)
        return items

    def all_sources(self) -> List[MediaSource]:
        """Return every MediaSource from every item in the project."""
        sources: List[MediaSource] = []
        for item in self.all_items():
            sources.extend(item.sources)
        return sources

    def media_files(self) -> List[str]:
        """
        Return a sorted list of unique file paths for all external media sources.
        Paths are as stored in the project (may be relative or absolute).
        """
        paths = {
            src.file_path
            for src in self.all_sources()
            if src.file_path is not None
        }
        return sorted(paths)

    def resolve_media_files(self) -> List[str]:
        """
        Return sorted absolute paths for all external media sources,
        resolving relative paths against the project directory.

        Requires that ``source_path`` is set.
        """
        if self.source_path is None:
            raise ValueError("source_path must be set to resolve relative media paths")
        project_dir = os.path.dirname(os.path.abspath(self.source_path))
        resolved = set()
        for src in self.all_sources():
            if src.file_path is not None:
                if os.path.isabs(src.file_path):
                    resolved.add(src.file_path)
                else:
                    resolved.add(os.path.normpath(os.path.join(project_dir, src.file_path)))
        return sorted(resolved)

    def missing_media_files(self) -> List[str]:
        """
        Return absolute paths of media files that are referenced but do not
        exist on disk.  Requires ``source_path`` to be set.
        """
        return [p for p in self.resolve_media_files() if not os.path.exists(p)]


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------

def _parse_float(value: Optional[str], default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _build_source(node: RppNode) -> MediaSource:
    source_type = node.attribs[0].upper() if node.attribs else "UNKNOWN"
    file_tokens = node.get_param("FILE")
    file_path = file_tokens[0] if file_tokens else None
    has_data = node.get_param("HASDATA")
    is_embedded = (file_path is None) and (has_data is not None)
    return MediaSource(
        source_type=source_type,
        file_path=file_path,
        is_embedded=is_embedded,
        node=node,
    )


def _build_item(node: RppNode) -> MediaItem:
    pos_tokens = node.get_param("POSITION")
    len_tokens = node.get_param("LENGTH")
    name_tokens = node.get_param("NAME")

    position = _parse_float(pos_tokens[0] if pos_tokens else None)
    length = _parse_float(len_tokens[0] if len_tokens else None)
    name = name_tokens[0] if name_tokens else None

    sources = [_build_source(s) for s in node.find_all("SOURCE")]
    return MediaItem(
        position=position,
        length=length,
        name=name,
        sources=sources,
        node=node,
    )


def _build_track(node: RppNode, index: int) -> Track:
    name_tokens = node.get_param("NAME")
    name = name_tokens[0] if name_tokens else f"Track {index + 1}"
    items = [_build_item(i) for i in node.find_all("ITEM")]
    return Track(name=name, index=index, items=items, node=node)


def build_project(root: RppNode, source_path: Optional[str] = None) -> ReaperProject:
    """
    Build a :class:`ReaperProject` from a parsed :class:`RppNode` tree.

    Args:
        root:        The root node returned by :func:`~reaper_parser.parse_rpp`.
        source_path: Optional path to the .rpp file (used for resolving relative
                     media paths).

    Returns:
        A fully populated :class:`ReaperProject`.
    """
    version = root.attribs[0] if len(root.attribs) > 0 else ""
    app_version = root.attribs[1] if len(root.attribs) > 1 else ""

    tracks = [
        _build_track(node, idx)
        for idx, node in enumerate(root.find_all("TRACK"))
    ]

    return ReaperProject(
        version=version,
        app_version=app_version,
        tracks=tracks,
        source_path=source_path,
        node=root,
    )


def load_project(path: str) -> ReaperProject:
    """
    Load a Reaper project file from disk and return a :class:`ReaperProject`.

    Args:
        path: Filesystem path to a .rpp file.

    Returns:
        A fully populated :class:`ReaperProject` with ``source_path`` set.
    """
    root = parse_rpp_file(path)
    return build_project(root, source_path=path)
