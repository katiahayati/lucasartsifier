"""Golden-snapshot lock on the FULL analysis output surface for LSL2.

The v1.0-lsl2 tag's behaviour on LSL2 is a CORRECT ORACLE -- 16 softlocks, four dangerous sinks,
its guard specs -- validated by playing the patched game to the ending. This test freezes that whole
surface (softlock items, groups, resource exhaustion, joint-window strandings, edge/gate guard specs,
and sink specs) so it cannot be silently changed. It exists because the sink behaviour was quietly
broken once by a later commit and nearly "fixed" a second time by re-litigating it.

KQ4 is deliberately NOT frozen here: it is still under active development, so its output is expected
to move. Locking it would only fire spurious failures on legitimate KQ4 work. Add it back once its
behaviour is validated the way LSL2's was.

If this test fails, the DEFAULT assumption is that the change is wrong, not the golden. Do not
regenerate the golden to make a red test green without understanding, or without the user's sign-off
(LSL2's behaviour is the oracle, not something to re-derive).

Regenerate deliberately (after a change you have confirmed is correct):
    python3 -c "import json, config; from snapshot import snapshot; \
        json.dump(snapshot(config.LSL2, with_placements=True), \
                  open('testdata/lsl2.golden.json','w'), indent=2, sort_keys=True)"

`with_placements=True` since 2026-08-01: a spec is a claim, a PLACEMENT is whether the patcher
could act on it, and the two move independently. Nothing froze the placement half for any game
until then, so the SCI1.1 placement work could have broken the placements of the one title that
has been played end to end without a test noticing.
"""
import json
import os
import sys

import config
from snapshot import snapshot

PASS, FAIL = [], []
_HERE = os.path.dirname(os.path.abspath(__file__))


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n      {detail}" if detail and not cond else ""))


def _diff(golden, got):
    """Field-by-field difference, so a failure names exactly what moved."""
    lines = []
    for k in sorted(set(golden) | set(got)):
        g, c = golden.get(k), got.get(k)
        if g == c:
            continue
        if isinstance(g, list) and isinstance(c, list):
            added = [x for x in c if x not in g]
            removed = [x for x in g if x not in c]
            lines.append(f"{k}: +{added}  -{removed}")
        else:
            lines.append(f"{k}: golden={g!r} got={c!r}")
    return "\n      ".join(lines)


def run():
    print("=== test_golden: the full analysis surface is frozen (LSL2 only) ===")
    for name, cfg in (("LSL2", config.LSL2),):
        path = os.path.join(_HERE, "testdata", f"{name.lower()}.golden.json")
        if not (os.path.exists(cfg.ir_path) and os.path.exists(path)):
            print(f"  (skip {name}: no IR or no golden)")
            continue
        # PLACEMENTS ARE PART OF THE SURFACE. A correct spec that lands nowhere ships nothing, and
        # until 2026-08-01 no game froze the placement half at all -- so the SCI1.1 placement work
        # (`trigger.py`, `patcher.py`) could silently break the placements of the one title that
        # has actually been played. Needs the game's own resources, because the patcher assembles
        # a project from them; skip rather than fail if the drive is not mounted.
        if not os.path.isdir(cfg.resource_dir):
            print(f"  (skip {name}: resources not mounted at {cfg.resource_dir} -- "
                  f"the placement half of the golden cannot be computed)")
            continue
        golden = json.load(open(path))
        got = snapshot(cfg, with_placements=True)
        check(f"{name}: full output surface matches the frozen golden",
              got == golden, _diff(golden, got))
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
