"""
Tests for reaper_project.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from reaper_parser import parse_rpp
from reaper_project import build_project, ReaperProject, Track, MediaItem, MediaSource


# ---------------------------------------------------------------------------
# Sample RPP snippets
# ---------------------------------------------------------------------------

SIMPLE_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  <TRACK {GUID-1}
    NAME "Drums"
    <ITEM
      POSITION 0
      LENGTH 4.5
      NAME "Kick loop"
      <SOURCE WAVE
        FILE "audio/kick.wav"
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
    <ITEM
      POSITION 8.0
      LENGTH 4.0
      <SOURCE WAVE
        FILE "audio/bass_sample.wav"
      >
    >
  >
>
"""

INLINE_MIDI_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  <TRACK {GUID-3}
    NAME "Piano"
    <ITEM
      POSITION 0
      LENGTH 2.0
      <SOURCE MIDI
        HASDATA 1 960 QN
        E 0 90 3c 64
        E 480 80 3c 00
      >
    >
  >
>
"""

NO_TRACKS_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  RIPPLE 0
>
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _build(rpp_text: str, source_path: str = None) -> ReaperProject:
    root = parse_rpp(rpp_text)
    return build_project(root, source_path=source_path)


# ---------------------------------------------------------------------------
# Tests: build_project
# ---------------------------------------------------------------------------

class TestBuildProject:
    def test_version_parsed(self):
        project = _build(SIMPLE_PROJECT)
        assert project.version == "0.1"
        assert project.app_version == "6.80/win64"

    def test_track_count(self):
        project = _build(SIMPLE_PROJECT)
        assert len(project.tracks) == 2

    def test_track_names(self):
        project = _build(SIMPLE_PROJECT)
        assert project.tracks[0].name == "Drums"
        assert project.tracks[1].name == "Bass"

    def test_track_indices(self):
        project = _build(SIMPLE_PROJECT)
        assert project.tracks[0].index == 0
        assert project.tracks[1].index == 1

    def test_item_counts(self):
        project = _build(SIMPLE_PROJECT)
        assert len(project.tracks[0].items) == 1
        assert len(project.tracks[1].items) == 2

    def test_item_position_and_length(self):
        project = _build(SIMPLE_PROJECT)
        item = project.tracks[0].items[0]
        assert item.position == pytest.approx(0.0)
        assert item.length == pytest.approx(4.5)

    def test_item_name(self):
        project = _build(SIMPLE_PROJECT)
        item = project.tracks[0].items[0]
        assert item.name == "Kick loop"

    def test_source_type_wave(self):
        project = _build(SIMPLE_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        assert source.source_type == "WAVE"
        assert source.file_path == "audio/kick.wav"
        assert not source.is_embedded

    def test_source_type_midi(self):
        project = _build(SIMPLE_PROJECT)
        source = project.tracks[1].items[0].sources[0]
        assert source.source_type == "MIDI"
        assert source.file_path == "midi/bass.mid"
        assert not source.is_embedded

    def test_embedded_midi_source(self):
        project = _build(INLINE_MIDI_PROJECT)
        source = project.tracks[0].items[0].sources[0]
        assert source.source_type == "MIDI"
        assert source.file_path is None
        assert source.is_embedded

    def test_no_tracks(self):
        project = _build(NO_TRACKS_PROJECT)
        assert project.tracks == []

    def test_source_path_stored(self):
        project = _build(SIMPLE_PROJECT, source_path="/projects/song.rpp")
        assert project.source_path == "/projects/song.rpp"


# ---------------------------------------------------------------------------
# Tests: ReaperProject helpers
# ---------------------------------------------------------------------------

class TestReaperProjectHelpers:
    def test_all_items(self):
        project = _build(SIMPLE_PROJECT)
        items = project.all_items()
        assert len(items) == 3

    def test_all_sources(self):
        project = _build(SIMPLE_PROJECT)
        sources = project.all_sources()
        assert len(sources) == 3

    def test_media_files(self):
        project = _build(SIMPLE_PROJECT)
        files = project.media_files()
        assert "audio/kick.wav" in files
        assert "midi/bass.mid" in files
        assert "audio/bass_sample.wav" in files

    def test_media_files_sorted(self):
        project = _build(SIMPLE_PROJECT)
        files = project.media_files()
        assert files == sorted(files)

    def test_media_files_no_duplicates(self):
        project = _build(SIMPLE_PROJECT)
        files = project.media_files()
        assert len(files) == len(set(files))

    def test_resolve_media_files_requires_source_path(self):
        project = _build(SIMPLE_PROJECT)  # no source_path
        with pytest.raises(ValueError):
            project.resolve_media_files()

    def test_resolve_media_files_absolute(self):
        project = _build(SIMPLE_PROJECT, source_path="/projects/song.rpp")
        resolved = project.resolve_media_files()
        # All paths should be absolute
        assert all(os.path.isabs(p) for p in resolved)
        # Should resolve relative to /projects/
        assert any("kick.wav" in p for p in resolved)

    def test_missing_media_files(self, tmp_path):
        # Create a real project file path so resolve_media_files works
        rpp_path = str(tmp_path / "song.rpp")
        project = _build(SIMPLE_PROJECT, source_path=rpp_path)
        missing = project.missing_media_files()
        # None of the files exist in tmp_path so all should be missing
        assert len(missing) == 3

    def test_all_items_embedded_midi(self):
        project = _build(INLINE_MIDI_PROJECT)
        sources = project.all_sources()
        assert len(sources) == 1
        assert sources[0].is_embedded
