# reaper_utils

Python utilities for processing [Reaper](https://www.reaper.fm/) DAW project files (`.rpp`) and related audio and MIDI files.

## Modules

| Module | Description |
|---|---|
| `reaper_parser.py` | Low-level parser for the Reaper RPP block format |
| `reaper_project.py` | High-level project model (tracks, items, media sources) |
| `reaper_media.py` | Utilities for listing, checking and copying media files |
| `reaper_midi.py` | Utilities for inspecting inline and external MIDI data |

## Requirements

* Python 3.8+
* No third-party dependencies

## Quick start

### Parse a project file

```python
from reaper_project import load_project

project = load_project("MySong.rpp")
print(f"Project: {project.app_version}")
for track in project.tracks:
    print(f"  Track: {track.name} ({len(track.items)} items)")
```

### List all referenced media files

```python
from reaper_project import load_project
from reaper_media import list_media_files, media_report

project = load_project("MySong.rpp")
print(media_report(project))
```

### Find missing media files

```python
from reaper_project import load_project
from reaper_media import check_missing_media

project = load_project("MySong.rpp")
missing = check_missing_media(project)
for m in missing:
    print(f"MISSING: {m.path}")
```

### Copy all media to a directory

```python
from reaper_project import load_project
from reaper_media import copy_media_to_directory

project = load_project("MySong.rpp")
copied = copy_media_to_directory(project, "/path/to/export", skip_missing=True)
print(f"Copied {len(copied)} files")
```

### Inspect MIDI content

```python
from reaper_project import load_project
from reaper_midi import midi_summary, get_inline_midi_sources

project = load_project("MySong.rpp")
print(midi_summary(project))

for track_name, midi_src in get_inline_midi_sources(project):
    print(f"  {track_name}: {midi_src.note_count()} notes, PPQ={midi_src.ppq}")
```

### Low-level RPP parsing

```python
from reaper_parser import parse_rpp_file, iter_nodes

root = parse_rpp_file("MySong.rpp")

# Find all SOURCE blocks anywhere in the tree
for source in iter_nodes(root, "SOURCE"):
    file_tokens = source.get_param("FILE")
    if file_tokens:
        print(file_tokens[0])
```

## RPP file format overview

Reaper project files are plain-text hierarchical files using a block format:

```
<REAPER_PROJECT 0.1 "6.80/win64" 1600000000
  RIPPLE 0
  <TRACK {GUID}
    NAME "My Track"
    <ITEM
      POSITION 0
      LENGTH 4.0
      <SOURCE WAVE
        FILE "audio/loop.wav"
      >
    >
  >
>
```

* Blocks begin with `<TAG attrib1 attrib2 ...` and end with `>`.
* Attribute lines are space-separated key-value pairs.
* Blocks can be arbitrarily nested.
* MIDI data may be stored inline using `HASDATA` / `E` lines inside a `<SOURCE MIDI>` block.

## Running tests

```bash
python -m pytest tests/ -v
```
