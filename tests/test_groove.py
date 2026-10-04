"""chkit.groove: fingerprints of synthetic charts and how alike they come out."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from chkit import groove  # noqa: E402
from chkit.chart.model import Chart, Note, TimeSignature  # noqa: E402
from chkit.chart.tempo import TempoMap  # noqa: E402

RES = 480


def make_chart(bar, bpm=120.0, bars=16, beats=4, fill_every=0, cymbal_source="markers"):
    """A chart repeating `bar`: [(position in 16ths, lane, cymbal)], `beats`
    quarters per bar; every `fill_every`-th bar is a tom fill instead."""
    tempo = TempoMap([(0, bpm)], RES)
    notes = []
    sixteenth = RES // 4
    for b in range(bars):
        start = b * beats * RES
        if fill_every and b % fill_every == fill_every - 1:
            for s in range(beats * 4):
                tick = start + s * sixteenth
                notes.append(Note(tick, tempo.tick_to_s(tick), "blue" if s % 2 else "green"))
            continue
        for pos, lane, cymbal in bar:
            tick = start + pos * sixteenth
            notes.append(Note(tick, tempo.tick_to_s(tick), lane, cymbal=cymbal))
    notes.sort(key=lambda n: (n.tick, n.lane))
    return Chart(resolution=RES, tempo=tempo, notes=notes, time_signatures=[TimeSignature(0, beats, 4)],
                 cymbal_source=cymbal_source)


def rock(hats=2, snare=(4, 12), kick=(0, 8)):
    """A 4/4 bar: hi-hat every `hats` 16ths, snare and kick on the given 16ths."""
    bar = [(p, "yellow", True) for p in range(0, 16, hats)]
    bar += [(p, "red", False) for p in snare]
    bar += [(p, "kick", False) for p in kick]
    return bar


def score(a, b):
    return groove.similarity(groove.prepare(a), groove.prepare(b))


class FingerprintTest(unittest.TestCase):
    def test_rock_beat(self):
        fp = groove.fingerprint(make_chart(rock(), bpm=120))
        self.assertEqual(fp["summary"], "4/4 · 8ths · snare 2+4 · 120 BPM")
        self.assertEqual(fp["bar_len"], 48)
        self.assertEqual(fp["pattern"]["snare"][12], "9")
        self.assertEqual(fp["pattern"]["snare"][24], "0")
        self.assertEqual(fp["pattern"]["kick"][24], "9")
        self.assertEqual(fp["features"]["fill"], 0.0)

    def test_labels(self):
        self.assertIn("16ths", groove.fingerprint(make_chart(rock(hats=1)))["summary"])
        self.assertIn("quarters", groove.fingerprint(make_chart(rock(hats=4)))["summary"])
        self.assertIn("snare 3", groove.fingerprint(make_chart(rock(snare=(8,), kick=(0,))))["summary"])
        self.assertIn("snare offbeats",
                      groove.fingerprint(make_chart(rock(snare=(2, 6, 10, 14), kick=(0, 4, 8, 12))))["summary"])
        shuffle = [(p, "yellow", True) for beat in range(4) for p in (beat * 12, beat * 12 + 8)]
        self.assertEqual(groove.hands_label("".join("9" if p in [x for x, _, _ in shuffle] else "0"
                                                    for p in range(48))), "shuffle")

    def test_fills_left_out_of_the_pattern(self):
        fp = groove.fingerprint(make_chart(rock(), fill_every=4))
        self.assertAlmostEqual(fp["features"]["fill"], 0.25)
        self.assertEqual(fp["pattern"]["tom"], "0" * 48)

    def test_groove_on_the_toms_is_not_a_fill(self):
        jungle = [(p, "green", False) for p in range(0, 16, 2)] + [(0, "kick", False), (8, "kick", False)]
        fp = groove.fingerprint(make_chart(jungle))
        self.assertEqual(fp["features"]["fill"], 0.0)
        self.assertEqual(fp["pattern"]["tom"][0], "9")
        self.assertIn("toms", fp["summary"])

    def test_plain_four_lane_yellow_is_the_hi_hat(self):
        bar = [(p, "yellow", False) for p in range(0, 16, 2)] + [(4, "red", False), (12, "red", False)]
        fp = groove.fingerprint(make_chart(bar, cymbal_source="none"))
        self.assertEqual(fp["pattern"]["cymbal"][0], "9")
        self.assertEqual(fp["pattern"]["tom"], "0" * 48)

    def test_expert_plus_kicks_do_not_count(self):
        chart = make_chart(rock())
        plain = groove.fingerprint(chart)
        chart.notes += [Note(n.tick + RES // 4, n.t, "kick", kick2x=True) for n in chart.notes if n.lane == "kick"]
        self.assertEqual(groove.fingerprint(chart)["pattern"], plain["pattern"])

    def test_too_few_notes(self):
        self.assertIsNone(groove.fingerprint(make_chart(rock(), bars=1)))

    def test_encode_decode(self):
        fp = groove.fingerprint(make_chart(rock()))
        self.assertEqual(groove.decode(groove.encode(fp)), fp)
        self.assertIsNone(groove.decode(groove.encode(dict(fp, version=groove.VERSION + 1))))
        self.assertIsNone(groove.decode("not json"))


class SimilarityTest(unittest.TestCase):
    def setUp(self):
        self.rock120 = groove.fingerprint(make_chart(rock(), bpm=120))

    def test_same_groove_same_tempo(self):
        s, parts = score(self.rock120, groove.fingerprint(make_chart(rock(), bpm=121)))
        self.assertGreater(s, 0.97)
        self.assertEqual(parts["mode"], "same")

    def test_tempo_counts(self):
        near = score(self.rock120, groove.fingerprint(make_chart(rock(), bpm=126)))[0]
        far = score(self.rock120, groove.fingerprint(make_chart(rock(), bpm=150)))[0]
        self.assertGreater(near, far)

    def test_pattern_counts_more_than_tempo(self):
        other_beat = groove.fingerprint(make_chart(rock(hats=4, snare=(8,), kick=(0, 6, 10)), bpm=120))
        other_tempo = groove.fingerprint(make_chart(rock(), bpm=135))
        self.assertGreater(score(self.rock120, other_tempo)[0], score(self.rock120, other_beat)[0])

    def test_double_tempo(self):
        # 16th hats at 90 against 8th hats at 180: the same hand speed (R2) ...
        sixteenths = groove.fingerprint(make_chart(rock(hats=1), bpm=90))
        eighths = groove.fingerprint(make_chart(rock(hats=2), bpm=180))
        s, parts = score(sixteenths, eighths)
        self.assertEqual(parts["mode"], "double")
        # ... alike, but less than the same groove
        same = score(sixteenths, groove.fingerprint(make_chart(rock(hats=1), bpm=90)))[0]
        self.assertLess(s, same)
        self.assertGreater(s, score(sixteenths, groove.fingerprint(make_chart(rock(hats=2), bpm=120)))[0])
        # the other way round it is the half tempo
        self.assertEqual(score(eighths, sixteenths)[1]["mode"], "half")
        self.assertAlmostEqual(score(eighths, sixteenths)[0], s)

    def test_three_four_has_no_pattern_in_common_with_four_four(self):
        waltz = [(0, "kick", False), (4, "red", False), (8, "red", False)] + \
                [(p, "yellow", True) for p in range(0, 12, 2)]
        s, parts = score(self.rock120, groove.fingerprint(make_chart(waltz, beats=3)))
        self.assertEqual(parts["pattern"], 0.0)

    def test_explain(self):
        _, parts = score(self.rock120, groove.fingerprint(make_chart(rock(), bpm=126)))
        self.assertRegex(groove.explain(parts), r"^beat \d+ % · tempo 120/126 BPM · feel \d+ %$")


if __name__ == "__main__":
    unittest.main()
