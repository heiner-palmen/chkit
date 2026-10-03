"""currentsong.txt: the song that is playing, empty in the menus."""

from __future__ import annotations

from typing import Optional


def parse(text: str) -> Optional[dict]:
    """currentsong.txt -> {"song", "artist", "charter", "path"}, None when empty
    (no song running). Both schemas Clone Hero writes:

        Ace of Spades                     (or "Song: Ace of Spades")
        Artist: Motörhead, 2008
        Charter: Neversoft
        Pfad: /home/user/.clonehero/Songs/.../notes.mid

    and the old single line "Song Name, Artist, Charter".
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return None
    info = {"song": "", "artist": "", "charter": "", "path": ""}
    if len(lines) > 1 or any(ln.startswith(("Artist:", "Charter:", "Pfad:", "Path:")) for ln in lines):
        first = lines[0]
        info["song"] = first[len("Song:"):].strip() if first.startswith("Song:") else first
        for ln in lines[1:]:
            key, _, value = ln.partition(":")
            value = value.strip()
            if key == "Artist":
                head, sep, tail = value.rpartition(",")
                info["artist"] = head.strip() if sep and tail.strip().isdigit() else value
            elif key == "Charter":
                info["charter"] = value
            elif key in ("Pfad", "Path"):
                info["path"] = value
        return info
    parts = lines[0].rsplit(", ", 2)
    info["song"] = parts[0]
    if len(parts) >= 2:
        info["artist"] = parts[1]
    if len(parts) == 3:
        info["charter"] = parts[2]
    return info
