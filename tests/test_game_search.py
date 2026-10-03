"""Tests for reading the screen (chkit.game.screen) and the song search built
on it (chkit.game.search). No game, no display, no evdev: a small stand-in for
Clone Hero draws its menus as pictures and reacts to the keys."""
import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from chkit.game import screen as cs  # noqa: E402
from chkit.game import search as ca  # noqa: E402

LIGHT, PANEL, WHITE, TAB_YELLOW = (208, 212, 214), (17, 17, 17), (255, 255, 255), (230, 170, 40)
FILTERS = ("Artist", "Album", "Charter", "Playlist", "Genre", "Source", "Song")
FILTER_WIDTH = {"Artist": 59, "Album": 67, "Charter": 79, "Playlist": 74, "Genre": 61, "Source": 70, "Song": 50}
SORTS = ("Song", "Artist", "Artist - Album", "Album")
CHAR_OF_KEY = {key: char for char, key in ca.QWERTZ.items()}


class Canvas:
    """Draws with the positions of a 1280x720 window into a picture of any size."""

    def __init__(self, width=640, height=360):
        self.w, self.h = width, height
        self.data = bytearray(bytes((27, 27, 27, 0)) * (width * height))

    def rect(self, x0, y0, x1, y1, rgb):
        px0, px1 = int(x0 * self.w / 1280), int(x1 * self.w / 1280)
        row = bytes((rgb[2], rgb[1], rgb[0], 0)) * (px1 - px0)
        for py in range(int(y0 * self.h / 720), int(y1 * self.h / 720)):
            o = (py * self.w + px0) * 4
            self.data[o:o + len(row)] = row

    def picture(self):
        return cs.Picture(self.w, self.h, bytes(self.data))


def draw(screen="list", menu=None, sort=None, dialog=None, row=(1, 1), names_behind=False, size=(640, 360)):
    """screen: list / title / main / setup / score; menu, sort: highlighted row; dialog: filter
    name; row: numbers standing for artist and name of the selected song."""
    c = Canvas(*size)
    if screen == "setup":
        c.rect(498, 268, 784, 306, LIGHT)
    if screen == "main":
        c.rect(24, 183, 342, 235, LIGHT)                   # QUICKPLAY
    if screen == "title":
        c.rect(539, 623, 551, 635, (69, 244, 0))           # Confirm
        c.rect(618, 623, 630, 635, (255, 0, 0))            # Back
    if screen != "list":
        return c.picture()
    c.rect(56, 33, 72, 49, (69, 244, 0))
    c.rect(205, 38, 221, 54, (255, 0, 0))
    c.rect(275, 41, 291, 57, (255, 161, 0))
    c.rect(41, 359, 908, 397, LIGHT)                       # the selected song
    c.rect(340 - 6 * row[0], 370, 360, 386, (60, 60, 60))    # its artist ...
    c.rect(380, 370, 400 + 6 * row[1], 386, (40, 40, 40))    # ... and name
    if names_behind:                                       # song names of the rows above, white on dark
        for y in (216, 257, 297):
            for x in range(380, 497, 14):                  # strokes of letters
                c.rect(x, y - 9, x + 6, y + 9, WHITE)
    for open_row, x0, x1 in ((menu, 500, 780), (sort, 374, 906)):
        if open_row is not None:
            c.rect(x0, 205, x1, 455, PANEL)
            y = 231 + 33.2 * open_row
            c.rect(x0, y - 16, x1, y + 16, LIGHT)
    if dialog is not None:
        c.rect(440, 270, 840, 390, (20, 20, 20))
        c.rect(549, 309, 578, 323, TAB_YELLOW)
        c.rect(540, 283, 680, 296, (209, 209, 209))        # "Searching for:"
        c.rect(690, 282, 690 + FILTER_WIDTH[dialog], 296, WHITE)
    return c.picture()


