"""
Sets Clone Hero's practice mode up for one spot of a song: the section the
spot starts in, then A and B around it. Every key only where the screen shows
that it means what it should (chkit.game.screen), like the song search.

  PracticeMode(keys, grab, song_running, search)
    .start(name, artist, wanted, spot)   from the menu or the score screen: Practice, the
                                         song, its section, A and B, play
    .next(spot, previous)                while the practice runs at the spot `previous`: the
                                         next spot (A/B in the same section, or a new section)

A spot is a dict: "section" (index in the section list, the chart's sections
in order), "section_start" / "section_end" (seconds, end None for the last),
"a" / "b" (seconds). A goes on `a` or up to one seek step before it, B on `b`
or after it; where they went is put into the spot ("placed_a", "placed_b").

What the practice mode does (v1.1.0.6142, measured 04.10.2026):
  - Main menu -> PRACTICE -> the song list (same search) -> song setup
    ("Ready") -> the list of sections (the chart's, in order; it wraps around
    at both ends). Choosing a section plays it; A and B start at its bounds.
    The first A in that list is often lost: it is pressed again.
  - Enter pauses (Escape does not). The pause menu: RESUME, RESTART SECTION,
    SET A POSITION, SET B POSITION, CLEAR A/B, NEW SECTION, ... It opens on
    the row used last. A and B stand left of it in whole seconds.
  - On SET A/B a press of left/right moves the point by 0.25 s (1-4 ms more
    or less); held, it keeps moving (about 5.5 s per second). B may go past
    the end of the section.
  - RESUME plays from A minus practice_delay (settings.ini, 2 s) and writes
    "Seeking to song time:<A - delay>" to Player.log: that tells where A
    really is. After B (and 1 s more) it goes back to A.
  - NEW SECTION opens the list on the section that runs.
  - Up/down change the speed while a song plays: no key goes to the game
    unless a menu is seen.

Methods return None when it went through, else why they stopped.
"""
import math
import os
import time

from . import screen as cs
from .search import PLAYER_LOG

SELECT, BACK, PAUSE = "A", "S", "ENTER"
SEEK_LEFT, SEEK_RIGHT = "LEFT", "RIGHT"
SETTINGS = os.path.expanduser("~/.clonehero/settings.ini")


