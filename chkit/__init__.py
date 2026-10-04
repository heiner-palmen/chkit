"""chkit: building blocks for Clone Hero tools.

    chkit.chart     read .chart / .mid drum charts, write .chart
    chkit.song      song folders: song.ini, chart MD5, audio files, text helpers
    chkit.chfiles   currentsong.txt, scorestats.json, scoredata.bin, MIDI profiles, playlists
    chkit.io        atomic writes, network folders with timeouts, tolerant JSON
    chkit.game      drive the running game (Linux, X11): read its window, search a song
    chkit.groove    groove fingerprint of a chart, and how alike two songs feel

Standard library only (Python 3.10+); chkit.game types through evdev
(pip install "chkit[game]").
"""

__version__ = "0.3.0"
