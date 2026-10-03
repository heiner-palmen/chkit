"""A tiny Standard MIDI File writer for the tests."""

import struct


def _varlen(value):
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))


def track(name=None, notes=(), texts=(), tempo=(), sigs=()):
    """notes: (tick, note, length, velocity); texts: (tick, text); tempo:
    (tick, bpm); sigs: (tick, numerator, denominator)."""
    events = []
    if name is not None:
        events.append((0, 0, b"\xff\x03" + _varlen(len(name)) + name.encode()))
    for tick, bpm in tempo:
        usec = int(round(60_000_000 / bpm))
        events.append((tick, 0, b"\xff\x51\x03" + usec.to_bytes(3, "big")))
    for tick, num, den in sigs:
        events.append((tick, 0, bytes([0xFF, 0x58, 4, num, den.bit_length() - 1, 24, 8])))
    for tick, text in texts:
        events.append((tick, 1, b"\xff\x01" + _varlen(len(text)) + text.encode()))
    for tick, note, length, velocity in notes:
        events.append((tick, 3, bytes([0x90, note, velocity])))
        events.append((tick + length, 2, bytes([0x80, note, 0])))
    events.sort(key=lambda e: (e[0], e[1]))
    data, last = b"", 0
    for tick, _, payload in events:
        data += _varlen(tick - last) + payload
        last = tick
    data += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + data


def midi(tracks, division=480):
    return b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), division) + b"".join(tracks)