class ScreenTest(unittest.TestCase):
    def test_states_at_three_sizes(self):
        for size in ((640, 360), (1280, 720), (1920, 1080)):
            with self.subTest(size=size):
                self.assertEqual(cs.describe(draw(size=size)), "list")
                self.assertEqual(cs.describe(draw("main", size=size)), "main")
                self.assertEqual(cs.describe(draw("title", size=size)), "title")
                self.assertEqual(cs.describe(draw("score", size=size)), "other")
                self.assertEqual(cs.describe(draw("setup", size=size)), "setup")
                self.assertEqual(cs.describe(draw(menu=0, size=size)), "menu-0")
                self.assertEqual(cs.describe(draw(menu=1, size=size)), "menu-1")
                self.assertEqual(cs.describe(draw(menu=3, size=size)), "menu-3")
                self.assertEqual(cs.describe(draw(sort=0, size=size)), "sort-0")
                self.assertEqual(cs.describe(draw(sort=1, size=size)), "sort-1")
                self.assertEqual(cs.describe(draw(dialog="Song", size=size)), "dialog-song")
                for name in FILTERS[:-1]:
                    self.assertEqual(cs.describe(draw(dialog=name, size=size)), "dialog", name)
        self.assertEqual(cs.describe(None), "unreadable")

    def test_song_names_behind_the_menu_do_not_hide_it(self):
        self.assertEqual(cs.menu_row(draw(menu=1, names_behind=True)), 1)
        self.assertIsNone(cs.menu_row(draw(names_behind=True)))

    def test_the_bar_of_the_selected_song_is_no_menu(self):
        pic = draw()
        self.assertIsNone(cs.menu_row(pic))
        self.assertIsNone(cs.sort_row(pic))
        self.assertFalse(cs.setup_panel(draw("main")))
        self.assertFalse(cs.main_menu(pic))
        self.assertFalse(cs.main_menu(draw("setup")))

    def test_black_picture(self):
        self.assertTrue(cs.Picture(64, 36, bytes(64 * 36 * 4)).black())
        self.assertFalse(draw().black())
        self.assertFalse(draw("main").black())             # dark grey, not black

    def test_selected_row_tells_songs_apart(self):
        self.assertEqual(cs.selected_row(draw(row=(2, 5))), cs.selected_row(draw(row=(2, 5))))
        a, b = cs.selected_row(draw(row=(2, 5))), cs.selected_row(draw(row=(2, 6)))
        self.assertEqual(a[0], b[0])
        self.assertNotEqual(a[1], b[1])
        self.assertNotEqual(cs.selected_row(draw(row=(3, 5)))[0], a[0])
        self.assertIsNone(cs.selected_row(draw("main")))


def song(artist, name, chart="a", preview=None):
    return {"artist": artist, "name": name, "md5": hashlib.md5(f"{artist}{name}{chart}".encode()).hexdigest(),
            "preview": preview}


LIBRARY = [
    song("AC/DC", "Thunderstruck", preview=61.5),
    song("All Time Low", "Paint You Wings", preview=38.0),
    song("Creo", "Dimension", preview=52.0),
    song("Jimmy Eat World", "Pain", preview=30.0),
    song("Metallica", "For Whom The Bell Tolls", chart="youngblood", preview=229.231),
    song("Metallica", "For Whom The Bell Tolls", chart="neversoft"),
    song("Metallica", "Orion"),
    song("Wolfmother", "Dimension", chart="neversoft"),
    song("Wolfmother", "Pilgrim", chart="harmonix", preview=123.53),
    song("Wolfmother", "Pilgrim", chart="neversoft"),
]


