"""Groove fingerprint of a drum chart, and how alike two of them feel.

A fingerprint holds what a drummer plays, from the Expert notes of a chart
(no Expert+ kicks), as a small dict that converts to JSON (`encode`/`decode`):

- grooves: the bar patterns the song is played with (verse, chorus, ...), up
  to MAX_GROOVES, each with its share of the groove time. Bars that play
  alike form one groove; its pattern says how often each place of the bar
  (12 per quarter: 16ths and triplets) holds a note, per voice: kick, snare,
  hands (whatever keeps time in the bar: hi-hat, ride, crash or a tom) and
  other (crashes and toms on top). Fills are left out, and so are bars
  without kick and snare (an intro on the hi-hat alone, a build-up on the
  kick alone).
- rhythm: how far apart the notes of kick, snare and hands come, in seconds
  (a histogram on a log scale). It does not depend on how the chart is
  notated: one charter writes a song at 92 BPM, another at 184.
- features: numbers for the feel, mostly per second: notes, hands, kick, the
  time-keeping voice and the snare per second, the busiest bars, kicks off
  the beat, on 16ths and in quick runs, kick on every beat, snare on the
  beat, triplets, fills, toms, crashes, bars of 2 or 4 quarters, how much of
  the song is not the main groove, and which cymbal keeps time (only where
  the chart tells cymbals from toms).
- the tempo (weighted by playing time) and a summary for the main groove,
  e.g. '4/4 · 8ths hi-hat · snare 2+4 · 172 BPM'.

    fp = fingerprint(chart.read(path))         None for a chart with too few notes
    fp["summary"]                              '4/4 · 8ths hi-hat · snare 2+4 · 172 BPM'
    a, b = prepare(fp1), prepare(fp2)          once per fingerprint, for comparing many
    score, why = similarity(a, b)              0..1 and the parts it is made of
    explain(why)                               'beat 94 % · tempo 172/168 BPM · feel 81 % (kick 2.1/3.0 per s)'

How alike two songs feel (`similarity`) is the weighted geometric mean of
four parts (PART_WEIGHTS), so a song far off in one of them drops a lot:

- feel (0.5): the feature numbers, each against how much it varies across
  the library; the notes, hands and kick per second count most.
- pattern (0.2): the grooves of one song against the best matching grooves
  of the other, weighted by their shares, both ways. Per voice the places
  played in at least half of the bars are compared (Dice; a kick one 16th
  off counts half). Bars of 2/4 are laid twice against bars of 4/4, and a
  pattern shifted by half a bar counts slightly less (x 0.9).
- rhythm (0.2): the histograms of the note distances, 1 - their Hellinger
  distance.
- tempo (0.1): the BPM on a log scale (20 % apart -> 0.64).
"beat" in `explain` is pattern and rhythm together. A song is also compared
with the other one played at double tempo (16ths at 90 BPM against 8ths at
180 BPM); its pattern then counts less (x 0.85) than the same pattern at the
same tempo. The numbers in seconds do not change with the notation.

Cymbals and toms come from the chart (`Note.cymbal`). A chart without cymbal
information (4-lane, not pro) has its yellow notes counted as cymbals and
blue/green as toms, except for the lane that keeps time in a bar; which
cymbal keeps time is unknown there. In a 5-lane chart a time-keeping orange
cymbal counts as the ride.

Standard library only.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_right
from collections import Counter

#: change it when the fingerprint changes: stored fingerprints of another version are computed again
VERSION = 2
#: grid positions per quarter note: 16ths (every 3) and 8th triplets (every 4) both fall on it
GRID = 12
VOICES = ("kick", "snare", "hands", "other")
MIN_NOTES = 32
MIN_FILL_TOMS = 4
TOM_GROOVE_SHARE = 0.4                 # more fill bars than this: the toms are the groove
FULL_GROOVE_SHARE = 0.3                # fewer bars with kick and snare than this: all bars are the groove
CLUSTER_JOIN = 0.7                     # bars this alike (weighted Dice) play the same groove
MAX_GROOVES = 3
MIN_GROOVE_SHARE = 0.1
KICK_RUN_S = 0.16                      # kicks this close (seconds) after each other form a run
IOI_MIN, IOI_MAX, IOI_BINS = 0.06, 2.4, 16
MIN_IOIS = 8

PART_WEIGHTS = {"feel": 0.5, "pattern": 0.2, "rhythm": 0.2, "tempo": 0.1}
VOICE_WEIGHTS = {"kick": 0.35, "snare": 0.3, "hands": 0.25, "other": 0.1}
RHYTHM_WEIGHTS = {"kick": 0.4, "snare": 0.3, "hands": 0.3}
NEAR_KICK = 0.5                        # a kick one 16th off counts this much
HALF_BAR_FACTOR = 0.9
HALF_BAR_TRY = 0.6                     # only patterns this far apart are tried half a bar shifted
DOUBLE_TEMPO_FACTOR = 0.85
PATTERN_FLOOR = 0.25                   # no pattern in common (3/4 against 4/4) still leaves the other parts
RHYTHM_FLOOR = 0.05
TEMPO_SPREAD = 0.2                     # log-tempo spread: 10 % apart -> 0.89, 20 % -> 0.64, 40 % -> 0.15
# feel numbers: key -> (weight, spread, compared on a log scale). The spreads are the standard
# deviations over a sample of the library (of log(x + 0.2) for the rates), wider for the shares
# that are 0 in most songs (kick runs, triplets), so that one of them cannot outweigh the rest
FEEL = {
    "nps": (2.0, 0.30, True),          # notes per second
    "hands_ps": (1.5, 0.30, True),     # snare, cymbal and tom notes per second (groove bars)
    "kick_ps": (3.0, 0.45, True),      # kick notes per second (groove bars)
    "keeper_ps": (0.25, 0.40, True),   # notes of the time-keeping voice per second
    "snare_ps": (0.25, 0.45, True),
    "peak_ps": (1.5, 0.30, True),      # notes per second of the busiest bars (90th percentile)
    "kick_off": (1.0, 0.22, False),    # share of the kicks off the beat
    "kick16": (0.25, 0.16, False),     # share of the kicks on the e and a of a beat
    "kick_run": (0.25, 0.20, False),   # share of the kicks in quick runs (3 or more)
    "four": (0.25, 0.25, False),       # share of the groove time with a kick on every beat
    "backbeat": (0.25, 0.25, False),   # share of the snare notes on a beat
    "triplet": (0.5, 0.15, False),     # share of the notes on triplet places
    "fill": (0.25, 0.09, False),       # share of the bars that are fills
    "tom": (0.25, 0.17, False),        # share of the hand notes on toms
    "crash": (0.5, 0.46, False),       # cymbal notes besides the time keeping, per groove bar
    "meter": (0.5, 0.22, False),       # share of the playing time in bars of 2 or 4 quarters
    "variety": (1.5, 0.23, False),     # share of the groove time outside the main groove
    "keeper_hihat": (1.0, 0.31, False),    # which voice keeps time (share of the groove time),
    "keeper_ride": (0.25, 0.26, False),    # only for charts that tell cymbals from toms
    "keeper_crash": (0.5, 0.21, False),
    "keeper_tom": (0.25, 0.15, False),
}
KEEPERS = ("hihat", "ride", "crash", "tom")
KEEPER_NAMES = {"hihat": "hi-hat", "ride": "ride", "crash": "crash", "tom": "toms"}
# how `explain` names a feel number; "%": a share, "/s": per second, "/bar": per bar
FEEL_TEXT = {
    "nps": ("notes", "/s"), "hands_ps": ("hands", "/s"), "kick_ps": ("kick", "/s"),
    "keeper_ps": ("time keeping", "/s"), "snare_ps": ("snare", "/s"), "peak_ps": ("busiest bars", "/s"),
    "kick_off": ("kick off the beat", "%"), "kick16": ("kick on 16ths", "%"), "kick_run": ("kick runs", "%"),
    "four": ("kick on every beat", "%"), "backbeat": ("snare on the beat", "%"), "triplet": ("triplets", "%"),
    "fill": ("fill bars", "%"), "tom": ("toms", "%"), "crash": ("crashes", "/bar"),
    "meter": ("bars of 2 or 4 beats", "%"), "variety": ("other grooves", "%"),
    "keeper_hihat": ("hi-hat keeps time", "%"), "keeper_ride": ("ride keeps time", "%"),
    "keeper_crash": ("crash keeps time", "%"), "keeper_tom": ("toms keep time", "%"),
}
EXPLAIN_FEEL_BELOW = 0.9               # name the feel number furthest apart when feel is below this


# -- computing ------------------------------------------------------------------------

def _pad(note, has_cymbals: bool) -> tuple[str, bool]:
    """(lane, cymbal?) of a hand note other than the snare."""
    if has_cymbals:
        return note.lane, bool(note.cymbal)
    return note.lane, note.lane == "yellow"


_LANE_ORDER = {"yellow": 0, "blue": 1, "green": 2}


def _bar(hits, has_cymbals: bool, five_lane: bool) -> dict:
    """One bar, `hits` [(place, note)]: the places per voice, the pad that
    keeps time (the one with most notes, cymbals first), what it is, and
    the counts of toms, cymbals and accent cymbals."""
    kick, snare, pads = set(), set(), {}
    for p, n in hits:
        if n.lane == "kick":
            kick.add(p)
        elif n.lane == "red":
            snare.add(p)
        else:
            pads.setdefault(_pad(n, has_cymbals), set()).add(p)
    keeper = max(pads, key=lambda k: (len(pads[k]), k[1], -_LANE_ORDER.get(k[0], 3))) if pads else None
    other = set()
    for k, places in pads.items():
        if k != keeper:
            other |= places
    # without cymbal information the lane that keeps time is no tom (a ride on blue)
    toms = sum(len(v) for k, v in pads.items() if not k[1] and (has_cymbals or k != keeper))
    cymbals = sum(len(v) for k, v in pads.items() if k[1] or (not has_cymbals and k == keeper))
    if keeper is None or not has_cymbals:
        kind = None
    elif not keeper[1]:
        kind = "tom"
    else:
        kind = {"yellow": "hihat", "blue": "ride", "green": "ride" if five_lane else "crash"}[keeper[0]]
    return {"kick": kick, "snare": snare, "hands": pads.get(keeper, set()), "other": other, "keeper": keeper,
            "kind": kind, "toms": toms, "cymbals": cymbals,
            "accents": sum(len(v) for k, v in pads.items() if k[1] and k != keeper)}


def _dice(a: set, b: set) -> float:
    return 1.0 if not a and not b else 2 * len(a & b) / (len(a) + len(b))


def _alike(a: tuple, b: tuple) -> float:
    """How alike two bars are: (kick, snare, hands) place sets."""
    return 0.35 * _dice(a[0], b[0]) + 0.3 * _dice(a[1], b[1]) + 0.35 * _dice(a[2], b[2])


def _grooves(groove_bars, bar, length, secs) -> list[dict]:
    """The bars grouped into grooves, biggest first: a bar joins the groove
    whose first bar is most alike (at least CLUSTER_JOIN), of the same
    length and with the same pad keeping time, else starts a new one."""
    same: dict = {}
    for i in groove_bars:
        key = (length[i], bar[i]["keeper"], frozenset(bar[i]["kick"]), frozenset(bar[i]["snare"]),
               frozenset(bar[i]["hands"]))
        same.setdefault(key, []).append(i)
    clusters = []
    for key, members in sorted(same.items(), key=lambda kv: (-sum(secs[i] for i in kv[1]), kv[1][0])):
        home, best = None, CLUSTER_JOIN
        for c in clusters:
            if c["key"][:2] == key[:2]:            # same bar length, same pad keeping time
                s = _alike(key[2:], c["key"][2:])
                if s >= best:
                    home, best = c, s
        if home is None:
            clusters.append({"key": key, "members": list(members)})
        else:
            home["members"] += members
    total = sum(secs[i] for i in groove_bars) or 1.0
    out = []
    for c in sorted(clusters, key=lambda c: -sum(secs[i] for i in c["members"])):
        weight = sum(secs[i] for i in c["members"])
        if out and (weight / total < MIN_GROOVE_SHARE or len(out) >= MAX_GROOVES):
            break
        n = c["key"][0]
        pattern = {}
        for v in VOICES:
            counts = Counter()
            for i in c["members"]:
                for p in bar[i][v]:
                    counts[p] += secs[i]
            pattern[v] = "".join(str(min(9, round(counts.get(p, 0) / weight * 9))) for p in range(n))
        kinds = Counter()
        for i in c["members"]:
            kinds[bar[i]["kind"]] += secs[i]
        out.append({"share": round(weight / total, 3), "bar_len": n, "keeper": kinds.most_common(1)[0][0],
                    "pattern": pattern, "first": min(c["members"])})
    return out


def _histogram(times: list[float]) -> list[int]:
    """Distances between notes following each other, IOI_MIN..IOI_MAX seconds
    on a log scale in IOI_BINS bins, each note shared between its two
    nearest bins; in % of the distances ([] for fewer than MIN_IOIS)."""
    hist = [0.0] * IOI_BINS
    count = 0
    span = math.log(IOI_MAX / IOI_MIN)
    times = sorted(times)
    for a, b in zip(times, times[1:]):
        d = b - a
        if d < 1e-4 or d > IOI_MAX:        # notes at the same time (two lanes of one voice) count once
            continue
        x = math.log(max(d, IOI_MIN) / IOI_MIN) / span * (IOI_BINS - 1)
        lo = min(int(x), IOI_BINS - 2)
        hist[lo] += 1 - (x - lo)
        hist[lo + 1] += x - lo
        count += 1
    return [round(h / count * 100) for h in hist] if count >= MIN_IOIS else []


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

    hits: dict[int, list] = {}
    for n in notes:
        q = round(n.tick * GRID / res)
        i = bisect_right(starts, q) - 1
        if 0 <= i < len(starts) - 1:
            hits.setdefault(i, []).append((q - starts[i], n))
    if not hits:
        return None
    played = sorted(hits)
    bar = {i: _bar(hits[i], has_cymbals, chart.cymbal_source == "five_lane") for i in played}
    length = {i: starts[i + 1] - starts[i] for i in played}
    secs = {i: max(bars[i + 1][1] - bars[i][1], 1e-6) for i in played}

    fills = {i for i in played if bar[i]["toms"] >= MIN_FILL_TOMS and bar[i]["toms"] >= bar[i]["cymbals"]}
    if len(fills) > TOM_GROOVE_SHARE * len(played):
        fills = set()                  # that many "fills" are the groove: played on the toms
    rest = [i for i in played if i not in fills] or played
    groove = [i for i in rest if bar[i]["kick"] and bar[i]["snare"]]
    if sum(secs[i] for i in groove) < FULL_GROOVE_SHARE * sum(secs[i] for i in rest):
        groove = rest
    grooves = _grooves(groove, bar, length, secs)

    seconds = sum(secs.values())
    groove_s = sum(secs[i] for i in groove)
    bpm = sum(chart.tempo.bpm_at(bars[i][0]) * secs[i] for i in played) / seconds
    in_groove = [(p, n) for i in groove for p, n in hits[i]]
    kicks = [p for p, n in in_groove if n.lane == "kick"]
    snares = [p for p, n in in_groove if n.lane == "red"]
    hands = [p for p, n in in_groove if n.lane != "kick"]
    kick_times = [n.t for n in notes if n.lane == "kick"]
    in_runs, run = 0, 1
    for j in range(1, len(kick_times) + 1):
        if j < len(kick_times) and kick_times[j] - kick_times[j - 1] <= KICK_RUN_S:
            run += 1
            continue
        if run >= 3:
            in_runs += run
        run = 1
    hand_notes = sum(1 for n in notes if n.lane not in ("kick", "red"))
    rates = sorted(len(hits[i]) / secs[i] for i in played)

    def share(part, whole):
        return round(part / whole, 3) if whole else 0.0

    features = {
        "nps": share(len(notes), seconds),
        "hands_ps": share(len(hands), groove_s),
        "kick_ps": share(len(kicks), groove_s),
        "keeper_ps": share(sum(len(bar[i]["hands"]) for i in groove), groove_s),
        "snare_ps": share(len(snares), groove_s),
        "peak_ps": round(rates[int(0.9 * (len(rates) - 1))], 3),
        "kick_off": share(sum(1 for p in kicks if p % GRID), len(kicks)),
        "kick16": share(sum(1 for p in kicks if p % 6 == 3), len(kicks)),
        "kick_run": share(in_runs, len(kick_times)),
        "four": share(sum(secs[i] for i in groove if length[i] % GRID == 0
                          and all(b * GRID in bar[i]["kick"] for b in range(length[i] // GRID))), groove_s),
        "backbeat": share(sum(1 for p in snares if p % GRID == 0), len(snares)),
        "triplet": share(sum(1 for p, _ in in_groove if p % 3), len(in_groove)),
        "fill": share(len(fills), len(played)),
        "tom": share(sum(bar[i]["toms"] for i in played), hand_notes),
        "crash": share(sum(bar[i]["accents"] for i in groove), len(groove)),
        "meter": share(sum(secs[i] for i in played if length[i] in (2 * GRID, 4 * GRID)), seconds),
        "variety": round(1 - grooves[0]["share"], 3),
    }
    kinds = Counter()
    for i in groove:
        if bar[i]["kind"]:
            kinds[bar[i]["kind"]] += secs[i]
    if has_cymbals and kinds:
        for k in KEEPERS:
            features["keeper_" + k] = share(kinds.get(k, 0), sum(kinds.values()))

    # the notes of each voice in the groove bars, in seconds, for the rhythm histograms
    times = {"kick": [], "snare": [], "hands": []}
    for i in groove:
        for p, n in hits[i]:
            if n.lane == "kick":
                times["kick"].append(n.t)
            elif n.lane == "red":
                times["snare"].append(n.t)
            elif _pad(n, has_cymbals) == bar[i]["keeper"]:
                times["hands"].append(n.t)

    first = [g.pop("first") for g in grooves]
    fp = {
        "version": VERSION,
        "bar_len": grooves[0]["bar_len"],
        "time_signature": _time_signature(chart, bars[first[0]][0]),
        "bpm": round(bpm, 2),
        "grooves": grooves,
        "rhythm": {v: _histogram(t) for v, t in times.items()},
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
    """How the hands keep time in the pattern: '16ths', '8ths', 'quarters',
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
    """'4/4 · 8ths hi-hat · snare 2+4 · 172 BPM' for a fingerprint (its main groove)."""
    main = fp["grooves"][0]
    parts = [fp.get("time_signature") or ""]
    hands = hands_label(main["pattern"]["hands"])
    keeper = KEEPER_NAMES.get(main.get("keeper"), "")
    if hands or keeper == "toms":
        parts.append(f"{hands} {keeper}".strip())
    snare = snare_label(main["pattern"]["snare"])
    if snare:
        parts.append(f"snare {snare}")
    parts.append(f"{round(fp['bpm'])} BPM")
    return " · ".join(p for p in parts if p)


