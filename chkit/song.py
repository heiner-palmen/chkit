"""A Clone Hero song folder: song.ini, chart file, chart MD5, audio files.

The MD5 of the chart file (notes.mid, else notes.chart) is the checksum Clone
Hero keys its scores by (scoredata.bin, scorestats.json "checksum").
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from typing import Iterator, Optional

CHART_FILES = ("notes.mid", "notes.chart")
AUDIO_EXT = (".ogg", ".opus", ".mp3", ".wav", ".flac")

_TAG = re.compile(r"<[^<>]*>")
# letters NFKD does not split into base letter + accent
_FOLD = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ł": "l", "đ": "d", "þ": "th", "ð": "d", "ı": "i"})


# -- text ---------------------------------------------------------------------------

def plain(text) -> str:
    """Text without Clone Hero's formatting tags ("<color=#FF0000>MORE</color>")
    and with single spaces."""
    return " ".join(_TAG.sub("", str(text or "")).split())


def fold(text) -> str:
    """Lower case, without accents and tags, single spaces: for searching.
    "Motörhead" and "MOTORHEAD" both become "motorhead"."""
    text = unicodedata.normalize("NFKD", plain(text).casefold().translate(_FOLD))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def split_charters(charter) -> list[str]:
    """'Harmonix, Neversoft' -> ['Harmonix', 'Neversoft']. Splits at , / & and
    at ' - ', ' + ', ' and '; tags are removed first; each name once."""
    parts = [plain(charter)]
    for delim in (" - ", " + ", " and ", ",", "/", "&"):
        parts = [p for part in parts for p in part.split(delim)]
    seen, result = set(), []
    for p in (p.strip() for p in parts):
        if p and p.casefold() not in seen:
            seen.add(p.casefold())
            result.append(p)
    return result


# -- song.ini ------------------------------------------------------------------------

def read_ini(path: str) -> dict:
    """All key = value lines of a song.ini, keys in lower case; the first value
    of a key wins. UTF-8 (with or without BOM), else cp1252. OSError if the
    file cannot be read."""
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith((";", "#", "[")):
            continue
        key, sep, value = line.partition("=")
        if sep and key.strip():
            data.setdefault(key.strip().lower(), value.strip())
    return data


def ini_next_to(chart_path: str) -> dict:
    """The song.ini in the folder of a chart file ({} if there is none)."""
    folder = os.path.dirname(os.path.abspath(chart_path))
    name = folder_files(folder).get("song.ini")
    if not name:
        return {}
    try:
        return read_ini(os.path.join(folder, name))
    except OSError:
        return {}


def to_int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None


def to_bool(value) -> Optional[bool]:
    if value is None:
        return None
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def year_of(value) -> Optional[int]:
    """'2008', ', 2008' or '2008-05' -> 2008; None without a plausible year."""
    for d in "".join(c if c.isdigit() else " " for c in str(value or "")).split():
        if len(d) == 4 and 1000 <= int(d) <= 2999:
            return int(d)
    return None


def preview_start(ini: dict) -> Optional[float]:
    """preview_start_time in seconds, None when the song.ini has none."""
    ms = to_int(ini.get("preview_start_time"))
    return ms / 1000 if ms is not None and ms >= 0 else None


# -- the folder ----------------------------------------------------------------------

def folder_files(folder: str) -> dict:
    """{lower-case file name: real name} of a folder ({} if unreadable)."""
    try:
        return {f.lower(): f for f in os.listdir(folder)}
    except OSError:
        return {}


def find_chart(folder: str, files: Optional[dict] = None) -> Optional[str]:
    """Path of the chart file Clone Hero plays: notes.mid, else notes.chart."""
    files = folder_files(folder) if files is None else files
    for name in CHART_FILES:
        if name in files:
            return os.path.join(folder, files[name])
    return None


def chart_md5(path: str) -> str:
    """MD5 (lower-case hex) of a chart file: Clone Hero's checksum for it."""
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def audio_stems(files) -> list[str]:
    """Names of the audio tracks among the file names (song, guitar, drums_1 ...)."""
    return sorted({os.path.splitext(f)[0] for f in files if f.lower().endswith(AUDIO_EXT)})


def song_folders(root: str) -> Iterator[tuple[str, dict]]:
    """(folder, {lower-case file name: real name}) for every folder with a
    song.ini below `root`, in a stable order. Symlinked folders are followed
    once."""
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        try:
            st = os.stat(dirpath)
        except OSError:
            dirnames[:] = []
            continue
        if (st.st_dev, st.st_ino) in seen:
            dirnames[:] = []
            continue
        seen.add((st.st_dev, st.st_ino))
        dirnames.sort()
        files = {f.lower(): f for f in filenames}
        if "song.ini" in files:
            yield dirpath, files
