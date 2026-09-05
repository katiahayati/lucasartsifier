"""A LOCAL ASSIGNED BY A SWITCH TREE IS A DERIVED REGISTER (2026-09-05, GK1 docs §1.59).

GK1's bayou is the specimen. The whole region hangs on flag 268, whose single writer
(`drumInset.sc:914`) sits under `local0 == 2` -- and `local0` is assigned once, in
`drumInset::init`, by a switch that IS the date:

    local0 = switch global11 { 410 -> switch global123 { 6 -> 2, 7 -> 1, 10 -> 3, else 0 },
                               800 -> 4, else (if (< global123 6) 0 else 1) }

so flag 268 is raisable in room 410 on day 6 and nowhere else. `derive_room_locals` refuses it
three times over -- non-room script, computed rhs, init-only -- and each refusal is right about
a different case, so this is a rule of its own. The chain needs THREE things and this pins all
of them: the local lowered with its arms as guarded writes; the lowering's own writes harvested
from a NON-ROOM script's `init` at the rooms that arm it (they reached no room before, which
would leave the register read everywhere and written nowhere -- "half a store is worse than
none"); and `_consumer_windows` collecting its wants from EDGE requirements, since flag 268 is
demanded by an edge and by no write at all.
"""
import sys

import config
import missability as M
import vocab as V

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def main():
    print("=== test_switch_local: a switch-valued local is a derived register ===")
    s = M.load(cfg=config.by_name("gk1"))
    ir = s.em.ir
    C = 123
    idx = getattr(ir, "_room_local_index", None) or {}
    mode = next((gi for gi, k in idx.items() if k == (815, 0)), None)
    check("GK1's drum-inset mode local (script 815, local0) is lowered",
          mode is not None, f"_room_local_index has no (815, 0); got {sorted(idx.values())[:8]}")
    if mode is None:
        print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
        return not FAIL

    # the switch arms became GUARDED CONSTANT WRITES, one per arm
    arms = {}
    for (R, room, v), brs in s._wbranch.items():
        if R == mode:
            arms.setdefault((room, v), []).extend(d for (d, _c, _co) in brs)
    def has_day(v, day):
        return any(set(d.get(C, ())) == {day} for d in arms.get((410, v), ()))
    check("the day-6 arm is a guarded write of mode 2", has_day(2, 6),
          f"mode-2 branches at rm410: {[{a: sorted(b) for a, b in d.items()} for d in arms.get((410, 2), ())]}")
    # ⛔ ONE ARM PER BRANCH, not one per value: mode 1 is reachable BOTH from `410 -> day 7` and
    # from the outer `else (if (< global123 6) 0 else 1)`, whose `<` is not a recoverable
    # equality, so it contributes an unconditional branch alongside the day-7 one. Folding the
    # branches would hide the day and this check would pass on the wrong evidence.
    check("its sibling arms carry their own days (7 -> mode 1, 10 -> mode 3)",
          has_day(1, 7) and has_day(3, 10),
          f"arms = {[(k, [{a: sorted(b) for a, b in d.items()} for d in v]) for k, v in sorted(arms.items())]}")

    # ...harvested at the rooms that ARM the inset, since script 815 is not a room
    rooms = sorted({room for (R, room, _v) in s._wbranch if R == mode})
    check("the mode's writes reach the rooms that arm the inset (410, 800)",
          410 in rooms and 800 in rooms, f"rooms = {rooms}")

    # the flag's own write demands the mode
    R268 = ir.flag_synth_base + 268
    f268 = [d for (R, room, v), brs in s._wbranch.items() if R == R268 and v == 1
            for (d, _c, _co) in brs]
    check("flag 268's write demands the drum mode",
          f268 and all(mode in d for d in f268),
          f"deps = {[{a: sorted(b) for a, b in d.items()} for d in f268][:3]}")

    # and the window -- which needs `want` collected from EDGE reqs, since no WRITE wants 268
    win = s._consumer_windows().get(C, {})
    w268 = sorted(win.get((R268, 1), []))
    check("flag 268 has a consumer window, and it starts at day 6",
          w268 and min(w268) == 6,
          f"win[268=1] = {w268 or '(none -- `want` is not collecting from edges)'}")

    # THE PAYOFF, in game terms: the bayou is a day-6 place
    for q, nm in ((490, "the bayou maze"), (480, "the bayou ritual")):
        days = sorted({v for (q2, v) in s._pstates[C] if q2 == q})
        check(f"{nm} (rm{q}) cannot be reached before day 6",
              days and min(days) == 6, f"rm{q} days = {days}")

    # THE FENCE: the recogniser admits only provably decomposable trees, and it is not a
    # corpus-wide re-plumbing -- KQ4 has none at all, so KQ4 cannot move.
    # (the recogniser cannot be re-run on THIS ir -- lowering rewrote the Local nodes away, so
    # it correctly finds nothing here. Ask it of a game it must not touch, and unit-test its
    # narrowness directly.)
    kq4 = V.derive_switch_locals(M.load(cfg=config.by_name("KQ4")).em.ir)
    check("KQ4 has no switch-valued locals at all, so it cannot move", not kq4, f"{sorted(kq4)}")
    lit = {"t": "Switch", "kids": [
        {"t": "Variable", "vtype": "Global", "index": 9},
        {"t": "Case", "kids": [{"t": "Number", "value": 1},
                               {"t": "List", "kids": [{"t": "Number", "value": 7}]}]},
        {"t": "Else", "kids": [{"t": "List", "kids": [{"t": "Number", "value": 8}]}]}]}
    computed = {"t": "Switch", "kids": [
        {"t": "Variable", "vtype": "Global", "index": 9},
        {"t": "Case", "kids": [{"t": "Number", "value": 1},
                               {"t": "List", "kids": [{"t": "Number", "value": 7}]}]},
        {"t": "Else", "kids": [{"t": "List", "kids": [
            {"t": "Send", "kids": []}]}]}]}
    check("the recogniser admits an all-literal switch and REFUSES a computed arm",
          V._switch_leaf_values(lit) == (True, [7, 8])
          and V._switch_leaf_values(computed)[0] is False,
          f"literal -> {V._switch_leaf_values(lit)}; computed -> {V._switch_leaf_values(computed)}")

    # ⛔ The lowering files a reset for its script under the SCRIPT NUMBER, which for a non-room
    # script is a room that does not exist (`init_writes[815] = {mode: 0}`). Inert -- no walk can
    # arrive at 815 -- and pinned here so it fails loudly if 815 ever becomes a room, in which
    # case the reset would start asserting a value on arrival somewhere real.
    check("the non-room script's reset lands at a phantom room and stays inert",
          815 not in set(getattr(s.em, "rooms", ()) or []),
          "script 815 is a room now -- its lowered reset is no longer inert")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