def practice_delay(path=SETTINGS):
    """practice_delay of settings.ini in seconds (2 when it says nothing)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                key, _, value = line.partition("=")
                if key.strip() == "practice_delay":
                    return int(value.strip()) / 1000
    except (OSError, ValueError):
        pass
    return 2.0


class SeekLog:
    """The "Seeking to song time:" lines the game writes to Player.log."""

    LINE = "Seeking to song time:"

    def __init__(self, path=PLAYER_LOG, sleep=time.sleep, now=time.monotonic):
        self.path, self.sleep, self.now = path, sleep, now
        self.offset = 0

    def mark(self):
        try:
            self.offset = os.path.getsize(self.path)
        except OSError:
            self.offset = 0

    def seeks(self):
        """Song times of the seeks since the mark (or the last call)."""
        try:
            with open(self.path, "rb") as fh:
                if os.fstat(fh.fileno()).st_size < self.offset:
                    self.offset = 0                        # a new log (game restarted)
                fh.seek(self.offset)
                data = fh.read()
        except OSError:
            return []
        end = data.rfind(b"\n") + 1
        self.offset += end
        out = []
        for line in data[:end].decode("utf-8", "replace").splitlines():
            if line.startswith(self.LINE):
                try:
                    out.append(float(line[len(self.LINE):]))
                except ValueError:
                    pass
        return out

    def first(self, timeout):
        """The first seek since the mark, None when none comes in time."""
        end = self.now() + timeout
        while True:
            found = self.seeks()
            if found:
                return found[0]
            if self.now() >= end:
                return None
            self.sleep(0.1)


class PracticeMode:
    LOAD_S = 25                    # the song is loaded after "Ready" (14.000 songs: a few seconds)
    MENU_S = 2.5                   # a menu shows a key this late at the most (else it is pressed again)
    SEEK_STEP_S = 0.25             # one press of left/right on SET A/B
    SEEK_PAUSE_S = 0.12            # between two of them (all arrive)
    MAX_SEEK_PRESSES = 800         # 200 s

    def __init__(self, keys, grab, song_running, search, seek_log=None, delay_s=None, starts=None,
                 sleep=time.sleep, now=time.monotonic, log=print):
        """`search`: a chkit.game.search.SongSearch on the same keys and
        screen; `seek_log`: SeekLog (None: A is not checked after RESUME);
        `starts`: the start of every section of the chart (seconds), to tell
        which one runs."""
        self.keys, self.grab, self.song_running, self.search = keys, grab, song_running, search
        self.seek_log = seek_log
        self.starts = list(starts or [])
        self.delay_s = practice_delay() if delay_s is None else delay_s
        self.sleep, self.now, self.log = sleep, now, log

    # -- small steps -------------------------------------------------------------------

    def wait(self, wanted, timeout):
        return self.search.wait(wanted, timeout)

    def press_until(self, key, wanted, timeout, tries=2):
        return self.search.press_until(key, wanted, timeout, tries)

    def to_main_menu(self):
        """Back to the main menu from the song list, its menus, the song setup
        or the score screen."""
        for _ in range(4):
            pic = self.grab()
            if pic is None:
                return "screen unreadable"
            if cs.main_row(pic) is not None:
                return None
            if cs.in_song_list(pic):
                if cs.dialog_open(pic):
                    pic = self.press_until("ESC", lambda p: not cs.dialog_open(p), self.MENU_S)
                elif cs.menu_row(pic) is not None or cs.sort_row(pic) is not None:
                    pic = self.press_until(BACK, lambda p: cs.describe(p) == "list", self.MENU_S)
                else:
                    pic = self.press_until(BACK, lambda p: cs.main_row(p) is not None, 4)
            elif cs.setup_panel(pic):
                pic = self.press_until(BACK, cs.in_song_list, 4)
            elif self.song_running() or cs.pause_menu(pic) or cs.section_list(pic):
                return "a song is running"
            else:                                         # the score screen: A goes to the song list
                pic = self.press_until(SELECT, cs.in_song_list, 8, tries=1)
            if pic is None:
                return "the way back to the main menu did not show up"
        return "the main menu did not come up"

    def to_practice_list(self):
        """Main menu -> PRACTICE -> its song list."""
        pic = self.grab()
        row = cs.main_row(pic) if pic is not None else None
        for _ in range(len(cs.MAIN_ROWS)):
            if row == cs.PRACTICE_ROW or row is None:
                break
            before = row
            pic = self.press_until("DOWN" if row < cs.PRACTICE_ROW else "UP",
                                   lambda p: cs.main_row(p) not in (before, None), self.MENU_S)
            row = cs.main_row(pic) if pic is not None else None
        if row != cs.PRACTICE_ROW:
            return "PRACTICE not reached in the main menu"
        if self.press_until(SELECT, cs.in_song_list, 8) is None:
            return "the song list did not come up after PRACTICE"
        self.sleep(0.5)                                   # the list scrolls in
        return None

    def to_sections(self):
        """The cursor is on the song: A (song setup), A ("Ready"), the song
        loads and the list of sections comes up."""
        if self.song_running():
            return "a song is running"
        if self.press_until(SELECT, cs.setup_panel, 4) is None:
            return "the song setup did not come up"
        self.sleep(0.5)
        self.keys.press(SELECT)                           # once: a second A would choose a section
        if self.wait(cs.section_list, self.LOAD_S) is None:
            return "the list of sections did not come up"
        self.sleep(0.5)
        return None

    def choose_section(self, target, current=0):
        """In the list of sections: from row `current` to `target`, then A.
        Every press must move the highlight or scroll the list. Up to ten
        sections the list does not scroll: the highlighted row is the one."""
        pic = self.grab()
        if pic is None or not cs.section_list(pic):
            return "the list of sections is not up"
        row = cs.section_row(pic)
        if 0 < len(self.starts) <= len(cs.SECTION_ROWS) and row is not None:
            current = row
        at = current
        while at != target:
            key = "DOWN" if at < target else "UP"
            seen = (cs.section_row(pic), cs.section_rows_bits(pic))
            pic = self.press_until(key, lambda p: cs.section_list(p)
                                   and (cs.section_row(p), cs.section_rows_bits(p)) != seen, self.MENU_S)
            if pic is None:
                return f"the list of sections did not move at row {at}"
            at += 1 if key == "DOWN" else -1
        self.sleep(0.3)
        if self.press_until(SELECT, lambda p: not cs.section_list(p), 3, tries=3) is None:
            return "the section did not start"
        return None

    def pause(self):
        """The pause menu of the practice mode (it shows A and B); left open
        (a step that stopped before), it is taken as it is."""
        pic = self.grab()
        if pic is not None and cs.ab_shown(pic):
            return None
        pic = self.press_until(PAUSE, cs.pause_menu, self.MENU_S)
        if pic is None:
            return "the pause menu did not come up"
        self.sleep(0.4)                                   # it fades in
        if self.wait(cs.ab_shown, 1) is None:
            self.keys.press(PAUSE)                        # Quickplay's: play on
            return "this is not the practice mode"
        return None

    def to_row(self, target):
        """The cursor of the pause menu to row `target`."""
        pic = self.grab()
        row = cs.pause_row(pic) if pic is not None else None
        for _ in range(2 * len(cs.PAUSE_ROWS)):
            if row == target or row is None:
                break
            before = row
            pic = self.press_until("DOWN" if row < target else "UP",
                                   lambda p: cs.pause_row(p) not in (before, None), self.MENU_S)
            row = cs.pause_row(pic) if pic is not None else None
        return None if row == target else f"row {target} not reached in the pause menu"

    def shown(self, which):
        """A or B ("A" / "B") in whole seconds as the pause menu shows it:
        the same twice in a row (the picture may lag behind a key)."""
        last = None
        for _ in range(6):
            pic = self.grab()
            value = cs.ab_time(pic, which) if pic is not None else None
            if value is not None and value == last:
                return value
            last = value
            self.sleep(0.15)
        return None

    def check_section(self, spot):
        """A and B are the bounds of the spot's section: the right one runs."""
        a = self.shown("A")
        want_a = math.floor(spot["section_start"])
        if a is None or abs(a - want_a) > 1:
            return f"A shows {a}, the section starts at {want_a}: another section runs?"
        end = spot.get("section_end")
        b = self.shown("B") if end is not None else None
        if b is not None and abs(b - math.floor(end)) > 1:
            return f"B shows {b}, the section ends at {math.floor(end)}"
        return None

    def presses(self, which, target, start):
        """Seek presses (+ right, - left) from `start` to `target`: A lands on
        it or before it, B on it or after it (2 ms of slack for the steps)."""
        steps = (target - start) / self.SEEK_STEP_S
        n = math.floor(steps + 0.008) if which == "A" else math.ceil(steps - 0.008)
        return max(-self.MAX_SEEK_PRESSES, min(self.MAX_SEEK_PRESSES, n))

    def seek(self, which, target, start):
        """Move A or B ("A" / "B") from `start` (seconds, as exact as known)
        towards `target`. Returns (failed, where it went)."""
        failed = self.to_row(cs.SET_A if which == "A" else cs.SET_B)
        if failed:
            return failed, start
        if self.wait(cs.seek_legend, 1) is None:
            return "the pause menu offers no Seek", start
        n = self.presses(which, target, start)
        for _ in range(abs(n)):
            self.keys.press(SEEK_RIGHT if n > 0 else SEEK_LEFT)
            self.sleep(self.SEEK_PAUSE_S)
        placed = start + n * self.SEEK_STEP_S
        self.sleep(0.3)
        shown = self.shown(which)
        if shown is None or abs(shown - math.floor(placed)) > 1:
            return f"{which} shows {shown}, wanted {math.floor(placed)}", placed
        return None, placed

    def set_points(self, spot, a_now, b_now):
        """A and B of the spot from where they are (seconds; b_now None: not
        known exactly, the shown seconds are taken). A stays before B: when
        the spot lies after the old B, B goes first."""
        if b_now is None:
            b_now = self.shown("B")
            if b_now is None:
                return "B cannot be read"
        order = ("B", "A") if spot["a"] >= b_now else ("A", "B")
        for which in order:
            start = a_now if which == "A" else b_now
            failed, placed = self.seek(which, spot[which.lower()], start)
            spot["placed_" + which.lower()] = placed
            if failed:
                return failed
        return None

    def resume(self):
        failed = self.to_row(cs.RESUME)
        if failed:
            return failed
        if self.press_until(SELECT, lambda p: not cs.pause_menu(p), self.MENU_S) is None:
            return "the song did not go on after RESUME"
        return None

    def resume_checked(self, spot):
        """RESUME, then the seek in Player.log says where A is; when it is not
        where it should be (a press lost), A is set once more."""
        for attempt in range(2):
            if self.seek_log is not None:
                self.seek_log.mark()
            failed = self.resume()
            if failed or self.seek_log is None:
                return failed
            seek = self.seek_log.first(3)
            if seek is None:
                self.log("A not confirmed: no seek in Player.log")
                return None
            a = seek + self.delay_s
            off = a - spot["placed_a"]
            spot["placed_a"] = a
            if abs(off) <= self.SEEK_STEP_S / 2 or attempt:
                if abs(off) > self.SEEK_STEP_S / 2:
                    self.log(f"A is {off:+.2f} s off after correcting")
                return None
            self.log(f"A is {off:+.2f} s off: setting it again")
            failed = self.pause()
            if failed:
                return failed
            failed, placed = self.seek("A", spot["a"], a)
            spot["placed_a"] = placed
            if failed:
                return failed
        return None

    # -- the whole way -----------------------------------------------------------------

    def start(self, name, artist, wanted, spot):
        """From the menu or the score screen to the spot, playing."""
        if self.song_running():
            return "a song is running"
        steps = (("main menu", self.to_main_menu), ("practice", self.to_practice_list),
                 ("song", lambda: self.search.run(name, artist, wanted)), ("setup", self.to_sections))
        for what, step in steps:
            failed = step()
            if failed:
                return f"{what}: {failed}"
        return self._play_spot(spot, current=0)

    def next(self, spot, previous):
        """While the practice runs at the spot `previous`: the next spot.
        Always through NEW SECTION, also in the same section: A and B start
        from the bounds of the section again, exactly known."""
        failed = self.pause()
        return failed or self.new_section(spot, previous["section"])

    def new_section(self, spot, current, retry=True):
        """Paused: NEW SECTION, the list opens on the section that runs
        (`current`, as far as known), then the spot."""
        failed = self.to_row(cs.NEW_SECTION)
        if failed:
            return failed
        if self.press_until(SELECT, cs.section_list, 4) is None:
            return "the list of sections did not come up"
        self.sleep(0.5)
        return self._play_spot(spot, current, retry)

    def running_section(self):
        """Paused right after choosing a section: which one runs, told by A
        (it starts at the section's start). None when A does not tell."""
        a = self.shown("A")
        found = [k for k, t in enumerate(self.starts) if a is not None and abs(math.floor(t) - a) <= 0]
        return found[0] if len(found) == 1 else None

    def _play_spot(self, spot, current, retry=False):
        failed = self.choose_section(spot["section"], current)
        if failed:
            return failed
        failed = self.pause()
        if failed:
            return failed
        failed = self.check_section(spot)
        if failed and retry:
            # the list did not open where it was thought (a step before stopped):
            # A tells which section runs, and from there it is found
            runs = self.running_section()
            if runs is not None and runs != spot["section"]:
                self.log(f"section {runs} runs, not {spot['section']}: choosing again")
                return self.new_section(spot, runs, retry=False)
        if failed:
            return failed
        failed = self.set_points(spot, spot["section_start"], spot.get("section_end"))
        return failed or self.resume_checked(spot)
