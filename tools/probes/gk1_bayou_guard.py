"""GK1: does the bayou's RITUAL PASSAGE start the crossing? -- asked of the live object.

    .venv-x/bin/python tools/sci_console.py --game <a COPY> --id gk1 \
        --binary <text-console scummvm> --script tools/probes/gk1_bayou_guard.py

Teleports to the bayou's final screen, stands Gabriel on the ritual passage and calls that
passage object's own `doit` under each combination of flag 216 (mask worn) and flag 299 (tattoo
painted). "ARMED" = it queued the cue that walks him into the ritual.

    stock game    -> ARMED in all four rows (the walk-in that kills you)
    patched game  -> ARMED only with BOTH flags

RUN THE STOCK GAME AS THE CONTROL. The first version of this check polled the game loop instead
of calling `doit`, and reported "nothing happens" on stock too -- the icon bar's modal loop was
starving the loop, so the reading said nothing about the guard ([[instruments-lie-run-the-control]]).
Console writes set the scene; they are test setup, not gameplay.
"""
import re
def log(*a): print(*a, flush=True)
def addr(out):
    m = re.search(r"Value returned:\s*([0-9a-f]{4}):([0-9a-f]{4})", out, re.I)
    return "%s:%s" % (m.group(1), m.group(2)) if m else None
def val(obj, sel, *a): return c.send(obj, sel, *a)[0]
def flag(n, on):
    g, bit = 127 + n // 16, 0x8000 >> (n % 16)
    v = c.gint(g); c.setg(g, (v | bit) if on else (v & ~bit))
c.resume(seconds=8); c.setg(123, 6)
c.cmd("room 490"); c.resume(seconds=12)
ego = c.gaddr(0)
c.send("roomScript", "changeState", 15); c.resume(seconds=6)
td = c.gaddr(78); _, o = c.send(td, "at", (val(td, "size") or 1) - 1); lst = addr(o)
ps = {}
for k in range(val(lst, "size") or 0):
    _, o = c.send(lst, "at", k); p = addr(o); ps[val(p, "dir")] = p
ritual, plain = ps[1], ps[0]
log("ritual passage dir=1 isRitual=%s ; plain passage dir=0 isRitual=%s" % (val(ritual, "isRitual"), val(plain, "isRitual")))
user = c.gaddr(80)
def trial(tag, p, x, y, f216, f299):
    flag(216, f216); flag(299, f299)
    c.send(ego, "posn", x, y)
    c.cmd("vv g 18 0")                      # forget anything queued earlier (test setup only)
    c.send(user, "canControl", 1)
    before = c.gaddr(18)
    _, out = c.send(p, "doit")
    after = c.gaddr(18)
    ctl = val(user, "canControl")
    log("%-44s g18 %s -> %s  canControl=%s  onMe=%s  => %s" % (tag, before, after, ctl, val(p, "onMe", ego),
        "ARMED" if after != "0000:0000" else "nothing happens"))
    return after != "0000:0000"
trial("ritual: mask not worn, no tattoo", ritual, 270, 88, False, False)
trial("ritual: mask worn, no tattoo", ritual, 270, 88, True, False)
trial("ritual: tattoo, mask not worn", ritual, 270, 88, False, True)
trial("ritual: mask worn AND tattoo", ritual, 270, 88, True, True)
