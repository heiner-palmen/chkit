"""Groove fingerprint of a drum chart, and how alike two of them feel.

A fingerprint holds what a drummer plays: the bar pattern of the song (where
in the bar kick, snare, cymbals and toms come, averaged over the groove bars),
the tempo, and a few numbers for the feel (notes per second, fills, triplets,
16ths, ride). It is computed from the Expert notes of a chart (no Expert+
kicks) and kept as a small dict that converts to JSON (`encode`/`decode`).

    fp = fingerprint(chart.read(path))         None for a chart with too few notes
    fp["summary"]                              '4/4 · 8ths · snare 2+4 · 172 BPM'
    a, b = prepare(fp1), prepare(fp2)          once per fingerprint, for comparing many
    score, why = similarity(a, b)              0..1 and the parts it is made of
    explain(why)                               'beat 94 % · tempo 172/168 BPM · feel 81 %'

How alike two songs feel (`similarity`): the bar pattern counts most, then
the tempo, then the feel numbers (0.5 / 0.3 / 0.2). The pattern is compared
voice by voice (cosine of the averaged bar patterns; kick, snare and cymbals
0.3 each, toms 0.1). A song is also compared with the other one played at
double tempo (16ths at 90 BPM against 8ths at 180 BPM: the same hand speed);
that counts slightly less (x 0.9) than the same pattern at the same tempo.
Bars of a different length (3/4 against 4/4) have no pattern in common.

Cymbals and toms come from the chart (`Note.cymbal`). A chart without cymbal
information (4-lane, not pro) has its yellow notes counted as cymbals (the
hi-hat in most of them) and blue/green as toms.

Standard library only.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_right
from collections import Counter

#: change it when the fingerprint changes: stored fingerprints of another version are computed again
VERSION = 1
#: grid positions per quarter note: 16ths (every 3) and 8th triplets (every 4) both fall on it
GRID = 12
VOICES = ("kick", "snare", "cymbal", "tom")
VOICE_WEIGHTS = {"kick": 0.3, "snare": 0.3, "cymbal": 0.3, "tom": 0.1}
PART_WEIGHTS = {"pattern": 0.5, "tempo": 0.3, "feel": 0.2}
DOUBLE_TEMPO_FACTOR = 0.9
TEMPO_SPREAD = 0.08                    # log-tempo spread: 5 % apart -> 0.82, 10 % -> 0.46, 20 % -> 0.07
# feel numbers: (key, how far apart counts as "different"); nps compares as a ratio
FEEL = (("nps", 0.30), ("fill", 0.15), ("triplet", 0.15), ("x16", 0.15), ("ride", 0.35))
MIN_NOTES = 32
MIN_FILL_TOMS = 4
TOM_GROOVE_SHARE = 0.4


# -- computing ------------------------------------------------------------------------

def _voice(note, has_cymbals: bool) -> str:
    if note.lane == "kick":
        return "kick"
    if note.lane == "red":
        return "snare"
    if has_cymbals:
        return "cymbal" if note.cymbal else "tom"
    return "cymbal" if note.lane == "yellow" else "tom"


def fingerprint(chart) -> dict | None:
    """The fingerprint of a chkit Chart (see the module docstring), or None
    when it has fewer than MIN_NOTES notes."""
    notes = [n for n in chart.notes if not n.kick2x]
    if len(notes) < MIN_NOTES:
        return None
    res = chart.resolution
    bars = chart.bar_lines()
    starts = [round(tick * GRID / res) for tick, _ in bars]
    has_cymbals = chart.cymbal_source != "none"

    played: dict[int, dict[str, set[int]]] = {}
    lanes: Counter = Counter()
    for n in notes:
        q = round(n.tick * GRID / res)
        i = bisect_right(starts, q) - 1
        if i < 0 or i >= len(starts) - 1:
            continue
        voice = _voice(n, has_cymbals)
        played.setdefault(i, {v: set() for v in VOICES})[voice].add(q - starts[i])
        if voice == "cymbal":
            lanes[n.lane] += 1
    if not played:
        return None

    length = {i: starts[i + 1] - starts[i] for i in played}
    fills = [i for i, v in played.items()
             if len(v["tom"]) >= MIN_FILL_TOMS and len(v["tom"]) >= len(v["cymbal"])]
    if len(fills) > TOM_GROOVE_SHARE * len(played):
        fills = []                     # that many "fills" are the groove: played on the toms
    groove = [i for i in played if i not in set(fills)] or list(played)
    bar_len = Counter(length[i] for i in groove).most_common(1)[0][0]
    main = sorted(i for i in groove if length[i] == bar_len)

    template = {}
    for v in VOICES:
        counts = Counter(p for i in main for p in played[i][v])
        template[v] = [counts.get(p, 0) / len(main) for p in range(bar_len)]

    # tempo and notes per second over the bars that are played
    seconds = sum(bars[i + 1][1] - bars[i][1] for i in played)
    bpm = (sum(chart.tempo.bpm_at(bars[i][0]) * (bars[i + 1][1] - bars[i][1]) for i in played) / seconds
           if seconds > 0 else chart.tempo.bpm_at(0))
    positions = [p for i in main for v in VOICES for p in played[i][v]]
    hits = sum(len(s) for v in played.values() for s in v.values())
    cymbals = sum(lanes.values())
    features = {
        "nps": round(hits / seconds, 3) if seconds > 0 else 0.0,
        "fill": round(len(fills) / len(played), 3),
        "triplet": round(sum(1 for p in positions if p % 3) / len(positions), 3) if positions else 0.0,
        "x16": round(sum(1 for p in positions if p % 6 == 3) / len(positions), 3) if positions else 0.0,
        "ride": round(lanes.get("blue", 0) / cymbals, 3) if cymbals else 0.0,
        "same_bar": round(Counter(tuple(tuple(sorted(played[i][v])) for v in VOICES) for i in main)
                          .most_common(1)[0][1] / len(main), 3),
    }
    fp = {
        "version": VERSION,
        "bar_len": bar_len,
        "time_signature": _time_signature(chart, bars[main[0]][0]),
        "bpm": round(bpm, 2),
        "pattern": {v: "".join(str(min(9, round(x * 9))) for x in template[v]) for v in VOICES},
        "features": features,
        "has_cymbals": has_cymbals,
    }
    fp["summary"] = summary(fp)
    return fp


def _time_signature(chart, tick: int) -> str:
    sig = None
    for s in sorted(chart.time_signatures):
        if s.tick <= tick:
            sig = s
    return f"{sig.numerator}/{sig.denominator}" if sig else "4/4"


def _strong(digits: str, level: int = 5) -> list[int]:
    return [p for p, d in enumerate(digits) if int(d) >= level]


def hands_label(digits: str) -> str:
    """How the cymbals keep time in the pattern: '16ths', '8ths', 'quarters',
    'triplets', 'shuffle', or '' when no grid is held."""
    strong = set(_strong(digits))
    n = len(digits)

    def covered(step, offsets=(0,)):
        spots = [p for p in range(n) if p % step in offsets]
        return spots and sum(1 for p in spots if p in strong) / len(spots) >= 0.75

    if covered(3):
        return "16ths"
    if covered(4):
        return "triplets"
    if covered(6):
        return "8ths"
    if covered(GRID, (0, 8)) and not covered(GRID, (4,)):
        return "shuffle"
    if covered(GRID):
        return "quarters"
    return ""


def snare_label(digits: str) -> str:
    """Where the snare sits: '2+4', '3' (halftime), 'every beat', 'offbeats'
    (on every &), or '' for no clear place."""
    strong = _strong(digits)
    beats = len(digits) // GRID
    on = [p // GRID + 1 for p in strong if p % GRID == 0]
    offs = [p for p in strong if p % GRID == GRID // 2]
    if beats and len(offs) == beats and not on:
        return "offbeats"
    if beats > 1 and len(on) == beats and len(strong) == beats:
        return "every beat"
    if on and len(on) == len(strong):
        return "+".join(str(b) for b in on)
    return ""


def summary(fp: dict) -> str:
    """'4/4 · 8ths · snare 2+4 · 172 BPM' for a fingerprint."""
    parts = [fp.get("time_signature") or ""]
    hands = hands_label(fp["pattern"]["cymbal"])
    if hands:
        parts.append(hands)
    elif max(fp["pattern"]["tom"], default="0") >= "5":
        parts.append("toms")
    snare = snare_label(fp["pattern"]["snare"])
    if snare:
        parts.append(f"snare {snare}")
    parts.append(f"{round(fp['bpm'])} BPM")
    return " · ".join(p for p in parts if p)


def encode(fp: dict) -> str:
    return json.dumps(fp, separators=(",", ":"), sort_keys=True)


def decode(text: str) -> dict | None:
    try:
        fp = json.loads(text)
    except (TypeError, ValueError):
        return None
    return fp if isinstance(fp, dict) and fp.get("version") == VERSION else None


# -- comparing ------------------------------------------------------------------------

class Prepared:
    """A fingerprint made ready for many comparisons: per voice the pattern
    as numbers, its non-empty places, its length, and the length it has when
    stretched to double tempo."""

    __slots__ = ("bar_len", "bpm", "features", "voices", "summary")

    def __init__(self, fp: dict):
        self.bar_len = fp["bar_len"]
        self.bpm = float(fp["bpm"])
        self.features = fp.get("features") or {}
        self.summary = fp.get("summary") or ""
        self.voices = {}
        for v in VOICES:
            dense = [int(d) / 9 for d in fp["pattern"][v]]
            sparse = [(p, x) for p, x in enumerate(dense) if x]
            norm = math.sqrt(sum(x * x for _, x in sparse))
            # stretched: position q holds what was at 2q, so every even place counts twice
            norm2 = math.sqrt(2 * sum(x * x for p, x in sparse if p % 2 == 0))
            self.voices[v] = (dense, sparse, norm, norm2)


def prepare(fp: dict) -> Prepared:
    return Prepared(fp)


def _pattern(a: Prepared, b: Prepared, mode: str) -> float:
    """Cosine per voice, weighted. mode 'same': as they are; 'double': b at
    double tempo (b's bar fills half of a's bar, twice); 'half': a at double tempo."""
    n = a.bar_len
    total = weights = 0.0
    for v in VOICES:
        da, sa, na, na2 = a.voices[v]
        db, sb, nb, nb2 = b.voices[v]
        if not sa and not sb:
            continue
        w = VOICE_WEIGHTS[v]
        weights += w
        if not sa or not sb:
            continue
        if mode == "same":
            if len(sa) > len(sb):
                dot = sum(x * da[p] for p, x in sb)
            else:
                dot = sum(x * db[p] for p, x in sa)
            norm = na * nb
        elif mode == "double":
            dot = sum(x * db[(2 * p) % n] for p, x in sa)
            norm = na * nb2
        else:
            dot = sum(x * da[(2 * p) % n] for p, x in sb)
            norm = na2 * nb
        if norm > 0:
            total += w * dot / norm
    return total / weights if weights else 0.0


def _tempo(bpm_a: float, bpm_b: float) -> float:
    if bpm_a <= 0 or bpm_b <= 0:
        return 0.0
    d = math.log(bpm_a / bpm_b)
    return math.exp(-d * d / (2 * TEMPO_SPREAD * TEMPO_SPREAD))


def _feel(a: Prepared, b: Prepared) -> float:
    parts = []
    for key, scale in FEEL:
        x, y = a.features.get(key), b.features.get(key)
        if x is None or y is None:
            continue
        if key == "nps":
            if x <= 0 or y <= 0:
                continue
            diff = abs(math.log(x / y))
        else:
            diff = abs(x - y)
        parts.append(math.exp(-diff / scale))
    return sum(parts) / len(parts) if parts else 0.0


def similarity(a: Prepared, b: Prepared) -> tuple[float, dict]:
    """(score 0..1, parts): how alike b feels to a. parts: pattern, tempo,
    feel (0..1 each), mode ('same', 'double': b is a at double tempo,
    'half': b is a at half tempo) and both tempos as compared."""
    feel = _feel(a, b)
    candidates = []
    for mode, bpm_a, bpm_b, factor in (("same", a.bpm, b.bpm, 1.0),
                                        ("double", a.bpm, b.bpm / 2, DOUBLE_TEMPO_FACTOR),
                                        ("half", a.bpm / 2, b.bpm, DOUBLE_TEMPO_FACTOR)):
        pattern = _pattern(a, b, mode) if a.bar_len == b.bar_len else 0.0
        tempo = _tempo(bpm_a, bpm_b)
        score = factor * (PART_WEIGHTS["pattern"] * pattern + PART_WEIGHTS["tempo"] * tempo
                          + PART_WEIGHTS["feel"] * feel)
        candidates.append((score, {"pattern": pattern, "tempo": tempo, "feel": feel, "mode": mode,
                                   "bpm_a": a.bpm, "bpm_b": b.bpm}))
    score, parts = max(candidates, key=lambda c: c[0])
    return score, parts


def explain(parts: dict) -> str:
    """'beat 94 % · tempo 172/168 BPM · feel 81 %' (+ 'at double tempo')."""
    text = (f"beat {round(parts['pattern'] * 100)} % · tempo {round(parts['bpm_a'])}/{round(parts['bpm_b'])} BPM"
            f" · feel {round(parts['feel'] * 100)} %")
    if parts["mode"] == "double":
        text += " · at double tempo"
    elif parts["mode"] == "half":
        text += " · at half tempo"
    return text