def encode(fp: dict) -> str:
    return json.dumps(fp, separators=(",", ":"), sort_keys=True)


def decode(text: str) -> dict | None:
    """The fingerprint, or None for one of another VERSION (compute it again)."""
    try:
        fp = json.loads(text)
    except (TypeError, ValueError):
        return None
    return fp if isinstance(fp, dict) and fp.get("version") == VERSION else None


# -- comparing ------------------------------------------------------------------------

_VOICE_W = tuple(VOICE_WEIGHTS[v] for v in VOICES)
_REST_W = _VOICE_W[1:]
# the weight of the rhythm voices present (bit i: the i-th voice of RHYTHM_WEIGHTS)
_RHYTHM_W = [sum(w for i, w in enumerate(RHYTHM_WEIGHTS.values()) if bits >> i & 1)
             for bits in range(1 << len(RHYTHM_WEIGHTS))]
_CORE = tuple(k for k in FEEL if not k.startswith("keeper_"))
_KEEPER = tuple("keeper_" + k for k in KEEPERS)
_CORE_W = sum(FEEL[k][0] for k in _CORE)
_KEEPER_W = sum(FEEL[k][0] for k in _KEEPER)


_HALF_OR_MORE = str.maketrans("0123456789", "0000011111")


def _mask(digits: str) -> int:
    """The places played in at least half of the bars, as bits."""
    return int(digits.translate(_HALF_OR_MORE)[::-1] or "0", 2)