class Game:
    """Clone Hero as far as the search sees it: menus, keys, the sorted list."""

    def __init__(self, songs=LIBRARY, screen="list", sort="Artist"):
        self.songs = list(songs)
        self.screen, self.sort = screen, sort
        self.menu = self.sort_list = self.dialog = None      # row, row, filter index
        self.text = ""
        self.cursor = self.order()[0]
        self.running = False
        self.keys = []                  # every key that arrived
        self.strays = []                # letters that arrived outside the search dialog
        self.deaf = {}                  # key -> how many presses the game misses
        self.dead = set()               # keys the game never reacts to
        self.rested = []                # songs the cursor came to rest on

    def order(self):
        if self.sort == "Song":
            return sorted(self.songs, key=lambda s: (s["name"].casefold(), s["artist"].casefold()))
        return sorted(self.songs, key=lambda s: (s["artist"].casefold(), s["name"].casefold()))

    def picture(self):
        if self.screen != "list":
            return draw(self.screen)
        artists = sorted({s["artist"] for s in self.songs})
        names = sorted({s["name"] for s in self.songs})
        return draw(menu=self.menu, sort=self.sort_list,
                    dialog=None if self.dialog is None else FILTERS[self.dialog],
                    row=(artists.index(self.cursor["artist"]), names.index(self.cursor["name"])))

    def move(self, to):
        if to is not self.cursor:
            self.cursor = to
            self.rested.append(to)

    def press(self, key):
        self.keys.append(key)
        if key in self.dead:
            return
        if self.deaf.get(key):
            self.deaf[key] -= 1
            return
        if self.dialog is not None:
            self.in_dialog(key)
        elif self.screen in ("main", "score"):
            if key == "A":
                self.screen = "list"
        elif self.screen == "setup":
            if key == "A":
                self.running = True
            elif key == "S":
                self.screen = "list"
        elif self.sort_list is not None:
            if key in ("UP", "DOWN"):
                self.sort_list = max(0, min(len(SORTS) - 1, self.sort_list + (1 if key == "DOWN" else -1)))
            elif key == "A":
                self.sort, self.sort_list = SORTS[self.sort_list], None
            elif key == "S":
                self.sort_list = None
        elif self.menu is not None:
            if key in ("UP", "DOWN"):
                self.menu = max(0, min(6, self.menu + (1 if key == "DOWN" else -1)))
            elif key in ("L", "S"):
                self.menu = None
            elif key == "A":
                row, self.menu = self.menu, None
                if row == 1:
                    self.dialog = FILTERS.index("Song" if self.sort == "Song" else "Artist")
                    self.text = ""
                elif row == 3:
                    self.sort_list = SORTS.index(self.sort)
        else:
            order = self.order()
            at = order.index(self.cursor)
            if key == "L":
                self.menu = 0
            elif key == "A":
                self.screen = "setup"
            elif key == "S":
                self.screen = "main"
            elif key in ("UP", "DOWN"):
                self.move(order[max(0, min(len(order) - 1, at + (1 if key == "DOWN" else -1)))])
            elif len(key) == 1 or key == "SPACE":
                self.strays.append(key)

    def in_dialog(self, key):
        if key == "TAB":
            self.dialog = (self.dialog + 1) % len(FILTERS)
        elif key in ("ENTER", "ESC"):
            self.dialog = None
        elif (key, False) in CHAR_OF_KEY:
            self.text += CHAR_OF_KEY[(key, False)]
            field = {"Song": "name", "Artist": "artist"}.get(FILTERS[self.dialog])
            hit = next((s for s in self.order() if field and s[field].casefold().startswith(self.text)), None)
            if hit:
                self.move(hit)


class Clock:
    def __init__(self):
        self.t = 100.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(seconds, 0.001)


class Keys:
    def __init__(self, game):
        self.game = game

    def press(self, name, shift=False, hold=0.03):
        self.game.press(name)

    def type(self, text, pause=0.04):
        for char in text:
            self.press(*ca.QWERTZ[char])


class Told:
    """What the game gives away about the song under the cursor (see ca.Selection)."""

    def __init__(self, game, md5=True):
        self.game, self.md5 = game, md5

    def mark(self):
        pass

    def rest(self):
        pass

    def read(self):
        s = self.game.cursor
        return {"md5": s["md5"] if self.md5 else None, "preview": s["preview"]}


class SearchBase(unittest.TestCase):
    def search(self, game, told=True, **kw):
        clock = self.clock = Clock()
        self.logged = []
        return ca.SongSearch(Keys(game), game.picture, lambda: game.running,
                             Told(game, **kw) if told else None,
                             sleep=clock.sleep, now=clock.now, log=self.logged.append)

    def find(self, game, artist, name, chart="a", **kw):
        want = next(s for s in game.songs if (s["artist"], s["name"]) == (artist, name)
                    and s["md5"] == song(artist, name, chart)["md5"])
        return self.search(game, **kw).run(name, artist, {"md5": want["md5"], "preview": want["preview"]}), want


