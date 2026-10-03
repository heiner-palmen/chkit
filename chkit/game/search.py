"""
Puts the cursor of Clone Hero's song list on a song, only where the screen
shows that the keys mean what they should (chkit.game.screen). Linux, X11.

  find_song(song)          the cursor on that chart (see SongSearch); song: artist, name, path/md5
  find_artist(artist)      the cursor on the first song of that artist
  press_enter()            sends Enter to the game
  type_in_search(text)     the old way without looking: A, L, DOWN, A, text, Enter
  find_keyboard_devices()  evdev paths of every connected keyboard
  keycode_to_name(code)    'F1', 'A', ...

Nothing is typed blindly unless the caller asks for it (blind=True): when the
game window cannot be read, the search stops. Keys go through a virtual
keyboard (uinput, needs the evdev package and write access to /dev/uinput).
The text is typed for the German QWERTZ layout (Y/Z swapped, umlauts,
punctuation); typing stops at the first character without a key.

  python3 -m chkit.game.search "Artist" "Song name" [song folder]    try a search by hand
"""
import os
import sys
import time

try:
    from evdev import InputDevice, UInput, ecodes, list_devices
except ImportError:                      # the rest of chkit needs no evdev; typing does
    InputDevice = UInput = ecodes = list_devices = None

from .. import song as chsong
from . import screen as ch_screen


def _need_evdev():
    if ecodes is None:
        raise ImportError("typing into the game needs the evdev package (pip install evdev)")


UINPUT_NAME = "chkit-autotype"           # is_keyboard_device() skips this device
CURRENTSONG = os.path.expanduser("~/.clonehero/currentsong.txt")
GAME_DATA = os.path.expanduser("~/.config/unity3d/srylain Inc_/Clone Hero")
PLAYER_LOG = os.path.join(GAME_DATA, "Player.log")
LEADERBOARD_CACHE = os.path.join(GAME_DATA, "LeaderboardCache")

# German QWERTZ: character -> (key, shift). Letters and digits are added below.
QWERTZ = {
    " ": ("SPACE", False), "ß": ("MINUS", False), "ü": ("LEFTBRACE", False), "+": ("RIGHTBRACE", False),
    "ö": ("SEMICOLON", False), "ä": ("APOSTROPHE", False), "#": ("BACKSLASH", False),
    ",": ("COMMA", False), ".": ("DOT", False), "-": ("SLASH", False),
    "!": ("1", True), '"': ("2", True), "$": ("4", True), "%": ("5", True), "&": ("6", True),
    "/": ("7", True), "(": ("8", True), ")": ("9", True), "=": ("0", True), "?": ("MINUS", True),
    "*": ("RIGHTBRACE", True), "'": ("BACKSLASH", True), ";": ("COMMA", True), ":": ("DOT", True),
    "_": ("SLASH", True),
}
QWERTZ.update({c: (c.upper(), False) for c in "abcdefghijklmnopqrstuvwx0123456789"})
QWERTZ.update({"y": ("Z", False), "z": ("Y", False)})


def typeable(text):
    """The text as it is typed: lower case (the search does not care), cut
    before the first character the keyboard table does not have."""
    out = []
    for char in text.lower():
        if char not in QWERTZ:
            break
        out.append(char)
    return "".join(out).strip()


class Keyboard:
    """The virtual keyboard the tools type with."""

    def __init__(self, ui, sleep=time.sleep):
        self.ui, self.sleep = ui, sleep

    def press(self, name, shift=False, hold=0.03):
        _need_evdev()
        code = getattr(ecodes, f"KEY_{name}")
        if shift:
            self.ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
            self.ui.syn()
        self.ui.write(ecodes.EV_KEY, code, 1)
        self.ui.syn()
        self.sleep(hold)
        self.ui.write(ecodes.EV_KEY, code, 0)
        if shift:
            self.ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
        self.ui.syn()

    def type(self, text, pause=0.04):
        for char in text:
            self.press(*QWERTZ[char])
            self.sleep(pause)


