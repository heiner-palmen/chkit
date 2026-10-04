"""
Reads the Clone Hero window and tells which part of the song menu it shows, so
the tools only type where the keys mean what they should (chkit.game.search).
Linux, X11 (also Xwayland); libX11 through ctypes, no extra packages.

  GameWindow().grab()      Picture of the game window, or None (no window, no X11, all black)
  title_screen(pic)        the game has started and waits for a player to join
  main_menu(pic)           the main menu is up, QUICKPLAY highlighted
  in_song_list(pic)        the song list is up (legend "Select / Back / Actions Menu")
  setup_panel(pic)         the panel after choosing a song is up ("Ready": green starts the song)
  selected_row(pic)        artist and name of the selected row as pictures, to compare rows
  menu_row(pic)            highlighted row of the Actions menu (0 = Song Options, 1 = Search), or None
  sort_row(pic)            highlighted row of the Sort List (0 = Song, 1 = Artist), or None
  dialog_open(pic)         the search dialog is open
  filter_is_song(pic)      the search dialog says "Searching for: Song"
  main_row(pic)            highlighted row of the main menu (PRACTICE_ROW = Practice), or None
  section_list(pic)        practice mode: the list of sections is up
  section_row(pic)         its highlighted row as it stands on the screen (0 = top), or None
  pause_menu(pic)          the pause menu is up (Quickplay or practice)
  pause_row(pic)           its highlighted row (RESUME, RESTART_SECTION, SET_A, SET_B, ...), or None
  ab_shown(pic)            the pause menu is the practice mode's (it shows A and B)
  ab_time(pic, "A")        the time of A (or "B") in whole seconds, or None
  describe(pic)            all of it in one word, for logs

Clone Hero has no interface for this, so it is read off the picture: a few
fixed spots, given for a 1280x720 window and scaled to the real size. Checked
with v1.1.0.6142 at 1280x720.

  python3 -m chkit.game.screen            what the window shows right now, with the measured values
  python3 -m chkit.game.screen --watch    print every change (for watching the timing of keys)
"""
import ctypes
import ctypes.util
import os
import subprocess
import sys
import time

REF_W, REF_H = 1280, 720
# a grab after this long without one is preceded by STALE_READS that are thrown away
STALE_AFTER_S, STALE_READS = 0.2, 4

