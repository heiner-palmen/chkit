"""Atomic writes, network folders with timeouts, tolerant JSON."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chkit import io  # noqa: E402


class IoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_atomic_write_and_json(self):
        path = os.path.join(self.dir, "a.json")
        io.write_json_atomic(path, {"ä": 1})
        self.assertEqual(io.read_json(path), {"ä": 1})
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o644")
        self.assertEqual([f for f in os.listdir(self.dir) if f.startswith(".")], [])
        with open(path, "w") as fh:
            fh.write('{"half": ')
        self.assertIsNone(io.read_json(path))
        self.assertIsNone(io.read_json(os.path.join(self.dir, "missing.json")))

    def test_copy_with_timeout(self):
        src, dst = os.path.join(self.dir, "src"), os.path.join(self.dir, "copy", "dst")
        with open(src, "w") as fh:
            fh.write("good")
        self.assertIsNone(io.copy_with_timeout(src, dst))
        with open(dst) as fh:
            self.assertEqual(fh.read(), "good")

        def refuse(path):
            raise ValueError("bad content")
        with open(src, "w") as fh:
            fh.write("bad")
        self.assertIn("bad content", io.copy_with_timeout(src, dst, check=refuse))
        with open(dst) as fh:
            self.assertEqual(fh.read(), "good")                     # never replaced by a refused copy
        self.assertFalse(os.path.exists(dst + ".new"))
        self.assertIn("not readable", io.copy_with_timeout(os.path.join(self.dir, "nope"), dst))

        def hanging(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        self.assertIn("no answer", io.copy_with_timeout(src, dst, timeout_s=1, run=hanging))

    def test_fetch_text(self):
        with open(os.path.join(self.dir, "f.txt"), "w") as fh:
            fh.write("hello")
        self.assertEqual(io.fetch_text(self.dir, "f.txt"), "hello")
        self.assertEqual(io.fetch_text(self.dir, "missing.txt"), "")
        self.assertIsNone(io.fetch_text(os.path.join(self.dir, "not-mounted"), "f.txt"))


if __name__ == "__main__":
    unittest.main()
