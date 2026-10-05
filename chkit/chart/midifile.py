""".mid files: read the PART DRUMS track of one difficulty (standard library only).

Note numbers (GuitarGame_ChartFormats, .mid Drums; Rock Band Network docs):
  Expert 96-101 = kick, red, yellow, blue, green, 5-lane green; 95 = Expert+ kick.
  Hard 84-89, Medium 72-77, Easy 60-65.
  110/111/112 = tom markers (yellow/blue/green): in a pro chart yellow, blue
  and green are CYMBALS by default, and notes of a marker's colour are toms
  while the marker is held. 109 = flam, 116 = star power, 120-124 = fill,
  126/127 = single/double roll, 103 = solo.
  Accents (velocity 127) and ghosts (velocity 1) count only when the track
  enables dynamics with the text event [ENABLE_CHART_DYNAMICS].
Cymbals are decided in this order: tom markers present (pro chart); song.ini
five_lane_drums or a 5-lane green note (fixed layout: yellow and orange are
cymbals); song.ini pro_drums (every yellow/blue/green is a cymbal); else a
plain 4-lane chart (all toms).
"""

from __future__ import annotations

import re
import struct
from bisect import bisect_right
from typing import Optional

from ..song import ini_next_to, to_bool
from .model import DIFFICULTIES, FIVE_LANE, FOUR_LANE_PRO, Chart, Note, Phrase, Section, TimeSignature
from .tempo import TempoMap

BASE = {"expert": 96, "hard": 84, "medium": 72, "easy": 60}
LANE_BY_OFFSET = {0: "kick", 1: "red", 2: "yellow", 3: "blue", 4: "green", 5: "green"}
TOM_MARKERS = {110: "yellow", 111: "blue", 112: "green"}
FIVE_LANE_CYMBAL_OFFSETS = {2, 4}          # 98 = yellow cymbal, 100 = orange cymbal (Expert)
EXPERT_PLUS_KICK = 95
FLAM, SOLO, STAR_POWER, ROLL, ROLL2 = 109, 103, 116, 126, 127
FILL_NOTES = range(120, 125)
_SECTION_TEXT = re.compile(r"\[(?:section|prc)[ _](.+?)\]")
_DYNAMICS = ("[ENABLE_CHART_DYNAMICS]", "ENABLE_CHART_DYNAMICS")


