# Does the guard mode survive save/restore, and does Restart reset it to full?
#
# Both are claims about STORAGE, not about any guard: the mode is an ordinary global, so a save
# should carry it and script 0 reloading on Restart should zero it. Neither had ever been watched
# happen. This needs no guard site, only the panel, so it runs from a cold start.
#
#   .venv-x/bin/python tools/drive_scummvm.py --game <COPY of the patched kq6> --id kq6 \
#       --script tools/kq6_mode_persist_probe.py
#
# The test is set LITE -> save -> set OFF -> restore: if the restore did nothing the plate would
# still read OFF, so a pass cannot be faked by the mode simply never changing.
#
# Writes build/kq6_mode_persist/*.png:
#   1_lite.png       LITE chosen
#   2_off.png        OFF chosen, after saving under LITE
#   3_restored.png   after restoring -- must read LITE again
#   4_restarted.png  after Restart -- must read FULL
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "kq6_mode_persist")
os.makedirs(OUT, exist_ok=True)
def out(n): return os.path.normpath(os.path.join(OUT, n))

PANEL_ICON = (306, 11)                    # rightmost icon on the drop-down bar
GUARDS     = (194, 173)                   # the plate, one row under SPEECH
BTN = {"full": (105, 121), "lite": (151, 121), "off": (208, 121)}
SAVE, RESTORE, RESTART = (104, 61), (104, 71), (104, 81)

def open_panel():
    move(160, 1); time.sleep(0.8)
    click(*PANEL_ICON); time.sleep(2.0)

def set_mode(name):
    click(*GUARDS); time.sleep(1.5)       # panel closes, chooser opens
    click(*BTN[name]); time.sleep(1.5)

# --- cold start ----------------------------------------------------------------------
for _ in range(7):
    key("Escape"); time.sleep(1.1)
    click(160, 100); time.sleep(1.1)
click(248, 190); time.sleep(6)            # PLAY on the title menu
for _ in range(8):
    key("Escape"); time.sleep(1.1)
    click(160, 120); time.sleep(1.1)

# --- LITE, then save ------------------------------------------------------------------
open_panel(); set_mode("lite")
open_panel(); shot(out("1_lite.png"))
click(*SAVE); time.sleep(2.5)
# ScummVM's own save overlay -- WINDOW pixels, not game coordinates
wclick(105, 103); time.sleep(1.2)         # the "New Save" tile
text("modetest"); time.sleep(0.5)
key("Return"); time.sleep(3.5)

# --- move the mode AWAY, so a no-op restore cannot pass ---------------------------------
open_panel(); set_mode("off")
open_panel(); shot(out("2_off.png"))

# --- restore, and look ------------------------------------------------------------------
click(*RESTORE); time.sleep(2.5)
wclick(318, 110); time.sleep(1.2)         # the saved slot's thumbnail
key("Return"); time.sleep(4.5)
open_panel(); shot(out("3_restored.png"))

# --- Restart must put it back to full ---------------------------------------------------
click(*RESTART); time.sleep(2.0)
key("Return"); time.sleep(2.0)
for _ in range(6):
    key("Escape"); time.sleep(1.0)
    click(160, 120); time.sleep(1.0)
open_panel(); shot(out("4_restarted.png"))
print("wrote", OUT)
