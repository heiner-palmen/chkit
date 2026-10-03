"""Clone Hero MIDI profiles (~/.clonehero/MIDI Profiles/<device>.yaml): which
MIDI note of the kit counts as which pad.

    DeviceName: TD-17:TD-17 MIDI 1 20:0
    Mappings:
      Red Pad:
      - NoteNumber: 38
        Velocity: 10
        OverHitThreshold: 0

Only this simple layout is read, no general YAML.
"""

from __future__ import annotations


def parse(text: str) -> dict:
    """{"device": name, "pads": {pad name: [{"note", "velocity", "overhit"}]}}."""
    profile = {"device": "", "pads": {}}
    pad, entry = None, None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = stripped.lstrip("- ").partition(":")
        key, value = key.strip(), value.strip().strip("'\"")
        if indent == 0:
            if key == "DeviceName":
                profile["device"] = value
            pad = None
            continue
        if not stripped.startswith("-") and value == "" and indent <= 2:
            pad = key
            profile["pads"].setdefault(pad, [])
            continue
        if pad is None:
            continue
        if stripped.startswith("-"):
            entry = {"note": None, "velocity": 0, "overhit": 0}
            profile["pads"][pad].append(entry)
        if entry is not None and value.lstrip("-").isdigit():
            field = {"NoteNumber": "note", "Velocity": "velocity", "OverHitThreshold": "overhit"}.get(key)
            if field:
                entry[field] = int(value)
    return profile


def note_to_pad(profile: dict) -> dict:
    """{MIDI note: (pad name, velocity threshold)}."""
    return {e["note"]: (pad, e["velocity"]) for pad, entries in profile["pads"].items()
            for e in entries if e.get("note") is not None}
