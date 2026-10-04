"""Tests for the practice mode screens (chkit.game.screen) and the driver
(chkit.game.practice). A stand-in for Clone Hero's practice mode draws its
screens and reacts to the keys, like the one for the song search."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chkit.game import practice as cp  # noqa: E402
from chkit.game import screen as cs  # noqa: E402
from chkit.game import search as ca  # noqa: E402
from test_game_search import LIGHT, WHITE, Canvas, Clock, draw  # noqa: E402

GREEN, RED, DARK_ROW = (69, 244, 0), (255, 0, 0), (30, 30, 30)


def dot(c, colour, x, y):
    c.rect(x - 6, y - 6, x + 7, y + 7, colour)


def draw_main(row, size=(1280, 720)):
    c = Canvas(*size)
    for colour, x, y in cs.MAIN_LEGEND:
        dot(c, GREEN if colour == "green" else RED, x, y)
    for i, y in enumerate(cs.MAIN_ROWS):
        c.rect(24, y - 23, 342, y + 23, LIGHT if i == row else DARK_ROW)
        c.rect(40, y - 10, 40 + 15 * (i + 3), y + 10, (17, 17, 17) if i == row else WHITE)    # the name
    return c.picture()


def draw_sections(names, top, cursor, size=(1280, 720)):
    """The list of sections, `top`: the first section shown, `cursor`: the chosen one."""
    c = Canvas(*size)
    for colour, x, y in cs.SECTION_LEGEND:
        dot(c, GREEN if colour == "green" else RED, x, y)
    for i, y in enumerate(cs.SECTION_ROWS):
        k = top + i
        if k >= len(names):
            break
        chosen = k == cursor
        c.rect(37, y - 15, 470, y + 16, LIGHT if chosen else DARK_ROW)
        c.rect(50, y - 8, 60 + 9 * (k % 23), y + 8, (17, 17, 17) if chosen else WHITE)
    return c.picture()


def draw_digit(c, digit, x0, y0):
    for r, bits in enumerate(cs._TEMPLATES[digit]):
        for col in range(cs.DIGIT_W):
            if bits >> (cs.DIGIT_W - 1 - col) & 1:
                c.rect(x0 + col, y0 + r, x0 + col + 1, y0 + r + 1, WHITE)


def draw_paused(row, a, b, practice=True, size=(1280, 720)):
    c = Canvas(*size)
    seek = row in (cs.SET_A, cs.SET_B)
    for colour, x, y in cs.PAUSE_LEGENDS[1 if seek else 0]:
        dot(c, GREEN if colour == "green" else RED, x, y)
    for i, y in enumerate(cs.PAUSE_ROWS if practice else cs.PAUSE_ROWS[:7]):
        c.rect(950, y - 16, 1230, y + 16, LIGHT if i == row else DARK_ROW)
        c.rect(964, y - 8, 964 + 12 * (i + 4), y + 8, (17, 17, 17) if i == row else WHITE)
    if practice:
        for which, seconds in (("A", a), ("B", b)):
            y = cs.AB_ROWS[which]
            x0, y0, x1, y1 = cs.AB_LETTER
            dy = y - cs.AB_ROWS["A"]
            for x in (x0 + 2, x1 - 5):                     # the strokes of the letter
                c.rect(x, y0 + dy + 1, x + 3, y1 + dy - 1, WHITE)
            s = int(seconds)
            text = f"{s // 3600:02d}{s // 60 % 60:02d}{s % 60:02d}"
            for x, d in zip(cs.AB_CELLS, text):
                draw_digit(c, d, x, y)
    return c.picture()


def draw_playing(size=(1280, 720)):
    c = Canvas(*size)
    c.rect(470, 300, 940, 720, (40, 40, 40))           # the highway
    return c.picture()


class PracticeScreenTest(unittest.TestCase):
    def test_main_menu_rows(self):
        for size in ((640, 360), (1280, 720), (1920, 1080)):
            for row in range(7):
                with self.subTest(size=size, row=row):
                    pic = draw_main(row, size)
                    self.assertEqual(cs.main_row(pic), row)
                    self.assertFalse(cs.in_song_list(pic))
        self.assertEqual(cs.describe(draw_main(3)), "main-3")
        self.assertIsNone(cs.main_row(draw()))
        self.assertIsNone(cs.main_row(draw_paused(0, 10, 20)))

    def test_section_list(self):
        names = [f"s{i}" for i in range(14)]
        for size in ((640, 360), (1280, 720), (1920, 1080)):
            with self.subTest(size=size):
                pic = draw_sections(names, 0, 3, size)
                self.assertTrue(cs.section_list(pic))
                self.assertEqual(cs.section_row(pic), 3)
                self.assertEqual(cs.describe(pic), "sections-3")
        self.assertEqual(cs.section_row(draw_sections(names, 4, 13)), 9)
        self.assertNotEqual(cs.section_rows_bits(draw_sections(names, 4, 13)),
                            cs.section_rows_bits(draw_sections(names, 3, 12)))
        self.assertFalse(cs.section_list(draw_main(3)))
        self.assertFalse(cs.section_list(draw_paused(0, 10, 20)))

    def test_pause_menu_and_times(self):
        for size in ((1280, 720), (1920, 1080)):
            for row in range(10):
                with self.subTest(size=size, row=row):
                    pic = draw_paused(row, 103, 123, size=size)
                    self.assertEqual(cs.pause_row(pic), row)
                    self.assertEqual(cs.seek_legend(pic), row in (cs.SET_A, cs.SET_B))
                    self.assertTrue(cs.ab_shown(pic))
                    self.assertEqual((cs.ab_time(pic, "A"), cs.ab_time(pic, "B")), (103, 123))
        quickplay = draw_paused(5, 0, 0, practice=False)
        self.assertTrue(cs.pause_menu(quickplay))
        self.assertFalse(cs.ab_shown(quickplay))
        # Quickplay's "Are you sure you want to restart?" puts a light bar over the letters
        c = Canvas(1280, 720)
        c.data[:] = bytearray(quickplay.data)
        c.rect(440, 330, 840, 362, LIGHT)
        self.assertFalse(cs.ab_shown(c.picture()))
        self.assertIsNone(cs.ab_time(quickplay, "A"))
        self.assertEqual(cs.describe(draw_paused(2, 1, 2)), "paused-2")

    def test_every_known_digit_is_read(self):
        for seconds in (0, 1, 22, 33, 44, 55, 66 * 60 + 7, 3600 + 17 * 60 + 4):
            with self.subTest(seconds=seconds):
                self.assertEqual(cs.ab_time(draw_paused(0, seconds, 0), "A"), seconds)


SECTIONS = [0.0, 13.06, 23.59, 36.57, 47.06, 57.59, 70.5, 81.0, 95.2, 104.0, 118.5, 130.0, 141.3]
SONG_END = 160.0


class PracticeGame:
    """The practice mode as far as the driver sees it (as measured, see
    chkit.game.practice)."""

    def __init__(self, screen="score", sections=SECTIONS, seek_step=0.25, lose_first_select=True):
        self.screen = screen
        self.sections = sections
        self.main = 0
        self.top = self.cursor = 0
        self.running_section = None
        self.row = 0                    # the pause menu opens on the row used last
        self.a = self.b = None
        self.seek_step = seek_step
        self.lose_first_select = lose_first_select
        self.keys = []
        self.speed_changes = 0
        self.stray = []
        self.loading = 0               # pictures until the list of sections is up
        self.deaf = {}
        self.drawn = {}
        self.resumed_at = []           # where A was at each RESUME (Player.log)

    def bounds(self, k):
        return self.sections[k], self.sections[k + 1] if k + 1 < len(self.sections) else SONG_END

    def running(self):
        return self.screen in ("loading", "sections", "playing", "paused", "qpaused")

    def picture(self):
        key = (self.screen, self.main, self.top, self.cursor, self.row,
               None if self.a is None else (math.floor(self.a), math.floor(self.b)))
        if self.screen != "loading" and key in self.drawn:
            return self.drawn[key]
        pic = self.drawn[key] = self._draw()
        return pic

    def _draw(self):
        if self.screen == "loading":
            self.loading -= 1
            if self.loading <= 0:
                self.screen = "sections"
            return draw_playing()
        if self.screen == "main":
            return draw_main(self.main)
        if self.screen in ("list", "setup"):
            return draw(self.screen)
        if self.screen == "score":
            return draw("score", size=(1280, 720))
        if self.screen == "sections":
            return draw_sections(self.sections, self.top, self.cursor)
        if self.screen == "paused":
            return draw_paused(self.row, math.floor(self.a), math.floor(self.b))
        if self.screen == "qpaused":
            return draw_paused(0, 0, 0, practice=False)
        return draw_playing()

    def press(self, key):
        self.keys.append(key)
        if self.deaf.get(key):
            self.deaf[key] -= 1
            return
        s = self.screen
        if s == "score":
            if key == "A":
                self.screen = "list"
            else:
                self.stray.append((s, key))
        elif s == "list":
            if key == "S":
                self.screen = "main"
            elif key == "A":
                self.screen = "setup"
            else:
                self.stray.append((s, key))
        elif s == "main":
            if key in ("UP", "DOWN"):
                self.main = max(0, min(6, self.main + (1 if key == "DOWN" else -1)))
            elif key == "A" and self.main == cs.PRACTICE_ROW:
                self.screen = "list"
            else:
                self.stray.append((s, key))
        elif s == "setup":
            if key == "A":
                self.screen, self.loading, self.top, self.cursor = "loading", 3, 0, 0
            elif key == "S":
                self.screen = "list"
        elif s == "sections":
            if key in ("UP", "DOWN"):
                n = len(self.sections)                     # it wraps around at both ends
                self.cursor = (self.cursor + (1 if key == "DOWN" else -1)) % n
                self.top = min(max(self.top, self.cursor - 9), self.cursor)
            elif key == "A":
                if self.lose_first_select:
                    self.lose_first_select = False
                    return
                self.running_section = self.cursor
                self.a, self.b = self.bounds(self.cursor)
                self.screen = "playing"
            else:
                self.stray.append((s, key))
        elif s == "playing":
            if key == "ENTER":
                self.screen = "paused"
            elif key in ("UP", "DOWN"):
                self.speed_changes += 1
            else:
                self.stray.append((s, key))
        elif s == "qpaused":
            if key == "ENTER":
                self.screen = "qplaying"
            else:
                self.stray.append((s, key))
        elif s == "qplaying":
            if key == "ENTER":
                self.screen = "qpaused"
            else:
                self.stray.append((s, key))
        elif s == "paused":
            if key in ("UP", "DOWN"):
                self.row = max(0, min(9, self.row + (1 if key == "DOWN" else -1)))
            elif key in ("LEFT", "RIGHT") and self.row in (cs.SET_A, cs.SET_B):
                step = self.seek_step if key == "RIGHT" else -self.seek_step
                if self.row == cs.SET_A:
                    self.a = max(0.0, min(self.b - 0.5, self.a + step))
                else:
                    self.b = max(self.a + 0.5, min(SONG_END, self.b + step))
            elif key == "A" and self.row == cs.RESUME:
                self.screen = "playing"
                self.resumed_at.append(self.a)
            elif key == "A" and self.row == cs.NEW_SECTION:
                self.screen = "sections"
                self.cursor = self.running_section
                self.top = max(0, self.cursor - 9)
            elif key == "ENTER":
                self.screen = "playing"
            else:
                self.stray.append((s, key))


class Keys:
    def __init__(self, game):
        self.game = game

    def press(self, name, shift=False, hold=0.03):
        self.game.press(name)


class SeekLog:
    """Player.log as far as RESUME goes: "Seeking to song time:<A - 2>"."""

    def __init__(self, game):
        self.game, self.seen = game, 0

    def mark(self):
        self.seen = len(self.game.resumed_at)

    def first(self, timeout):
        new = self.game.resumed_at[self.seen:]
        return new[0] - 2.0 if new else None


def spot(section, a, b, sections=SECTIONS):
    end = sections[section + 1] if section + 1 < len(sections) else None
    return {"section": section, "section_start": sections[section], "section_end": end, "a": a, "b": b}


class PracticeTest(unittest.TestCase):
    def mode(self, game, found=None, seek_log=True, starts=True):
        clock = self.clock = Clock()
        self.logged = []
        search = ca.SongSearch(Keys(game), game.picture, game.running, None, sleep=clock.sleep, now=clock.now,
                               log=self.logged.append)
        searched = self.searched = []

        def run(name, artist=None, wanted=None):        # the song search has its own tests
            searched.append((game.screen, name))
            return found
        search.run = run
        return cp.PracticeMode(Keys(game), game.picture, game.running, search,
                               seek_log=SeekLog(game) if seek_log else None, delay_s=2.0,
                               starts=game.sections if starts else None,
                               sleep=clock.sleep, now=clock.now, log=self.logged.append)

    def assertPlaced(self, game, a, b):
        """A on `a` or up to a step before it, B on `b` or up to a step after it."""
        self.assertTrue(a - 0.25 < game.a <= a + 0.003, f"A at {game.a}, wanted {a}")
        self.assertTrue(b - 0.003 <= game.b < b + 0.25, f"B at {game.b}, wanted {b}")

    def test_from_the_score_screen_to_the_spot(self):
        game = PracticeGame("score")
        s = spot(1, 19.661, 24.896)
        failed = self.mode(game).start("Kickstand", "Soundgarden", None, s)
        self.assertIsNone(failed)
        self.assertEqual(self.searched, [("list", "Kickstand")])
        self.assertEqual((game.screen, game.running_section), ("playing", 1))
        self.assertPlaced(game, 19.661, 24.896)                 # B past the end of the section (23.59)
        self.assertAlmostEqual(s["placed_a"], game.a, places=6)
        self.assertEqual((game.stray, game.speed_changes), ([], 0))
        self.assertEqual(game.resumed_at, [game.a])

    def test_section_further_down_scrolls_the_list(self):
        game = PracticeGame("list")
        self.assertIsNone(self.mode(game).start("x", "y", None, spot(11, 131.0, 140.0)))
        self.assertEqual(game.running_section, 11)
        self.assertPlaced(game, 131.0, 140.0)

    def test_last_section_without_a_known_end(self):
        game = PracticeGame("main")
        self.assertIsNone(self.mode(game).start("x", "y", None, spot(12, 143.0, 150.0)))
        self.assertTrue(143.0 - 0.25 < game.a <= 143.0)
        self.assertTrue(150.0 <= game.b < 151.25)               # from the shown seconds of B

    def test_next_spot_in_the_same_section(self):
        game = PracticeGame("main")
        mode = self.mode(game)
        first, second = spot(1, 14.0, 18.0), spot(1, 19.661, 22.5)
        self.assertIsNone(mode.start("x", "y", None, first))
        self.assertIsNone(mode.next(second, first))
        self.assertEqual(game.screen, "playing")
        self.assertPlaced(game, 19.661, 22.5)
        self.assertNotIn("S", game.keys)                  # no new section, no way back

    def test_next_spot_in_another_section(self):
        game = PracticeGame("main")
        mode = self.mode(game)
        first, second = spot(1, 19.661, 24.896), spot(4, 49.689, 54.971)
        self.assertIsNone(mode.start("x", "y", None, first))
        self.assertIsNone(mode.next(second, first))
        self.assertEqual(game.running_section, 4)
        self.assertPlaced(game, 49.689, 54.971)
        self.assertEqual(game.speed_changes, 0)

    def test_a_lost_seek_press_is_put_right_after_resume(self):
        game = PracticeGame("main")
        game.deaf["RIGHT"] = 1
        s = spot(1, 19.661, 22.0)
        self.assertIsNone(self.mode(game).start("x", "y", None, s))
        self.assertPlaced(game, 19.661, 22.0)
        self.assertEqual(len(game.resumed_at), 2)                # once more after putting it right
        self.assertTrue(any("A is -0.25 s off" in m for m in self.logged))

    def test_steps_a_little_longer_than_a_quarter(self):
        game = PracticeGame("main", seek_step=0.2509)
        self.assertIsNone(self.mode(game).start("x", "y", None, spot(3, 45.2, 46.9)))
        self.assertTrue(abs(game.a - 45.2) < 0.25)

    def test_nothing_while_a_song_runs(self):
        game = PracticeGame("playing")
        self.assertEqual(self.mode(game).start("x", "y", None, spot(1, 19.0, 24.0)), "a song is running")
        self.assertEqual(game.keys, [])

    def test_search_that_fails_stops_before_the_song(self):
        game = PracticeGame("main")
        failed = self.mode(game, found="the wanted chart is not among the songs of that name").start(
            "x", "y", None, spot(1, 19.0, 24.0))
        self.assertTrue(failed.startswith("song: "))
        self.assertEqual((game.screen, game.keys[-1]), ("list", "A"))     # the A that opened the list

    def test_a_missed_pause_key_is_pressed_again(self):
        game = PracticeGame("main")
        self.assertIsNone(self.mode(game).start("x", "y", None, spot(2, 26.0, 33.0)))
        game.deaf["ENTER"] = 1
        self.assertIsNone(self.mode(game).next(spot(5, 60.0, 64.0), spot(2, 26.0, 33.0)))
        self.assertEqual(game.running_section, 5)

    def test_pause_menu_left_open_is_taken_as_it_is(self):
        game = PracticeGame("main")
        mode = self.mode(game)
        first = spot(1, 19.661, 24.896)
        self.assertIsNone(mode.start("x", "y", None, first))
        game.screen = "paused"                                   # a step before stopped in the menu
        self.assertIsNone(mode.next(spot(2, 32.696, 37.872), first))
        self.assertEqual((game.screen, game.running_section), ("playing", 2))
        self.assertPlaced(game, 32.696, 37.872)

    def test_wrong_idea_of_the_running_section_is_put_right(self):
        # a step before stopped after choosing section 2, the tool still thinks 1 runs
        game = PracticeGame("main")
        mode = self.mode(game)
        self.assertIsNone(mode.start("x", "y", None, spot(2, 26.0, 30.0)))
        self.assertIsNone(mode.next(spot(4, 49.689, 54.971), spot(1, 19.661, 24.896)))
        self.assertEqual(game.running_section, 4)
        self.assertPlaced(game, 49.689, 54.971)
        self.assertTrue(any("section 5 runs, not 4" in m for m in self.logged))   # 3 down from 2

    def test_up_to_ten_sections_the_row_tells_which_runs(self):
        sections = SECTIONS[:8]
        game = PracticeGame("main", sections=sections)
        mode = self.mode(game)
        self.assertIsNone(mode.start("x", "y", None, spot(2, 26.0, 30.0, sections)))
        self.assertIsNone(mode.next(spot(5, 60.0, 64.0, sections), spot(1, 19.661, 24.896, sections)))
        self.assertEqual(game.running_section, 5)
        self.assertFalse(any("choosing again" in m for m in self.logged))

    def test_next_spot_in_the_same_section_starts_from_its_bounds(self):
        game = PracticeGame("main")
        game.deaf["RIGHT"] = 0
        mode = self.mode(game)
        first, second = spot(3, 37.0, 40.0), spot(3, 44.0, 46.0)
        self.assertIsNone(mode.start("x", "y", None, first))
        self.assertIsNone(mode.next(second, first))
        self.assertEqual(game.running_section, 3)
        self.assertPlaced(game, 44.0, 46.0)

    def test_quickplay_pause_menu_is_left_alone(self):
        game = PracticeGame("qplaying")
        failed = self.mode(game).next(spot(2, 26.0, 33.0), spot(1, 19.0, 24.0))
        self.assertEqual(failed, "this is not the practice mode")
        self.assertEqual(game.screen, "qplaying")                # paused and played on
        self.assertEqual(game.stray, [])

    def test_spot_after_the_old_b_moves_b_first(self):
        game = PracticeGame("main")
        mode = self.mode(game)
        # section 1 is 13.06 .. 23.59: A at 14..16 first, then a spot from 17 to 21
        # (A would have to pass the old B at 16 if it went first)
        first = spot(1, 14.0, 16.0)
        self.assertIsNone(mode.start("x", "y", None, first))
        self.assertIsNone(mode.next(spot(1, 17.0, 21.0), first))
        self.assertPlaced(game, 17.0, 21.0)

    def test_presses(self):
        mode = self.mode(PracticeGame())
        self.assertEqual(mode.presses("A", 19.661, 13.056), 26)  # 19.556: before the bar line
        self.assertEqual(mode.presses("B", 24.896, 23.587), 6)   # 25.087: after it
        self.assertEqual(mode.presses("A", 13.056, 13.056), 0)
        self.assertEqual(mode.presses("A", 15.556, 13.056), 10)  # on the dot (2 ms of slack)
        self.assertEqual(mode.presses("B", 20.0, 23.587), -14)


if __name__ == "__main__":
    unittest.main()
