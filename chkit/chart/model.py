"""The drum chart as the readers return it."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import NamedTuple, Optional

from .tempo import TempoMap

#: lane names; 5-lane charts are mapped onto them (see `Note.pad` for the raw pad)
LANES = ("kick", "red", "yellow", "blue", "green")
#: lane -> number, as many tools count them (0 = kick ... 4 = green)
LANE_CODES = {lane: i for i, lane in enumerate(LANES)}
DIFFICULTIES = ("expert", "hard", "medium", "easy")

FOUR_LANE, FOUR_LANE_PRO, FIVE_LANE = "4lane", "4lane_pro", "5lane"


@dataclass
class Note:
    tick: int
    t: float                     # seconds from tick 0 (chart offset not applied)
    lane: str                    # one of LANES
    cymbal: bool = False         # pro drums: hi-hat/ride/crash instead of tom
    kick2x: bool = False         # Expert+ kick (2x kick)
    accent: bool = False
    ghost: bool = False
    flam: bool = False
    pad: int = 0                 # raw pad 0-5 (.chart note type / .mid offset); 5-lane keeps orange vs green here


@dataclass
class Phrase:
    kind: str                    # "sp" | "fill" | "roll" | "roll2" | "solo"
    tick0: int
    tick1: int
    t0: float
    t1: float


class Section(NamedTuple):
    tick: int
    t: float
    name: str


class TimeSignature(NamedTuple):
    tick: int
    numerator: int
    denominator: int


@dataclass
class Chart:
    resolution: int
    tempo: TempoMap
    notes: list[Note] = field(default_factory=list)
    phrases: list[Phrase] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    time_signatures: list[TimeSignature] = field(default_factory=lambda: [TimeSignature(0, 4, 4)])
    difficulty: str = "expert"
    drum_type: str = FOUR_LANE
    #: how cymbals were decided: "markers" | "five_lane" | "pro_flag" | "none"
    cymbal_source: str = "none"
    #: [Song] Offset of a .chart in seconds (0 for .mid)
    offset: float = 0.0
    source: str = ""

    @property
    def end_time(self) -> float:
        return self.notes[-1].t if self.notes else 0.0

    def bar_lines(self, extra_bars: int = 2) -> list[tuple[int, float]]:
        """(tick, seconds) of every bar line up to `extra_bars` bars after the
        last note, following the time signature changes."""
        end_tick = self.notes[-1].tick if self.notes else 0
        sigs = list(self.time_signatures) or [TimeSignature(0, 4, 4)]
        if sigs[0].tick != 0:
            sigs.insert(0, TimeSignature(0, 4, 4))
        bars = []
        for i, sig in enumerate(sigs):
            step = max(int(self.resolution * 4 * sig.numerator / sig.denominator), 1)
            stop = sigs[i + 1].tick if i + 1 < len(sigs) else end_tick + extra_bars * step
            tick = sig.tick
            while tick < stop:
                bars.append((tick, self.tempo.tick_to_s(tick)))
                tick += step
        return bars

    def section_at(self, t: float) -> Optional[Section]:
        """The section a time (seconds) falls into, None before the first one."""
        i = bisect_right([s.t for s in self.sections], t) - 1
        return self.sections[i] if i >= 0 else None
