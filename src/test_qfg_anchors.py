"""QFG-VGA anchors: the combat arenas are NOT the ending.

The derived goal set for QFG-VGA was the ten combat arenas plus CharSave -- rooms the player
visits dozens of times and always leaves (docs/QFG-STATE-EXPLOSION.md §8.5). They read terminal
because their exit is `(global2 newRoom: global12)` -- a return to the PREVIOUS room -- written in
the `Arena` class (script 211) that all ten inherit, and the model resolved neither the
inheritance nor the prevRoom destination. A goal set like that answers every requirement question
against the wrong end of the game, and unlike an EMPTY goal set (`missability._build` raises)
nothing catches a WRONG one -- this test is that catch, at the anchor level.

Pinned WRONGNESS only: no arena may be a goal, and every arena must have a way back out. What
the goal set derives TO once the arenas fall away is a measurement for the report, not an
assertion here -- pinning it before it is understood would freeze whatever the first run says.

Skips cleanly when the QFG-VGA IR is absent (it is a sweep title, not a repo artifact).

Run: python3 test_qfg_anchors.py
"""
import sys
sys.path.insert(0, ".")

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

ARENAS = (425, 430, 435, 440, 445, 450, 455, 460, 465)


def run():
    import os
    import config
    cfg = config.by_name("qfgvga")
    if cfg is None or not os.path.exists(cfg.ir_path):
        print("  (skip: no QFG-VGA IR under build/sweep/qfgvga)")
        return 0
    import missability as M
    import anchors as A
    em = M.load(cfg=cfg).em
    edges = A.movement_edges(em)
    print("-- every arena leaves again (the Arena-class return is modelled) --")
    for a in ARENAS:
        outs = set(edges.get(a, ())) - {a}
        check(f"arena {a} has a way out", bool(outs), "no out-edges")
    print("-- and none of them is mistaken for the ending --")
    start, goals = A.discover(em)
    hit = sorted(set(goals) & set(ARENAS))
    check("no combat arena is a goal", not hit, f"goals include arenas {hit}")
    check("a goal still exists at all", bool(goals), "empty goal set")
    print(f"   (derived start={start}, goals={sorted(goals)})")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(run())
