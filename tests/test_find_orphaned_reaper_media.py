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
    assert "song.mid" not in {p.name for p in orphaned}


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


def test_collect_project_audio_references_groups_files_by_project(tmp_path: Path):
    used_a = tmp_path / "used_a.wav"
    used_b = tmp_path / "used_b.mid"
    used_a.write_text("data")
    used_b.write_text("data")
    first = tmp_path / "first.rpp"
    second = tmp_path / "second.rpp"
    first.write_text('FILE "used_a.wav"\nFILE "used_b.mid"\n', encoding="utf-8")
    second.write_text('FILE "used_b.mid"\n', encoding="utf-8")

    references = script.collect_project_audio_references(
        [first.resolve(), second.resolve()], script.parse_audio_types(None)
    )

    assert references == {
        first.resolve(): [used_a.resolve(), used_b.resolve()],
        second.resolve(): [used_b.resolve()],
    }


def test_print_report_lists_referenced_audio_files_per_project(tmp_path: Path, capsys):
    used = tmp_path / "used.wav"
    orphan = tmp_path / "orphan.wav"
    used.write_text("data")
    orphan.write_text("data")
    project = tmp_path / "project.rpp"
    project.write_text('FILE "used.wav"\n', encoding="utf-8")

    script.print_report(
        {used.resolve(), orphan.resolve()},
        [project.resolve()],
        {orphan.resolve()},
        project_references={project.resolve(): [used.resolve()]},
    )

    assert capsys.readouterr().out.splitlines() == [
        "Audio/MIDI files found: 2",
        "Project files scanned: 1",
        "Orphaned files: 1",
        str(project.resolve()),
        f"  {used.resolve()}",
        str(orphan.resolve()),
    ]


def test_build_parser_supports_listing_referenced_audio_files():
    args = script.build_parser().parse_args(["/tmp/project", "--list_referenced_audio_files"])

    assert args.list_referenced_audio_files is True


def test_print_report_describes_projects_without_referenced_audio_files(tmp_path: Path, capsys):
    project = tmp_path / "empty.rpp"
    project.write_text("", encoding="utf-8")

    script.print_report(
        set(),
        [project.resolve()],
        set(),
        project_references={project.resolve(): []},
    )

    assert capsys.readouterr().out.splitlines() == [
        "Audio/MIDI files found: 0",
        "Project files scanned: 1",
        "Orphaned files: 0",
        str(project.resolve()),
        "  (no audio/MIDI files referenced)",
    ]


def test_delete_orphaned_moves_to_recycle_bin(tmp_path: Path, monkeypatch):
    orphan = tmp_path / "orphan.wav"
    orphan.write_text("data")
    target = tmp_path / "trash"
    monkeypatch.setattr("builtins.input", lambda _: "y")
    monkeypatch.setattr(script, "recycle_bin_directory", lambda: target)

    script.maybe_delete_orphaned({orphan.resolve()}, delete_orphaned_audio_files=True)

    assert not orphan.exists()
    assert (target / "orphan.wav").exists()


def test_delete_orphaned_cancels_on_non_yes(tmp_path: Path, monkeypatch):
    orphan = tmp_path / "orphan.wav"
    orphan.write_text("data")
    monkeypatch.setattr("builtins.input", lambda _: "n")

    script.maybe_delete_orphaned({orphan.resolve()}, delete_orphaned_audio_files=True)

    assert orphan.exists()


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
    assert script.recycle_bin_directory(tmp_path, "linux") == tmp_path / ".local" / "share" / "Trash" / "files"
