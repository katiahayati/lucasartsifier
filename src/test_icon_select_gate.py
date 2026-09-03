"""An icon-derived destination carries the icon's own CLICK GATE (GK1, 2026-09-02).

GK1's two travel maps route through `chgRoom`, whose destination rides `setScript:`'s register
argument -- a value `_script_prop_values` resolves from the map icons' `(global2 cue: N)` sends.
Those sends used to be UNGUARDED ("the icon clicked is the player's choice, not a state"). But
the container class decides whether a click reaches the icon's `cue` at all: `IconMap::
dispatchEvent` sends `(icon cue:)` only under `(self select: icon 1)`, and `IconMap::select`
returns 1 only if the ICON's own `select` does. Five icons override `select` with a day test:

  * rm205 `airport`   -- `(if (!= gDay 7) <msg, return 0> else <msg .. self .., return 0>)`:
    returns 0 on BOTH branches, so the map never cues it; on day 7 the message call names
    `self` as its caller and the Messager cues the icon back when the text ends -- THAT is
    the boarding. The destination 750 (the plane) carries `day == 7`.
  * rm205 `grandma` (380), rm200 `voodooShop` (250), `voodooMus` (260), `moonBeam` (290):
    `(return 1)` on the permitting path, `(return 0)` after a refusal message otherwise.

Every other icon inherits `IconI::select` = `(return 1)`: unconditional, as before. And the
first-visit travel movie (rm372, `newRoom: global175`, assigned only from the maps' dispatch)
inherits each value's guard when no register in it is written by either script -- the day is
written by nine scripts, none of them 200/205/372 -- so the phantom any-day flights to Germany
and Africa (docs/GK1-SOFTLOCK-CANDIDATES.md §1.37) close at both hops.

The protocol is DERIVED from the container class (which selector gates which), never spelled
by name; the day value is read from the icon's branch, never typed ([[clause-that-protects-a-
known-answer]]). Runs on the cached GK1 model (built by the suite anyway)."""
import sys

import config
import extract as X
import ir as I
import missability as M
from guard_ast import GAnd, GNot, Pred

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def _leaves(g):
    """{(polarity, repr(core))} over a guard's conjunctive leaves; a nested tree is one leaf."""
    if g is None:
        return set()
    kids = g.kids if isinstance(g, GAnd) else [g]
    out = set()
    for a in kids:
        if isinstance(a, GNot):
            out.add(("neg", repr(a.kid)))
        else:
            out.add(("pos", repr(a)))
    return out


def _register_var(sc):
    chg = sc.by_name["chgRoom"]
    return next(n for ast in chg.methods.values() for n in I.walk(ast)
                if n.get("t") == "Property" and n.get("name") == "register")


def _exit_var(sc, gidx):
    for o in sc.objects:
        for ast in o.methods.values():
            for n in I.walk(ast):
                if n.get("t") != "Send":
                    continue
                _r, msgs = I.send_pairs(n)
                for sel, params in msgs:
                    if sel == "newRoom" and params and I.is_global(params[0]) \
                            and params[0].get("index") == gidx:
                        return params[0]
    return None


def main():
    print("=== test_icon_select_gate: an icon-derived destination carries its click gate ===")
    cfg = config.by_name("gk1")
    s = M.load(cfg=cfg)
    ir = s.em.ir
    base = getattr(ir, "flag_synth_base", None)
    sc205, sc200, sc372 = ir.scripts[205], ir.scripts[200], ir.scripts[372]

    # -- the protocol, derived from the container class ------------------------------------
    gate = getattr(X, "_container_gate", None)
    got = gate(ir, sc205, sc205.by_name["airport"]) if gate else None
    check("the map's container class gates an element's `cue` on its `select` (derived)",
          got is not None and tuple(got[:2]) == ("select", "cue"), f"got {got!r}")
    check("a room object is in no container: no gate",
          gate is not None and gate(ir, sc205, sc205.by_name["rm205"]) is None)

    # -- rm205, the greater New Orleans map --------------------------------------------------
    r205 = X._script_prop_values(ir, sc205, _register_var(sc205))
    check("rm205 -> 750 (the plane): the airport icon boards on day 7 ONLY, via the say:-caller "
          "cue-back on the day-7 branch (both branches return 0)",
          _leaves(r205.get(750)) == {("neg", "123!=7")}, f"got {r205.get(750)!r}")
    check("rm205 -> 380 (grandma): select permits under !g181; cue refuses days >= 7 (early "
          "return read as a path condition)",
          _leaves(r205.get(380)) == {("neg", "181!=0"), ("neg", "123>=7")}, f"got {r205.get(380)!r}")
    for dst in (490, 470, 200, 330, 350):
        check(f"rm205 -> {dst}: an icon with the inherited `(return 1)` select stays unguarded",
              dst in r205 and r205[dst] is None, f"got {r205.get(dst)!r}")

    # -- rm200, the city map ---------------------------------------------------------------
    r200 = X._script_prop_values(ir, sc200, _register_var(sc200))
    check("rm200 -> 250 (voodoo shop): open while day <= 6, and its cue needs !g181",
          _leaves(r200.get(250)) == {("neg", "123>6"), ("neg", "181!=0")}, f"got {r200.get(250)!r}")
    check("rm200 -> 290 (moonbeam): open while day < 5",
          _leaves(r200.get(290)) == {("neg", "123>=5")}, f"got {r200.get(290)!r}")
    l260 = _leaves(r200.get(260))
    check("rm200 -> 260 (museum): the three refusals negated, day <= 6 among them",
          ("neg", "123>6") in l260 and len(l260) == 3
          and any("123==5" in t for _p, t in l260) and any("123==6" in t for _p, t in l260),
          f"got {r200.get(260)!r}")
    check("rm200 -> 205: TWO icons name it (greatNO1/greatNO2), so the value drops its guard",
          205 in r200 and r200[205] is None, f"got {r200.get(205)!r}")
    for dst in (210, 230, 300, 430):
        check(f"rm200 -> {dst}: inherited select, unguarded", dst in r200 and r200[dst] is None,
              f"got {r200.get(dst)!r}")

    # -- the second hop: the first-visit movie inherits the value's guard ----------------------
    v175 = _exit_var(sc372, 175)
    check("rm372 exits on global175", v175 is not None)
    r372 = X.var_room_values(ir, 372, v175) if v175 is not None else {}
    check("rm372 -> 750 rides the day-7 gate: the day register is written by neither script",
          _leaves(r372.get(750)) == {("neg", "123!=7")}, f"got {r372.get(750)!r}")
    check("rm372 -> 380 rides grandma's gate",
          _leaves(r372.get(380)) == {("neg", "181!=0"), ("neg", "123>=7")}, f"got {r372.get(380)!r}")
    check("rm372 -> 200 (an unguarded icon) stays free", 200 in r372 and r372[200] is None)
    if base is not None:
        f449 = f"{base + 449}"
        check("no rm372 guard names flag 449 -- rm205's dispatch raises it on the very path to "
              "the movie, so it may not ride (the write check)",
              not any(f449 + "!=" in t or f449 + "==" in t
                      for g in r372.values() for _p, t in _leaves(g)))
    check("rm372's destination SET is unchanged by the gate (19 rooms)", len(r372) == 19,
          f"got {sorted(r372)}")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