class SongSearch:
    """Puts the cursor of Clone Hero's song list on one song, from wherever
    the game is, and looks at the screen before every step (ch_screen.py):

      a song is running          nothing is done
      song setup panel ("Ready") nothing is done: green would start the song
      not in the song list       A once (main menu, score screen), then wait for the list
      song list                  L opens the Actions menu, DOWN to "Search", A opens the dialog
      search dialog              TAB until it says "Searching for: Song", the song name, Enter

    A step whose result does not show up on the screen ends the search; the
    keys that would follow are not sent, so nothing is typed into a menu that
    reads letters as buttons. `run` returns None when the cursor was set and
    else the reason as text.

    The search takes the first song in the list whose name begins with the
    typed text; in a list sorted by artist that can be another chart of the
    song or a song of another artist. With `selection` (Selection) and what
    is known about the wanted chart (see `wanted`) the hit is checked. If it
    is the wrong one:

      1. the rows below with the same artist and name are tried (other charts
         of the song),
      2. the list is sorted by song for a moment (Actions menu -> Sort List),
         where the songs of that name stand together; they are tried one by
         one, then the sort is set back. The cursor stays on its song.

    If the chart is not found, the cursor is put on the artist and `run`
    says so.
    """

    FILTERS = 7                            # Artist, Album, Charter, Playlist, Genre, Source, Song
    DUPLICATES = 6                         # charts of the same song that are tried in step 1
    SAME_NAME = 15                         # rows that are tried in step 2

    def __init__(self, keys, grab, song_running, selection=None, sleep=time.sleep,
                 now=time.monotonic, log=print):
        self.keys, self.grab, self.song_running, self.selection = keys, grab, song_running, selection
        self.sleep, self.now, self.log = sleep, now, log

    def wait(self, wanted, timeout):
        """Watch the screen until wanted(picture) holds. The picture, or None
        when the time is up."""
        end = self.now() + timeout
        while True:
            pic = self.grab()
            if pic is not None and wanted(pic):
                return pic
            if self.now() >= end:
                return None
            self.sleep(0.03)

    def press_until(self, key, wanted, timeout, tries=2):
        """Press the key and wait for its result; the game sometimes misses a
        key, so it is pressed again as long as the screen has not changed."""
        before = ch_screen.describe(self.grab())
        for _ in range(tries):
            self.keys.press(key)
            pic = self.wait(wanted, timeout)
            if pic is not None:
                return pic
            if ch_screen.describe(self.grab()) != before:
                return None                # something else happened: do not press again
        return None

    def run(self, name, artist=None, wanted=None):
        """`wanted`: what tells the wanted chart apart (see `wanted`), None to
        take the first hit as it is."""
        text, artist_text = typeable(name), typeable(artist or "")
        if not text:
            return f"nothing to type for '{name}'"
        failed = self.to_song_list()
        if failed:
            return failed
        failed = self.search(text)
        if failed or not wanted or self.selection is None:
            return failed
        hit = self.is_wanted(wanted)
        if hit is None:
            self.log("hit not checked: the game did not tell which chart it is")
        if hit is not False:
            return None
        first = self.row()
        for step in range(1, self.DUPLICATES):
            hit = self.down(wanted, same=first)
            if hit:
                self.log(f"the wanted chart is {step} below the first hit")
                return None
            if hit is None:
                break                      # the row below is another song
        failed = self.search_by_song_sort(text, wanted)
        if failed and artist_text and not self.search(artist_text, tabs_after_song=1):
            failed += "; the cursor is at the artist"
        return failed

    def search_by_song_sort(self, text, wanted):
        """Step 2: with the list sorted by song, go through the songs of that name."""
        failed, before = self.set_sort(ch_screen.SORT_SONG)
        if failed:
            return failed
        self.log("list sorted by song")
        hit = None
        failed = self.search(text)
        if not failed:
            hit, tried, others = self.is_wanted(wanted), 1, 0
            name = (self.row() or (None, None))[1]
            while not hit and tried < self.SAME_NAME and others < 3:
                hit, tried = self.down(wanted), tried + 1
                if hit is None:
                    break
                row = self.row()           # three other names in a row: past the songs of that name
                others = others + 1 if name and row and row[1] != name else 0
            if hit:
                self.log(f"found as number {tried} of that name")
        if before != ch_screen.SORT_SONG:
            unsorted, _ = self.set_sort(before)
            if unsorted:
                return f"the list is still sorted by song: {unsorted}"
        return failed or (None if hit else "the wanted chart is not among the songs of that name")

    def set_sort(self, target):
        """Sort the list by the row `target` of the Sort List. (reason, None)
        when that failed, else (None, row that was in use before)."""
        failed = self.open_menu(ch_screen.SORT_LIST_ROW)
        if failed:
            return failed, None
        self.keys.press("A")               # only once: a second A would pick a sort
        pic = self.wait(lambda p: ch_screen.sort_row(p) is not None, 4)
        if pic is None:
            return "the Sort List did not open", None
        before = row = ch_screen.sort_row(pic)
        for _ in range(len(ch_screen.MENU_ROWS)):
            if row == target:
                break
            pic = self.press_until("DOWN" if row < target else "UP",
                                   lambda p: ch_screen.sort_row(p) not in (row, None), 1)
            if pic is None:
                return "the Sort List did not move", None
            row = ch_screen.sort_row(pic)
        if row != target:
            return "the Sort List did not move", None
        self.keys.press("A")
        if self.wait(lambda p: ch_screen.describe(p) == "list", 8) is None:
            return "the Sort List did not close", None
        self.sleep(0.4)                    # the list is built again
        return None, before

    def row(self):
        pic = self.grab()
        return ch_screen.selected_row(pic) if pic is not None else None

    def is_wanted(self, wanted):
        """True/False: the chart the cursor came to rest on is / is not the
        wanted one. None when the game did not tell."""
        seen = self.selection.read()
        if seen.get("md5") and wanted.get("md5"):
            return seen["md5"] == wanted["md5"]
        if seen.get("preview") is not None and wanted.get("preview") is not None:
            return abs(seen["preview"] - wanted["preview"]) < 0.002
        return None

    def down(self, wanted, same=None):
        """One row down. True: that is the wanted chart. False: it is not.
        None: it is not, and the row is another song (`same`: artist and name
        as before) or the list is not up any more. The row is always read:
        the game does not tell a second time what a row is that the cursor
        has just rested on."""
        if self.song_running() or ch_screen.describe(self.grab()) != "list":
            return None
        self.selection.mark()
        self.keys.press("DOWN")
        self.sleep(0.25)                   # the list moves
        row = self.row()
        if self.is_wanted(wanted):
            return True
        return None if same is not None and row != same else False

    def open_menu(self, target):
        """Open the Actions menu and move to the row `target`."""
        pic = self.grab()
        if pic is None:
            return "screen unreadable"
        if ch_screen.dialog_open(pic):     # left open: start over with an empty one
            self.keys.press("ESC")
            pic = self.wait(lambda p: not ch_screen.dialog_open(p), 3)
            if pic is None:
                return "an open search dialog did not close"
        if ch_screen.menu_row(pic) is None:
            pic = self.press_until("L", lambda p: ch_screen.menu_row(p) is not None, 1.5)
            if pic is None:
                return "the Actions menu did not open"
        for _ in range(len(ch_screen.MENU_ROWS)):
            row = ch_screen.menu_row(pic)
            if row == target:
                return None
            pic = self.press_until("DOWN" if row < target else "UP",
                                   lambda p: ch_screen.menu_row(p) not in (row, None), 1)
            if pic is None:
                return "the Actions menu did not move"
        return None if ch_screen.menu_row(pic) == target else "row not reached in the Actions menu"

    def to_song_list(self):
        """Into the song list (A from the main menu or the score screen), with
        every step checked on the screen. None when it is there, else why not."""
        if self.song_running():
            return "a song is running"
        pic = self.grab()
        if pic is None:
            return "screen unreadable"
        if not ch_screen.in_song_list(pic):
            if ch_screen.setup_panel(pic):
                return "the song setup panel is open (green would start the song)"
            self.log("not in the song list: pressing A")
            self.keys.press("A")
            if self.wait(ch_screen.in_song_list, 8) is None:
                return "the song list did not come up after A"
            self.sleep(0.5)                # the list scrolls in
        elif ch_screen.sort_row(pic) is not None:      # left open
            self.keys.press("S")
            if self.wait(lambda p: ch_screen.describe(p) == "list", 3) is None:
                return "an open Sort List did not close"
        if self.song_running():
            return "a song is running"
        return None

    def run_artist(self, artist):
        """The cursor on the first song of `artist` (search filter "Artist")."""
        text = typeable(artist)
        if not text:
            return f"nothing to type for '{artist}'"
        return self.to_song_list() or self.search(text, tabs_after_song=1)

    def search(self, text, tabs_after_song=0):
        """One round of the search dialog. The filters are told apart by
        "Song" alone; the others are reached from there (Artist is the next)."""
        failed = self.open_menu(ch_screen.SEARCH_ROW)
        if failed:
            return failed
        if self.press_until("A", ch_screen.dialog_open, 2) is None:
            return "the search dialog did not open"
        self.sleep(0.25)                   # the dialog fades in
        if not self.to_song_filter():
            self.keys.press("ESC")
            return "the search filter 'Song' was not found"
        for _ in range(tabs_after_song):
            if self.tab() is None:
                self.keys.press("ESC")
                return "the search filter did not change"
        if self.selection is not None:
            self.selection.mark()          # the cursor jumps while the text is typed
        self.keys.type(text)
        if self.selection is not None:
            self.selection.rest()
        self.sleep(0.3)
        if self.wait(ch_screen.dialog_open, 0) is None:
            return "the search dialog closed while typing"
        if self.press_until("ENTER", lambda p: not ch_screen.dialog_open(p), 4) is None:
            return "the search dialog did not close after Enter"
        return None

    def to_song_filter(self):
        """TAB until the dialog says "Song". With the list sorted by artist it
        opens with "Artist", six before "Song": those six go quickly, then it
        is looked at after every TAB."""
        if self.wait(ch_screen.filter_is_song, 0) is not None:
            return True
        for _ in range(self.FILTERS - 1):
            self.keys.press("TAB")
            self.sleep(0.06)
        if self.wait(ch_screen.filter_is_song, 0.5) is not None:
            return True
        for _ in range(self.FILTERS):
            if self.tab() is None:
                return False
            if self.wait(ch_screen.filter_is_song, 0) is not None:
                return True
        return False

    def tab(self):
        """TAB to the next search filter; the picture with the new filter name."""
        pic = self.grab()
        width = ch_screen.filter_width(pic) if pic is not None else None
        return self.press_until("TAB", lambda p: ch_screen.dialog_open(p)
                                and ch_screen.filter_width(p) != width, 0.8)


