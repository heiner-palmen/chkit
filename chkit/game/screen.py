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


def describe(pic):
    if pic is None:
        return "unreadable"
    if not in_song_list(pic):
        return ("main" if main_menu(pic) else "title" if title_screen(pic)
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

    def grab(self):
        """Picture of the window, or None if it cannot be read."""
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