# Title screen: green and red square of the legend at the bottom.
TITLE_LEGEND = (("green", 545, 629), ("red", 624, 629))
# Main menu: the highlighted bar of QUICKPLAY (right of its text) and spots around it.
MAIN_LIGHT = ((240, 205), (290, 207), (330, 212))
MAIN_DARK = ((12, 205), (290, 250), (290, 170), (355, 210))
# Legend at the top left of the song list: green, red and orange dot.
LEGEND = (("green", 64, 41), ("red", 213, 46), ("orange", 283, 49))
# Actions menu: its rows are centred at these heights; the highlight of a row
# spans x 500..780 and is looked at MENU_MARGIN above and below the centre
# (free of the row's text), inside the menu and on both sides of it.
MENU_ROWS = (231, 264, 297, 331)           # Song Options, Search, Show Scoring Info, Sort List
MENU_MARGIN = 12
MENU_INSIDE = tuple(range(505, 776, 10))
MENU_OUTSIDE = (tuple(range(445, 496, 5)), tuple(range(785, 836, 5)))
SEARCH_ROW, SORT_LIST_ROW = 1, 3
# Sort List (Actions menu -> Sort List): same rows, wider (x 374..906).
SORT_INSIDE = tuple(range(385, 896, 15))
SORT_OUTSIDE = (tuple(range(340, 369, 4)),)
SORT_SONG, SORT_ARTIST = 0, 1              # then Artist - Album, Album, ...
# Song setup panel after choosing a song: same column as the Actions menu, its
# highlighted row is looked for in these heights (from, to, step).
PANEL_ROWS = (240, 570, 5)
# Selected row of the song list: a light bar, artist right-aligned, then the name.
BAR_Y, BAR_ENDS = 377, (48, 370, 800)
ARTIST_BOX = (60, 362, 366, 394)
NAME_BOX = (376, 362, 790, 394)
# Search dialog: the yellow word TAB in "PRESS TAB TO CHANGE SEARCH FILTER" ...
TAB_BOX = (540, 304, 590, 328)
TAB_SHARE = 0.015                          # measured 0.032
# ... and the bold filter name in "Searching for: Song". "Song" is the shortest
# of the seven names: 50 px, the next one ("Artist") has 59.
# The name is pure white, "Searching for:" in front of it is grey (209).
TITLE_BOX = (445, 279, 835, 300)
BOLD_WHITE = 232
SONG_WIDTH = (40, 54.5)
# Main menu: seven rows (QUICKPLAY, VERSUS, ONLINE, PRACTICE, NEWS, SETTINGS,
# QUIT); the highlighted one is a light bar, looked at right of the longest
# text. Legend at the bottom: "Confirm / Back / (Hold) Enter Leaderboards Mode".
MAIN_LEGEND = (("green", 459, 629), ("red", 538, 629))
MAIN_ROWS = (207, 263, 319, 375, 431, 487, 543)
MAIN_ROW_XS = tuple(range(232, 336, 6))
MAIN_ROW_MARGIN = 12
PRACTICE_ROW = 3
# Practice mode, the list of sections ("SECTION", legend "Select / Back" on
# top of it, rows from y 247 on, 36.4 apart). A highlighted row is light above
# and below its text, ROW_LINES from its centre.
SECTION_LEGEND = (("green", 196, 226), ("red", 277, 226))
SECTION_ROWS = tuple(262.5 + 36.4 * i for i in range(10))
SECTION_XS = tuple(range(45, 466, 10))
ROW_LINES = (-11, 13)
# Practice mode, the pause menu ("PAUSED", rows from y 246 on, 36 apart). On
# SET A / SET B POSITION the legend gets "<-> Seek" and moves to the left.
PAUSE_LEGENDS = ((("green", 1032, 226), ("red", 1113, 226)), (("green", 996, 226), ("red", 1077, 226)))
PAUSE_ROWS = tuple(262 + 36 * i for i in range(10))
PAUSE_XS = tuple(range(956, 1226, 10))
(RESUME, RESTART_SECTION, SET_A, SET_B, CLEAR_AB, NEW_SECTION,
 PAUSE_QUICKPLAY, PAUSE_NEW_SONG, PAUSE_OPTIONS, PAUSE_QUIT) = range(10)
# The times of A and B left of the pause menu ("A: 00:01:56"): six digits in
# fixed cells, white on dark. A digit is told by its picture (DIGITS: 19 rows
# of 15 dots, each row 4 hex digits, cut from the game), a dot or two of shift
# allowed.
AB_ROWS = {"A": 326, "B": 362}
AB_CELLS = (849, 863, 883, 897, 917, 931)
AB_LETTER = (821, 328, 836, 344)           # the "A" / "B" in front
AB_LETTER_SHARE = (0.12, 0.5)
DIGIT_W, DIGIT_H, DIGIT_SHIFT, DIGIT_MISS, DIGIT_SURE = 15, 19, 2, 24, 6
DIGIT_MAYBE, DIGIT_MARGIN = 45, 10
DIGITS = {
    "0": "0000000007e00e701c18181c180c380c300c300c300c300c300c380c180c18180c380ff003e0",
    "1": "0000000001c003c007c00ec018c000c000c000c000c000c000c000c000c000c000c00ff80ff8",
    "2": "000003e00ff01c38181818180018001800380030006000c00180030006000c001ff83ffc0000",
    "3": "0000000007e00e701838181810180018003001e001f00038001800183018381818381ff007c0",
    "4": "00000000006000e001e001a0032006200e200c201820302070207ffc00300020002000200020",
    "5": "000000000ff80ff00c000c000c0008001fe01ff000380018001800180018003818701fe00fc0",
    "6": "0000000000e001c001800380070006000dc01ff01c3838183018301c3018181818380ff007c0",
    "7": "00003ffc3ffc00180018003000300060006000c000c00180018003000300060006000c000000",
    "8": "000000000fe01c7018381818181818181c3007e00ff01c3838183018301c381818381ff007e0",
    "9": "000000000fe01e701838301830183018381818381ff007f0006000c001c00380030007000e00",
}


