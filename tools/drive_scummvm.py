#!/usr/bin/env python3
"""Drive a game under ScummVM and screenshot it, with nobody at the keyboard.

Three KQ6 panel builds shipped on a theory because checking one meant asking the user to
play. It does not: ScummVM opens a real window on this box's `:0` (WSLg), XTEST can move
and click the mouse and press keys, and the window's own pixels can be read straight off
the X server. That closes the loop -- a patch can be built, installed into a scratch copy
of the game, driven to the screen in question and compared against the same screen from
the previous build, in one command.

    setup (once):
        python3 -m venv .venv-x && .venv-x/bin/pip install python-xlib pillow
    use:
        .venv-x/bin/python tools/drive_scummvm.py --game <dir> --id kq6 --script my.py

`--script` is a python file run with this module's helpers already in its namespace
(`shot move click key focus press release`, and `time`). Coordinates are the GAME's
(320x200 for SCI), scaled to wherever the window happens to be.

Notes paid for in blood:
  * `import -window root` (ImageMagick) FAILS under WSLg. Read the window by id instead,
    which is what `shot()` does.
  * `pkill -f "scummvm ..."` matches your own shell's command line and kills the shell.
    Use `pkill -x scummvm`.
  * After copying patch files into the scratch game, `cmp` them -- a shell that died
    mid-command silently skips the copy, and then you are testing the old build and
    believing the new one.
  * Point `--game` at a COPY. Never at the player's installed game.
"""
import argparse
import os
import subprocess
import sys
import time

try:
    from Xlib import X, XK, display
    from Xlib.ext import xtest
    from PIL import Image
except ImportError as e:                         # the rest of the repo is stdlib-only on purpose
    raise SystemExit(
        "%s -- this tool is the one part of the repo with dependencies. Run it from a venv:\n"
        "    python3 -m venv .venv-x && .venv-x/bin/pip install python-xlib pillow\n"
        "    .venv-x/bin/python tools/drive_scummvm.py ..." % e)

GAME_W, GAME_H = 320, 200


class Screen:
    def __init__(self, title_match, timeout=40):
        self.d = display.Display(os.environ.get("DISPLAY", ":0"))
        self.root = self.d.screen().root
        self.win = None
        deadline = time.time() + timeout
        while time.time() < deadline and self.win is None:
            self.win = self._find(self.root, title_match)
            if self.win is None:
                time.sleep(0.5)
        if self.win is None:
            raise SystemExit("no window whose title contains %r appeared" % title_match)
        g = self.win.get_geometry()
        self.size = (g.width, g.height)
        t = self.win.translate_coords(self.root, 0, 0)
        self.origin = (-t.x, -t.y)

    def _find(self, w, needle):
        try:
            for c in w.query_tree().children:
                n = c.get_wm_name()
                if n and needle.lower() in n.lower():
                    return c
                r = self._find(c, needle)
                if r:
                    return r
        except Exception:                        # noqa: BLE001 -- window died mid-walk
            pass
        return None

    # ---- output -----------------------------------------------------------------
    def shot(self, path):
        """The window's pixels, straight off the X server (root capture does not work here)."""
        raw = self.win.get_image(0, 0, self.size[0], self.size[1], X.ZPixmap, 0xFFFFFFFF)
        Image.frombytes("RGB", self.size, raw.data, "raw", "BGRX").save(path)
        return path

    # ---- input ------------------------------------------------------------------
    def focus(self):
        self.win.set_input_focus(X.RevertToParent, X.CurrentTime)
        self.d.sync()

    def move(self, gx, gy, settle=0.12):
        ax = self.origin[0] + int(gx * self.size[0] / float(GAME_W))
        ay = self.origin[1] + int(gy * self.size[1] / float(GAME_H))
        xtest.fake_input(self.d, X.MotionNotify, x=ax, y=ay)
        self.d.sync()
        time.sleep(settle)

    # ScummVM's OWN dialogs (save/restore, the global menu) are drawn by the launcher GUI in
    # WINDOW pixels, not in the game's 320x200 -- so a game-coordinate click lands somewhere
    # else entirely. These take window pixels, read straight off a screenshot.
    def wmove(self, wx, wy, settle=0.12):
        xtest.fake_input(self.d, X.MotionNotify,
                         x=self.origin[0] + int(wx), y=self.origin[1] + int(wy))
        self.d.sync()
        time.sleep(settle)

    def wclick(self, wx, wy, hold=0.10, settle=0.35):
        self.wmove(wx, wy)
        self.press()
        time.sleep(hold)
        self.release()
        time.sleep(settle)

    def press(self, button=1):
        xtest.fake_input(self.d, X.ButtonPress, button)
        self.d.sync()

    def release(self, button=1):
        xtest.fake_input(self.d, X.ButtonRelease, button)
        self.d.sync()

    def click(self, gx=None, gy=None, hold=0.10, settle=0.2):
        if gx is not None:
            self.move(gx, gy)
        self.press()
        time.sleep(hold)
        self.release()
        time.sleep(settle)

    def key(self, name, n=1, settle=0.25):
        kc = self.d.keysym_to_keycode(XK.string_to_keysym(name))
        for _ in range(n):
            xtest.fake_input(self.d, X.KeyPress, kc)
            self.d.sync()
            time.sleep(0.06)
            xtest.fake_input(self.d, X.KeyRelease, kc)
            self.d.sync()
            time.sleep(settle)

    def text(self, s, settle=0.06):
        """Type a string (letters and digits only -- enough to name a save slot)."""
        for ch in s:
            self.key({" ": "space"}.get(ch, ch), settle=settle)


def launch(game_dir, game_id, ini):
    """ScummVM on its OWN config, so the player's scummvm.ini is never touched."""
    if not os.path.exists(ini):
        with open(ini, "w") as f:
            f.write("[scummvm]\nfullscreen=false\nscale_factor=2\nmusic_driver=null\n"
                    "music_volume=0\nsfx_volume=0\nspeech_volume=0\n")
    p = subprocess.Popen(["scummvm", "--config=" + ini, "-p", game_dir,
                          "--no-fullscreen", game_id],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--game", required=True, help="game directory -- USE A COPY")
    ap.add_argument("--id", required=True, help="ScummVM game id, e.g. kq6")
    ap.add_argument("--title", default=None, help="substring of the window title (default: id)")
    ap.add_argument("--script", required=True, help="python file to run against the window")
    ap.add_argument("--ini", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "drive_scummvm.ini"))
    ap.add_argument("--keep", action="store_true", help="leave ScummVM running afterwards")
    a = ap.parse_args(argv)

    proc = launch(a.game, a.id, a.ini)
    try:
        s = Screen(a.title or a.id)
        s.focus()
        ns = {"s": s, "shot": s.shot, "move": s.move, "click": s.click, "key": s.key,
              "focus": s.focus, "press": s.press, "release": s.release, "time": time,
              "wmove": s.wmove, "wclick": s.wclick, "text": s.text,
              # the script is a FILE, so give it the name it would have had if imported --
              # scripts locate their output next to themselves
              "__file__": os.path.abspath(a.script), "__name__": "__drive__"}
        exec(compile(open(a.script).read(), a.script, "exec"), ns)   # noqa: S102 -- that is the point
    finally:
        if not a.keep:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
