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
"a" / "b" (seconds).

What the practice mode does (v1.1, measured 04.10.2026):
  - Main menu -> PRACTICE -> the song list -> song setup ("Ready") -> the list
    of sections. Choosing a section plays it; A and B start at its bounds.
  - The pause menu: RESUME, RESTART SECTION, SET A POSITION, SET B POSITION,
    CLEAR A/B, NEW SECTION, ... A and B stand left of it in whole seconds. On
    SET A/B the arrow keys move the point ("Seek"); RESUME plays from A.
  - Up/down change the speed while a song plays: no key goes to the game
    unless a menu is seen.

`run`-like methods return None when it went through, else why they stopped.
"""
import math
import time

from . import screen as cs

SELECT, BACK, PAUSE = "A", "S", "ESC"
SEEK_LEFT, SEEK_RIGHT = "LEFT", "RIGHT"


class PracticeMode:
    LOAD_S = 25                    # the song is loaded after "Ready" (14.000 songs: a few seconds)
    MAX_SEEK_PRESSES = 600
    SEEK_PAUSE_S = 0.05            # between two seek presses
    #: seconds one press of an arrow key moves A or B; None: unknown, the
    #: label is read after every press
    SEEK_STEP_S = None

    def __init__(self, keys, grab, song_running, search, sleep=time.sleep, now=time.monotonic, log=print):
        """`search`: a chkit.game.search.SongSearch on the same keys and screen."""
        self.keys, self.grab, self.song_running, self.search = keys, grab, song_running, search
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
                    pic = self.press_until("ESC", lambda p: not cs.dialog_open(p), 2)
                elif cs.menu_row(pic) is not None or cs.sort_row(pic) is not None:
                    pic = self.press_until(BACK, lambda p: cs.describe(p) == "list", 2)
                else:
                    pic = self.press_until(BACK, lambda p: cs.main_row(p) is not None, 3)
            elif cs.setup_panel(pic):
                pic = self.press_until(BACK, cs.in_song_list, 3)
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
                                   lambda p: cs.main_row(p) not in (before, None), 1.5)
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
        self.sleep(0.3)
        self.keys.press(SELECT)                           # once: a second A would choose a section
        if self.wait(cs.section_list, self.LOAD_S) is None:
            return "the list of sections did not come up"
        self.sleep(0.5)
        return None

    def choose_section(self, target, current=0):
        """In the list of sections: from row `current` to `target`, then A.
        Every press must move the highlight or scroll the list."""
        pic = self.grab()
        if pic is None or not cs.section_list(pic):
            return "the list of sections is not up"
        at = current
        while at != target:
            key = "DOWN" if at < target else "UP"
            seen = (cs.section_row(pic), cs.section_rows_bits(pic))
            pic = self.press_until(key, lambda p: cs.section_list(p)
                                   and (cs.section_row(p), cs.section_rows_bits(p)) != seen, 1.5)
            if pic is None:
                return f"the list of sections did not move at row {at}"
            at += 1 if key == "DOWN" else -1
        if self.press_until(SELECT, lambda p: not cs.section_list(p), 4) is None:
            return "the section did not start"
        return None

    def pause(self):
        """The pause menu of the practice mode (it shows A and B)."""
        if self.press_until(PAUSE, cs.ab_shown, 2.5) is None:
            return "the pause menu did not come up"
        self.sleep(0.25)                                  # it fades in
        return None

    def to_row(self, target):
        """The cursor of the pause menu to row `target`."""
        pic = self.grab()
        row = cs.pause_row(pic) if pic is not None else None
        for _ in range(len(cs.PAUSE_ROWS)):
            if row == target or row is None:
                break
            before = row
            pic = self.press_until("DOWN" if row < target else "UP",
                                   lambda p: cs.pause_row(p) not in (before, None), 1.5)
            row = cs.pause_row(pic) if pic is not None else None
        return None if row == target else f"row {target} not reached in the pause menu"

    def ab(self):
        """(A, B) in whole seconds as the pause menu shows them."""
        pic = self.grab()
        if pic is None:
            return None, None
        return cs.ab_time(pic, "A"), cs.ab_time(pic, "B")

    def shown(self, which):
        pic = self.grab()
        return cs.ab_time(pic, which) if pic is not None else None

    def check_section(self, spot):
        """A and B are the bounds of the spot's section: the right one runs."""
        a, b = self.ab()
        want_a = math.floor(spot["section_start"])
        if a is None or abs(a - want_a) > 1:
            return f"A shows {a}, the section starts at {want_a}: another section runs?"
        if spot.get("section_end") is not None and b is not None and abs(b - math.floor(spot["section_end"])) > 1:
            return f"B shows {b}, the section ends at {math.floor(spot['section_end'])}"
        return None

    def seek(self, which, target, start=None):
        """Move A or B ("A" / "B") to `target` seconds. `start`: where it is
        now, exactly (the section bounds), for SEEK_STEP_S."""
        failed = self.to_row(cs.SET_A if which == "A" else cs.SET_B)
        if failed:
            return failed
        if self.wait(cs.seek_legend, 1) is None:
            return "the pause menu offers no Seek"
        want = math.floor(target)
        self.placed = target
        if self.SEEK_STEP_S and start is not None:
            presses = max(-self.MAX_SEEK_PRESSES, min(self.MAX_SEEK_PRESSES, round((target - start) / self.SEEK_STEP_S)))
            key = SEEK_RIGHT if presses > 0 else SEEK_LEFT
            for _ in range(abs(presses)):
                self.keys.press(key)
                self.sleep(self.SEEK_PAUSE_S)
            self.placed = start + presses * self.SEEK_STEP_S
            self.sleep(0.2)
        else:
            shown = self.shown(which)
            presses = 0
            while shown is not None and shown != want and presses < self.MAX_SEEK_PRESSES:
                self.keys.press(SEEK_RIGHT if shown < want else SEEK_LEFT)
                presses += 1
                self.sleep(self.SEEK_PAUSE_S)
                shown = self.shown(which)
        shown = self.shown(which)
        if shown is None or abs(shown - want) > 1:
            return f"{which} shows {shown}, wanted {want}"
        return None

    def set_points(self, spot, a_now, b_now):
        """A and B of the spot; `a_now` / `b_now`: where they are (seconds).
        A stays before B: when the spot lies after the old B, B goes first.
        Where they went is kept in the spot ("placed_a", "placed_b") for the
        next one."""
        order = (("B", spot["b"], b_now), ("A", spot["a"], a_now)) if spot["a"] >= b_now \
            else (("A", spot["a"], a_now), ("B", spot["b"], b_now))
        for which, target, start in order:
            failed = self.seek(which, target, start)
            if failed:
                return failed
            spot["placed_" + which.lower()] = self.placed
        return None

    def resume(self):
        failed = self.to_row(cs.RESUME)
        if failed:
            return failed
        if self.press_until(SELECT, lambda p: not cs.pause_menu(p), 2) is None:
            return "the song did not go on after RESUME"
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
        """While the practice runs at the spot `previous`: the next spot."""
        failed = self.pause()
        if failed:
            return failed
        if spot["section"] == previous["section"]:
            return self.set_points(spot, previous.get("placed_a", previous["a"]),
                                   previous.get("placed_b", previous["b"])) or self.resume()
        failed = self.to_row(cs.NEW_SECTION)
        if failed:
            return failed
        if self.press_until(SELECT, cs.section_list, 3) is None:
            return "the list of sections did not come up"
        self.sleep(0.3)
        return self._play_spot(spot, current=previous["section"])

    def _play_spot(self, spot, current):
        failed = self.choose_section(spot["section"], current)
        if failed:
            return failed
        failed = self.pause() or self.check_section(spot)
        if failed:
            return failed
        end = spot.get("section_end")
        failed = self.set_points(spot, spot["section_start"], end if end is not None else spot["b"])
        return failed or self.resume()
