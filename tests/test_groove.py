"""chkit.groove: fingerprints of synthetic charts and how alike they come out."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from chkit import groove  # noqa: E402
from chkit.chart.model import Chart, Note, TimeSignature  # noqa: E402
from chkit.chart.tempo import TempoMap  # noqa: E402

RES = 480


def make_chart(bar, bpm=120.0, bars=16, beats=4, fill_every=0, cymbal_source="markers", parts=None, stretch=1):
    """A chart repeating `bar`: [(position in 16ths, lane, cymbal)], `beats`
    quarters per bar; every `fill_every`-th bar is a tom fill instead.
    parts: [(bars, bar)] one after the other instead. stretch=2 writes the
    same music at double tempo (every 16th an 8th, bpm x 2, the bar lines
    of `beats` quarters each)."""
    tempo = TempoMap([(0, bpm * stretch)], RES)
    notes = []
    sixteenth = RES // 4 * stretch
    b = 0
    for count, pattern in parts or [(bars, bar)]:
        for _ in range(count):
            start = b * beats * 4 * sixteenth
            if fill_every and b % fill_every == fill_every - 1:
                for s in range(beats * 4):
                    tick = start + s * sixteenth
                    notes.append(Note(tick, tempo.tick_to_s(tick), "blue" if s % 2 else "green"))
            else:
                for pos, lane, cymbal in pattern:
                    tick = start + round(pos * sixteenth)
                    notes.append(Note(tick, tempo.tick_to_s(tick), lane, cymbal=cymbal))
            b += 1
    notes.sort(key=lambda n: (n.tick, n.lane))
    return Chart(resolution=RES, tempo=tempo, notes=notes, time_signatures=[TimeSignature(0, beats, 4)],
                 cymbal_source=cymbal_source)


def rock(hats=2, snare=(4, 12), kick=(0, 8), lane="yellow", cymbal=True):
    """A 4/4 bar: hi-hat (or `lane`) every `hats` 16ths, snare and kick on the given 16ths."""
    bar = [(p, lane, cymbal) for p in range(0, 16, hats)]
    bar += [(p, "red", False) for p in snare]
    bar += [(p, "kick", False) for p in kick]
    return bar


def fp_of(*args, **kwargs):
    return groove.fingerprint(make_chart(*args, **kwargs))


def score(a, b):
    return groove.similarity(groove.prepare(a), groove.prepare(b))


class FingerprintTest(unittest.TestCase):
    def test_rock_beat(self):
        fp = fp_of(rock(), bpm=120)
        self.assertEqual(fp["summary"], "4/4 · 8ths hi-hat · snare 2+4 · 120 BPM")
        self.assertEqual(fp["bar_len"], 48)
        main = fp["grooves"][0]
        self.assertEqual(len(fp["grooves"]), 1)
        self.assertEqual(main["share"], 1.0)
        self.assertEqual(main["keeper"], "hihat")
        self.assertEqual(main["pattern"]["snare"][12], "9")
        self.assertEqual(main["pattern"]["snare"][24], "0")
        self.assertEqual(main["pattern"]["kick"][24], "9")
        self.assertEqual(main["pattern"]["hands"][6], "9")
        self.assertEqual(fp["features"]["fill"], 0.0)
        self.assertEqual(fp["features"]["keeper_hihat"], 1.0)
        self.assertAlmostEqual(fp["features"]["kick_ps"], 1.0, places=2)      # 2 kicks a bar of 2 s
        self.assertAlmostEqual(fp["features"]["hands_ps"], 5.0, places=2)     # 8 hats + 2 snares
        self.assertEqual(fp["features"]["backbeat"], 1.0)

    def test_labels(self):
        self.assertIn("16ths", fp_of(rock(hats=1))["summary"])
        self.assertIn("quarters", fp_of(rock(hats=4))["summary"])
        self.assertIn("snare 3", fp_of(rock(snare=(8,), kick=(0,)))["summary"])
        self.assertIn("snare offbeats", fp_of(rock(snare=(2, 6, 10, 14), kick=(0, 4, 8, 12)))["summary"])
        shuffle = {beat * 12 + off for beat in range(4) for off in (0, 8)}
        self.assertEqual(groove.hands_label("".join("9" if p in shuffle else "0" for p in range(48))), "shuffle")

    def test_which_cymbal_keeps_time(self):
        ride = fp_of(rock(lane="blue"))
        self.assertEqual(ride["summary"], "4/4 · 8ths ride · snare 2+4 · 120 BPM")
        self.assertEqual(ride["features"]["keeper_ride"], 1.0)
        self.assertIn("8ths crash", fp_of(rock(lane="green"))["summary"])
        # a crash on the one on top of the hi-hat is an accent, not the time keeping
        accents = fp_of(rock() + [(0, "green", True)])
        self.assertEqual(accents["grooves"][0]["keeper"], "hihat")
        self.assertEqual(accents["features"]["crash"], 1.0)
        self.assertEqual(accents["grooves"][0]["pattern"]["other"][0], "9")

    def test_five_lane_orange_keeps_time_as_the_ride(self):
        fp = fp_of(rock(lane="green"), cymbal_source="five_lane")
        self.assertEqual(fp["grooves"][0]["keeper"], "ride")

    def test_plain_four_lane(self):
        # no cymbal information: the time-keeping lane is the hands, its cymbal unknown
        fp = fp_of(rock(cymbal=False), cymbal_source="none")
        self.assertEqual(fp["summary"], "4/4 · 8ths · snare 2+4 · 120 BPM")
        self.assertNotIn("keeper_hihat", fp["features"])
        self.assertEqual(fp["grooves"][0]["pattern"]["hands"][0], "9")
        # a ride on blue is no tom and no fill
        ride = fp_of(rock(lane="blue", cymbal=False), cymbal_source="none")
        self.assertEqual(ride["features"]["tom"], 0.0)
        self.assertEqual(ride["features"]["fill"], 0.0)

    def test_fills_left_out_of_the_pattern(self):
        fp = fp_of(rock(), fill_every=4)
        self.assertAlmostEqual(fp["features"]["fill"], 0.25)
        self.assertEqual(fp["grooves"][0]["pattern"]["other"], "0" * 48)
        self.assertEqual(fp["grooves"][0]["share"], 1.0)

    def test_groove_on_the_toms_is_not_a_fill(self):
        jungle = [(p, "green", False) for p in range(0, 16, 2)] + [(4, "red", False), (12, "red", False),
                                                                   (0, "kick", False), (8, "kick", False)]
        fp = fp_of(jungle)
        self.assertEqual(fp["features"]["fill"], 0.0)
        self.assertEqual(fp["grooves"][0]["keeper"], "tom")
        self.assertEqual(fp["features"]["keeper_tom"], 1.0)
        self.assertIn("8ths toms", fp["summary"])

    def test_verse_and_chorus_are_two_grooves(self):
        verse = rock(kick=(0, 10))
        chorus = rock(hats=4, lane="blue", kick=(0, 2, 6, 8, 10, 14))
        fp = fp_of(None, parts=[(8, verse), (8, chorus), (4, verse)])
        shares = [g["share"] for g in fp["grooves"]]
        self.assertEqual(shares, [0.6, 0.4])
        self.assertEqual([g["keeper"] for g in fp["grooves"]], ["hihat", "ride"])
        self.assertAlmostEqual(fp["features"]["variety"], 0.4)
        self.assertAlmostEqual(fp["features"]["keeper_ride"], 0.4)

    def test_bars_without_kick_and_snare_are_no_groove(self):
        intro = [(p, "yellow", True) for p in range(0, 16, 2)]
        fp = fp_of(None, parts=[(4, intro), (12, rock())])
        self.assertEqual(len(fp["grooves"]), 1)
        self.assertEqual(fp["grooves"][0]["pattern"]["snare"][12], "9")
        self.assertEqual(fp["grooves"][0]["share"], 1.0)

    def test_kick_numbers(self):
        four = fp_of(rock(kick=(0, 4, 8, 12)))
        self.assertEqual(four["features"]["four"], 1.0)
        self.assertEqual(four["features"]["kick_off"], 0.0)
        # 16th kicks at 100 BPM (0.15 s apart) in runs of four
        runs = fp_of(rock(kick=(0, 1, 2, 3, 8, 9, 10, 11)), bpm=100)
        self.assertEqual(runs["features"]["kick_run"], 1.0)
        self.assertEqual(runs["features"]["kick16"], 0.5)
        self.assertEqual(fp_of(rock())["features"]["kick_run"], 0.0)
        syncopated = fp_of(rock(kick=(0, 3, 10)))
        self.assertAlmostEqual(syncopated["features"]["kick_off"], 2 / 3, places=3)

    def test_triplets(self):
        shuffle = [(beat * 4 + off, "yellow", True) for beat in range(4) for off in (0, 8 / 3)]
        fp = fp_of(shuffle + [(4, "red", False), (12, "red", False), (0, "kick", False), (8, "kick", False)])
        self.assertGreater(fp["features"]["triplet"], 0.3)
        self.assertEqual(fp_of(rock())["features"]["triplet"], 0.0)

    def test_rhythm_in_seconds(self):
        fp = fp_of(rock(), bpm=120)
        hands = fp["rhythm"]["hands"]                   # 8th hats at 120: 0.25 s apart
        span = groove.math.log(groove.IOI_MAX / groove.IOI_MIN)
        x = groove.math.log(0.25 / groove.IOI_MIN) / span * (groove.IOI_BINS - 1)
        self.assertEqual(hands.index(max(hands)), round(x))
        self.assertEqual(sum(hands), 100)

    def test_the_notation_does_not_change_the_numbers_in_seconds(self):
        # 16th hats at 90 BPM, and the same music written as 8ths at 180 BPM
        plain = fp_of(rock(hats=1), bpm=90)
        doubled = fp_of(rock(hats=1), bpm=90, stretch=2)
        self.assertEqual(doubled["bpm"], 180.0)
        self.assertEqual(plain["rhythm"], doubled["rhythm"])
        for key in ("nps", "hands_ps", "kick_ps", "snare_ps", "peak_ps"):
            self.assertAlmostEqual(plain["features"][key], doubled["features"][key], places=2, msg=key)

    def test_expert_plus_kicks_do_not_count(self):
        chart = make_chart(rock())
        plain = groove.fingerprint(chart)
        chart.notes += [Note(n.tick + RES // 4, n.t, "kick", kick2x=True) for n in chart.notes if n.lane == "kick"]
        self.assertEqual(groove.fingerprint(chart)["grooves"], plain["grooves"])
        self.assertEqual(groove.fingerprint(chart)["features"], plain["features"])

    def test_too_few_notes(self):
        self.assertIsNone(groove.fingerprint(make_chart(rock(), bars=1)))

    def test_encode_decode(self):
        fp = fp_of(rock())
        self.assertEqual(groove.decode(groove.encode(fp)), fp)
        self.assertIsNone(groove.decode(groove.encode(dict(fp, version=groove.VERSION + 1))))
        self.assertIsNone(groove.decode(groove.encode(dict(fp, version=1))))     # computed again
        self.assertIsNone(groove.decode("not json"))


class SimilarityTest(unittest.TestCase):
    def setUp(self):
        self.rock120 = fp_of(rock(), bpm=120)

    def test_same_groove_same_tempo(self):
        s, parts = score(self.rock120, fp_of(rock(), bpm=121))
        self.assertGreater(s, 0.97)
        self.assertEqual(parts["mode"], "same")
        self.assertEqual(score(self.rock120, self.rock120)[0], 1.0)

    def test_tempo_counts(self):
        near = score(self.rock120, fp_of(rock(), bpm=126))[0]
        far = score(self.rock120, fp_of(rock(), bpm=150))[0]
        self.assertGreater(near, far)

    def test_pattern_counts(self):
        other_beat = fp_of(rock(hats=4, snare=(8,), kick=(0, 6, 10)), bpm=120)
        other_tempo = fp_of(rock(), bpm=132)
        self.assertGreater(score(self.rock120, other_tempo)[0], score(self.rock120, other_beat)[0])

    def test_a_busy_kick_does_not_feel_like_a_plain_one(self):
        busy = fp_of(rock(kick=(0, 1, 2, 3, 6, 8, 9, 10, 11, 14)), bpm=120)
        s, parts = score(self.rock120, busy)
        self.assertLess(s, 0.75)
        self.assertLess(s, score(self.rock120, fp_of(rock(), bpm=135))[0])
        self.assertEqual(parts["apart"][0], "kick_ps")

    def test_a_ballad_is_not_like_a_busy_song_at_the_same_tempo(self):
        ballad = fp_of(rock(hats=4, snare=(8,), kick=(0,)), bpm=70)
        busy = fp_of(rock(hats=1, snare=(4, 12), kick=(0, 2, 3, 8, 10, 11)), bpm=70)
        calm = fp_of(rock(hats=4, snare=(8,), kick=(0, 10)), bpm=80)
        self.assertLess(score(ballad, busy)[0], 0.5)
        self.assertGreater(score(ballad, calm)[0], score(ballad, busy)[0])

    def test_double_tempo(self):
        # 16th hats at 90 against 8th hats at 180: the same hand speed (R2) ...
        sixteenths = fp_of(rock(hats=1), bpm=90)
        eighths = fp_of(rock(hats=2), bpm=180)
        s, parts = score(sixteenths, eighths)
        self.assertEqual(parts["mode"], "double")
        # ... alike, but less than the same groove; it is the hand speed that makes them alike
        self.assertLess(s, score(sixteenths, fp_of(rock(hats=1), bpm=90))[0])
        self.assertGreater(s, score(sixteenths, fp_of(rock(hats=4), bpm=180))[0])
        # the other way round it is the half tempo
        self.assertEqual(score(eighths, sixteenths)[1]["mode"], "half")
        self.assertAlmostEqual(score(eighths, sixteenths)[0], s)

    def test_the_same_music_written_at_double_tempo(self):
        plain = fp_of(rock(hats=1, kick=(0, 6, 8)), bpm=90)
        doubled = fp_of(rock(hats=1, kick=(0, 6, 8)), bpm=90, stretch=2)
        s, parts = score(plain, doubled)
        self.assertGreater(s, 0.8)
        self.assertEqual(parts["rhythm"], 1.0)
        self.assertGreater(s, score(plain, fp_of(rock(hats=1, snare=(8,), kick=(0, 3, 10, 14)), bpm=90))[0])

    def test_three_four_has_no_pattern_in_common_with_four_four(self):
        waltz = [(0, "kick", False), (4, "red", False), (8, "red", False)] + \
                [(p, "yellow", True) for p in range(0, 12, 2)]
        s, parts = score(self.rock120, fp_of(waltz, beats=3))
        self.assertEqual(parts["pattern"], 0.0)

    def test_two_four_bars_lie_twice_against_four_four(self):
        half = [(p, "yellow", True) for p in range(0, 8, 2)] + [(0, "kick", False), (4, "red", False)]
        s, parts = score(self.rock120, fp_of(half, beats=2, bars=32))
        self.assertEqual(parts["pattern"], 1.0)
        self.assertGreater(s, 0.9)

    def test_bar_lines_half_a_bar_apart(self):
        beat = rock(snare=(4, 12, 14), kick=(0, 2, 3))
        shifted = [((p + 8) % 16, lane, cymbal) for p, lane, cymbal in beat]
        _, parts = score(fp_of(beat), fp_of(shifted))
        self.assertAlmostEqual(parts["pattern"], groove.HALF_BAR_FACTOR)

    def test_symmetric(self):
        other = fp_of(rock(hats=4, lane="blue", kick=(0, 3, 10)), bpm=140)
        self.assertAlmostEqual(score(self.rock120, other)[0], score(other, self.rock120)[0])

    def test_score_alone(self):
        other = fp_of(rock(), bpm=126)
        a, b = groove.prepare(self.rock120), groove.prepare(other)
        self.assertEqual(groove.similarity(a, b, details=False), (groove.similarity(a, b)[0], None))

    def test_explain(self):
        _, parts = score(self.rock120, fp_of(rock(), bpm=126))
        self.assertRegex(groove.explain(parts), r"^beat \d+ % · tempo 120/126 BPM · feel \d+ %$")
        _, parts = score(self.rock120, fp_of(rock(kick=(0, 1, 2, 3, 6, 8, 9, 10, 11, 14))))
        text = groove.explain(parts)
        self.assertRegex(text, r"^beat \d+ % · tempo 120/120 BPM · feel \d+ % \(kick 1\.0/5\.0 per s\)$")
        _, parts = score(fp_of(rock(hats=1), bpm=90), fp_of(rock(hats=2), bpm=180))
        self.assertTrue(groove.explain(parts).endswith(" · at double tempo"))

    def test_explain_texts_name_the_kick_neutrally(self):
        for key, (name, unit) in groove.FEEL_TEXT.items():
            text = groove._feel_text(key, 0.5, 0.25)
            self.assertIsNone(re.search(r"double|bass|2x|expert|blast", text, re.I), text)
        self.assertEqual(set(groove.FEEL_TEXT), set(groove.FEEL))


if __name__ == "__main__":
    unittest.main()