class Selection:
    """What the game gives away about the song the cursor rests on:

      md5      About 0.7 s after the cursor came to rest the game asks for the
               leaderboard of the chart and writes the answer to
               LeaderboardCache/<MD5 of the chart file><...>.cache.json. Not
               when it has an answer younger than 30 s, and not offline.
      preview  About a second after, the preview starts and Player.log gets
               "Seeking to song time:<seconds>": the preview_start_time of
               the song.ini, if it has one.

    mark() goes before the first key that moves the cursor, rest() after the
    last one (mark() alone for a single key), then read().
    """

    LINE = "Seeking to song time:"
    FETCH = 0.5                            # a cache file written this long after rest() is the new song's
    FETCHED = 1.0                          # by then the game has asked, if it asks at all
    LIMIT = 1.8                            # by then the preview has started

    def __init__(self, cache_dir=LEADERBOARD_CACHE, log_path=PLAYER_LOG, sleep=time.sleep,
                 now=time.monotonic, clock=time.time):
        self.cache_dir, self.log_path = cache_dir, log_path
        self.sleep, self.now, self.clock = sleep, now, clock
        self.offset = self.since = self.rested = self.rested_clock = 0.0

    def mark(self):
        try:
            self.offset = os.path.getsize(self.log_path)
        except OSError:
            self.offset = 0
        self.since = self.clock()
        self.rest()

    def rest(self):
        self.rested, self.rested_clock = self.now(), self.clock()

    def _newest_cache(self):
        """(time, md5) of the newest cache file written since the mark, or None."""
        newest = None
        try:
            with os.scandir(self.cache_dir) as entries:
                for entry in entries:
                    if not entry.name.endswith(".cache.json"):
                        continue
                    mtime = entry.stat().st_mtime
                    if mtime >= self.since and (newest is None or mtime > newest[0]):
                        newest = (mtime, entry.name[:32].lower())
        except OSError:
            return None
        return newest

    def _new_lines(self):
        try:
            with open(self.log_path, "rb") as fh:
                if os.fstat(fh.fileno()).st_size < self.offset:
                    self.offset = 0        # a new log (game restarted)
                fh.seek(self.offset)
                data = fh.read()
        except OSError:
            return []
        end = data.rfind(b"\n") + 1        # whole lines only
        self.offset += end
        return data[:end].decode("utf-8", "replace").splitlines()

    def read(self):
        """{"md5": ..., "preview": ...} of the song the cursor rests on; a
        value the game did not tell is None."""
        seen = {"md5": None, "preview": None}
        while True:
            newest = self._newest_cache()
            if newest:
                seen["md5"] = newest[1]
            for line in self._new_lines():
                if line.startswith(self.LINE):
                    try:
                        seen["preview"] = float(line[len(self.LINE):])
                    except ValueError:
                        pass
            waited = self.now() - self.rested
            if newest and (newest[0] >= self.rested_clock + self.FETCH or waited >= self.FETCHED):
                return seen
            if waited >= self.LIMIT:
                return seen
            self.sleep(0.1)


