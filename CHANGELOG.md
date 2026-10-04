# Changelog

## 0.4.0 (2026-10-04)

- `chkit.game.practice`: sets up Clone Hero's practice mode for one spot of a song, from the menu or the score screen: Practice, the song (the same search), its section, then A and B moved by Seek in the pause menu (0.25 s a press), and play. `next()` goes to the next spot through NEW SECTION, so A and B always start from the known section bounds. A is checked afterwards by the seek the game writes to `Player.log` and set again when a key press got lost; a wrong idea of the running section is put right by what A shows. Measured with v1.1.0.6142: Enter pauses, B may pass the end of the section, the list of sections opens on the running one.
- `chkit.game.screen`: the highlighted row of the main menu, the practice mode's list of sections and pause menu, the Seek legend, and the times of A and B read digit by digit. Quickplay's pause menu and its dialogs are told apart from the practice mode's.
- `GameWindow.grab()` throws away the reads of the first 200 ms after a pause: under Xwayland the first requests after a while return the picture from before, which made a menu look as if a key had not arrived.

## 0.3.0 (2026-10-04)

- `chkit.groove`: groove fingerprint of a drum chart (the averaged bar pattern of kick, snare, cymbals and toms on a 12-per-quarter grid, tempo, feel numbers, a one-line summary such as `4/4 · 8ths · snare 2+4 · 172 BPM`) and `similarity()` of two fingerprints: pattern first, then tempo, then feel; a song played at double tempo counts as alike, slightly less than the same pattern.

## 0.2.1 (2026-10-03)

- `.mid` reader: tom markers and flams are looked up by bisection instead of a scan over all marker spans per note. A discography chart (199,002 notes, every tom marked on its own) took 33 s to read, now 1.1 s.

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
