# chkit

Building blocks for Clone Hero tools, in plain Python (standard library only, Python 3.10+).

| Module | What it does |
|---|---|
| `chkit.chart` | Reads the drum track of `.chart` and `.mid` files (any difficulty) into one model: notes with lane, cymbal/tom, Expert+ kick, accent, ghost, flam; tempo map (tick ↔ seconds); time signatures; sections; bar lines; star power, fills and rolls. Writes `.chart`. |
| `chkit.song` | Song folders: `song.ini` (UTF-8 or cp1252), the chart file Clone Hero plays, its MD5 (the checksum Clone Hero keys scores by), audio tracks, text helpers (formatting tags, charter lists, accent-free search keys). |
| `chkit.chfiles` | Files of the game: `currentsong.txt`, `scorestats.json`, `scoredata.bin` (decoded: playcount, best score, stars, percent, full combo), MIDI profiles (which kit note is which pad), and a simple playlist format. |
| `chkit.io` | Atomic writes (temp file + rename), copying from network folders through a child process with a timeout (a stale CIFS mount cannot hang the caller), JSON that tolerates half-written files. |
| `chkit.groove` | A groove fingerprint per chart (bar pattern per voice, tempo, feel, a one-line summary) and how alike two songs feel to play, 0–100 %, with the reasons. |
| `chkit.game` | Drives the running game (Linux, X11/Xwayland): reads its window to tell which menu is up, and puts the cursor of the song list on a song or an artist. Keys go out only where the screen shows they mean what they should. |

```python
from chkit import chart, song
from chkit.chfiles import scorestats

c = chart.read("Songs/Dio - The Last in Line/notes.mid")      # Expert, song.ini next to it
for note in c.notes:
    print(note.t, note.lane, "cymbal" if note.cymbal else "")
print(c.bar_lines()[:4], c.section_at(60.0))
print(song.chart_md5(song.find_chart("Songs/Dio - The Last in Line")))
```

## Songs with a similar groove

```python
from chkit import chart, groove

a = groove.fingerprint(chart.read("Songs/AC-DC - Back in Black/notes.mid"))
b = groove.fingerprint(chart.read("Songs/Metallica - Devil's Dance/notes.mid"))
print(a["summary"])                                  # 4/4 · 8ths · snare 2+4 · 94 BPM
score, parts = groove.similarity(groove.prepare(a), groove.prepare(b))
print(f"{score:.0%}", groove.explain(parts))         # 96% beat 95 % · tempo 94/96 BPM · feel 96 %
```

The pattern counts most (where kick, snare, cymbals and toms fall in the bar, averaged over the bars that are not fills), then the tempo, then the feel (notes per second, fills, triplets, 16ths, ride). 16ths at 90 BPM and 8ths at 180 BPM count as alike (the same hand speed), a bit less than the same pattern. A fingerprint is a small dict (`encode`/`decode` for storing it); `prepare` it once to compare it with many others (about 15 µs per pair).

## Searching a song in the running game

```python
from chkit.game import search

failed = search.find_song({"artist": "Dio", "name": "The Last in Line",
                           "path": "Songs/Dio - The Last in Line"})
failed = search.find_artist("Dio")          # the first song of the artist
print("found" if failed is None else f"stopped: {failed}")
```

Clone Hero has no interface for this, so `chkit.game.screen` reads a few fixed spots of the window (measured at 1280x720 with v1.1.0.6142, scaled to the real size). When the window cannot be read, a song is running or a step does not show up, the search stops and returns why; it types blindly only with `find_song(..., blind=True)`, meant for someone sitting at the game. Keys go through a virtual keyboard: install `chkit[game]` (evdev) and give the user write access to `/dev/uinput`. Text is typed for the German QWERTZ layout.

```bash
python3 -m chkit.game.screen --watch                  # what the window shows, on every change
python3 -m chkit.game.search "Dio" "The Last in Line"    # try a search by hand
```

## Cymbals and toms

- **`.mid`**: in a pro-drums chart yellow, blue and green are cymbals by default. The notes 110/111/112 are *tom markers*: notes of their colour are toms while the marker is held. A chart without tom markers is pro if `song.ini` says `pro_drums = True` (then every yellow/blue/green note is a cymbal), otherwise a plain 4-lane chart (all toms).
- **`.chart`**: cymbals are marked explicitly (notes 66/67/68); without markers there are only toms.
- **5-lane** charts (`five_lane_drums`, or a 5-lane green note) have a fixed layout: yellow and orange are cymbals. They are mapped onto the 4-lane names; `Note.pad` keeps the raw pad.
- Accents and ghosts in `.mid` count only when the track enables dynamics (`[ENABLE_CHART_DYNAMICS]`).

Sources: TheNathannator, [GuitarGame_ChartFormats](https://thenathannator.github.io/GuitarGame_ChartFormats/) (`.mid` and `.chart` drums); Rock Band Network drum authoring docs.

## Install

Copy or clone it next to your tool and put the folder on `sys.path`, or install it:

```bash
pip install git+https://github.com/heiner-palmen/chkit.git
pip install "chkit[game] @ git+https://github.com/heiner-palmen/chkit.git"    # with typing into the game
```

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## License

MIT
