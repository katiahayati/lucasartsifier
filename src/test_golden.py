"""Golden-snapshot lock on the FULL analysis output surface, for both games.

The v1.0-lsl2 tag's behaviour on LSL2 is a CORRECT ORACLE -- 16 softlocks, four dangerous sinks,
its guard specs -- validated by playing the patched game to the ending. This test freezes that whole
surface (softlock items, groups, resource exhaustion, joint-window strandings, edge/gate guard specs,
and sink specs) so it cannot be silently changed. It exists because the sink behaviour was quietly
broken once by a later commit and nearly "fixed" a second time by re-litigating it.

If this test fails, the DEFAULT assumption is that the change is wrong, not the golden. Do not
regenerate the golden to make a red test green without understanding -- and, for LSL2, without the
user's sign-off (its behaviour is the oracle, not something to re-derive).

Regenerate deliberately (after a change you have confirmed is correct):
    python3 -c "import json, config; from snapshot import snapshot; \
        json.dump(snapshot(config.LSL2), open('testdata/lsl2.golden.json','w'), indent=2, sort_keys=True)"
    (and likewise config.KQ4 -> testdata/kq4.golden.json)
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
    print("=== test_golden: the full analysis surface is frozen ===")
    for name, cfg in (("LSL2", config.LSL2), ("KQ4", config.KQ4)):
        path = os.path.join(_HERE, "testdata", f"{name.lower()}.golden.json")
        if not (os.path.exists(cfg.ir_path) and os.path.exists(path)):
            print(f"  (skip {name}: no IR or no golden)")
            continue
        golden = json.load(open(path))
        got = snapshot(cfg)
        check(f"{name}: full output surface matches the frozen golden",
              got == golden, _diff(golden, got))
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
