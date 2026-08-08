# Drive KQ6 from a cold start to the control panel and photograph the GUARDS control.
# Run through tools/drive_scummvm.py, which supplies shot/move/click/key/press/release.
#
#   .venv-x/bin/python tools/drive_scummvm.py --game <COPY of the patched kq6> --id kq6 \
#       --script tools/kq6_panel_probe.py
#
# Writes build/kq6_panel_probe/*.png. What each one is for:
#   rest.png      the panel at rest -- GUARDS over the current mode, nothing below it
#   press.png     50 ms after ButtonPress -- where the press-animation artifact showed up
#   chooser.png   the 3-button chooser, with the panel gone from behind it
#   after.png     the panel reopened -- the plate must read back the mode just picked
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "kq6_panel_probe")
os.makedirs(OUT, exist_ok=True)
def out(n): return os.path.normpath(os.path.join(OUT, n))

# --- cold start: Sierra logo, title screen, then the intro --------------------------
for _ in range(7):
    key("Escape"); time.sleep(1.1)
    click(160, 100); time.sleep(1.1)
click(248, 190); time.sleep(6)                     # PLAY on the title menu
for _ in range(8):
    key("Escape"); time.sleep(1.1)
    click(160, 120); time.sleep(1.1)

def open_panel():
    move(160, 1); time.sleep(0.8)                  # the icon bar drops from the top edge
    click(306, 11); time.sleep(2.0)                # rightmost icon = the control panel

GUARDS = (194, 173)                                # the plate, one row under SPEECH

open_panel(); shot(out("rest.png"))
move(*GUARDS); time.sleep(0.3)
press(); time.sleep(0.05); shot(out("press.png"))  # the frame the artifact lived in
release(); time.sleep(1.5); shot(out("chooser.png"))
click(151, 121); time.sleep(1.5)                   # LITE
open_panel(); shot(out("after.png"))
print("wrote", OUT)
