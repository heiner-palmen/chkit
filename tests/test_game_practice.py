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


# 8 and 9 have not been seen in the game yet: made-up pictures, for the tests only
MADE_UP = {"8": "0000000007e00e701c181818181818300ff00ff01818300c300c300c300c18180ff003e00000",
           "9": "0000000007e00e701818300c300c300c381c1ffc0fdc001c003800700060038007000e000000"}


def setUpModule():
    for d, code in MADE_UP.items():
        cs._TEMPLATES.setdefault(d, cs._template(code))


def tearDownModule():
    for d in MADE_UP:
        if d not in cs.DIGITS:
            cs._TEMPLATES.pop(d, None)


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
            c.rect(x0 + 3, y0 + y - cs.AB_ROWS["A"] + 2, x1 - 3, y1 + y - cs.AB_ROWS["A"] - 2, WHITE)
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
        self.assertIsNone(cs.ab_time(quickplay, "A"))
        self.assertEqual(cs.describe(draw_paused(2, 1, 2)), "paused-2")

    def test_every_known_digit_is_read(self):
        for seconds in (0, 1, 22, 33, 44, 55, 66 * 60 + 7, 3600 + 17 * 60 + 4):
            with self.subTest(seconds=seconds):
                self.assertEqual(cs.ab_time(draw_paused(0, seconds, 0), "A"), seconds)


SECTIONS = [0.0, 13.06, 23.59, 36.57, 47.06, 57.59, 70.5, 81.0, 95.2, 104.0, 118.5, 130.0, 141.3]
SONG_END = 160.0


class PracticeGame:
    """The practice mode as far as the driver sees it."""

    def __init__(self, screen="score", sections=SECTIONS, seek_step=0.1, new_section_at_current=True):
        self.screen = screen
        self.sections = sections
        self.main = 0
        self.top = self.cursor = 0
        self.running_section = None
        self.row = 0
        self.a = self.b = None
        self.seek_step = seek_step
        self.new_section_at_current = new_section_at_current
        self.keys = []
        self.speed_changes = 0
        self.stray = []
        self.loading = 0               # pictures until the list of sections is up
        self.deaf = {}
        self.drawn = {}

    def bounds(self, k):
        return self.sections[k], self.sections[k + 1] if k + 1 < len(self.sections) else SONG_END

    def running(self):
        return self.screen in ("loading", "sections", "playing", "paused")

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
                self.cursor = max(0, min(len(self.sections) - 1, self.cursor + (1 if key == "DOWN" else -1)))
                self.top = min(max(self.top, self.cursor - 9), self.cursor)
            elif key == "A":
                self.running_section = self.cursor
                self.a, self.b = self.bounds(self.cursor)
                self.screen = "playing"
            else:
                self.stray.append((s, key))
        elif s == "playing":
            if key == "ESC":
                self.screen, self.row = "paused", 0
            elif key in ("UP", "DOWN"):
                self.speed_changes += 1
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
            elif key == "A" and self.row == cs.NEW_SECTION:
                self.screen = "sections"
                self.cursor = self.running_section if self.new_section_at_current else 0
                self.top = max(0, self.cursor - 9)
            elif key == "ESC":
                self.screen = "playing"
            else:
                self.stray.append((s, key))


class Keys:
    def __init__(self, game):
        self.game = game

    def press(self, name, shift=False, hold=0.03):
        self.game.press(name)


def spot(section, a, b, sections=SECTIONS):
    end = sections[section + 1] if section + 1 < len(sections) else None
    return {"section": section, "section_start": sections[section], "section_end": end, "a": a, "b": b}