class Picture:
    """One frame of the window: 32 bit BGRX rows as XGetImage delivers them."""

    def __init__(self, width, height, data, stride=None):
        self.width, self.height, self.data = width, height, data
        self.stride = stride or width * 4

    def rgb(self, x, y):
        """Pixel at the reference position (x, y of a 1280x720 window)."""
        px = min(self.width - 1, max(0, int(x * self.width / REF_W)))
        py = min(self.height - 1, max(0, int(y * self.height / REF_H)))
        o = py * self.stride + px * 4
        return self.data[o + 2], self.data[o + 1], self.data[o]

    def real(self, x0, y0, x1, y1):
        """A reference box in real pixels (x range, y range)."""
        return (range(int(x0 * self.width / REF_W), int(x1 * self.width / REF_W)),
                range(int(y0 * self.height / REF_H), int(y1 * self.height / REF_H)))

    def at(self, px, py):
        o = py * self.stride + px * 4
        return self.data[o + 2], self.data[o + 1], self.data[o]

    def black(self):
        """Nothing but black: a window that cannot be read (some Wayland
        sessions hand out black for it) or a loading screen."""
        return all(max(self.rgb(x, y)) <= 10 for x in range(40, REF_W, 80) for y in range(30, REF_H, 60))


def _is(colour, rgb):
    r, g, b = rgb
    if colour == "green":
        return g > 180 and r < 140 and b < 100
    if colour == "red":
        return r > 200 and g < 80 and b < 80
    if colour == "orange":
        return r > 200 and 110 < g < 200 and b < 80
    if colour == "light":                  # the highlight bar (208, 212, 214)
        return min(rgb) > 170
    raise ValueError(colour)


def in_song_list(pic):
    return all(_is(colour, pic.rgb(x, y)) for colour, x, y in LEGEND)


def _light_share(pic, xs, ys):
    spots = [(x, y) for y in ys for x in xs]
    return sum(_is("light", pic.rgb(x, y)) for x, y in spots) / len(spots)


def _highlighted_row(pic, inside, outside):
    """The one row of MENU_ROWS that is light across `inside`, above and below
    its text, and not light in `outside`: the bar of the selected song is
    light there too, song names behind a menu are light only in places."""
    found = []
    for i, y in enumerate(MENU_ROWS):
        ys = (y - MENU_MARGIN, y + MENU_MARGIN)
        if (_light_share(pic, inside, ys) >= 0.85
                and max(_light_share(pic, side, ys) for side in outside) < 0.5):
            found.append(i)
    return found[0] if len(found) == 1 else None


def menu_row(pic):
    """Index of the highlighted row of the Actions menu, None when no menu is
    seen. Only the upper rows are told apart, that is where Search is."""
    return _highlighted_row(pic, MENU_INSIDE, MENU_OUTSIDE)


def sort_row(pic):
    """Index of the highlighted row of the Sort List (it opens on the sort in
    use), None when it is not seen. Only the upper rows are told apart."""
    return _highlighted_row(pic, SORT_INSIDE, SORT_OUTSIDE)


def title_screen(pic):
    """The screen the game starts with: no menu yet, "Press Start/Enter to
    Join" (legend "Confirm / Back / Join")."""
    return all(_is(colour, pic.rgb(x, y)) for colour, x, y in TITLE_LEGEND)


def main_menu(pic):
    """The main menu as it comes up once a player has joined: QUICKPLAY, the
    first entry, highlighted."""
    return (all(_is("light", pic.rgb(x, y)) for x, y in MAIN_LIGHT)
            and not any(_is("light", pic.rgb(x, y)) for x, y in MAIN_DARK))


def setup_panel(pic):
    """The panel between song list and song ("Ready", instrument, difficulty):
    a highlighted row in the middle of the screen, dark on both sides. There
    the green button starts the song."""
    for y in range(*PANEL_ROWS):
        if (_light_share(pic, MENU_INSIDE, (y,)) >= 0.95
                and max(_light_share(pic, side, (y,)) for side in MENU_OUTSIDE) == 0):
            return True
    return False