def _varlen(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def read_tracks(blob: bytes) -> tuple[int, list[dict]]:
    """(ticks per beat, tracks). A track: {"name", "notes": [(tick, on, note,
    velocity)], "texts": [(tick, text)], "tempo": [(tick, bpm)], "sigs":
    [(tick, numerator, denominator)]}. ValueError for a file that is not MIDI."""
    if blob[:4] != b"MThd":
        raise ValueError("not a MIDI file")
    header, _fmt, ntracks, division = struct.unpack(">IHHH", blob[4:14])
    if division & 0x8000:
        raise ValueError("SMPTE time division is not supported")
    pos, tracks = 8 + header, []
    for _ in range(ntracks):
        if pos + 8 > len(blob):
            break                                # fewer tracks than the header says: the game plays it too
        tag, length = blob[pos:pos + 4], struct.unpack(">I", blob[pos + 4:pos + 8])[0]
        if tag != b"MTrk":
            if not tag.isalpha():
                raise ValueError("broken MIDI track header")
            pos += 8 + length                    # a chunk of another kind: skipped (the standard says so)
            continue
        data = blob[pos + 8:pos + 8 + length]
        pos += 8 + length
        track = {"name": "", "notes": [], "texts": [], "tempo": [], "sigs": []}
        tick = p = running = 0
        try:
            while p < len(data):
                delta, p = _varlen(data, p)
                tick += delta
                status = data[p]
                if status & 0x80:
                    p += 1
                    if status < 0xF0:
                        running = status
                else:
                    status = running
                if status == 0xFF:                       # meta event
                    meta = data[p]
                    size, p = _varlen(data, p + 1)
                    payload = data[p:p + size]
                    p += size
                    if meta == 0x03 and not track["name"]:
                        track["name"] = payload.decode("latin-1", errors="replace")
                    elif meta == 0x51 and size == 3:
                        track["tempo"].append((tick, 60_000_000 / int.from_bytes(payload, "big")))
                    elif meta == 0x58 and size >= 2:
                        track["sigs"].append((tick, payload[0], 1 << payload[1]))
                    elif meta in (0x01, 0x05):
                        track["texts"].append((tick, payload.decode("latin-1", errors="replace")))
                elif status in (0xF0, 0xF7):                 # sysex
                    size, p = _varlen(data, p)
                    p += size
                else:
                    kind = status & 0xF0
                    if kind in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                        d1, d2 = data[p], data[p + 1]
                        p += 2
                        if kind in (0x80, 0x90):
                            track["notes"].append((tick, kind == 0x90 and d2 > 0, d1, d2))
                    elif kind in (0xC0, 0xD0):
                        p += 1
        except IndexError:
            pass                                             # a track cut short: keep what was read
        tracks.append(track)
    return division, tracks


def read_mid(path: str, difficulty: str = "expert", ini: Optional[dict] = None) -> Chart:
    """The PART DRUMS track of one difficulty. `ini`: the song.ini values (read
    from the chart's folder when not given). ValueError without a drum track."""
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"unknown difficulty: {difficulty}")
    with open(path, "rb") as fh:
        division, tracks = read_tracks(fh.read())
    ini = ini_next_to(path) if ini is None else ini

    changes = [c for t in tracks for c in t["tempo"]]
    sigs = sorted(TimeSignature(*s) for t in tracks for s in t["sigs"])
    tempo = TempoMap(changes, division)
    chart = Chart(resolution=division, tempo=tempo, difficulty=difficulty, source=path)
    if sigs:
        chart.time_signatures = sigs
    for t in tracks:
        if t["name"].casefold() == "events":
            for tick, text in t["texts"]:
                m = _SECTION_TEXT.match(text)
                if m:
                    chart.sections.append(Section(tick, tempo.tick_to_s(tick), m.group(1)))
    chart.sections.sort()

    drums = next((t for t in tracks if t["name"].casefold() == "part drums"), None)
    if drums is None:
        raise ValueError(f"no PART DRUMS track in {path}")
    dynamics = any(text.strip() in _DYNAMICS for _, text in drums["texts"])

    base = BASE[difficulty]
    held: dict[int, int] = {}
    spans: dict[int, list[tuple[int, int]]] = {}
    hits = []
    for tick, on, note, velocity in drums["notes"]:
        offset = note - base
        if on and (0 <= offset <= 5 or (note == EXPERT_PLUS_KICK and difficulty == "expert")):
            hits.append((tick, note, velocity))
        elif note in TOM_MARKERS or note in (FLAM, SOLO, STAR_POWER, ROLL, ROLL2) or note in FILL_NOTES:
            if on:
                held.setdefault(note, tick)
            elif note in held:
                spans.setdefault(note, []).append((held.pop(note), tick))
    end = (drums["notes"][-1][0] + 1) if drums["notes"] else 1
    for note, start in held.items():                    # never released: to the end of the track
        spans.setdefault(note, []).append((start, end))

    # the spans of one pitch follow each other without overlap (a second note-on
    # while held is ignored), so the last span starting at or before a tick is
    # the only one that can hold it; charts that mark every tom have thousands
    starts = {note: [a for a, _ in ranges] for note, ranges in spans.items()}

    def held_at(note: int, tick: int) -> bool:
        i = bisect_right(starts.get(note, ()), tick) - 1
        return i >= 0 and tick < spans[note][i][1]

    tom_lanes = {lane: note for note, lane in TOM_MARKERS.items()}
    has_markers = any(spans.get(n) for n in TOM_MARKERS)
    has_five = any(note - base == 5 for _, note, _ in hits)
    if has_markers:
        chart.cymbal_source, chart.drum_type = "markers", FOUR_LANE_PRO
    elif to_bool(ini.get("five_lane_drums")) or has_five:
        chart.cymbal_source, chart.drum_type = "five_lane", FIVE_LANE
    elif to_bool(ini.get("pro_drums")):
        chart.cymbal_source, chart.drum_type = "pro_flag", FOUR_LANE_PRO

    for tick, note, velocity in hits:
        kick2x = note == EXPERT_PLUS_KICK
        offset = 0 if kick2x else note - base
        lane = LANE_BY_OFFSET[offset]
        cymbal = False
        if lane in tom_lanes and offset != 5:
            if chart.cymbal_source == "markers":
                cymbal = not held_at(tom_lanes[lane], tick)
            elif chart.cymbal_source == "five_lane":
                cymbal = offset in FIVE_LANE_CYMBAL_OFFSETS
            elif chart.cymbal_source == "pro_flag":
                cymbal = True
        chart.notes.append(Note(
            tick=tick, t=tempo.tick_to_s(tick), lane=lane, cymbal=cymbal, kick2x=kick2x,
            accent=dynamics and velocity == 127, ghost=dynamics and velocity == 1,
            flam=lane != "kick" and held_at(FLAM, tick), pad=offset))
    chart.notes.sort(key=lambda n: (n.tick, n.pad, n.kick2x))

    kinds = {STAR_POWER: "sp", ROLL: "roll", ROLL2: "roll2", SOLO: "solo"}
    phrases = set()
    for note, ranges in spans.items():
        kind = "fill" if note in FILL_NOTES else kinds.get(note)
        if kind:
            phrases.update((kind, a, b) for a, b in ranges)     # the 5 fill notes count once
    chart.phrases = [Phrase(kind, a, b, tempo.tick_to_s(a), tempo.tick_to_s(b))
                     for kind, a, b in sorted(phrases, key=lambda p: (p[1], p[0]))]
    return chart
