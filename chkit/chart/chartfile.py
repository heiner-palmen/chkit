""".chart files: read the drum track of one difficulty, write a drum chart.

Note numbers (GuitarGame_ChartFormats, .chart Drums):
  N 0-4 lanes (kick, red, yellow, blue, 4-lane green / 5-lane orange), N 5 5-lane green,
  N 32 Expert+ kick, N 34-38 accents, N 40-44 ghosts, N 66-68 cymbal markers
  (yellow, blue, green), N 109 flam;
  S 2 star power, S 64 fill (activation), S 65 single roll, S 66 double roll.
In .chart, cymbals are marked explicitly; a 4-lane chart without cymbal
markers has only toms. 5-lane charts (song.ini five_lane_drums) have a fixed
layout: yellow (N 2) and orange (N 4) are cymbals.
"""

from __future__ import annotations

import math
import re
from typing import Optional

from ..song import ini_next_to, to_bool
from .model import DIFFICULTIES, FIVE_LANE, FOUR_LANE_PRO, LANES, Chart, Note, Phrase, Section, TimeSignature
from .tempo import TempoMap

_SECTION = re.compile(r"^\[(.+?)\]\s*$")
_NOTE = re.compile(r"^(\d+)\s*=\s*([NS])\s+(\d+)\s+(\d+)$")
_TEMPO = re.compile(r"^(\d+)\s*=\s*B\s+(\d+)$")
_TS = re.compile(r"^(\d+)\s*=\s*TS\s+(\d+)(?:\s+(\d+))?$")
_EVENT_SECTION = re.compile(r'^(\d+)\s*=\s*E\s+"section (.+)"$')

LANE_BY_TYPE = {0: "kick", 1: "red", 2: "yellow", 3: "blue", 4: "green", 5: "green"}
CYMBAL_MARKERS = {66: "yellow", 67: "blue", 68: "green"}
FIVE_LANE_CYMBAL_TYPES = {2, 4}
PHRASES = {2: "sp", 64: "fill", 65: "roll", 66: "roll2"}
TRACK_NAMES = {"expert": "ExpertDrums", "hard": "HardDrums", "medium": "MediumDrums", "easy": "EasyDrums"}


def _blocks(text: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        m = _SECTION.match(line)
        if m:
            current = m.group(1)
            blocks.setdefault(current, [])
        elif current and line and line not in ("{", "}"):
            blocks[current].append(line)
    return blocks


def read_chart(path: str, difficulty: str = "expert", ini: Optional[dict] = None) -> Chart:
    """The drum track of one difficulty. `ini`: the song.ini values (read from
    the chart's folder when not given). ValueError if the track is missing."""
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"unknown difficulty: {difficulty}")
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        blocks = _blocks(fh.read())
    ini = ini_next_to(path) if ini is None else ini

    resolution, offset = 192, 0.0
    for line in blocks.get("Song", []):
        key, _, value = line.partition("=")
        key, value = key.strip().casefold(), value.strip().strip('"')
        try:
            if key == "resolution":
                resolution = int(value)
            elif key == "offset":
                offset = float(value)
        except ValueError:
            pass

    changes, sigs = [], []
    for line in blocks.get("SyncTrack", []):
        m = _TEMPO.match(line)
        if m:
            changes.append((int(m.group(1)), int(m.group(2)) / 1000.0))
            continue
        m = _TS.match(line)
        if m:                                   # denominator is 2^exponent, default 4
            sigs.append(TimeSignature(int(m.group(1)), int(m.group(2)), 2 ** int(m.group(3) or 2)))
    tempo = TempoMap(changes, resolution)
    chart = Chart(resolution=resolution, tempo=tempo, difficulty=difficulty, offset=offset, source=path)
    if sigs:
        chart.time_signatures = sorted(sigs)

    for line in blocks.get("Events", []):
        m = _EVENT_SECTION.match(line)
        if m:
            tick = int(m.group(1))
            chart.sections.append(Section(tick, tempo.tick_to_s(tick), m.group(2)))
    chart.sections.sort()

    track = blocks.get(TRACK_NAMES[difficulty])
    if track is None:
        raise ValueError(f"no [{TRACK_NAMES[difficulty]}] in {path}")

    raw, accents, ghosts, cymbals, flams = [], {}, {}, {}, set()
    has_five = False
    phrases = set()
    for line in track:
        m = _NOTE.match(line)
        if not m:
            continue
        tick, kind, ntype, length = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
        if kind == "S":
            if ntype in PHRASES:
                phrases.add((PHRASES[ntype], tick, tick + length))
        elif ntype in LANE_BY_TYPE:
            raw.append((tick, ntype))
            has_five = has_five or ntype == 5
        elif ntype == 32:
            if difficulty == "expert":
                raw.append((tick, 32))
        elif 34 <= ntype <= 38:
            accents.setdefault(tick, set()).add(LANES[ntype - 34])
        elif 40 <= ntype <= 44:
            ghosts.setdefault(tick, set()).add(LANES[ntype - 40])
        elif ntype in CYMBAL_MARKERS:
            cymbals.setdefault(tick, set()).add(CYMBAL_MARKERS[ntype])
        elif ntype == 109:
            flams.add(tick)

    five_lane = bool(to_bool(ini.get("five_lane_drums"))) or has_five
    if cymbals:
        chart.cymbal_source, chart.drum_type = "markers", FOUR_LANE_PRO
    elif five_lane:
        chart.cymbal_source, chart.drum_type = "five_lane", FIVE_LANE
    elif to_bool(ini.get("pro_drums")):
        chart.drum_type = FOUR_LANE_PRO           # pro, but this chart marks no cymbals

    for tick, ntype in raw:
        lane = "kick" if ntype == 32 else LANE_BY_TYPE[ntype]
        if chart.cymbal_source == "five_lane":
            cymbal = ntype in FIVE_LANE_CYMBAL_TYPES
        else:
            cymbal = lane in cymbals.get(tick, ())
        chart.notes.append(Note(
            tick=tick, t=tempo.tick_to_s(tick), lane=lane, cymbal=cymbal, kick2x=ntype == 32,
            accent=lane in accents.get(tick, ()), ghost=lane in ghosts.get(tick, ()),
            flam=tick in flams and lane != "kick", pad=0 if ntype == 32 else ntype))
    chart.notes.sort(key=lambda n: (n.tick, n.pad, n.kick2x))
    chart.phrases = [Phrase(kind, t0, t1, tempo.tick_to_s(t0), tempo.tick_to_s(t1))
                     for kind, t0, t1 in sorted(phrases, key=lambda p: (p[1], p[0]))]
    return chart


