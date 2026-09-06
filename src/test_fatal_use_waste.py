"""A FATAL USE COUNTS ONLY WHEN THE USE WASTES THE ITEM (USER ruling, 2026-08-27).

*"the problem with the skull is you waste it for later."* `fatal_uses` finds an item whose use
arms a machine you cannot survive. Deaths are in scope ([[one-rule-death-is-in-scope]]) and the
detector's docstring argues that at length -- but a death you simply restore from, offered on the
screen that offers it, is `death_traps`' business. What THIS detector is for is the item you
cannot get back, and the difference between the two is whether the use SPENDS it.

Why it needed pinning: without the waste test, GK1's patch shipped a guard on `sDaggerOnMalia`
that refuses a move the player is entitled to make -- the FP row the USER had already ruled out,
turned into a wrong instruction inside a real patch. A known false positive is cheap in a report
and expensive in a patch.

⛔ THE FENCE, and it cost the first draft. The question is asked of the ROOM, not the machine:

    KQ6 rm420 throwSkull   -- `(gEgo put: 11 gCurRoom)` at state 23, INSIDE the machine
    KQ5 rm30  ropeOnBranch -- `(gEgo put: 20 31)` at the ARMING SITE, one statement before the
                              `setScript:` -- the machine itself spends nothing

A first draft read `info["drops"]` and would have deleted KQ5's INSTALLED, PLAY-CONFIRMED rm30
guard. "Was it wasted here" is a question about the whole use, so the room answers it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                                         # noqa: E402
import missability as M                                               # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- %s" % detail) if detail and not cond else ""))


_MODELS = {}


def model(name):
    if name not in _MODELS:
        cfg = config.by_name(name)
        _MODELS[name] = M.load(cfg=cfg) if cfg and os.path.exists(cfg.ir_path) else None
    return _MODELS[name]


def test_kept():
    """Both surviving rows spend their item -- one in the machine, one at the arming site."""
    print("\n-- a use that WASTES the item is still a fatal use --")
    for name, item, room, machine in (("KQ6", 11, 420, "throwSkull"),
                                      ("kq5", 20, 30, "ropeOnBranch")):
        s = model(name)
        if s is None:
            print("  (skip %s: no IR)" % name)
            continue
        rows = s.fatal_uses()
        check("%s keeps %s@rm%d (item %d)" % (name, machine, room, item),
              any(r["item"] == item and r["room"] == room and r["machine"] == machine
                  for r in rows),
              str([(r["item"], r["room"], r["machine"]) for r in rows]))
        check("...because the room spends it: rm%d in drops[%d]" % (room, item),
              room in s.drops.get(item, ()), str(sorted(s.drops.get(item, ()))))

    # The fence: KQ5's spend is NOT in the machine, so a machine-scoped test would drop it.
    s = model("kq5")
    if s is not None:
        inside = any(20 in (i.get("drops") or ())
                     for i in s.em.machines if i["inst"] == "ropeOnBranch")
        check("⛔ KQ5's rope is spent at the ARMING SITE, not by the machine "
              "(a machine-scoped test would delete a play-confirmed guard)", not inside)


def test_dropped():
    """GK1's knife: a death you restore from, with the knife still in your pocket."""
    print("\n-- a use that does NOT waste the item is not one --")
    s = model("gk1")
    if s is None:
        print("  (skip gk1: no IR)")
        return
    check("GK1 has no fatal_uses row", s.fatal_uses() == [],
          str([(r["item"], r["room"], r["machine"]) for r in s.fatal_uses()]))
    check("...because the knife (64) is never put down ANYWHERE in the game",
          not s.drops.get(64), str(sorted(s.drops.get(64, ()))))
    # And the row's absence is the WASTE test, not the machine going missing: the machine is
    # still there and still lethal, which is what the guard would have hung off.
    insts = {i["inst"] for i in s.em.machines}
    check("...and `sDaggerOnMalia` is still a machine the model sees",
          "sDaggerOnMalia" in insts)


def run():
    print("=== test_fatal_use_waste: a fatal use counts only when the use WASTES the item ===")
    test_kept()
    test_dropped()
    print("\n%d passed, %d failed%s"
          % (len(PASS), len(FAIL), ("  FAILURES: %s" % FAIL) if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
