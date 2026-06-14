"""
reaper_midi.py - Utilities for inspecting MIDI data in Reaper projects.

Reaper can store MIDI either as:
  1. External .mid files referenced by a FILE attribute inside a <SOURCE MIDI> block.
  2. Inline (embedded) MIDI stored directly inside a <SOURCE MIDI> block as
     Reaper's own event format (HASDATA lines followed by E/X/em/etc. lines).

This module provides helpers for both cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from reaper_parser import RppNode
from reaper_project import ReaperProject, MediaSource


# ---------------------------------------------------------------------------
# Inline MIDI event model
# ---------------------------------------------------------------------------

# Reaper inline MIDI event types found in <SOURCE MIDI> blocks:
#   E  - regular MIDI event
#   e  - extra (continuation?) event
#   X  - SYSEX
#   em - meta event
#   Em - meta event (alternate)

@dataclass
class MidiEvent:
    """A single MIDI event from an inline <SOURCE MIDI> block."""

    delta_ticks: int      # Tick offset from the previous event
    status: int           # MIDI status byte (e.g. 0x90 = note-on)
    data1: int            # First data byte
    data2: int            # Second data byte (0 for 1-byte messages)
    raw_line: str         # Original line as it appeared in the project file


@dataclass
class InlineMidiSource:
    """An inline (embedded) MIDI source parsed from a <SOURCE MIDI> block."""

    ppq: int                       # Pulses per quarter-note (from HASDATA)
    events: List[MidiEvent] = field(default_factory=list)
    node: RppNode = field(repr=False, default=None)

    def note_count(self) -> int:
        """Return the number of note-on events (status 0x90, velocity > 0)."""
        return sum(
            1 for e in self.events
            if (e.status & 0xF0) == 0x90 and e.data2 > 0
        )

    def channel_numbers(self) -> List[int]:
        """Return a sorted list of unique MIDI channel numbers (1-based) used."""
        channels = {(e.status & 0x0F) + 1 for e in self.events if e.status >= 0x80}
        return sorted(channels)

    def duration_ticks(self) -> int:
        """Return the total duration in ticks (sum of all delta values)."""
        return sum(e.delta_ticks for e in self.events)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_hex(value: str, default: int = 0) -> int:
    try:
        return int(value, 16)
    except (ValueError, TypeError):
        return default


def _parse_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_inline_midi(node: RppNode) -> Optional[InlineMidiSource]:
    """
    Parse an inline MIDI source from a ``<SOURCE MIDI>`` :class:`~reaper_parser.RppNode`.

    Returns ``None`` if the node does not contain inline MIDI data
    (i.e. it references an external file instead).

    Args:
        node: A ``<SOURCE MIDI>`` node from the parsed project tree.

    Returns:
        An :class:`InlineMidiSource` or ``None``.
    """
    has_data = node.get_param("HASDATA")
    if has_data is None:
        return None

    # HASDATA <flag> <ppq> QN
    ppq = _parse_int(has_data[1]) if len(has_data) > 1 else 960
    source = InlineMidiSource(ppq=ppq, node=node)

    for tokens in node.params:
        if not tokens:
            continue
        event_type = tokens[0]
        if event_type not in ("E", "e", "X", "em", "Em"):
            continue
        if len(tokens) < 2:
            continue

        delta = _parse_int(tokens[1])
        status = _parse_hex(tokens[2]) if len(tokens) > 2 else 0
        data1 = _parse_hex(tokens[3]) if len(tokens) > 3 else 0
        data2 = _parse_hex(tokens[4]) if len(tokens) > 4 else 0

        source.events.append(MidiEvent(
            delta_ticks=delta,
            status=status,
            data1=data1,
            data2=data2,
            raw_line=" ".join(tokens),
        ))

    return source


# ---------------------------------------------------------------------------
# Project-level helpers
# ---------------------------------------------------------------------------

def get_inline_midi_sources(project: ReaperProject) -> List[Tuple[str, InlineMidiSource]]:
    """
    Return all inline MIDI sources found in *project*.

    Args:
        project: A loaded :class:`~reaper_project.ReaperProject`.

    Returns:
        A list of ``(track_name, InlineMidiSource)`` tuples.
    """
    results: List[Tuple[str, InlineMidiSource]] = []
    for track in project.tracks:
        for item in track.items:
            for src in item.sources:
                if src.source_type == "MIDI" and src.is_embedded:
                    parsed = parse_inline_midi(src.node)
                    if parsed is not None:
                        results.append((track.name, parsed))
    return results


def get_external_midi_sources(project: ReaperProject) -> List[Tuple[str, MediaSource]]:
    """
    Return all external MIDI file sources found in *project*.

    Args:
        project: A loaded :class:`~reaper_project.ReaperProject`.

    Returns:
        A list of ``(track_name, MediaSource)`` tuples where
        ``source.source_type == 'MIDI'`` and ``source.file_path`` is set.
    """
    results: List[Tuple[str, MediaSource]] = []
    for track in project.tracks:
        for item in track.items:
            for src in item.sources:
                if src.source_type == "MIDI" and src.file_path is not None:
                    results.append((track.name, src))
    return results


def midi_summary(project: ReaperProject) -> str:
    """
    Return a human-readable summary of all MIDI content in *project*.

    Args:
        project: A loaded :class:`~reaper_project.ReaperProject`.

    Returns:
        A formatted multi-line string.
    """
    inline = get_inline_midi_sources(project)
    external = get_external_midi_sources(project)

    lines: List[str] = []
    lines.append(f"MIDI summary for: {project.source_path or '(unknown)'}")
    lines.append(f"  Inline MIDI sources : {len(inline)}")
    lines.append(f"  External MIDI files : {len(external)}")
    lines.append("")

    if inline:
        lines.append("Inline MIDI:")
        for track_name, src in inline:
            lines.append(f"  Track: {track_name!r}")
            lines.append(f"    PPQ           : {src.ppq}")
            lines.append(f"    Events        : {len(src.events)}")
            lines.append(f"    Note-ons      : {src.note_count()}")
            lines.append(f"    Channels used : {src.channel_numbers()}")
            lines.append(f"    Duration (ticks): {src.duration_ticks()}")
        lines.append("")

    if external:
        lines.append("External MIDI files:")
        for track_name, src in external:
            lines.append(f"  Track: {track_name!r}")
            lines.append(f"    File: {src.file_path!r}")
        lines.append("")

    return "\n".join(lines)