def _doubled(digits: str) -> str:
    """The pattern played at double tempo: place q holds what was at 2q (twice per bar)."""
    n = len(digits)
    return digits[::2] * 2 if n % 2 == 0 else "".join(digits[2 * q % n] for q in range(n))


def _voices_of(masks: tuple, n: int) -> tuple:
    """(kick, its note count, the kick one 16th to either side, the other
    voices, their note counts) of one pattern, as bit masks."""
    kick = masks[0]
    return (kick, kick.bit_count(), ((kick << 3) | (kick >> 3)) & ((1 << n) - 1), masks[1:],
            tuple(m.bit_count() for m in masks[1:]))


def _rotated(masks: tuple, n: int) -> tuple:
    full, by = (1 << n) - 1, n // 2
    return tuple(((m >> by) | (m << (n - by))) & full for m in masks)


def _tiled(voices: tuple, n: int) -> tuple:
    """A pattern of n places twice in a row (2/4 laid against 4/4)."""
    return _voices_of(tuple(m | (m << n) for m in (voices[0], *voices[3])), 2 * n)


class Groove:
    """One groove of a prepared fingerprint: its share, bar length and its
    voices as they are, at double tempo, and both shifted by half a bar
    (each as `_voices_of`)."""

    __slots__ = ("share", "n", "plain", "doubled", "plain_half", "doubled_half")

    def __init__(self, g: dict):
        self.share = g["share"]
        n = self.n = g["bar_len"]
        masks = tuple(_mask(g["pattern"][v]) for v in VOICES)
        doubled = tuple(_mask(_doubled(g["pattern"][v])) for v in VOICES)
        self.plain, self.doubled = _voices_of(masks, n), _voices_of(doubled, n)
        self.plain_half = _voices_of(_rotated(masks, n), n) if n % (2 * GRID) == 0 else None
        self.doubled_half = _voices_of(_rotated(doubled, n), n) if n % (2 * GRID) == 0 else None