def wanted(song):
    """What tells the chart of a song (dict with path and/or md5) apart: the
    MD5 of its chart file and its preview start in seconds. None when neither
    is known."""
    folder = song.get("path") or ""
    files = chsong.folder_files(folder)
    md5 = (song.get("md5") or "").lower() or None
    if md5 is None:
        chart = chsong.find_chart(folder, files)        # notes.mid first, like the game
        if chart:
            try:
                md5 = chsong.chart_md5(chart)
            except OSError:
                pass
    preview = preview_start(os.path.join(folder, files["song.ini"])) if "song.ini" in files else None
    return {"md5": md5, "preview": preview} if md5 or preview is not None else None


def preview_start(song_ini):
    """preview_start_time of a song.ini in seconds, None when it has none
    (the game then picks a start itself)."""
    try:
        return chsong.preview_start(chsong.read_ini(song_ini))
    except OSError:
        return None


def song_running(path=CURRENTSONG):
    """Clone Hero writes the running song into currentsong.txt and empties it afterwards."""
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def find_song(song, log=print, blind=False):
    """Put the cursor of the song list on the song (dict with artist, name and,
    for checking the hit, path and/or md5). Without a readable screen (no X11
    window) nothing is typed, unless blind=True: then the old sequence is
    typed from the main menu without looking (only for someone watching the
    game). Returns None when the search went through, else why it stopped."""
    artist, name = song.get("artist") or "", song.get("name") or ""
    try:
        window = ch_screen.GameWindow()
        readable = window.grab() is not None
    except OSError as e:
        log(f"search: {e}")
        readable = False
    if not readable:
        if song_running():
            log("search: a song is running, nothing typed")
            return "a song is running"
        if not blind:
            log("search: cannot see the game window, nothing typed")
            return "cannot see the game window"
        log("search: cannot see the game window, typing blindly")
        type_in_search(f"{artist} - {name}")
        return None
    _need_evdev()
    with UInput(name=UINPUT_NAME) as ui:
        time.sleep(0.3)                    # give the game a moment to see the new keyboard
        start = time.monotonic()
        search = SongSearch(Keyboard(ui), window.grab, song_running, Selection(),
                            log=lambda m: log(f"search: {m}"))
        failed = search.run(name, artist, wanted(song))
        time.sleep(0.1)
    took = time.monotonic() - start
    log(f"search: '{typeable(name)}' done in {took:.1f}s" if failed is None
        else f"search: stopped after {took:.1f}s: {failed}")
    return failed


