# Changelog

## 0.2.0 (2026-10-03)

- `chkit.game` (Linux, X11), taken from clonehero_scripts (`ch_screen.py`, `ch_autotype.py`): `screen` reads the Clone Hero window and tells which part of the song menu it shows; `search` puts the cursor of the song list on a song (`find_song`) or on the first song of an artist (`find_artist`, new), every key sent only where the screen shows it means what it should.
- No blind typing unless asked: `find_song(..., blind=True)` keeps the old sequence for when the window cannot be read (someone sits at the game); `find_artist` never types blindly. Without a readable window they return the reason instead.
- evdev is needed only for typing (extra `game`); importing `chkit.game` works without it.

## 0.1.1 (2026-10-03)

- Tempo map: the same operation order as the readers chkit replaced, so note times are bit-identical to them (a difference in the 15th digit changed a cut point in the shorts extractor at near ties).

## 0.1.0 (2026-10-03)

First version, taken from the tools that had their own copies:

- `chkit.chart`: `.chart` / `.mid` drum reader (based on the reader of the shorts extractor), `.chart` writer (from the autocharter). New on the way: ghost notes, flams, all four difficulties, `[Song]` Offset, `.mid` dynamics only when enabled, 5-lane recognised by its green note, fill phrases counted once, tolerant reading of truncated MIDI files.
- `chkit.song`: `song.ini`, chart file and MD5, audio tracks, song folders, text helpers.
- `chkit.chfiles`: `currentsong.txt`, `scorestats.json`, `scoredata.bin`, MIDI profiles, playlist format.
- `chkit.io`: atomic writes, network folders with timeouts, tolerant JSON.