class SearchTest(SearchBase):
    def test_from_the_song_list(self):
        game = Game()
        failed, want = self.find(game, "AC/DC", "Thunderstruck")
        self.assertIsNone(failed)
        self.assertIs(game.cursor, want)
        self.assertEqual(game.keys[:3], ["L", "DOWN", "A"])
        self.assertEqual(game.keys.count("TAB"), 6)             # Artist ... Song
        self.assertEqual(game.keys[-1], "ENTER")
        self.assertEqual((game.strays, game.screen, game.sort, game.running), ([], "list", "Artist", False))

    def test_from_the_main_menu_a_comes_first(self):
        game = Game(screen="main")
        failed, want = self.find(game, "AC/DC", "Thunderstruck")
        self.assertIsNone(failed)
        self.assertEqual(game.keys[:4], ["A", "L", "DOWN", "A"])
        self.assertIs(game.cursor, want)

    def test_from_the_score_screen_a_comes_first(self):
        game = Game(screen="score")
        failed, want = self.find(game, "AC/DC", "Thunderstruck")
        self.assertIsNone(failed)
        self.assertEqual(game.keys[:4], ["A", "L", "DOWN", "A"])
        self.assertIs(game.cursor, want)

    def test_nothing_while_a_song_runs(self):
        game = Game()
        game.running = True
        failed, _ = self.find(game, "AC/DC", "Thunderstruck")
        self.assertEqual((failed, game.keys), ("a song is running", []))

    def test_the_setup_panel_is_left_alone(self):
        game = Game(screen="setup")
        failed, _ = self.find(game, "AC/DC", "Thunderstruck")
        self.assertIn("setup panel", failed)
        self.assertEqual((game.keys, game.running), ([], False))

    def test_a_missed_key_is_pressed_again(self):
        game = Game()
        game.deaf = {"L": 1, "DOWN": 1, "TAB": 2}
        failed, want = self.find(game, "AC/DC", "Thunderstruck")
        self.assertIsNone(failed)
        self.assertIs(game.cursor, want)
        self.assertEqual(game.strays, [])

    def test_no_letters_when_the_menu_does_not_open(self):
        game = Game()
        game.dead = {"L"}
        failed, _ = self.find(game, "AC/DC", "Thunderstruck")
        self.assertEqual(failed, "the Actions menu did not open")
        self.assertEqual(set(game.keys), {"L"})

    def test_no_letters_when_the_dialog_does_not_open(self):
        game = Game()
        game.dead = {"A"}
        failed, _ = self.find(game, "AC/DC", "Thunderstruck")
        self.assertEqual(failed, "the search dialog did not open")
        self.assertEqual((game.strays, set(game.keys)), ([], {"L", "DOWN", "A"}))

    def test_without_the_song_filter_nothing_is_typed(self):
        game = Game()
        game.dead = {"TAB"}
        failed, _ = self.find(game, "AC/DC", "Thunderstruck")
        self.assertEqual(failed, "the search filter 'Song' was not found")
        self.assertEqual((game.strays, game.dialog, game.keys[-1]), ([], None, "ESC"))

    def test_menu_or_dialog_left_open(self):
        game = Game()
        game.menu = 0
        failed, want = self.find(game, "AC/DC", "Thunderstruck")
        self.assertIsNone(failed)
        self.assertEqual(game.keys[:2], ["DOWN", "A"])
        game = Game()
        game.dialog, game.text = 3, "xyz"
        failed, want = self.find(game, "AC/DC", "Thunderstruck")
        self.assertIsNone(failed)
        self.assertEqual(game.keys[0], "ESC")
        self.assertIs(game.cursor, want)

    def test_list_sorted_by_song_needs_no_tab(self):
        game = Game(sort="Song")
        failed, want = self.find(game, "AC/DC", "Thunderstruck")
        self.assertIsNone(failed)
        self.assertNotIn("TAB", game.keys)
        self.assertIs(game.cursor, want)

    def test_other_chart_of_the_song_is_below(self):
        game = Game()
        failed, want = self.find(game, "Wolfmother", "Pilgrim", "neversoft")
        self.assertIsNone(failed)
        self.assertIs(game.cursor, want)
        self.assertEqual(game.sort, "Artist")
        self.assertEqual(self.logged, ["the wanted chart is 1 below the first hit"])

    def test_song_of_another_artist_comes_first(self):
        game = Game()
        failed, want = self.find(game, "Wolfmother", "Dimension", "neversoft")
        self.assertIsNone(failed)
        self.assertIs(game.cursor, want)
        self.assertEqual((game.sort, game.sort_list, game.menu, game.dialog), ("Artist", None, None, None))
        self.assertEqual(self.logged, ["list sorted by song", "found as number 2 of that name"])
        self.assertEqual(game.strays, [])

    def test_name_that_is_the_start_of_another(self):
        game = Game()                                           # "pain" also starts "Paint You Wings"
        failed, want = self.find(game, "Jimmy Eat World", "Pain")
        self.assertIsNone(failed)
        self.assertIs(game.cursor, want)
        self.assertEqual(game.sort, "Artist")

    def test_chart_that_is_not_there(self):
        game = Game()
        search = self.search(game)
        failed = search.run("Dimension", "Wolfmother", {"md5": "0" * 32, "preview": None})
        self.assertEqual(failed, "the wanted chart is not among the songs of that name; the cursor is at the artist")
        self.assertEqual((game.sort, game.cursor["artist"], game.strays), ("Artist", "Wolfmother", []))

    def test_without_knowing_the_chart_the_first_hit_stays(self):
        game = Game()
        self.assertIsNone(self.search(game).run("Dimension", "Wolfmother", None))
        self.assertEqual(game.cursor["artist"], "Creo")
        game = Game()
        self.assertIsNone(self.search(game, told=False).run("Dimension", "Wolfmother", {"md5": "0" * 32}))
        self.assertEqual(game.cursor["artist"], "Creo")

    def test_game_that_tells_nothing_keeps_the_first_hit(self):
        game = Game()                                           # offline: no md5, and no preview start known
        failed, _ = self.find(game, "Wolfmother", "Dimension", "neversoft", md5=False)
        self.assertIsNone(failed)
        self.assertEqual(game.cursor["artist"], "Creo")
        self.assertEqual(self.logged, ["hit not checked: the game did not tell which chart it is"])

    def test_preview_start_alone_can_tell(self):
        game = Game()
        failed, want = self.find(game, "Wolfmother", "Pilgrim", "harmonix", md5=False)
        self.assertIsNone(failed)
        self.assertIs(game.cursor, want)
        game = Game()                                           # "pain" first finds "Paint You Wings"
        failed, want = self.find(game, "Jimmy Eat World", "Pain", md5=False)
        self.assertIsNone(failed)
        self.assertIs(game.cursor, want)
        self.assertEqual(self.logged, ["list sorted by song", "found as number 1 of that name"])

    def test_nothing_to_type(self):
        game = Game()
        self.assertEqual(self.search(game).run("¿?", "X", None), "nothing to type for '¿?'")
        self.assertEqual(game.keys, [])