class Prepared:
    """A fingerprint made ready for many comparisons: the grooves as bit
    masks, the rhythm histograms as roots (see `_rhythm`), the feel numbers
    scaled by their spread in the library and the root of their weight (log
    scale where FEEL says so), so that their weighted distance is a plain one."""

    __slots__ = ("bpm", "features", "summary", "grooves", "shares", "rhythm", "voices", "core", "keeper")

    def __init__(self, fp: dict):
        self.bpm = float(fp["bpm"])
        self.features = fp.get("features") or {}
        self.summary = fp.get("summary") or ""
        self.grooves = [Groove(g) for g in fp["grooves"]]
        self.shares = sum(g.share for g in self.grooves) or 1.0
        # the roots of the histograms one after the other, each times the root of its weight (a
        # missing one as zeros), and which are there (bits): see _rhythm
        rhythm = fp.get("rhythm") or {}
        self.rhythm = tuple(math.sqrt(x * w / 100) for v, w in RHYTHM_WEIGHTS.items()
                            for x in (rhythm.get(v) or [0] * IOI_BINS))
        self.voices = sum(1 << i for i, v in enumerate(RHYTHM_WEIGHTS) if rhythm.get(v))
        self.core = tuple(_scaled(k, self.features.get(k, 0.0)) for k in _CORE)
        self.keeper = (tuple(_scaled(k, self.features[k]) for k in _KEEPER)
                       if all(k in self.features for k in _KEEPER) else None)


