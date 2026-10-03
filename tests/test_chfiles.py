"""Files of Clone Hero: currentsong, scorestats, scoredata, MIDI profiles, playlists."""

import json
import os
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chkit.chfiles import currentsong, midiprofile, playlist, scoredata, scorestats  # noqa: E402

DIO = "8d66422b8827baa1d09f1c7fd7033af8"


def scoredata_bin(charts, version=scoredata.VERSION):
    out = struct.pack("<II", version, len(charts))
    for md5, playcount, rows in charts:
        out += bytes.fromhex(md5) + bytes([len(rows)]) + playcount.to_bytes(3, "little")
        for row in rows:
            out += struct.pack("<HBBBHBII", *row)
    return out


class CurrentSongTest(unittest.TestCase):
    def test_schemas(self):
        self.assertIsNone(currentsong.parse("  \n"))
        new = currentsong.parse("Ace of Spades\nArtist: Motörhead, 1980\nCharter: Neversoft\nPfad: /x/notes.mid\n")
        self.assertEqual(new, {"song": "Ace of Spades", "artist": "Motörhead", "charter": "Neversoft",
                               "path": "/x/notes.mid"})
        self.assertEqual(currentsong.parse("Song: One\nArtist: Metallica")["song"], "One")
        old = currentsong.parse("Battery, Metallica, Harmonix")
        self.assertEqual((old["song"], old["artist"], old["charter"]), ("Battery", "Metallica", "Harmonix"))


class ScoreStatsTest(unittest.TestCase):
    STATS = {"checksum": DIO.upper(), "score_timestamp": "2026-10-02T17:09:14.2304480Z",
             "players": [{"instrument": "Guitar", "score": 999999},
                         {"instrument": "ProDrums", "difficulty": "Expert", "score": 398960, "stars": 6,
                          "notes_hit": 1746, "total_notes": 1773, "is_fc": False,
                          "section_stats": [{"section_name": "Intro", "notes_hit": 51, "notes_count": 51},
                                            {"section_name": "Verse 1", "notes_hit": 79, "notes_count": 81}]}]}

    def test_result_and_sections(self):
        r = scorestats.result(self.STATS)
        self.assertEqual((r["md5"], r["instrument"], r["percent"], r["fc"], r["score"]),
                         (DIO, "ProDrums", 98, 0, 398960))
        self.assertEqual(r["at"], 1790960954.0)                  # 2026-10-02 17:09:14 UTC
        player = scorestats.drum_player(self.STATS)
        self.assertEqual(scorestats.section_misses(player),
                         [{"index": 1, "name": "Verse 1", "missed": 2, "notes": 81}])
        self.assertIsNone(scorestats.result({"checksum": "x"}))
        self.assertIsNone(scorestats.result("broken"))
        guitar_only = dict(self.STATS, players=[{"instrument": "Guitar"}])
        self.assertIsNone(scorestats.result(guitar_only)["instrument"])


class ScoreDataTest(unittest.TestCase):
    def test_parse_and_summary(self):
        records = scoredata.parse_scoredata(scoredata_bin([
            (DIO, 12, [(0, 3, 100, 1, 100, 6, 1, 999999), (9, 3, 99, 0, 100, 6, 2, 430690),
                       (8, 3, 50, 1, 100, 5, 0, 1000)])]))
        guitar, dio, band = records[DIO]
        self.assertEqual((dio["instrument"], dio["difficulty"], dio["percent"], dio["fc"], dio["playcount"]),
                         ("ProDrums", "Expert", 99.0, False, 12))
        self.assertEqual((band["percent"], band["fc"]), (None, None))
        s = scoredata.summaries(records)[DIO]
        self.assertEqual((s["playcount"], s["instrument"], s["score"], s["fc"]), (12, "ProDrums", 430690, 0))

    def test_broken(self):
        good = scoredata_bin([(DIO, 1, [(9, 3, 99, 0, 100, 6, 2, 1)])])
        for bad in (good[:-2], good + b"x", scoredata_bin([], version=1), b"ab"):
            with self.assertRaises(ValueError):
                scoredata.parse_scoredata(bad)


class MidiProfileTest(unittest.TestCase):
    YAML = """DeviceName: TD-17:TD-17 MIDI 1 20:0
Mappings:
  Red Pad:
  - NoteNumber: 38
    Velocity: 10
    OverHitThreshold: 0
  - NoteNumber: 40
    Velocity: 12
    OverHitThreshold: 0
  Kick Pad:
  - NoteNumber: 36
    Velocity: 10
    OverHitThreshold: 0
  Yellow Cymbal:
  - NoteNumber: 46
    Velocity: 10
    OverHitThreshold: 0
"""

    def test_parse(self):
        p = midiprofile.parse(self.YAML)
        self.assertEqual(p["device"], "TD-17:TD-17 MIDI 1 20:0")
        self.assertEqual([e["note"] for e in p["pads"]["Red Pad"]], [38, 40])
        self.assertEqual(midiprofile.note_to_pad(p), {38: ("Red Pad", 10), 40: ("Red Pad", 12),
                                                      36: ("Kick Pad", 10), 46: ("Yellow Cymbal", 10)})


class PlaylistTest(unittest.TestCase):
    def test_load(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "p.json")
        with open(path, "w") as fh:
            json.dump([{"artist": "<b>M</b>", "name": "One", "charter_refs": "Harmonix", "song_length": "444000",
                        "md5": "ab", "path": "/x"}, {"artist": "", "name": "no artist"}], fh)
        (song,) = playlist.load(path)
        self.assertEqual((song["artist"], song["charter"], song["song_length"]), ("M", "Harmonix", 444000))
        with open(path, "w") as fh:
            json.dump({"not": "a list"}, fh)
        with self.assertRaises(ValueError):
            playlist.load(path)


if __name__ == "__main__":
    unittest.main()