class ArtistSearchTest(SearchBase):
    """run_artist(): only the artist is known (CloneSmith sends no song name)."""

    def test_cursor_on_the_first_song_of_the_artist(self):
        game = Game()
        failed = self.search(game).run_artist("Wolfmother")
        self.assertIsNone(failed)
        self.assertEqual(game.cursor["artist"], "Wolfmother")
        self.assertEqual(game.keys.count("TAB"), 7)             # Artist ... Song, then on to Artist
        self.assertEqual((game.strays, game.screen, game.running), ([], "list", False))

    def test_from_the_main_menu_and_never_during_a_song(self):
        game = Game()
        game.screen = "main"
        self.assertIsNone(self.search(game).run_artist("AC/DC"))
        self.assertEqual(game.keys[0], "A")
        game = Game()
        game.running = True
        self.assertEqual(self.search(game).run_artist("AC/DC"), "a song is running")
        self.assertEqual(game.keys, [])

    def test_nothing_to_type(self):
        self.assertEqual(self.search(Game()).run_artist("¿?"), "nothing to type for '¿?'")


class BlindTest(unittest.TestCase):
    """Without a readable game window nothing is typed unless the caller asks."""

    def test_unreadable_window_types_nothing_by_default(self):
        typed, logged = [], []
        old_window, old_type, old_running = ca.ch_screen.GameWindow, ca.type_in_search, ca.song_running

        class NoWindow:
            def grab(self):
                return None
        ca.ch_screen.GameWindow, ca.type_in_search, ca.song_running = NoWindow, typed.append, lambda: False
        try:
            self.assertEqual(ca.find_song({"artist": "A", "name": "B"}, logged.append), "cannot see the game window")
            self.assertEqual(ca.find_artist("A", logged.append), "cannot see the game window")
            self.assertEqual(typed, [])
            self.assertIsNone(ca.find_song({"artist": "A", "name": "B"}, logged.append, blind=True))
            self.assertEqual(typed, ["A - B"])
        finally:
            ca.ch_screen.GameWindow, ca.type_in_search, ca.song_running = old_window, old_type, old_running