def _scaled(key: str, x: float) -> float:
    weight, spread, log = FEEL[key]
    return (math.log(x + 0.2) if log else x) * math.sqrt(weight) / spread


def prepare(fp: dict) -> Prepared:
    return Prepared(fp)


def _voices(a: tuple, b: tuple) -> float:
    """Dice per voice, weighted; a voice empty in both does not count; a
    kick one 16th off counts NEAR_KICK. a, b: as `_voices_of`."""
    x, cx, x_near, a_rest, a_counts = a
    y, cy, y_near, b_rest, b_counts = b
    total = weights = 0.0
    if x or y:
        weights = _VOICE_W[0]
        if x and y:
            near = min((x & ~y & y_near).bit_count(), (y & ~x & x_near).bit_count())
            total = weights * 2 * ((x & y).bit_count() + NEAR_KICK * near) / (cx + cy)
    for x, y, cx, cy, w in zip(a_rest, b_rest, a_counts, b_counts, _REST_W):
        if x or y:
            weights += w
            if x and y:
                total += w * 2 * (x & y).bit_count() / (cx + cy)
    return total / weights if weights else 0.0


def _groove_pair(ga: Groove, gb: Groove, mode: str) -> float:
    """How alike two grooves are. mode 'same': as they are; 'double': gb at
    double tempo; 'half': ga at double tempo."""
    va = ga.doubled if mode == "half" else ga.plain
    vb, vb_half = (gb.doubled, gb.doubled_half) if mode == "double" else (gb.plain, gb.plain_half)
    if ga.n != gb.n:                   # 2/4 against 4/4: the short bar twice
        if ga.n == 2 * gb.n:
            vb, vb_half = _tiled(vb, gb.n), None
        elif gb.n == 2 * ga.n:
            va = _tiled(va, ga.n)
            vb_half = None
        else:
            return 0.0
    s = _voices(va, vb)
    if vb_half is not None and s < HALF_BAR_TRY:        # the bar lines half a bar apart?
        s = max(s, HALF_BAR_FACTOR * _voices(va, vb_half))
    return s


