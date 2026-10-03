# Changelog

## 0.1.1 (2026-10-03)

- Tempo map: the same operation order as the readers chkit replaced, so note times are bit-identical to them (a difference in the 15th digit changed a cut point in the shorts extractor at near ties).

## 0.1.0 (2026-10-03)

First version, taken from the tools that had their own copies:

- `chkit.chart`: `.chart` / `.mid` drum reader (based on the reader of the shorts extractor), `.chart` writer (from the autocharter). New on the way: ghost notes, flams, all four difficulties, `[Song]` Offset, `.mid` dynamics only when enabled, 5-lane recognised by its green note, fill phrases counted once, tolerant reading of truncated MIDI files.
- `chkit.song`: `song.ini`, chart file and MD5, audio tracks, song folders, text helpers.
- `chkit.chfiles`: `currentsong.txt`, `scorestats.json`, `scoredata.bin`, MIDI profiles, playlist format.
- `chkit.io`: atomic writes, network folders with timeouts, tolerant JSON.