def _text_bits(pic, box):
    """The dark text in a box of the light bar, as bytes: equal for equal text."""
    xs, ys = pic.real(*box)
    return bytes(max(pic.at(px, py)) < 110 for py in ys for px in xs)


def selected_row(pic):
    """(artist, name) of the selected row of the song list as pictures of the
    text, to see whether two rows say the same; None when the bar of the
    selected song is not where it normally is (ends of the list)."""
    if not all(_is("light", pic.rgb(x, BAR_Y)) for x in BAR_ENDS):
        return None
    return _text_bits(pic, ARTIST_BOX), _text_bits(pic, NAME_BOX)


def tab_share(pic):
    xs, ys = pic.real(*TAB_BOX)
    if not len(xs) or not len(ys):
        return 0.0
    hits = 0
    for py in ys:
        for px in xs:
            r, g, b = pic.at(px, py)
            if r > 200 and 120 < g < 200 and b < 90:
                hits += 1
    return hits / (len(xs) * len(ys))


def dialog_open(pic):
    return tab_share(pic) >= TAB_SHARE


def filter_width(pic):
    """Width of the bold filter name in the dialog title, in reference pixels
    (None when there is no pure white in the title line)."""
    xs, ys = pic.real(*TITLE_BOX)
    cols = [px for px in xs if any(min(pic.at(px, py)) > BOLD_WHITE for py in ys)]
    if not cols:
        return None
    return (cols[-1] - cols[0]) * REF_W / pic.width


def filter_is_song(pic):
    width = filter_width(pic)
    return dialog_open(pic) and width is not None and SONG_WIDTH[0] <= width <= SONG_WIDTH[1]


def _legend(pic, dots):
    return all(_is(colour, pic.rgb(x, y)) for colour, x, y in dots)


def _one_light_row(pic, rows, xs, lines):
    """The one row of `rows` (centres) whose bar is light on `lines` (offsets
    from the centre, free of the row's text), None when not exactly one is."""
    found = [i for i, y in enumerate(rows) if _light_share(pic, xs, [y + d for d in lines]) >= 0.9]
    if len(found) != 1:
        return None
    others = [_light_share(pic, xs, [y + d for d in lines]) for i, y in enumerate(rows) if i != found[0]]
    return found[0] if max(others, default=0) < 0.3 else None


def main_row(pic):
    """Highlighted row of the main menu (0 = QUICKPLAY ... PRACTICE_ROW ...
    6 = QUIT), None when the main menu is not seen."""
    if not _legend(pic, MAIN_LEGEND):
        return None
    return _one_light_row(pic, MAIN_ROWS, MAIN_ROW_XS, (-MAIN_ROW_MARGIN, 0, MAIN_ROW_MARGIN))


def section_list(pic):
    """Practice mode: the list of sections is up."""
    return _legend(pic, SECTION_LEGEND)


def section_row(pic):
    """Highlighted row of the section list as it stands on the screen (0 =
    top row), None when the list is not seen."""
    return _one_light_row(pic, SECTION_ROWS, SECTION_XS, ROW_LINES) if section_list(pic) else None


def section_rows_bits(pic):
    """The text of the visible section rows as one picture, to see whether
    the list scrolled."""
    return b"".join(_text_bits(pic, (45, y - 8, 465, y + 9)) for y in SECTION_ROWS[::3])


def pause_menu(pic):
    """Practice mode: the pause menu is up."""
    return any(_legend(pic, dots) for dots in PAUSE_LEGENDS)


def pause_row(pic):
    """Highlighted row of the pause menu (RESUME ... PAUSE_QUIT), None when
    the menu is not seen."""
    return _one_light_row(pic, PAUSE_ROWS, PAUSE_XS, ROW_LINES) if pause_menu(pic) else None


def seek_legend(pic):
    """The pause menu offers "Seek" (on SET A / SET B POSITION)."""
    return _legend(pic, PAUSE_LEGENDS[1])


def _template(code):
    """DIGITS entry -> one int per row (DIGIT_W bits, left dot highest)."""
    return [int(code[4 * r:4 * r + 4], 16) for r in range(DIGIT_H)]


