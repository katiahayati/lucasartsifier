"""Emit every game's patched SOURCE TREE, so two revisions can be diffed byte for byte.

WHY THIS IS NOT THE SNAPSHOT SURFACE. `snapshot.py` freezes whether a guard landed -- `applied`,
`kind`, `sites`, the skip reason -- and never one byte of the source text a placement produced.
Every fix to the text arithmetic in `patcher.py` (the span walk, the candidate scan, which `(if`
a demand is conjoined onto, where the marker goes) is therefore INVISIBLE to a green snapshot
run. A guard that moved to the wrong site, or that commented out the arming it was meant to
hold, reads as "no regression" ([[measure-the-emitted-bytes]]).

HOW TO USE IT -- two runs and a recursive diff. The control is a git worktree at the last commit
before the change:

    git worktree add /tmp/pre <pre-change-commit>
    python3 tools/measure_emitted_bytes.py /tmp/pre/src  /tmp/emit_pre
    python3 tools/measure_emitted_bytes.py "$PWD/src"    /tmp/emit_now
    diff -r /tmp/emit_pre /tmp/emit_now && echo "BYTE-IDENTICAL"

Both runs read the same build trees and the same IR, so any difference in the output is a
difference the change made. `--games` narrows the set; with no flag it does all five.

⛔ IT WRITES ONLY WHERE YOU POINT IT. `assemble` copies the game's decompiled sources into
`<out>/<game>` and the appliers rewrite them in place; nothing here touches `~/sierra/Games`,
`/mnt/i`, or any installed patch ([[install-patches-by-default]]).
"""
import argparse
import os
import shutil
import sys

GAMES = ("LSL2", "KQ4", "KQ6", "dagger", "kq5")


def emit(src_dir, out_dir, games):
    sys.path.insert(0, src_dir)
    import config                                                        # noqa: E402
    import guards as G                                                   # noqa: E402
    import missability as M                                              # noqa: E402
    import patcher as P                                                  # noqa: E402

    done, skipped = [], []
    for name in games:
        cfg = config.by_name(name)
        if cfg is None or not os.path.exists(cfg.ir_path):
            skipped.append(name)
            print("SKIP %s -- no IR" % name)
            continue
        s = M.load(cfg=cfg)
        specs, sinks = G.guard_specs(s), G.sink_remedies(s)
        dest = os.path.join(out_dir, name)
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest)
        P.configure(s.em.ir)
        nums = P.assemble(dest, cfg)
        titles = {n: t for t, n in nums.items()}
        P.apply_sink_remedies(dest, sinks, titles)
        P.apply_guards(dest, specs, titles, nums,
                       s_drops=lambda it: s.drops.get(it, set()), rooms=set(s.rooms),
                       entry_frontier=lambda r: G.commit_entry_frontier(s, r),
                       defer_info=lambda sp: G.defer_to_entry(s, sp))
        done.append(name)
        print("DONE %s -> %s" % (name, dest))
    print("emitted %d game(s): %s%s"
          % (len(done), ", ".join(done),
             ("  (skipped %s)" % ", ".join(skipped)) if skipped else ""))
    return 0 if done else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", help="the src/ directory to run the patcher FROM")
    ap.add_argument("out", help="directory to emit the patched source trees into")
    ap.add_argument("--games", default=",".join(GAMES),
                    help="comma-separated game names (default: all five)")
    a = ap.parse_args()
    return emit(os.path.abspath(a.src), os.path.abspath(a.out),
                [g for g in a.games.split(",") if g])


if __name__ == "__main__":
    sys.exit(main())
