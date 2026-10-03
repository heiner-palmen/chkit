"""The playlist format of the tools (list of song entries as the playlist chain
of ParseCHScoreDataAndSongCache writes it: md5, artist, name, charter_refs,
path, difficulty, song_length, ...)."""

from __future__ import annotations

import json

from ..song import plain


def song_from_entry(entry) -> "dict | None":
    """Playlist entry -> song dict (None if artist or name is missing)."""
    if not isinstance(entry, dict) or not plain(entry.get("artist")) or not plain(entry.get("name")):
        return None
    try:
        length = int(entry.get("song_length"))
    except (TypeError, ValueError):
        length = None
    return {
        "artist": plain(entry["artist"]),
        "name": plain(entry["name"]),
        "charter": plain(entry.get("charter_refs") or entry.get("charter")),
        "path": entry.get("path") or "",
        "md5": entry.get("md5") or "",
        "album": entry.get("album") or "",
        "year": entry.get("year") or "",
        "genre": entry.get("genre") or "",
        "difficulty": entry.get("difficulty") or "",
        "song_length": length,
    }


def load(path: str) -> list:
    """The songs of a playlist file. ValueError if it is no playlist or empty."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("playlist is not a JSON list")
    songs = [s for s in (song_from_entry(e) for e in data) if s]
    if not songs:
        raise ValueError("playlist has no songs")
    return songs
