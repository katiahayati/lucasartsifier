"""GK1: is Grace's room (the hounfour's point of no return) refused until you are ready?

    GK1_GRACE=without|with .venv-x/bin/python tools/sci_console.py --game <a COPY> --id gk1 \
        --binary <text-console scummvm> --input-script tools/probes/idle.script \
        --script tools/probes/gk1_grace_guard.py

Teleports into the hounfour, clicks through the elevator arrival, stands at Grace's door and
opens it with the key. `Hounfour timeForCeremony` is the latch the scene sets as its first act:

    patched, without the guises and the deposit flag -> latch 0, scene script held (refused)
    patched, with both guises and flag 351           -> latch 1 (the scene runs)
    stock                                            -> latch 1 either way

⛔ NEEDS `--input-script` (script mode): without it the scene's cues never run and ScummVM exits.
⛔ The harness cannot DISMISS the refusal's message box (its clock stalls inside GK1's dialog
loop), so the return to the hallway after "Not yet!" is NOT covered here -- that half needs a
person at the keyboard.
"""
import os
WITH = os.environ.get("GK1_GRACE", "without") == "with"
import re, time
def log(*a): print(*a, flush=True)
def addr(out):
    m = re.search(r"Value returned:\s*([0-9a-f]{4}):([0-9a-f]{4})", out, re.I)
    return "%s:%s" % (m.group(1), m.group(2)) if m else None
def val(obj, sel, *a): return c.send(obj, sel, *a)[0]
def name(a):
    m = re.search(r"\] (\S+) :", c.cmd("vo %s" % a) or ""); return m.group(1) if m else "?"
def sub(obj):
    _, o = c.send(obj, "script"); a = addr(o); return name(a) if a and a != "0000:0000" else None
N = [0]
def step(*events, wait=1500):
    N[0] += 1; tag = "m%d" % N[0]
    c.cmd("script clear"); t = 200
    for e in events:
        c.cmd("script add t=+%d %s" % (t, e)); t += 400
    c.cmd("script add t=+%d mark %s" % (t + wait, tag)); c.cmd("script add t=+%d break" % (t + wait + 100))
    c.resume(seconds=60, instructions=6000000); c.wait_mark(tag, timeout=20)
def snap(tag):
    log("%-26s room=%s curLoc=%s tfc=%s hall.state=%s hall.script=%s canControl=%s" % (
        tag, c.gint(11), val("Hounfour", "curLoc"), val("Hounfour", "timeForCeremony"),
        val("sMainHallways", "state"), sub("sMainHallways"), val(c.gaddr(80), "canControl")))
def flag(n, on):
    g, bit = 127 + n // 16, 0x8000 >> (n % 16)
    v = c.gint(g); c.setg(g, (v | bit) if on else (v & ~bit))
def has(n): return val(ego, "has", n)
def open_grace_door(tag):
    c.send("keypad", "doVerb", 123)            # the key on the keypad: unlock + open + walk in
    for i in range(7):
        step("move 160 120", wait=2500)
        snap("%s, door +%d" % (tag, i + 1))
        if val("Hounfour", "timeForCeremony") or sub("sMainHallways") == "sHRoom8": break
try:
    step("move 160 120")
    ego = c.gaddr(0)
    c.send(ego, "get", 64); c.setg(123, 10)
    c.cmd("room 800")
    step("move 160 120", wait=4000)
    for i in range(6):
        step("click 160 120", wait=3000)
        if val(c.gaddr(80), "canControl"): break
    snap("in the elevator room")
    c.send("sHRoom6", "dispose")                 # test shortcut: leave the elevator room
    for i in range(4):
        step("move 160 120", wait=2500)
    snap("in the hallway")
    c.send("Hounfour", "curLoc", 7)              # test shortcut: stand at Grace's door
    c.send("sMainHallways", "setScript", "sEgoInRoundHallway", 0, 3)
    for i in range(3):
        step("move 160 120", wait=2500)
    snap("at Grace's door")
    c.send(ego, "get", 80)                       # the hounfour key
    if WITH:
        c.send(ego, "get", 78); c.send(ego, "get", 79); flag(351, True)
    else:
        flag(351, False)
    log("guises held: boar=%s wolf=%s ; deposit flag 351 %s" % (has(78), has(79), "set" if WITH else "clear"))
    open_grace_door("with" if WITH else "WITHOUT")
    latch = val("Hounfour", "timeForCeremony")
    log("RESULT: ceremony latch=%s -- %s" % (latch, "the scene STARTED" if latch else
        "the scene was REFUSED (its script is entered and held at the refusal line)"))
except Exception as e:
    time.sleep(1); log("EXC:", str(e)[:70], "| returncode", c.proc.poll(), "| errors", c.errors()[-2:])