_TEMPLATES = {d: _template(code) for d, code in DIGITS.items()}


def read_digit(pic, x0, y0):
    """The digit in the cell at (x0, y0), None when it is none of DIGITS."""
    s = DIGIT_SHIFT
    width = DIGIT_W + 2 * s
    rows = []
    for dy in range(DIGIT_H + 2 * s):
        bits = 0
        for dx in range(width):
            bits = bits << 1 | (min(pic.rgb(x0 - s + dx, y0 - s + dy)) > 120)
        rows.append(bits)
    if not any(rows):
        return None
    mask = (1 << DIGIT_W) - 1
    misses = {}
    # the cell where it normally is first: a clear match there ends the search
    shifts = [(s, s)] + [(oy, ox) for oy in range(2 * s + 1) for ox in range(2 * s + 1) if (oy, ox) != (s, s)]
    for oy, ox in shifts:
        shift = width - DIGIT_W - ox
        for digit, tpl in _TEMPLATES.items():
            miss = sum(bin((rows[oy + r] >> shift & mask) ^ tpl[r]).count("1") for r in range(DIGIT_H))
            misses[digit] = min(miss, misses.get(digit, miss))
        if min(misses.values()) <= DIGIT_SURE:
            break
    (best_miss, best), (second, _) = sorted((m, d) for d, m in misses.items())[:2]
    # the font is drawn a little differently now and then (measured up to 27
    # dots off): a digit that is clearly nearer than any other counts too
    if best_miss <= DIGIT_MISS or (best_miss <= DIGIT_MAYBE and second - best_miss >= DIGIT_MARGIN):
        return best
    return None


def ab_shown(pic):
    """The pause menu shows A and B: it is the one of the practice mode
    (Quickplay's has none). The letters are a quarter light (measured
    0.22-0.32); a light bar over them (a dialog) is not a letter."""
    if not pause_menu(pic):
        return False
    x0, y0, x1, y1 = AB_LETTER
    for which in ("A", "B"):
        dy = AB_ROWS[which] - AB_ROWS["A"]
        if not AB_LETTER_SHARE[0] <= _light_share(pic, range(x0, x1), range(y0 + dy, y1 + dy)) <= AB_LETTER_SHARE[1]:
            return False
    return True


def ab_time(pic, which):
    """The time of A or B ("A" / "B") in seconds as the pause menu shows it
    (whole seconds), None when it cannot be read."""
    if not ab_shown(pic):
        return None
    digits = [read_digit(pic, x, AB_ROWS[which]) for x in AB_CELLS]
    if None in digits:
        return None
    h, m, s = (int(digits[i] + digits[i + 1]) for i in (0, 2, 4))
    return h * 3600 + m * 60 + s if m < 60 and s < 60 else None


def describe(pic):
    if pic is None:
        return "unreadable"
    if not in_song_list(pic):
        if pause_menu(pic):
            row = pause_row(pic)
            return "paused" if row is None else f"paused-{row}"
        if section_list(pic):
            row = section_row(pic)
            return "sections" if row is None else f"sections-{row}"
        row = main_row(pic)
        if row:
            return f"main-{row}"
        return ("main" if main_menu(pic) or row == 0 else "title" if title_screen(pic)
                else "setup" if setup_panel(pic) else "other")
    if dialog_open(pic):
        return "dialog-song" if filter_is_song(pic) else "dialog"
    row = menu_row(pic)
    if row is not None:
        return f"menu-{row}"
    row = sort_row(pic)
    return "list" if row is None else f"sort-{row}"


