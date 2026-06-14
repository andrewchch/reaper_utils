"""
Tests for reaper_media.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from reaper_parser import parse_rpp
from reaper_project import build_project
from reaper_media import list_media_files, check_missing_media, copy_media_to_directory, media_report


# ---------------------------------------------------------------------------
# Sample RPP text
# ---------------------------------------------------------------------------

SIMPLE_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  <TRACK {GUID-1}
    NAME "Drums"
    <ITEM
      POSITION 0
      LENGTH 4.5
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
      <SOURCE WAVE
        FILE "audio/bass_sample.wav"
      >
    >
  >
>
"""

SHARED_FILE_PROJECT = """<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  <TRACK {GUID-1}
    NAME "Track A"
    <ITEM
      POSITION 0
      LENGTH 4.0
      <SOURCE WAVE
        FILE "audio/shared.wav"
      >
    >
  >
  <TRACK {GUID-2}
    NAME "Track B"
    <ITEM
      POSITION 4.0
      LENGTH 4.0
      <SOURCE WAVE
        FILE "audio/shared.wav"
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project(rpp_text: str, rpp_path: str):
    root = parse_rpp(rpp_text)
    return build_project(root, source_path=rpp_path)


# ---------------------------------------------------------------------------
# Tests: list_media_files
# ---------------------------------------------------------------------------

class TestListMediaFiles:
    def test_basic(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        media = list_media_files(project)
        assert len(media) == 2

    def test_paths_are_absolute(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        media = list_media_files(project)
        assert all(os.path.isabs(m.path) for m in media)

    def test_source_types(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        types = {m.source_type for m in list_media_files(project)}
        assert types == {"WAVE"}

    def test_missing_flag(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        media = list_media_files(project)
        # Files don't exist
        assert all(not m.exists for m in media)

    def test_existing_flag(self, tmp_path):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "kick.wav").write_bytes(b"RIFF" + b"\x00" * 36)
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        media = list_media_files(project)
        kick = next(m for m in media if "kick.wav" in m.path)
        assert kick.exists
        assert kick.size_bytes == 40

    def test_shared_file_deduplicated(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SHARED_FILE_PROJECT, rpp_path)
        media = list_media_files(project)
        assert len(media) == 1

    def test_shared_file_tracks(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SHARED_FILE_PROJECT, rpp_path)
        media = list_media_files(project)
        assert sorted(media[0].track_names) == ["Track A", "Track B"]

    def test_inline_midi_excluded(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(INLINE_MIDI_PROJECT, rpp_path)
        media = list_media_files(project)
        assert len(media) == 0

    def test_requires_source_path(self):
        root = parse_rpp(SIMPLE_PROJECT)
        project = build_project(root)  # no source_path
        with pytest.raises(ValueError):
            list_media_files(project)

    def test_results_sorted(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        media = list_media_files(project)
        paths = [m.path for m in media]
        assert paths == sorted(paths)


# ---------------------------------------------------------------------------
# Tests: check_missing_media
# ---------------------------------------------------------------------------

class TestCheckMissingMedia:
    def test_all_missing(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        missing = check_missing_media(project)
        assert len(missing) == 2

    def test_one_present(self, tmp_path):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "kick.wav").write_bytes(b"RIFF" + b"\x00" * 36)
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        missing = check_missing_media(project)
        assert len(missing) == 1
        assert "bass_sample.wav" in missing[0].path

    def test_none_missing(self, tmp_path):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "kick.wav").write_bytes(b"data")
        (audio_dir / "bass_sample.wav").write_bytes(b"data")
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        missing = check_missing_media(project)
        assert missing == []


# ---------------------------------------------------------------------------
# Tests: copy_media_to_directory
# ---------------------------------------------------------------------------

class TestCopyMediaToDirectory:
    def _setup(self, tmp_path):
        """Create a project with real audio files on disk."""
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "kick.wav").write_bytes(b"KICK")
        (audio_dir / "bass_sample.wav").write_bytes(b"BASS")
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        return project

    def test_copies_files(self, tmp_path):
        project = self._setup(tmp_path)
        dest = str(tmp_path / "exported")
        copied = copy_media_to_directory(project, dest)
        assert len(copied) == 2
        assert os.path.exists(os.path.join(dest, "kick.wav"))
        assert os.path.exists(os.path.join(dest, "bass_sample.wav"))

    def test_creates_dest_dir(self, tmp_path):
        project = self._setup(tmp_path)
        dest = str(tmp_path / "new_dir" / "media")
        copy_media_to_directory(project, dest)
        assert os.path.isdir(dest)

    def test_no_overwrite_by_default(self, tmp_path):
        project = self._setup(tmp_path)
        dest = str(tmp_path / "exported")
        os.makedirs(dest)
        dest_file = os.path.join(dest, "kick.wav")
        with open(dest_file, "wb") as f:
            f.write(b"ORIGINAL")
        copy_media_to_directory(project, dest)
        with open(dest_file, "rb") as f:
            assert f.read() == b"ORIGINAL"

    def test_overwrite_flag(self, tmp_path):
        project = self._setup(tmp_path)
        dest = str(tmp_path / "exported")
        os.makedirs(dest)
        dest_file = os.path.join(dest, "kick.wav")
        with open(dest_file, "wb") as f:
            f.write(b"OLD")
        copy_media_to_directory(project, dest, overwrite=True)
        with open(dest_file, "rb") as f:
            assert f.read() == b"KICK"

    def test_raises_on_missing_file(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)  # no audio files created
        dest = str(tmp_path / "exported")
        with pytest.raises(FileNotFoundError):
            copy_media_to_directory(project, dest)

    def test_skip_missing(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)  # no audio files created
        dest = str(tmp_path / "exported")
        copied = copy_media_to_directory(project, dest, skip_missing=True)
        assert copied == []


# ---------------------------------------------------------------------------
# Tests: media_report
# ---------------------------------------------------------------------------

class TestMediaReport:
    def test_no_media(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(INLINE_MIDI_PROJECT, rpp_path)
        report = media_report(project)
        assert "No external media files" in report

    def test_report_contains_filename(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        report = media_report(project)
        assert "kick.wav" in report
        assert "bass_sample.wav" in report

    def test_report_shows_missing(self, tmp_path):
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        report = media_report(project)
        assert "Missing" in report

    def test_report_shows_present(self, tmp_path):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "kick.wav").write_bytes(b"data")
        (audio_dir / "bass_sample.wav").write_bytes(b"data")
        rpp_path = str(tmp_path / "song.rpp")
        project = _project(SIMPLE_PROJECT, rpp_path)
        report = media_report(project)
        assert "Present" in report