# -- writing ---------------------------------------------------------------------------

#: the [Song] block as most chart tools write it; values overridable through `song`
SONG_DEFAULTS = {"Name": "Unknown", "Artist": "Unknown", "Charter": "", "Album": "", "Year": "",
                 "Offset": 0, "Resolution": 192, "Player2": "bass", "Difficulty": 0, "PreviewStart": 0,
                 "PreviewEnd": 0, "Genre": "rock", "MediaType": "cd", "MusicStream": "song.ogg"}
_QUOTED = {"Name", "Artist", "Charter", "Album", "Year", "Genre", "MediaType", "MusicStream"}
_LANE_TYPE = {"kick": 0, "red": 1, "yellow": 2, "blue": 3, "green": 4}
_CYMBAL_MARKER = {"yellow": 66, "blue": 67, "green": 68}


def chart_text(chart: Chart, song: Optional[dict] = None) -> str:
    """The .chart text for a (4-lane) drum chart in its difficulty track,
    with cymbal markers, Expert+ kicks, accents, ghosts, flams, phrases and
    sections."""
    header = dict(SONG_DEFAULTS, Resolution=chart.resolution, Offset=chart.offset, **(song or {}))
    lines = ["[Song]", "{"]
    for key, value in header.items():
        lines.append(f'  {key} = "{value}"' if key in _QUOTED else f"  {key} = {value}")
    lines += ["}", "[SyncTrack]", "{"]
    sync = []
    sigs = list(chart.time_signatures)
    if not any(s.tick == 0 for s in sigs):
        sigs.append(TimeSignature(0, 4, 4))
    for s in sigs:
        exponent = int(math.log2(s.denominator)) if s.denominator > 0 else 2
        sync.append((s.tick, 0, f"TS {s.numerator}" + ("" if exponent == 2 else f" {exponent}")))
    for tick, bpm in chart.tempo.changes:
        sync.append((tick, 1, f"B {int(round(bpm * 1000))}"))
    lines += [f"  {tick} = {text}" for tick, _, text in sorted(sync)]
    lines += ["}", "[Events]", "{"]
    lines += [f'  {s.tick} = E "section {s.name}"' for s in sorted(chart.sections)]
    lines += ["}", f"[{TRACK_NAMES[chart.difficulty]}]", "{"]
    entries = []
    for n in chart.notes:
        entries.append((n.tick, 0, f"N {32 if n.kick2x else _LANE_TYPE[n.lane]} 0"))
        if n.cymbal and n.lane in _CYMBAL_MARKER:
            entries.append((n.tick, 1, f"N {_CYMBAL_MARKER[n.lane]} 0"))
        if n.accent:
            entries.append((n.tick, 2, f"N {34 + _LANE_TYPE[n.lane]} 0"))
        if n.ghost:
            entries.append((n.tick, 2, f"N {40 + _LANE_TYPE[n.lane]} 0"))
        if n.flam:
            entries.append((n.tick, 3, "N 109 0"))
    types = {v: k for k, v in PHRASES.items()}
    for p in chart.phrases:
        if p.kind in types:
            entries.append((p.tick0, 4, f"S {types[p.kind]} {p.tick1 - p.tick0}"))
    seen = set()
    for tick, _, text in sorted(entries):
        if (tick, text) not in seen:
            seen.add((tick, text))
            lines.append(f"  {tick} = {text}")
    lines += ["}", ""]
    return "\n".join(lines)


def write_chart(chart: Chart, path: str, song: Optional[dict] = None) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(chart_text(chart, song))