def _pattern(a: Prepared, b: Prepared, mode: str) -> float:
    """Each groove against the best matching groove of the other song,
    weighted by the shares, both ways."""
    sims = [[_groove_pair(ga, gb, mode) for gb in b.grooves] for ga in a.grooves]
    ab = sum(ga.share * max(row) for ga, row in zip(a.grooves, sims)) / a.shares
    ba = sum(gb.share * max(col) for gb, col in zip(b.grooves, zip(*sims))) / b.shares
    return (ab + ba) / 2


def _rhythm(a: Prepared, b: Prepared) -> float:
    """How alike the rhythm histograms are: 1 - the Hellinger distance of
    the weighted Bhattacharyya coefficient BC over the voices either song
    has (a voice only one song has counts 0). With h the roots of the
    histograms, |ha - hb|^2 is 2 - 2 BC for a voice both have and 1 for a
    voice one has, so one distance over all voices gives the weighted BC."""
    either = _RHYTHM_W[a.voices | b.voices]
    if not either:
        return 0.0
    both, one = _RHYTHM_W[a.voices & b.voices], _RHYTHM_W[a.voices ^ b.voices]
    bc = (2 * both + one - math.dist(a.rhythm, b.rhythm) ** 2) / (2 * either)
    return 1 - math.sqrt(min(1.0, max(0.0, 1 - bc)))


