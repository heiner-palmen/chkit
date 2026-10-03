"""
Clone Hero's scoredata.bin: playcount, best score, stars, hit percentage and
full combo per chart (MD5).

Layout of scoredata.bin as written by v1.1.0.6142 (little endian), decoded on
03.10.2026 and checked against the online leaderboard cache (294 runs), the
scoredata.bin of August 2025 and the results screenshots. Encore (github.com/unicxrn/encore,
src/main/play/scoredata.ts) reads the same layout.

    u32  version tag, 20211009
    u32  number of charts
    per chart:
        16B  MD5 of the chart file (notes.mid / notes.chart)
        u8   number of rows
        u24  playcount of the chart (all instruments and all profiles together)
        per row, 16 bytes (one row per chart and instrument):
            +0   u16  instrument (Clone Hero's enum: 6 Drums, 9 ProDrums, 8 Band ...)
            +2   u8   difficulty (0 Easy ... 3 Expert) of the best-score run
            +3   u8   best percent ever reached at that difficulty, rounded down
            +4   u8   full combo: 1 once the chart was full-combo'd (stays set)
            +5   u16  playback speed in percent of the best-score run
            +7   u8   stars of the best-score run
            +8   u32  modifier flags of the best-score run
            +12  u32  best score

On drums an overhit breaks the combo, so 100 % without a full combo happens.
The file is shared by all profiles of the game.
"""
import struct

VERSION = 20211009
INSTRUMENTS = {0: "Guitar", 1: "Bass", 2: "Rhythm", 3: "GuitarCoop", 4: "SixFretGuitar", 5: "SixFretBass",
               6: "Drums", 7: "Keys", 8: "Band", 9: "ProDrums", 10: "SixFretRhythm", 11: "SixFretGuitarCoop",
               12: "Crowd", 13: "Vocals", 14: "SixFretKeys", 0xFFFF: "None"}
DIFFICULTIES = {0: "Easy", 1: "Medium", 2: "Hard", 3: "Expert"}
BAND, NONE = 8, 0xFFFF
DRUMS = ("ProDrums", "Drums")              # the library takes ProDrums first

_HEADER = struct.Struct("<II")
_ROW = struct.Struct("<HBBBHBII")          # 16 bytes
_CHART_HEAD = 20                           # md5 + u8 rows + u24 playcount


def parse_scoredata(data):
    """MD5 (lower-case hex) -> list of records {"instrument", "difficulty",
    "score", "stars", "percent", "fc", "playcount", "speed"}; None where the
    meaning is not known (percent and fc of Band rows, empty rows).
    ValueError if the bytes do not fit the layout."""
    if len(data) < _HEADER.size:
        raise ValueError(f"{len(data)} bytes, too short for a scoredata.bin")
    version, count = _HEADER.unpack_from(data, 0)
    if version != VERSION:
        raise ValueError(f"version tag {version}, this code reads {VERSION} (another Clone Hero version?)")
    out, pos = {}, _HEADER.size
    for _ in range(count):
        if pos + _CHART_HEAD > len(data):
            raise ValueError(f"ends inside a chart at byte {pos}")
        md5 = data[pos:pos + 16].hex()
        rows = data[pos + 16]
        playcount = int.from_bytes(data[pos + 17:pos + 20], "little")
        pos += _CHART_HEAD
        if pos + rows * _ROW.size > len(data):
            raise ValueError(f"ends inside the rows of chart {md5}")
        records = out.setdefault(md5, [])
        for _ in range(rows):
            instrument, difficulty, percent, fc, speed, stars, _mods, score = _ROW.unpack_from(data, pos)
            pos += _ROW.size
            known = instrument not in (BAND, NONE)
            records.append({
                "instrument": INSTRUMENTS.get(instrument, f"Unknown({instrument})"),
                "difficulty": DIFFICULTIES.get(difficulty, f"Unknown({difficulty})"),
                "score": score,
                "stars": stars if instrument != NONE else None,
                "percent": float(percent) if known and percent <= 100 else None,
                "fc": bool(fc) if known and fc in (0, 1) else None,
                "playcount": playcount,
                "speed": speed,
            })
    if pos != len(data):
        raise ValueError(f"{len(data) - pos} unexpected bytes after the last chart")
    return out


def summaries(records):
    """One summary per MD5: the playcount of the chart, and score, stars,
    percentage and full combo of its ProDrums row (Drums if there is none)."""
    result = {}
    for md5, recs in records.items():
        counts = [r["playcount"] for r in recs if r.get("playcount") is not None]
        rows = {r.get("instrument"): r for r in recs}
        best = next((rows[i] for i in DRUMS if i in rows), None) or {}
        result[md5] = {
            "playcount": max(counts) if counts else None,
            "instrument": best.get("instrument"),
            "difficulty": best.get("difficulty"),
            "score": best.get("score"),
            "stars": best.get("stars"),
            "percent": best.get("percent"),
            "fc": None if best.get("fc") is None else int(best["fc"]),
        }
    return result
