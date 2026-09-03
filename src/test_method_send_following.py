"""A handler's same-script METHOD SEND is a call: the callee's writes happen under the handler's
condition (2026-09-03, GK1 docs §1.40).

The harvest (`opmodel._hwalk`) follows `PublicCall`/`LocalCall` into procedures and never followed
a method send -- `(obj sel:)` to an object or class defined in the SAME script, or `(self sel:)`.
GK1's flag 268 (the bayou icon's presence on the day map) is raised in exactly one place, the
drum-code puzzle's `PhraseDisplay::checkPhrases` (script 815), reached ONLY as
`drumInset::dispose` -> `(PhraseDisplay checkPhrases:)`: a handler the harvest walked (the inset
is scoped into the drummers' room 410 by `setInset:`), two sends deep. So the flag had NO
recorded writer at all -- the one presence flag in that state -- and carrying the icon's
presence condition would have sealed the bayou (docs §1.35, the invented-seal direction).

Bounded: same script only, own methods only, `init`/`changeState` never (the cast and the
machines own those), depth 3, no recursion; the callee walks under its own method's verb-param
scope. Runs on the cached GK1 model (built by the suite anyway)."""
import sys

import config
import missability as M

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def main():
    print("=== test_method_send_following: a handler's method send is a call ===")
    cfg = config.by_name("gk1")
    s = M.load(cfg=cfg)
    em = s.em
    base = getattr(em.ir, "flag_synth_base", None)
    check("GK1's flags are lowered", base is not None)
    r268 = base + 268 if base is not None else None
    rows = [(room, sc, v, g) for (room, sc, gi, v, g) in em.handler_writes if gi == r268]
    check("flag 268 (the bayou icon's presence) HAS a recorded handler writer",
          bool(rows), "no handler_writes row -- the drum inset's dispose -> checkPhrases chain is unwalked")
    check("...at the drummers' room (410) from the drum inset script (815), raised to 1",
          any(room == 410 and sc == 815 and v == 1 for (room, sc, v, _g) in rows),
          f"rows = {[(r, sc, v) for (r, sc, v, _g) in rows][:6]}")
    check("...under the puzzle's own condition, not unguarded",
          all(g is not None for (_r, _sc, _v, g) in rows), f"guards = {[g for (*_x, g) in rows][:3]}")
    check("...and at the hounfour (800), whose ceremonial-room script (900) arms the same inset -- "
          "the two `setInset:` sites in the game, and no other room",
          {(room, sc) for (room, sc, _v, _g) in rows} == {(410, 815), (800, 815)},
          f"rooms/scripts = {sorted({(room, sc) for (room, sc, _v, _g) in rows})}")
    r346 = base + 346 if base is not None else None
    check("the drum-pattern flag 346 (`drumPlay` 29) is captured through the same chain",
          any(gi == r346 and room == 410 for (room, _sc, gi, _v, _g) in em.handler_writes))
    check("the register model now knows flag 268", r268 in em.reg_dom or r268 in em.reg_vals,
          f"reg_dom={em.reg_dom.get(r268)} reg_vals={em.reg_vals.get(r268)}")
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
