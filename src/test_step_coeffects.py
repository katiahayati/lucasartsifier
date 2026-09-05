"""TWO THINGS A COUNTER STEP DOES NOT NECESSARILY DO (2026-09-05, GK1 docs §1.56).

`_step_neco(C, f, t)` answers "what must be true of the OTHER registers once the crosser has
taken the counter step f -> t". Its callers apply the answer as an OVERRIDE -- `pv[R] = {v}`,
plus a confinement when the fact is a monotone latch -- so every entry it invents NARROWS the
modelled player, which is the direction that fabricates dead ends. Two entries were invented.

⭐ (A) A STEP'S CO-EFFECTS ARE WHAT IT DOES TO OTHER REGISTERS. The step's own half of the
function already says so (`cs = {R: v for (R, v) in co if R != C}`); the dep-producer half did
not, so `C` itself could come back as its own necessary co-effect -- [[same-rule-two-places]],
both readings inside one function. GK1 reads `_step_neco(123, 0, 1) = {123: 1, ...}`: "to
advance the day from 0 to 1 the day must become 1", which is the step, not an effect of it.
Harmless at 0 -> 1 and fatal anywhere else: `_apply_neco` runs AFTER the seal arm has seeded
`pv[C] = {w}` by hand, so `pv[123] = {1}` erased the crossing, the post-flip confinement
`{4..11}` intersected it to nothing, and the crosser could not leave the flip room.

⭐ (B) A DEP THE ZERO-INIT ALREADY SATISFIES HAS NO PRODUCER. `_value_neco(S, vs, ...)`
intersects the co-writes of every recorded producer of `S in vs` -- sound only when the player
must have run one of them. Registers are zero-init here (`pv.get(reg, {0})` is the closure's
own floor, §1.41's reading), so a dep admitting 0 is satisfied by never writing S at all and
nothing is necessary. GK1's specimen is flag 470, a PLATFORM test the bayou and dream scripts
spell both ways (`(if (and (== (Platform) 1) (not (proc13_0 470))) ...)` / `(if (proc13_0 470)
...)`), which reaches the branch table as `deps {712: [0, 1]}` -- the register's whole domain,
establishing nothing. Read as a demand, its "producers" are the game's opening at rm93, and
the opening's co-writes (`global123 := 1`, `global179 := 70`) were handed back as facts about
a day-4 crossing.

Both fixes only ever REMOVE entries, so both widen the modelled player: the sound direction.
"""
import sys

import config
import missability as M

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def main():
    print("=== test_step_coeffects: what a counter step does NOT necessarily do ===")
    s = M.load(cfg=config.by_name("gk1"))
    C = 123
    check("GK1's day counter is a counter", C in getattr(s, "_counters", ()),
          f"counters = {sorted(getattr(s, '_counters', ()))}")

    # --- (A) -----------------------------------------------------------------------------
    dom = sorted(set(s.em.reg_vals.get(C, ())) | {0})
    selfref = {(f, f + 1): s._step_neco(C, f, f + 1) for f in dom
               if C in s._step_neco(C, f, f + 1)}
    check("no step of the day counter reports the day as its own co-effect",
          not selfref, f"self-referential steps: { {k: dict(v) for k, v in selfref.items()} }")

    # ...and the seal arm's by-hand flip keeps the value it seeded. This is the consequence
    # that matters: `_apply_neco` must not erase `pv[C] = {w}`.
    pv = {C: {0, 1, 2, 3, 4}}
    s._apply_neco(C, 4, pv, {})
    check("_apply_neco leaves the crossing value in the crosser's hand",
          4 in pv.get(C, ()), f"pv[{C}] = {sorted(pv.get(C, ()))} after the 3 -> 4 flip")

    # --- (B) -----------------------------------------------------------------------------
    # flag 470 (register 712) is the platform test both bayou and dream spell in both
    # directions, so its dep spans the register's whole domain.
    plat = 712
    check("GK1's platform flag is a two-valued register",
          set(s.em.reg_vals.get(plat, ())) == {0, 1},
          f"reg_vals[{plat}] = {sorted(s.em.reg_vals.get(plat, ()))}")
    check("a dep the zero-init satisfies yields no necessary co-effect",
          s._value_neco(plat, {0, 1}, C, 3, 3, frozenset()) == {}
          and s._value_neco(plat, {0}, C, 3, 3, frozenset()) == {},
          f"vs={{0,1}} -> {s._value_neco(plat, {0, 1}, C, 3, 3, frozenset())}; "
          f"vs={{0}} -> {s._value_neco(plat, {0}, C, 3, 3, frozenset())}")

    # ...and the rule must not gut a dep the zero-init does NOT satisfy: the day step's own
    # dependency is `flag 15 == 1`, and its clear is exactly the fact §1.45 landed.
    dayend = s.em.ir.flag_synth_base + 15
    check("the day-end flag's clear survives -- a 1-valued dep still has producers",
          s._step_neco(C, 3, 4).get(dayend) == 0,
          f"_step_neco({C},3,4) = { {k: v for k, v in sorted(s._step_neco(C, 3, 4).items())} }; "
          f"day-end flag register = {dayend}")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
