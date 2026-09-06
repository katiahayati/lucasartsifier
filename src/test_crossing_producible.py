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
    # -- exact stages and the banned item (§1.48) ------------------------------------------------
    s._rp_xcache = {}
    check("the control crosser takes the day-4 -> 5 flip with every item",
          s._staged_pre(123, 4, {}, require_steps=True)[0] is not None)
    for it, w, what in ((32, 5, "the first tomb sketch: day 4 ends only by showing it"),
                        (38, 4, "reconVeve: day 3's arm demands it"),
                        (40, 4, "the bracelet mold: day 3's arm demands its use")):
        check(f"banning item {it} ({what}), nobody takes the flip into day {w}: its flat row is an FP",
              s._closure_flip_dead(123, w, it), f"flip_dead = {s._closure_flip_dead(123, w, it)}")
    # ⭐ PROMOTED 2026-09-05 (docs GK1 §1.66). This check used to read "the croc mask's day-7 row
    # STANDS: nobody reaches day 7 in the record, so the mask is not the difference" -- a pin on
    # the §1.34 gap. With the day fan modelled and bounded (1.34 + the windows/prune fixpoint),
    # day 7 IS reached, and the answer flips to what the scripts say: day 6 ends at the bayou
    # ritual, whose `roomScript` state 81 demands flag 216, and 216 is raised ONLY by using the
    # mask in the maze (rm490, verb 31). So a maskless player never crosses into day 7, and the
    # mask IS the difference.
    check("the croc mask IS the difference at the day-6 -> 7 flip: 216 gates the ritual's own "
          "day advance and only the maze's mask-use raises it",
          s._closure_flip_dead(123, 7, 21),
          f"flip_dead(123, 7, crocMask) = {s._closure_flip_dead(123, 7, 21)} -- if this is False "
          f"again, the day-6 ending has gone missing from the model (docs 1.34/1.62)")
    live = s._step_live(123, 1, pre_g[0], pre_g[1], {123: {0, 1}})
    check("`_step_live` names the producer it found (room 370, the day-end flag)",
          live is not None and live[0] == 370 and (base + 15) in live[1], f"got {live}")
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
