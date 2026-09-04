"""The icon bar's gets are placeless sources, and every item-declaring script is that scope
(2026-09-03, GK1 docs §1.46).

GK1 splits its inventory across two non-room scripts (tile1.sc = 24 with 52 items, GKInvItem.sc
= 15 with 30); `inventory_scripts` kept the plurality holder and script 15 was homed nowhere --
its thirty items' handlers never walked. The murder photo (item 1) is granted by OPENING ITS
ENVELOPE: `phoEnvelope::doVerb 6` says its line with `self` as caller and `cue` does `put: 0`,
`get: 2`, `get: 1` -- an inventory conversion available wherever the player stands, at the cost
of the envelope. The closure now takes such a get anywhere; the wallet's master card (71) is the
same class. Drops and writes in that scope stay as they were (the KQ6 lamp lesson)."""
import sys

import config
import ir as I
import missability as M
import vocab as V

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def main():
    print("=== test_inventory_scope_grants: the icon bar's gets are placeless sources ===")
    gk = config.by_name("gk1")
    inv = V.inventory_scripts(I.load_ir(gk.ir_path))
    check("GK1's inventory scope is BOTH item-declaring scripts (15 and 24)", set(inv) == {15, 24}, f"got {sorted(inv)}")
    for g in ("KQ6", "KQ5", "LSL2"):
        cfg = getattr(config, g, None) or config.by_name(g.lower())
        inv2 = V.inventory_scripts(I.load_ir(cfg.ir_path))
        check(f"{g}'s inventory scope is unchanged (one script)", len(inv2) == 1, f"got {sorted(inv2)}")
    s = M.load(cfg=gk)
    em = s.em
    check("script 15 is homed everywhere (global_homed)", 15 in em.global_homed, f"global_homed = {sorted(em.global_homed)}")
    ig = getattr(em, "inventory_gets", [])
    got = {(sc, it) for (sc, it, _g) in ig}
    check("the murder photo (1) and the graduation photo (2) are placeless gets from the envelope's cue",
          (15, 1) in got and (15, 2) in got, f"inventory_gets = {sorted(got)[:12]}")
    check("the master card (71) is a placeless get from the wallet's cue", (24, 71) in got, f"inventory_gets = {sorted(got)[:12]}")
    check("no placeless DROP was recorded (drops stay refused in that scope)",
          all(len(x) == 3 for x in ig))
    s._rp_xcache = {}
    (rooms, pv, items), _c = s._staged_pre(123, 1, {})
    check("the day-1 closure holds the murder photo (opened anywhere)", 1 in items, f"items = {sorted(items)[:20]}")
    check("...and the master card", 71 in items, f"items = {sorted(items)[:20]}")
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
