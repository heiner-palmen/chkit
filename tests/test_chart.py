"""Reading and writing drum charts (.chart and .mid)."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chkit import chart  # noqa: E402
from chkit.chart import TempoMap  # noqa: E402
import smf  # noqa: E402

R = 480
CHART = """[Song]
{
  Name = "Test"
  Offset = 0.25
  Resolution = 480
}
[SyncTrack]
{
  0 = TS 4
  0 = B 120000
  3840 = B 60000
  3840 = TS 3 3
}
[Events]
{
  0 = E "section Intro"
  1920 = E "section Verse 1"
}
[ExpertDrums]
{
  0 = N 0 0
  0 = N 32 0
  0 = N 2 0
  0 = N 66 0
  480 = N 1 0
  480 = N 35 0
  960 = N 2 0
  960 = N 42 0
  1440 = N 3 0
  1440 = N 109 0
  1920 = S 64 480
  1920 = S 2 960
  2400 = N 4 0
  2400 = N 68 0
}
[HardDrums]
{
  0 = N 0 0
  0 = N 32 0
}
"""


class Folder:
    def __init__(self):
        self.dir = tempfile.mkdtemp()

    def write(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "wb" if isinstance(data, bytes) else "w") as fh:
            fh.write(data)
        return path

    def close(self):
        shutil.rmtree(self.dir)


class TempoTest(unittest.TestCase):
    def test_conversions(self):
        t = TempoMap([(0, 120.0), (960, 60.0)], 480)
        self.assertEqual(t.tick_to_s(480), 0.5)
        self.assertEqual(t.tick_to_s(960), 1.0)
        self.assertEqual(t.tick_to_s(1440), 2.0)
        self.assertEqual(t.s_to_tick(2.0), 1440)
        self.assertEqual(t.s_to_tick(0.25), 240)
        self.assertEqual(t.bpm_at(1000), 60.0)
        self.assertEqual(t.beat_times(1.6), [0.0, 0.5, 1.0])

    def test_missing_start_tempo_is_120(self):
        t = TempoMap([(960, 60.0)], 480)
        self.assertEqual(t.tick_to_s(960), 1.0)


class ChartFileTest(unittest.TestCase):
    def setUp(self):
        self.f = Folder()
        self.addCleanup(self.f.close)

    def test_expert_track(self):
        c = chart.read(self.f.write("notes.chart", CHART), ini={})
        got = [(n.tick, n.lane, n.cymbal, n.kick2x, n.accent, n.ghost, n.flam) for n in c.notes]
        self.assertEqual(got, [
            (0, "kick", False, False, False, False, False),
            (0, "kick", False, True, False, False, False),
            (0, "yellow", True, False, False, False, False),
            (480, "red", False, False, True, False, False),
            (960, "yellow", False, False, False, True, False),
            (1440, "blue", False, False, False, False, True),
            (2400, "green", True, False, False, False, False),
        ])
        self.assertEqual((c.cymbal_source, c.drum_type, c.offset), ("markers", "4lane_pro", 0.25))
        self.assertEqual([(s.name, s.t) for s in c.sections], [("Intro", 0.0), ("Verse 1", 2.0)])
        self.assertEqual([(p.kind, p.tick0, p.tick1) for p in c.phrases], [("fill", 1920, 2400), ("sp", 1920, 2880)])
        self.assertEqual(c.time_signatures, [(0, 4, 4), (3840, 3, 8)])
        self.assertEqual(c.notes[-1].t, 2.5)

    def test_other_difficulty_has_no_expert_plus_kick(self):
        c = chart.read(self.f.write("notes.chart", CHART), difficulty="hard", ini={})
        self.assertEqual([(n.lane, n.kick2x) for n in c.notes], [("kick", False)])
        with self.assertRaises(ValueError):
            chart.read(self.f.write("x.chart", CHART), difficulty="easy", ini={})

    def test_no_cymbal_markers_means_toms_and_five_lane_layout(self):
        text = CHART.replace("  0 = N 66 0\n", "").replace("  2400 = N 68 0\n", "")
        c = chart.read(self.f.write("notes.chart", text), ini={"pro_drums": "True"})
        self.assertFalse(any(n.cymbal for n in c.notes))
        self.assertEqual(c.drum_type, "4lane_pro")
        c = chart.read(self.f.write("notes.chart", text), ini={"five_lane_drums": "1"})
        self.assertEqual([(n.lane, n.cymbal) for n in c.notes if n.lane in ("yellow", "green")],
                         [("yellow", True), ("yellow", True), ("green", True)])

    def test_song_ini_next_to_the_chart(self):
        text = CHART.replace("  0 = N 66 0\n", "").replace("  2400 = N 68 0\n", "")
        path = self.f.write("notes.chart", text)
        self.f.write("song.ini", "[song]\nfive_lane_drums = True\n")
        self.assertEqual(chart.read(path).drum_type, "5lane")

    def test_bar_lines_follow_time_signatures(self):
        c = chart.read(self.f.write("notes.chart", CHART), ini={})
        self.assertEqual([t for t, _ in c.bar_lines()][:3], [0, 1920])   # last note at 2400, 2 bars more
        self.assertEqual(c.section_at(2.1).name, "Verse 1")
        self.assertIsNone(c.section_at(-1))

    def test_write_and_read_again(self):
        c = chart.read(self.f.write("notes.chart", CHART), ini={})
        out = self.f.write("out.chart", "")
        chart.write_chart(c, out, {"Name": "Again", "Artist": "Me"})
        d = chart.read(out, ini={})
        key = lambda n: (n.tick, n.lane, n.cymbal, n.kick2x, n.accent, n.ghost, n.flam)
        self.assertEqual([key(n) for n in d.notes], [key(n) for n in c.notes])
        self.assertEqual((d.sections, d.time_signatures, d.offset), (c.sections, c.time_signatures, 0.25))
        self.assertEqual([(p.kind, p.tick0, p.tick1) for p in d.phrases], [(p.kind, p.tick0, p.tick1) for p in c.phrases])
        self.assertEqual(d.tempo.changes, c.tempo.changes)
        with open(out) as fh:
            self.assertIn('Name = "Again"', fh.read())


def drums(notes, texts=()):
    return smf.track("PART DRUMS", notes=notes, texts=texts)


class MidiFileTest(unittest.TestCase):
    def setUp(self):
        self.f = Folder()
        self.addCleanup(self.f.close)

    def read(self, tracks, ini=None, difficulty="expert"):
        blob = smf.midi([smf.track(tempo=[(0, 120)], sigs=[(0, 4, 4)])] + tracks)
        return chart.read(self.f.write("notes.mid", blob), difficulty, {} if ini is None else ini)

    def test_tom_markers_turn_pads_into_toms_while_held(self):
        c = self.read([drums([(0, 98, 10, 100), (0, 96, 10, 100),
                              (480, 110, 480, 100), (480, 98, 10, 100), (720, 98, 10, 100),
                              (960, 98, 10, 100), (960, 100, 10, 100)])])
        self.assertEqual([(n.tick, n.lane, n.cymbal) for n in c.notes],
                         [(0, "kick", False), (0, "yellow", True), (480, "yellow", False), (720, "yellow", False),
                          (960, "yellow", True), (960, "green", True)])
        self.assertEqual((c.cymbal_source, c.drum_type), ("markers", "4lane_pro"))

    def test_every_tom_marked_on_its_own(self):
        # some charts put a short tom marker under every tom note: thousands of spans
        notes, want = [], []
        for i in range(3000):
            tick = i * 120
            tom = i % 3 != 0
            notes.append((tick, 99, 10, 100))
            if tom:
                notes.append((tick, 111, 60, 100))
            want.append(not tom)
        c = self.read([drums(notes)])
        self.assertEqual([n.cymbal for n in c.notes], want)

    def test_pro_flag_plain_and_five_lane(self):
        notes = [(0, 98, 10, 100), (480, 99, 10, 100)]
        self.assertEqual([n.cymbal for n in self.read([drums(notes)], {"pro_drums": "True"}).notes], [True, True])
        plain = self.read([drums(notes)])
        self.assertEqual(([n.cymbal for n in plain.notes], plain.drum_type), ([False, False], "4lane"))
        five = self.read([drums(notes + [(960, 100, 10, 100), (1440, 101, 10, 100)])])
        self.assertEqual(five.drum_type, "5lane")
        self.assertEqual([(n.pad, n.cymbal) for n in five.notes], [(2, True), (3, False), (4, True), (5, False)])

    def test_dynamics_only_when_enabled(self):
        notes = [(0, 97, 10, 127), (480, 97, 10, 1), (960, 97, 10, 100)]
        off = self.read([drums(notes)])
        self.assertEqual([(n.accent, n.ghost) for n in off.notes], [(False, False)] * 3)
        on = self.read([drums(notes, texts=[(0, "[ENABLE_CHART_DYNAMICS]")])])
        self.assertEqual([(n.accent, n.ghost) for n in on.notes], [(True, False), (False, True), (False, False)])

    def test_expert_plus_kick_flam_phrases_and_sections(self):
        fill = [(1920, n, 480, 100) for n in range(120, 125)]
        c = self.read([drums([(0, 95, 10, 100), (0, 96, 10, 100), (480, 109, 10, 100), (480, 97, 10, 100),
                              (0, 116, 960, 100)] + fill),
                       smf.track("EVENTS", texts=[(0, "[section Intro]"), (1920, "[prc_verse_1]")])])
        self.assertEqual([(n.lane, n.kick2x, n.flam) for n in c.notes],
                         [("kick", False, False), ("kick", True, False), ("red", False, True)])
        self.assertEqual([(p.kind, p.tick0, p.tick1) for p in c.phrases], [("sp", 0, 960), ("fill", 1920, 2400)])
        self.assertEqual([(s.name, s.t) for s in c.sections], [("Intro", 0.0), ("verse_1", 2.0)])

    def test_other_difficulties(self):
        c = self.read([drums([(0, 95, 10, 100), (0, 84, 10, 100), (0, 85, 10, 100), (0, 96, 10, 100)])],
                      difficulty="hard")
        self.assertEqual([n.lane for n in c.notes], ["kick", "red"])

    def test_tempo_and_signatures(self):
        blob = smf.midi([smf.track(tempo=[(0, 120), (960, 60)], sigs=[(0, 4, 4), (1920, 6, 8)]),
                         drums([(1920, 97, 10, 100)])])
        c = chart.read(self.f.write("notes.mid", blob), ini={})
        self.assertEqual(c.notes[0].t, 3.0)
        self.assertEqual(c.time_signatures, [(0, 4, 4), (1920, 6, 8)])

    def test_fewer_tracks_than_the_header_says(self):
        # 05.10. (Ozzy Osbourne - Patient Number 9, oemmes_): the header says 4 tracks,
        # the file ends after 3; Clone Hero plays it
        tracks = [smf.track(tempo=[(0, 120)], sigs=[(0, 4, 4)]), drums([(0, 96, 10, 100), (480, 97, 10, 100)])]
        blob = bytearray(smf.midi(tracks))
        blob[10:12] = (4).to_bytes(2, "big")
        c = chart.read(self.f.write("notes.mid", bytes(blob)), "expert", {})
        self.assertEqual([n.tick for n in c.notes], [0, 480])
        # and a chunk of another kind between the tracks is skipped
        blob = smf.midi([tracks[0], b"XFIH" + (3).to_bytes(4, "big") + b"abc", tracks[1]])
        blob = blob[:10] + (3).to_bytes(2, "big") + blob[12:]
        c = chart.read(self.f.write("other.mid", blob), "expert", {})
        self.assertEqual([n.tick for n in c.notes], [0, 480])

    def test_no_drum_track_and_not_midi(self):
        with self.assertRaises(ValueError):
            chart.read(self.f.write("notes.mid", smf.midi([smf.track(tempo=[(0, 120)])])), ini={})
        with self.assertRaises(ValueError):
            chart.read(self.f.write("bad.mid", b"nope"), ini={})
        with self.assertRaises(ValueError):
            chart.read(self.f.write("song.ogg", b""), ini={})


if __name__ == "__main__":
    unittest.main()
