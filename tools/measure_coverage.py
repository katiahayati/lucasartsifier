"""Of everything the analyzer FOUND, how much does the patch actually GUARD?

    python3 tools/measure_coverage.py gk1
    python3 tools/measure_coverage.py KQ6 --items      # also resolve item ids to names

⛔ WHY THIS EXISTS. `build/build_patch.py` prints only the edits that APPLIED --
`if not e["applied"]: continue` -- so a spec that was derived and then skipped leaves NO TRACE
in a build log. For ten days GK1 read as "the patch is built" while five of its eleven specs
were being dropped for want of a controllable trigger and two of its four shipped guards were
conditioned on an item the record calls a false positive. Nothing lied; nothing asked either.

It prints the DENOMINATOR: every spec `guards` derives, every edit `patcher` returns, applied
and skipped alike with the reason, and the set of items the shipped guards actually demand.

⛔ It writes only into a throwaway project directory (default under $TMPDIR) -- it never touches
an installed game ([[install-patches-by-default]]).
"""
import argparse
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

import config                                                            # noqa: E402
import guards as G                                                       # noqa: E402
import missability as M                                                  # noqa: E402
import patcher as P                                                      # noqa: E402


def _loc(e):
    if e.get("from_room") is not None:
        return "rm%s->rm%s" % (e.get("from_room"), e.get("to_room"))
    for k in ("register", "machine", "anchor", "title"):
        if e.get(k) is not None:
            return "%s %s" % (k, e[k])
    return "?"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game", help="a config name: LSL2, KQ4, KQ6, kq5, dagger, gk1, ...")
    ap.add_argument("--items", action="store_true", help="resolve item ids to names")
    ap.add_argument("--dest", default=None, help="scratch project dir (default: a temp dir)")
    a = ap.parse_args(argv)

    cfg = config.by_name(a.game)
    if cfg is None or not os.path.exists(cfg.ir_path):
        return "no IR for %s" % a.game
    s = M.load(cfg=cfg)
    P.configure(s.em.ir)
    dest = a.dest or os.path.join(tempfile.gettempdir(), "coverage_%s" % a.game)
    nums = P.assemble(dest, cfg)
    titles = {n: t for t, n in nums.items()}

    specs, sinks, res = G.guard_specs(s), G.sink_remedies(s), G.resource_remedies(s)
    print("== DERIVED: %d guard spec(s), %d sink remedy(ies), %d resource remedy(ies) =="
          % (len(specs), len(sinks), len(res)))
    for sp in specs:
        keep = {k: sp[k] for k in ("site", "from_room", "to_room", "items", "item", "register",
                                   "value", "machine", "room", "condition") if k in sp}
        print("   " + json.dumps(keep, default=str)[:240])

    P.install_mode_chooser(dest, titles)
    edits = (P.apply_sink_remedies(dest, sinks, titles)
             + P.apply_resource_remedies(dest, res, titles)
             + P.apply_guards(dest, specs, titles, nums,
                              s_drops=lambda it: s.drops.get(it, set()), rooms=set(s.rooms),
                              entry_frontier=lambda r: G.commit_entry_frontier(s, r),
                              defer_info=lambda sp: G.defer_to_entry(s, sp)))

    print("\n== OUTCOME ==")
    demanded = set()
    for e in edits:
        kind = (e.get("placement") or {}).get("kind") or ""
        if e["applied"]:
            demanded.update(e.get("items") or
                            ([e["item"]] if e.get("item") is not None else []))
            print("  [ok  ] %-22s %-12s" % (_loc(e), kind))
        else:
            print("  [SKIP] %-22s %-12s %s"
                  % (_loc(e), kind, e.get("why") or e.get("reason") or "?"))

    ok = sum(1 for e in edits if e["applied"])
    print("\n%d spec(s) derived -> %d edit(s) attempted -> %d applied, %d skipped"
          % (len(specs) + len(sinks) + len(res), len(edits), ok, len(edits) - ok))
    if len(specs) + len(sinks) + len(res) != len(edits):
        print("⛔ %d spec(s) produced NO EDIT AT ALL -- a spec kind the placement layer has no "
              "site for is the shape that ships nothing and says nothing"
              % (len(specs) + len(sinks) + len(res) - len(edits)))

    names = sorted((s.g.item_name(i) or str(i)) if a.items else str(i) for i in demanded)
    print("items the SHIPPED guards demand: %s" % (names or "(none)"))
    print("\n⛔ An item demanded here is not a softlock guarded. Check the demanded set against "
          "the game's oracle before calling anything covered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