def find_clonehero_window():
    """X11 window id of the visible Clone Hero window, or None. clonehero.sh
    passes the game's process id in CLONEHERO_PID; without it the process and
    then the window class are looked up."""
    pid = os.environ.get("CLONEHERO_PID", "")
    try:
        if not pid.isdigit():
            pid = subprocess.run(["pgrep", "-ox", "clonehero"], capture_output=True, text=True,
                                 timeout=5).stdout.strip()
        by = ["--pid", pid] if pid.isdigit() else ["--class", "clonehero"]
        out = subprocess.run(["xdotool", "search", "--onlyvisible"] + by, capture_output=True,
                             text=True, timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return int(out[0]) if out and out[0].isdigit() else None


class _XImage(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int),
                ("format", ctypes.c_int), ("data", ctypes.c_void_p), ("byte_order", ctypes.c_int),
                ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int),
                ("bitmap_pad", ctypes.c_int), ("depth", ctypes.c_int),
                ("bytes_per_line", ctypes.c_int), ("bits_per_pixel", ctypes.c_int)]


class GameWindow:
    """Copies the Clone Hero window with XGetImage (a few milliseconds, nothing
    visible on screen). Raises OSError when there is no X display."""

    def __init__(self, find_window=find_clonehero_window):
        name = ctypes.util.find_library("X11")
        if not name:
            raise OSError("libX11 not found")
        x = ctypes.CDLL(name)
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XGetImage.restype = ctypes.POINTER(_XImage)
        x.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
        x.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong] + [ctypes.c_void_p] * 7
        x.XDestroyImage.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        # A window that is gone raises an X error; the default handler would
        # end the process.
        self._handler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(lambda d, e: 0)
        x.XSetErrorHandler(self._handler)
        self._x = x
        self._display = x.XOpenDisplay(None)
        if not self._display:
            raise OSError("cannot open X display %r" % os.environ.get("DISPLAY"))
        self._find_window = find_window
        self._window = None
        self._last = 0.0

    def grab(self):
        """Picture of the window, or None if it cannot be read."""
        if time.monotonic() - self._last > STALE_AFTER_S:
            # Xwayland hands out the picture of the request before for the first
            # one or two requests after a pause (04.10.2026, RoadieOne): those go
            for _ in range(STALE_READS):
                self._grab()
                time.sleep(0.05)
        pic = self._grab()
        self._last = time.monotonic()
        return pic

    def _grab(self):
        for _ in range(2):                 # the window id is kept; once more if it is gone
            if self._window is None:
                self._window = self._find_window()
            if self._window is None:
                return None
            pic = self._read(self._window)
            if pic is not None:
                return pic
            self._window = None
        return None

    def _read(self, window):
        root, border, depth = ctypes.c_ulong(), ctypes.c_uint(), ctypes.c_uint()
        wx, wy, w, h = ctypes.c_int(), ctypes.c_int(), ctypes.c_uint(), ctypes.c_uint()
        ok = self._x.XGetGeometry(self._display, window, ctypes.byref(root), ctypes.byref(wx),
                                  ctypes.byref(wy), ctypes.byref(w), ctypes.byref(h),
                                  ctypes.byref(border), ctypes.byref(depth))
        if not ok or w.value < 100 or h.value < 100:
            return None
        image = self._x.XGetImage(self._display, window, 0, 0, w.value, h.value, 0xFFFFFFFF, 2)  # ZPixmap
        self._x.XSync(self._display, 0)
        if not image:
            return None
        i = image.contents
        try:
            if i.bits_per_pixel != 32:
                return None
            pic = Picture(i.width, i.height, ctypes.string_at(i.data, i.bytes_per_line * i.height),
                          i.bytes_per_line)
        finally:
            self._x.XDestroyImage(image)
        return None if pic.black() else pic


def details(pic):
    if pic is None:
        return "unreadable (no window, or not an X11 session)"
    return (f"{describe(pic)}  [{pic.width}x{pic.height}  legend="
            + "/".join("%d,%d,%d" % pic.rgb(x, y) for _, x, y in LEGEND)
            + f"  menu row={menu_row(pic)}  TAB share={tab_share(pic):.3f}  filter width={filter_width(pic)}]")


def main():
    try:
        window = GameWindow()
    except OSError as e:
        sys.exit(f"cannot read the game window: {e}")
    if "--watch" in sys.argv[1:]:
        last, start = None, time.time()
        while True:
            state = describe(window.grab())
            if state != last:
                print(f"{time.time() - start:8.2f}s  {state}", flush=True)
                last = state
            time.sleep(0.02)
    print(details(window.grab()))


if __name__ == "__main__":
    main()