def find_artist(artist, log=print):
    """Put the cursor on the first song of `artist`; every step checked on the
    screen, never typed blindly. Returns None when it went through, else why
    it stopped."""
    try:
        window = ch_screen.GameWindow()
        readable = window.grab() is not None
    except OSError as e:
        log(f"search: {e}")
        readable = False
    if not readable:
        log("search: cannot see the game window, nothing typed")
        return "cannot see the game window"
    _need_evdev()
    with UInput(name=UINPUT_NAME) as ui:
        time.sleep(0.3)                    # give the game a moment to see the new keyboard
        search = SongSearch(Keyboard(ui), window.grab, song_running, None, log=lambda m: log(f"search: {m}"))
        failed = search.run_artist(artist)
        time.sleep(0.1)
    log(f"search: artist '{typeable(artist)}' done" if failed is None else f"search: stopped: {failed}")
    return failed


def press_enter():
    """Send Enter to Clone Hero."""
    _need_evdev()
    with UInput(name=UINPUT_NAME) as ui:
        time.sleep(0.2)                    # give the game a moment to see the new keyboard
        ui.write(ecodes.EV_KEY, ecodes.KEY_ENTER, 1)
        ui.write(ecodes.EV_KEY, ecodes.KEY_ENTER, 0)
        ui.syn()
        time.sleep(0.1)


