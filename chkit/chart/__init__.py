"""Clone Hero drum charts: read .chart and .mid, write .chart.

    from chkit import chart
    c = chart.read("…/notes.mid")             # Expert, song.ini next to it
    for n in c.notes: n.tick, n.t, n.lane, n.cymbal
    c.bar_lines(), c.sections, c.section_at(42.0), c.tempo.tick_to_s(960)
"""

from __future__ import annotations

import os
from typing import Optional

from .chartfile import chart_text, read_chart, write_chart
from .midifile import read_mid, read_tracks
from .model import (DIFFICULTIES, FIVE_LANE, FOUR_LANE, FOUR_LANE_PRO, LANE_CODES, LANES, Chart, Note, Phrase,
                    Section, TimeSignature)
from .tempo import TempoMap

__all__ = ["read", "read_chart", "read_mid", "read_tracks", "chart_text", "write_chart", "Chart", "Note",
           "Phrase", "Section", "TimeSignature", "TempoMap", "LANES", "LANE_CODES", "DIFFICULTIES",
           "FOUR_LANE", "FOUR_LANE_PRO", "FIVE_LANE"]


def read(path: str, difficulty: str = "expert", ini: Optional[dict] = None) -> Chart:
    """A .chart or .mid file (by its extension)."""
    ext = os.path.splitext(path)[1].casefold()
    if ext == ".chart":
        return read_chart(path, difficulty, ini)
    if ext in (".mid", ".midi"):
        return read_mid(path, difficulty, ini)
    raise ValueError(f"not a chart file: {path}")