class TypingTest(unittest.TestCase):
    def test_typeable(self):
        self.assertEqual(ca.typeable("Joker & the Thief"), "joker & the thief")
        self.assertEqual(ca.typeable("Señorita"), "se")                  # cut before the first unknown character
        self.assertEqual(ca.typeable("  T.N.T. "), "t.n.t.")
        self.assertEqual(ca.typeable(""), "")

    @unittest.skipIf(ca.ecodes is None, "needs evdev (key names)")
    def test_german_layout(self):
        self.assertEqual(ca.QWERTZ["y"], ("Z", False))
        self.assertEqual(ca.QWERTZ["z"], ("Y", False))
        self.assertEqual(ca.QWERTZ["'"], ("BACKSLASH", True))
        self.assertEqual(ca.QWERTZ["&"], ("6", True))
        self.assertEqual(ca.QWERTZ["-"], ("SLASH", False))
        for char, (key, _) in ca.QWERTZ.items():
            self.assertTrue(hasattr(ca.ecodes, f"KEY_{key}"), char)


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = os.path.join(self.tmp, "LeaderboardCache")
        os.mkdir(self.cache)
        self.log = os.path.join(self.tmp, "Player.log")
        with open(self.log, "w") as fh:
            fh.write("Seeking to song time:11\n")
        self.clock = Clock()
        self.sel = ca.Selection(self.cache, self.log, sleep=self.clock.sleep, now=self.clock.now,
                                clock=self.clock.now)

    def cache_file(self, md5, when):
        path = os.path.join(self.cache, md5.upper() + "f" * 64 + ".cache.json")
        with open(path, "w") as fh:
            fh.write("{}")
        os.utime(path, (when, when))

    def test_md5_of_the_newest_cache_file_and_preview_from_the_log(self):
        self.cache_file("a" * 32, self.clock.t - 60)                     # older than the mark
        self.sel.mark()
        self.cache_file("b" * 32, self.clock.t + 0.7)
        with open(self.log, "a") as fh:
            fh.write("SongHash: xyz\nSeeking to song time:67.3167083333333\nSeeking to song")   # last line unfinished
        self.assertEqual(self.sel.read(), {"md5": "b" * 32, "preview": 67.3167083333333})

    def test_nothing_told(self):
        self.sel.mark()
        start = self.clock.t
        self.assertEqual(self.sel.read(), {"md5": None, "preview": None})
        self.assertGreaterEqual(self.clock.t - start, ca.Selection.LIMIT)

    def test_file_from_while_typing_counts_after_a_moment(self):
        self.sel.mark()
        self.cache_file("c" * 32, self.clock.t + 0.1)
        self.clock.sleep(1.5)                                            # typing
        self.sel.rest()
        start = self.clock.t
        self.assertEqual(self.sel.read()["md5"], "c" * 32)
        self.assertLess(self.clock.t - start, ca.Selection.LIMIT)

    def test_missing_folder_and_log(self):
        sel = ca.Selection(self.cache + "-none", self.log + "-none", sleep=self.clock.sleep,
                           now=self.clock.now, clock=self.clock.now)
        sel.mark()
        self.assertEqual(sel.read(), {"md5": None, "preview": None})


class WantedTest(unittest.TestCase):
    def test_from_the_song_folder(self):
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "notes.mid"), "wb") as fh:
            fh.write(b"chart")
        with open(os.path.join(folder, "Song.ini"), "w") as fh:
            fh.write("[song]\nname = X\npreview_start_time = 38000\n")
        self.assertEqual(ca.wanted({"path": folder}),
                         {"md5": hashlib.md5(b"chart").hexdigest(), "preview": 38.0})
        self.assertEqual(ca.wanted({"path": folder, "md5": "ABC"})["md5"], "abc")     # the playlist knows it

    def test_no_preview_start(self):
        folder = tempfile.mkdtemp()
        for text in ("[song]\nname = X\n", "[song]\npreview_start_time = -1\n", "[song]\npreview_start_time = x\n"):
            with open(os.path.join(folder, "song.ini"), "w") as fh:
                fh.write(text)
            self.assertEqual(ca.wanted({"path": folder, "md5": "ab"}), {"md5": "ab", "preview": None})

    def test_nothing_known(self):
        self.assertIsNone(ca.wanted({"artist": "A", "name": "B"}))
        self.assertIsNone(ca.wanted({"path": "/nonexistent/song"}))


if __name__ == "__main__":
    unittest.main()
