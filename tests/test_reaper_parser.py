"""
Tests for reaper_parser.py
"""

import sys
import os

# Ensure the project root is on the path so imports work when running from tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from reaper_parser import parse_rpp, RppNode, iter_nodes


# ---------------------------------------------------------------------------
# Sample RPP text snippets
# ---------------------------------------------------------------------------

MINIMAL_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
>
"""

SIMPLE_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  RIPPLE 0
  GROUPOVERRIDE 0 0 0
  <TRACK {GUID-1}
    NAME "Drums"
    PEAKCOL 16576
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
        E 480 90 40 64
        E 480 80 40 00
      >
    >
  >
>
"""


# ---------------------------------------------------------------------------
# Tests: parse_rpp
# ---------------------------------------------------------------------------

class TestParseRpp:
    def test_minimal_project(self):
        root = parse_rpp(MINIMAL_PROJECT)
        assert root.tag == "REAPER_PROJECT"
        assert root.attribs[0] == "0.1"
        assert root.attribs[1] == "6.80/win64"

    def test_simple_project_tracks(self):
        root = parse_rpp(SIMPLE_PROJECT)
        tracks = root.find_all("TRACK")
        assert len(tracks) == 2

    def test_track_name_param(self):
        root = parse_rpp(SIMPLE_PROJECT)
        track = root.find("TRACK")
        name_tokens = track.get_param("NAME")
        assert name_tokens == ["Drums"]

    def test_items_in_track(self):
        root = parse_rpp(SIMPLE_PROJECT)
        drums_track = root.find("TRACK")
        items = drums_track.find_all("ITEM")
        assert len(items) == 1

    def test_source_file_path(self):
        root = parse_rpp(SIMPLE_PROJECT)
        drums_track = root.find("TRACK")
        item = drums_track.find("ITEM")
        source = item.find("SOURCE")
        assert source is not None
        file_tokens = source.get_param("FILE")
        assert file_tokens == ["audio/kick.wav"]

    def test_nested_blocks(self):
        root = parse_rpp(SIMPLE_PROJECT)
        bass_track = root.find_all("TRACK")[1]
        items = bass_track.find_all("ITEM")
        assert len(items) == 2

    def test_find_returns_none_for_missing_tag(self):
        root = parse_rpp(MINIMAL_PROJECT)
        assert root.find("NONEXISTENT") is None

    def test_find_recursive(self):
        root = parse_rpp(SIMPLE_PROJECT)
        sources = root.find_recursive("SOURCE")
        assert len(sources) == 3  # kick.wav, bass.mid, bass_sample.wav

    def test_get_param_case_insensitive(self):
        root = parse_rpp(SIMPLE_PROJECT)
        track = root.find("TRACK")
        # NAME stored as NAME, query as name
        assert track.get_param("name") == ["Drums"]
        assert track.get_param("NAME") == ["Drums"]

    def test_get_param_missing(self):
        root = parse_rpp(SIMPLE_PROJECT)
        track = root.find("TRACK")
        assert track.get_param("NONEXISTENT") is None

    def test_top_level_params(self):
        root = parse_rpp(SIMPLE_PROJECT)
        ripple = root.get_param("RIPPLE")
        assert ripple == ["0"]

    def test_invalid_file_raises(self):
        with pytest.raises(ValueError):
            parse_rpp("this is not a valid rpp file")

    def test_inline_midi_source(self):
        root = parse_rpp(INLINE_MIDI_PROJECT)
        source = root.find_recursive("SOURCE")[0]
        assert source.attribs[0] == "MIDI"
        assert source.get_param("HASDATA") is not None

    def test_item_position_and_length(self):
        root = parse_rpp(SIMPLE_PROJECT)
        item = root.find("TRACK").find("ITEM")
        assert item.get_param("POSITION") == ["0"]
        assert item.get_param("LENGTH") == ["4.5"]


# ---------------------------------------------------------------------------
# Tests: iter_nodes
# ---------------------------------------------------------------------------

class TestIterNodes:
    def test_iter_tracks(self):
        root = parse_rpp(SIMPLE_PROJECT)
        tracks = list(iter_nodes(root, "TRACK"))
        assert len(tracks) == 2

    def test_iter_items(self):
        root = parse_rpp(SIMPLE_PROJECT)
        items = list(iter_nodes(root, "ITEM"))
        assert len(items) == 3

    def test_iter_sources(self):
        root = parse_rpp(SIMPLE_PROJECT)
        sources = list(iter_nodes(root, "SOURCE"))
        assert len(sources) == 3

    def test_iter_no_match(self):
        root = parse_rpp(SIMPLE_PROJECT)
        assert list(iter_nodes(root, "NOTHING")) == []


# ---------------------------------------------------------------------------
# Tests: RppNode helpers
# ---------------------------------------------------------------------------

class TestRppNode:
    def test_repr(self):
        root = parse_rpp(MINIMAL_PROJECT)
        r = repr(root)
        assert "REAPER_PROJECT" in r

    def test_find_all_empty(self):
        root = parse_rpp(MINIMAL_PROJECT)
        assert root.find_all("TRACK") == []

    def test_multi_attribs(self):
        root = parse_rpp(SIMPLE_PROJECT)
        # Root node should have version attribs
        assert len(root.attribs) >= 2