def type_in_search(text, enter=True):
    """The old way, without looking at the screen: A, L, DOWN, A, then the
    text and, with enter=True, Enter. Only right from the main menu."""
    _need_evdev()
    with UInput(name=UINPUT_NAME) as ui:
        keys = Keyboard(ui)
        for key, pause in (("A", 1), ("L", 0.5), ("DOWN", 0.2), ("A", 0.3)):
            keys.press(key, hold=0)
            time.sleep(pause)
        keys.type(typeable(text), pause=0.1)
        if enter:
            time.sleep(0.3)
            keys.press("ENTER", hold=0)
            time.sleep(0.1)


def is_keyboard_device(dev):
    try:
        if dev.name == UINPUT_NAME:        # our own typing device is not a keyboard to listen on
            return False
        if "keyboard" in dev.name.lower():
            return True
        keys = dev.capabilities().get(ecodes.EV_KEY, [])
        return ecodes.KEY_A in keys and ecodes.KEY_ENTER in keys
    except Exception:
        return False


def find_keyboard_devices():
    _need_evdev()
    devices = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            if is_keyboard_device(dev):
                devices.append(path)
        except Exception:
            continue
    return devices


def keycode_to_name(code):
    _need_evdev()
    name = ecodes.KEY.get(code)
    # a few codes have several names (e.g. KEY_MUTE / KEY_MIN_INTERESTING):
    # evdev returns a list for those, which used to crash the listener thread
    if isinstance(name, (list, tuple)):
        name = name[0]
    return name.replace("KEY_", "").upper() if name else None


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    find_song({"artist": sys.argv[1], "name": sys.argv[2], "path": (sys.argv[3:] or [None])[0]})
