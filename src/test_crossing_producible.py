"""A crossing must be producible under the value it carries (2026-09-03, GK1 docs §1.44).

The closure arm of `register_value_strandings` asks whether a player who crosses a counter
flip carrying S == b0 can still produce a winning story. It built that player's world with
`_staged_pre` and then set `R := w` BY HAND -- never asking whether the flip step itself has a
live producer under the carried value. GK1's ten presence rows were that: "day 2 with the police
lobby unknown" is a dead end on the far side, and a player who never was, because day 1 ends
only through Grace's "go home", which flag 65 gates, which only the lake's cutscene raises, and
the lake exists only through the radio, the sergeant and Grace's own day-1 topic.

`_staged_pre(..., require_steps=True)` now refuses a crosser whose stage -- or whose flip --
has no live producer (`_step_live`). Pinned on the cached GK1 model in seconds (the full
detector takes an hour there)."""
import sys

import config
import missability as M

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def main():
    print("=== test_crossing_producible: a flip nobody can take is not a seal ===")
    s = M.load(cfg=config.by_name("gk1"))
    base = s.em.ir.flag_synth_base
    s._rp_xcache = {}
    pre_g, _c = s._staged_pre(123, 1, {}, require_steps=True)
    check("the unconfined crosser CAN take the day-1 -> 2 flip (rm370 with the day-end flag)",
          pre_g is not None)
    for f, what in ((63, "the police lobby icon"), (64, "the lake icon"), (66, "the sergeant's flag")):
        s._rp_xcache = {}
        pre_b, _c = s._staged_pre(123, 1, {base + f: {0}}, require_steps=True)
        check(f"carrying flag {f} = 0 ({what}), NOBODY takes the day-1 -> 2 flip: day 1 ends only "
              f"through go-home <- flag 65 <- the lake <- this chain", pre_b is None)
    s._rp_xcache = {}
    pre_old, _c = s._staged_pre(123, 1, {base + 63: {0}})
    check("without `require_steps` the staged PRE still seeds as before (the windows' caller)", pre_old is not None)
    live = s._step_live(123, 1, pre_g[0], pre_g[1], {123: {0, 1}})
    check("`_step_live` names the producer it found (room 370, the day-end flag)",
          live is not None and live[0] == 370 and (base + 15) in live[1], f"got {live}")
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
