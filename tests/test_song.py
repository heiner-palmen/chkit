"""Song folders: song.ini, chart file, MD5, text helpers."""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chkit import song  # noqa: E402


class SongTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, rel, data=b""):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def test_read_ini_encodings_comments_and_first_value(self):
        p = self.write("a/song.ini", "﻿[Song]\nArtist = Motörhead\nNAME=Ace\n; x\nname = Other\n".encode("utf-8"))
        self.assertEqual(song.read_ini(p), {"artist": "Motörhead", "name": "Ace"})
        p = self.write("b/song.ini", "[song]\nartist = Motörhead\n".encode("cp1252"))
        self.assertEqual(song.read_ini(p)["artist"], "Motörhead")
        self.assertEqual(song.ini_next_to(os.path.join(self.dir, "a", "notes.mid"))["name"], "Ace")
        self.assertEqual(song.ini_next_to(os.path.join(self.dir, "none", "notes.mid")), {})

    def test_values(self):
        self.assertEqual((song.to_int(" 4 "), song.to_int("4.0"), song.to_int("")), (4, 4, None))
        self.assertEqual((song.to_bool("True"), song.to_bool("0"), song.to_bool(None)), (True, False, None))
        self.assertEqual((song.year_of(", 2008"), song.year_of("2008-05"), song.year_of("x")), (2008, 2008, None))
        self.assertEqual(song.preview_start({"preview_start_time": "45000"}), 45.0)
        self.assertIsNone(song.preview_start({"preview_start_time": "-1"}))

    def test_text(self):
        self.assertEqual(song.plain("<color=#FF0000>MORE</color>  now"), "MORE now")
        self.assertEqual(song.fold("<b>Motörhead</b> ÆON Beyoncé"), "motorhead aeon beyonce")
        self.assertEqual(song.split_charters("Harmonix, Neversoft"), ["Harmonix", "Neversoft"])
        self.assertEqual(song.split_charters("Sygenysis+Nunchuck"), ["Sygenysis+Nunchuck"])
        self.assertEqual(song.split_charters("A + B / a"), ["A", "B"])

    def test_chart_file_md5_and_audio(self):
        self.write("s/song.ini", "[song]\n")
        self.write("s/notes.chart", b"chart")
        self.assertTrue(song.find_chart(os.path.join(self.dir, "s")).endswith("notes.chart"))
        mid = self.write("s/NOTES.MID", b"mid")                    # Clone Hero plays notes.mid first
        self.assertEqual(song.find_chart(os.path.join(self.dir, "s")), mid)
        self.assertEqual(song.chart_md5(mid), hashlib.md5(b"mid").hexdigest())
        self.assertIsNone(song.find_chart(os.path.join(self.dir, "missing")))
        self.assertEqual(song.audio_stems(["song.ogg", "drums_1.opus", "album.png", "Guitar.OGG"]),
                         ["Guitar", "drums_1", "song"])

    def test_song_folders(self):
        self.write("Pack/B/song.ini")
        self.write("Pack/A/song.ini")
        self.write("Pack/A/sub/readme.txt")
        found = [os.path.relpath(f, self.dir) for f, _ in song.song_folders(self.dir)]
        self.assertEqual(found, [os.path.join("Pack", "A"), os.path.join("Pack", "B")])


if __name__ == "__main__":
    unittest.main()
