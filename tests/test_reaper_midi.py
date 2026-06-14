"""
Tests for reaper_midi.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from reaper_parser import parse_rpp
from reaper_project import build_project
from reaper_midi import (
    parse_inline_midi,
    get_inline_midi_sources,
    get_external_midi_sources,
    midi_summary,
    InlineMidiSource,
    MidiEvent,
)


# ---------------------------------------------------------------------------
# Sample RPP text
# ---------------------------------------------------------------------------

INLINE_MIDI_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  <TRACK {GUID-1}
    NAME "Piano"
    <ITEM
      POSITION 0
      LENGTH 2.0
      <SOURCE MIDI
        HASDATA 1 960 QN
        E 0 90 3c 64
        E 480 80 3c 00
        E 480 90 40 64
        E 480 80 40 00
      >
    >
  >
>
"""

EXTERNAL_MIDI_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  <TRACK {GUID-2}
    NAME "Bass"
    <ITEM
      POSITION 0
      LENGTH 8.0
      <SOURCE MIDI
        FILE "midi/bass.mid"
      >
    >
  >
>
"""

MIXED_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  <TRACK {GUID-1}
    NAME "Piano"
    <ITEM
      POSITION 0
      LENGTH 2.0
      <SOURCE MIDI
        HASDATA 1 480 QN
        E 0 90 3c 7f
        E 240 80 3c 00
      >
    >
  >
  <TRACK {GUID-2}
    NAME "Bass"
    <ITEM
      POSITION 0
      LENGTH 8.0
      <SOURCE MIDI
        FILE "midi/bass.mid"
      >
    >
  >
>
"""

NO_MIDI_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  <TRACK {GUID-3}
    NAME "Drums"
    <ITEM
      POSITION 0
      LENGTH 4.5
      <SOURCE WAVE
        FILE "audio/kick.wav"
      >
    >
  >
>
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _project(rpp_text: str):
    root = parse_rpp(rpp_text)
    return build_project(root)


# ---------------------------------------------------------------------------
# Tests: parse_inline_midi
# ---------------------------------------------------------------------------

class TestParseInlineMidi:
    def test_returns_none_for_external(self):
        project = _project(EXTERNAL_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        assert result is None

    def test_returns_inline_midi_source(self):
        project = _project(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        assert isinstance(result, InlineMidiSource)

    def test_ppq(self):
        project = _project(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        assert result.ppq == 960

    def test_event_count(self):
        project = _project(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        assert len(result.events) == 4

    def test_first_event(self):
        project = _project(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        event = result.events[0]
        assert event.delta_ticks == 0
        assert event.status == 0x90   # note-on
        assert event.data1 == 0x3c   # middle C
        assert event.data2 == 0x64   # velocity 100

    def test_note_off_event(self):
        project = _project(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        event = result.events[1]
        assert event.status == 0x80  # note-off
        assert event.data1 == 0x3c

    def test_note_count(self):
        project = _project(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        # 2 note-on events (status 0x90, velocity > 0)
        assert result.note_count() == 2

    def test_channel_numbers(self):
        project = _project(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        # All events are on channel 1 (0x90 & 0x0F == 0 -> channel 1)
        assert result.channel_numbers() == [1]

    def test_duration_ticks(self):
        project = _project(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        # 0 + 480 + 480 + 480 = 1440
        assert result.duration_ticks() == 1440

    def test_mixed_ppq(self):
        project = _project(MIXED_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        assert result.ppq == 480

    def test_note_count_zero_for_note_offs(self):
        project = _project(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        result = parse_inline_midi(source.node)
        # Only count note-ons with velocity > 0
        note_ons = [e for e in result.events if (e.status & 0xF0) == 0x90 and e.data2 > 0]
        assert len(note_ons) == 2


# ---------------------------------------------------------------------------
# Tests: get_inline_midi_sources
# ---------------------------------------------------------------------------

class TestGetInlineMidiSources:
    def test_finds_inline_midi(self):
        project = _project(INLINE_MIDI_PROJECT)
        sources = get_inline_midi_sources(project)
        assert len(sources) == 1

    def test_track_name(self):
        project = _project(INLINE_MIDI_PROJECT)
        track_name, _ = get_inline_midi_sources(project)[0]
        assert track_name == "Piano"

    def test_no_inline_for_external(self):
        project = _project(EXTERNAL_MIDI_PROJECT)
        sources = get_inline_midi_sources(project)
        assert sources == []

    def test_mixed_project(self):
        project = _project(MIXED_PROJECT)
        sources = get_inline_midi_sources(project)
        assert len(sources) == 1
        assert sources[0][0] == "Piano"

    def test_no_midi(self):
        project = _project(NO_MIDI_PROJECT)
        sources = get_inline_midi_sources(project)
        assert sources == []


# ---------------------------------------------------------------------------
# Tests: get_external_midi_sources
# ---------------------------------------------------------------------------

class TestGetExternalMidiSources:
    def test_finds_external_midi(self):
        project = _project(EXTERNAL_MIDI_PROJECT)
        sources = get_external_midi_sources(project)
        assert len(sources) == 1

    def test_track_name(self):
        project = _project(EXTERNAL_MIDI_PROJECT)
        track_name, src = get_external_midi_sources(project)[0]
        assert track_name == "Bass"
        assert src.file_path == "midi/bass.mid"

    def test_no_external_for_inline(self):
        project = _project(INLINE_MIDI_PROJECT)
        sources = get_external_midi_sources(project)
        assert sources == []

    def test_mixed_project(self):
        project = _project(MIXED_PROJECT)
        sources = get_external_midi_sources(project)
        assert len(sources) == 1
        assert sources[0][0] == "Bass"

    def test_no_midi(self):
        project = _project(NO_MIDI_PROJECT)
        sources = get_external_midi_sources(project)
        assert sources == []


# ---------------------------------------------------------------------------
# Tests: midi_summary
# ---------------------------------------------------------------------------

class TestMidiSummary:
    def test_summary_contains_track_name(self):
        project = _project(INLINE_MIDI_PROJECT)
        summary = midi_summary(project)
        assert "Piano" in summary

    def test_summary_inline_count(self):
        project = _project(INLINE_MIDI_PROJECT)
        summary = midi_summary(project)
        assert "Inline MIDI sources" in summary or "inline" in summary.lower()

    def test_summary_external_file(self):
        project = _project(EXTERNAL_MIDI_PROJECT)
        summary = midi_summary(project)
        assert "bass.mid" in summary

    def test_summary_mixed(self):
        project = _project(MIXED_PROJECT)
        summary = midi_summary(project)
        assert "Piano" in summary
        assert "Bass" in summary

    def test_summary_no_midi(self):
        project = _project(NO_MIDI_PROJECT)
        summary = midi_summary(project)
        assert "0" in summary
