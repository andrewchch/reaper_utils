# reaper_utils
Some python Reaper utilities

## Find orphaned Reaper media

Use `find_orphaned_reaper_media.py` to find audio/MIDI files not referenced by Reaper projects:

```bash
python find_orphaned_reaper_media.py /path/to/start_directory \
  --audio_types "wav,mid" \
  --ignore_backups \
  --delete_orphaned_audio_files
```
