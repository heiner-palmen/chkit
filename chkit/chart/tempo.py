"""Tick <-> seconds conversion for a chart's tempo map."""

from __future__ import annotations

from bisect import bisect_right


class TempoMap:
    """Piecewise tempo map built from (tick, bpm) changes.

    A change at tick 0 is added (120 BPM) when the chart has none, which is
    what Clone Hero does as well.
    """

    def __init__(self, changes: list[tuple[int, float]], resolution: int) -> None:
        changes = sorted((int(t), float(b)) for t, b in changes if b > 0)
        if not changes or changes[0][0] != 0:
            changes = [(0, 120.0)] + [c for c in changes if c[0] != 0]
        self.resolution = resolution
        self.changes = changes
        self._ticks: list[int] = []
        self._seconds: list[float] = []
        t, prev_tick, prev_bpm = 0.0, changes[0][0], changes[0][1]
        for tick, bpm in changes:
            # same operation order as the readers chkit replaced: bit-identical times
            t += (tick - prev_tick) / resolution * (60.0 / prev_bpm)
            self._ticks.append(tick)
            self._seconds.append(t)
            prev_tick, prev_bpm = tick, bpm

    def bpm_at(self, tick: int) -> float:
        return self.changes[max(bisect_right(self._ticks, tick) - 1, 0)][1]

    def tick_to_s(self, tick: float) -> float:
        i = max(bisect_right(self._ticks, tick) - 1, 0)
        return self._seconds[i] + (tick - self._ticks[i]) / self.resolution * (60.0 / self.changes[i][1])

    def s_to_tick(self, seconds: float) -> float:
        """The (fractional) tick at a time in seconds."""
        i = max(bisect_right(self._seconds, seconds) - 1, 0)
        return self._ticks[i] + (seconds - self._seconds[i]) * self.changes[i][1] / 60.0 * self.resolution

    def beat_times(self, until_s: float) -> list[float]:
        """Every quarter-note beat up to `until_s`, in seconds."""
        beats, tick = [], 0
        while True:
            t = self.tick_to_s(tick)
            if t > until_s:
                return beats
            beats.append(t)
            tick += self.resolution