def _feel(a: Prepared, b: Prepared) -> float:
    """0..1 over the feel numbers both have (which cymbal keeps time only
    when both charts tell cymbals from toms)."""
    total, weights = math.dist(a.core, b.core) ** 2, _CORE_W
    if a.keeper is not None and b.keeper is not None:
        total += math.dist(a.keeper, b.keeper) ** 2
        weights += _KEEPER_W
    return math.exp(-0.5 * total / weights)


def _apart(a: Prepared, b: Prepared) -> tuple | None:
    """(key, value of a, value of b) of the feel number that counts most
    against the two."""
    pairs = list(zip(_CORE, a.core, b.core))
    if a.keeper is not None and b.keeper is not None:
        pairs += zip(_KEEPER, a.keeper, b.keeper)
    key, x, y = max(pairs, key=lambda p: (p[1] - p[2]) ** 2)
    return (key, a.features.get(key, 0.0), b.features.get(key, 0.0)) if x != y else None


def _tempo(bpm_a: float, bpm_b: float) -> float:
    if bpm_a <= 0 or bpm_b <= 0:
        return 0.0
    d = math.log(bpm_a / bpm_b)
    return math.exp(-d * d / (2 * TEMPO_SPREAD * TEMPO_SPREAD))


def similarity(a: Prepared, b: Prepared, details: bool = True) -> tuple[float, dict | None]:
    """(score 0..1, parts): how alike b feels to a. parts: feel, pattern,
    rhythm, beat (pattern and rhythm together), tempo (0..1 each), mode
    ('same', 'double': b is a at double tempo, 'half': b is a at half
    tempo), both tempos as compared and `apart`: the feel number that counts
    most against the two, with both values (or None). details=False: the
    score alone (parts None), for ranking many songs."""
    feel = _feel(a, b)
    rhythm = _rhythm(a, b)
    w = PART_WEIGHTS
    rest = max(feel, 1e-6) ** w["feel"] * max(rhythm, RHYTHM_FLOOR) ** w["rhythm"]
    best = None
    for mode, bpm_a, bpm_b, factor in (("same", a.bpm, b.bpm, 1.0),
                                        ("double", a.bpm, b.bpm / 2, DOUBLE_TEMPO_FACTOR),
                                        ("half", a.bpm / 2, b.bpm, DOUBLE_TEMPO_FACTOR)):
        tempo = _tempo(bpm_a, bpm_b)
        bound = rest * max(tempo, 1e-6) ** w["tempo"] * factor ** w["pattern"]
        if best is not None and bound <= best[0]:
            continue                   # cannot win even with the same pattern
        pattern = factor * _pattern(a, b, mode)
        score = rest * max(tempo, 1e-6) ** w["tempo"] * max(pattern, PATTERN_FLOOR) ** w["pattern"]
        if best is None or score > best[0]:
            best = (score, mode, pattern, tempo)
    score, mode, pattern, tempo = best
    if not details:
        return score, None
    pw = w["pattern"] + w["rhythm"]
    beat = (max(pattern, PATTERN_FLOOR) ** w["pattern"] * max(rhythm, RHYTHM_FLOOR) ** w["rhythm"]) ** (1 / pw)
    return score, {"feel": feel, "pattern": pattern, "rhythm": rhythm, "beat": beat, "tempo": tempo, "mode": mode,
                   "bpm_a": a.bpm, "bpm_b": b.bpm, "apart": _apart(a, b)}


def _feel_text(key: str, x: float, y: float) -> str:
    name, unit = FEEL_TEXT[key]
    if unit == "%":
        return f"{name} {round(x * 100)}/{round(y * 100)} %"
    if unit == "/bar":
        return f"{name} {x:.1f}/{y:.1f} per bar"
    return f"{name} {x:.1f}/{y:.1f} per s"


def explain(parts: dict) -> str:
    """'beat 94 % · tempo 172/168 BPM · feel 81 % (kick 2.1/3.0 per s)'
    (+ 'at double tempo'); the feel number furthest apart is named when
    feel is below EXPLAIN_FEEL_BELOW."""
    text = (f"beat {round(parts['beat'] * 100)} % · tempo {round(parts['bpm_a'])}/{round(parts['bpm_b'])} BPM"
            f" · feel {round(parts['feel'] * 100)} %")
    apart = parts.get("apart")
    if apart and parts["feel"] < EXPLAIN_FEEL_BELOW:
        text += f" ({_feel_text(*apart)})"
    if parts["mode"] == "double":
        text += " · at double tempo"
    elif parts["mode"] == "half":
        text += " · at half tempo"
    return text
