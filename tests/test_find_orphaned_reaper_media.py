from pathlib import Path

import find_orphaned_reaper_media as script


def test_find_orphaned_files_with_discovered_projects(tmp_path: Path):
    (tmp_path / "used.wav").write_text("data")
    (tmp_path / "orphan.wav").write_text("data")
    (tmp_path / "song.mid").write_text("data")
    (tmp_path / "project.rpp").write_text('FILE "used.wav"\nFILE "song.mid"\n', encoding="utf-8")

    _, project_files, _, orphaned = script.find_orphaned_audio_files(str(tmp_path))

    assert [p.name for p in project_files] == ["project.rpp"]
    assert {p.name for p in orphaned} == {"orphan.wav"}


def test_ignore_backups_excludes_rpp_bak(tmp_path: Path):
    (tmp_path / "used.wav").write_text("data")
    (tmp_path / "orphan.wav").write_text("data")
    (tmp_path / "project.rpp.bak").write_text('FILE "used.wav"\n', encoding="utf-8")

    _, project_files, _, orphaned = script.find_orphaned_audio_files(
        str(tmp_path), ignore_backups=True
    )

    assert project_files == []
    assert {p.name for p in orphaned} == {"used.wav", "orphan.wav"}


def test_project_file_argument_limits_scan(tmp_path: Path):
    (tmp_path / "used.wav").write_text("data")
    (tmp_path / "orphan.wav").write_text("data")
    selected = tmp_path / "selected.rpp"
    selected.write_text('FILE "used.wav"\n', encoding="utf-8")
    (tmp_path / "ignored.rpp").write_text("", encoding="utf-8")

    _, project_files, _, orphaned = script.find_orphaned_audio_files(
        str(tmp_path), project_file=str(selected)
    )

    assert project_files == [selected.resolve()]
    assert {p.name for p in orphaned} == {"orphan.wav"}


def test_delete_orphaned_moves_to_recycle_bin(tmp_path: Path, monkeypatch):
    orphan = tmp_path / "orphan.wav"
    orphan.write_text("data")
    target = tmp_path / "trash"
    monkeypatch.setattr("builtins.input", lambda _: "y")
    monkeypatch.setattr(script, "recycle_bin_directory", lambda: target)

    script.maybe_delete_orphaned({orphan.resolve()}, delete_orphaned_audio_files=True)

    assert not orphan.exists()
    assert (target / "orphan.wav").exists()


def test_move_to_recycle_bin_handles_name_collision(tmp_path: Path, monkeypatch):
    target = tmp_path / "trash"
    existing = target / "orphan.wav"
    target.mkdir()
    existing.write_text("existing")
    orphan = tmp_path / "orphan.wav"
    orphan.write_text("new")
    monkeypatch.setattr(script, "recycle_bin_directory", lambda: target)

    moved_to = script.move_to_recycle_bin(orphan.resolve())

    assert moved_to.name == "orphan_1.wav"
    assert (target / "orphan.wav").read_text() == "existing"
    assert moved_to.read_text() == "new"


def test_recycle_bin_directory_platform_selection(tmp_path: Path):
    assert script.recycle_bin_directory(tmp_path, "darwin") == tmp_path / ".Trash"
    assert script.recycle_bin_directory(tmp_path, "windows") == tmp_path / "Recycle.Bin"
