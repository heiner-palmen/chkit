"""scorestats.json: Clone Hero's statistics of the last run (v1.1+).

Per player: instrument, difficulty, score, stars, notes_hit / total_notes,
is_fc, excess_hits (overhits) and per section notes_hit / notes_count; at the
top the chart MD5 ("checksum"), playback speed and the time of the score.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

DRUMS = ("ProDrums", "Drums")


def timestamp(stats: dict) -> Optional[float]:
    """score_timestamp ('2026-10-03T14:27:04.4025450Z') -> epoch seconds."""
    try:
        return datetime.strptime(str(stats.get("score_timestamp"))[:19], "%Y-%m-%dT%H:%M:%S") \
            .replace(tzinfo=timezone.utc).timestamp()
    except (AttributeError, ValueError):
        return None


def drum_player(stats: dict) -> Optional[dict]:
    """The drums player of a run: ProDrums before Drums, then the higher score."""
    players = [p for p in (stats or {}).get("players") or [] if isinstance(p, dict) and p.get("instrument") in DRUMS]
    players.sort(key=lambda p: (p.get("instrument") == "ProDrums", p.get("score") or 0), reverse=True)
    return players[0] if players else None


def percent(player: dict) -> Optional[int]:
    """Hit percentage as Clone Hero shows and stores it: rounded down."""
    hit, total = player.get("notes_hit"), player.get("total_notes")
    if isinstance(hit, int) and isinstance(total, int) and total:
        return math.floor(100 * hit / total)
    return None


def result(stats: dict) -> Optional[dict]:
    """One run in short: {"md5", "at", "instrument", "difficulty", "score",
    "stars", "percent", "fc"} of the drums player (instrument None without
    one). None if the file lacks the chart MD5 or the time."""
    if not isinstance(stats, dict):
        return None
    md5 = str(stats.get("checksum") or "").strip().lower()
    at = timestamp(stats)
    if len(md5) != 32 or at is None:
        return None
    event = {"md5": md5, "at": at, "instrument": None}
    player = drum_player(stats)
    if player:
        event.update({"instrument": player.get("instrument"), "difficulty": player.get("difficulty"),
                      "score": player.get("score"), "stars": player.get("stars"), "percent": percent(player),
                      "fc": 1 if player.get("is_fc") else 0})
    return event


def section_misses(player: dict) -> list[dict]:
    """[{"index", "name", "missed", "notes"}] for the sections with missed notes."""
    out = []
    for i, s in enumerate(player.get("section_stats") or []):
        if not isinstance(s, dict):
            continue
        hit, count = s.get("notes_hit") or 0, s.get("notes_count") or 0
        if count > hit:
            out.append({"index": i, "name": s.get("section_name", ""), "missed": count - hit, "notes": count})
    return out