class PracticeTest(unittest.TestCase):
    def mode(self, game, found=None, step=None):
        clock = self.clock = Clock()
        self.logged = []
        search = ca.SongSearch(Keys(game), game.picture, game.running, None, sleep=clock.sleep, now=clock.now,
                               log=self.logged.append)
        searched = self.searched = []

        def run(name, artist=None, wanted=None):        # the song search has its own tests
            searched.append((game.screen, name))
            return found
        search.run = run
        mode = cp.PracticeMode(Keys(game), game.picture, game.running, search, sleep=clock.sleep,
                               now=clock.now, log=self.logged.append)
        mode.SEEK_STEP_S = step
        return mode

    def test_from_the_score_screen_to_the_spot(self):
        game = PracticeGame("score")
        failed = self.mode(game).start("Kickstand", "Soundgarden", None, spot(1, 19.661, 24.896))
        self.assertIsNone(failed)
        self.assertEqual(self.searched, [("list", "Kickstand")])
        self.assertEqual((game.screen, game.running_section), ("playing", 1))
        self.assertEqual((math.floor(game.a), math.floor(game.b)), (19, 24))
        self.assertEqual((game.stray, game.speed_changes), ([], 0))

    def test_exact_steps_when_the_seek_step_is_known(self):
        game = PracticeGame("main")
        self.assertIsNone(self.mode(game, step=0.1).start("x", "y", None, spot(1, 19.661, 24.896)))
        self.assertAlmostEqual(game.a, 19.661, delta=0.051)        # within half a step
        self.assertAlmostEqual(game.b, 24.896, delta=0.051)

    def test_section_further_down_scrolls_the_list(self):
        game = PracticeGame("list")
        self.assertIsNone(self.mode(game).start("x", "y", None, spot(11, 131.0, 140.0)))
        self.assertEqual((game.running_section, math.floor(game.a), math.floor(game.b)), (11, 131, 140))

    def test_next_spot_in_the_same_section(self):
        game = PracticeGame("main")
        mode = self.mode(game, step=0.1)
        first, second = spot(1, 14.0, 18.0), spot(1, 19.661, 22.5)
        self.assertIsNone(mode.start("x", "y", None, first))
        self.assertIsNone(mode.next(second, first))
        self.assertEqual(game.screen, "playing")
        self.assertAlmostEqual(game.a, 19.661, delta=0.051)
        self.assertAlmostEqual(game.b, 22.5, delta=0.051)
        self.assertNotIn("S", game.keys)                  # no new section, no way back

    def test_next_spot_in_another_section(self):
        for at_current in (True, False):
            with self.subTest(at_current=at_current):
                game = PracticeGame("main", new_section_at_current=at_current)
                mode = self.mode(game)
                first, second = spot(1, 19.661, 24.896), spot(4, 49.689, 54.971)
                self.assertIsNone(mode.start("x", "y", None, first))
                failed = mode.next(second, first)
                if at_current:
                    self.assertIsNone(failed)
                    self.assertEqual((game.running_section, math.floor(game.a), math.floor(game.b)), (4, 49, 54))
                else:
                    # the list opened at the top: the wrong section runs, A says so
                    self.assertIn("another section", failed)
                self.assertEqual(game.speed_changes, 0)

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
        game.deaf["ESC"] = 1
        self.assertIsNone(self.mode(game).start("x", "y", None, spot(2, 26.0, 33.0)))
        self.assertEqual(game.keys.count("ESC"), 2)

    def test_spot_after_the_old_b_moves_b_first(self):
        game = PracticeGame("main", seek_step=0.1)
        mode = self.mode(game, step=0.1)
        # section 1 is 13.06 .. 23.59: a spot from 20 to 30 needs B past the old B
        # first, else A would have to pass it
        self.assertIsNone(mode.start("x", "y", None, spot(1, 14.0, 16.0)))
        self.assertIsNone(mode.next(spot(1, 17.0, 21.0), spot(1, 14.0, 16.0)))
        self.assertAlmostEqual(game.a, 17.0, delta=0.051)
        self.assertAlmostEqual(game.b, 21.0, delta=0.051)


if __name__ == "__main__":
    unittest.main()
