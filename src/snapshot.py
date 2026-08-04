"""Honest regression snapshot: the FULL analysis+patch output surface for a game, as a canonical
dict, so any change can be diffed. The lesson that motivated it: "findings identical" is NOT
"unregressed" -- guard specs, sink specs and patch placements can move while the item list does not
(the LSL2 anchor derivation added a spurious rm10->90 guard spec that the item list never showed).

Usage:
    python3 snapshot.py LSL2 > /tmp/lsl2.before      # then make a change, re-run, diff
    python3 snapshot.py LSL2 --start 21              # override an anchor to compare
"""
from __future__ import annotations

import dataclasses
import json
import sys

import config
import missability as M
import guards as G


def snapshot(cfg, with_placements=False):
    s = M.load(cfg=cfg)
    # EVERY DETECTOR THAT PRODUCES A VERDICT BELONGS IN HERE, and the reason is that each one
    # added late was, until it was added, emitting into the dark: `toll_strandings` had four KQ6
    # rows with no golden, no oracle and no diff able to notice one appearing or vanishing.
    #
    # ⚠️ THERE ARE THREE DEFINITIONS OF "CAUGHT" IN THIS CODEBASE and they are not the same set:
    #     this file            -- the FROZEN surface, and the only one that is a regression net
    #     test_kq4_ground_truth -- analyze | joint | exhaustion | dangerous_sinks | register_flip
    #     test_kq6_ground_truth -- the above, plus fatal_uses and toll
    # The oracles are per-game verdict lists and may legitimately differ; THIS one may not be the
    # narrowest of the three, because a detector outside it cannot move any golden. That is what
    # `dangerous_sinks` and `fatal_uses` were until 2026-07-31 -- both carry real LSL2 and KQ6
    # verdicts (the rejuvenator sinks; KQ6's mint, peppermint and skull) and neither was frozen
    # anywhere. Adding a detector? Add it here too, or it is not watched.
    #
    # `register_strandings` joined 2026-08-02, the day it turned CAUSAL and its one surviving KQ6
    # row was user-confirmed (the letter). It had been deliberately absent while degenerate --
    # freezing 323 junk rows would have pinned the breakage rather than revealed it.
    items = sorted({c["item"] for c in s.analyze()} | {j["item"] for j in s.joint_strandings()}
                   | {r["item"] for r in s.register_flip_strandings()}
                   | {t["item"] for t in s.toll_strandings()}
                   | {d["item"] for d in s.dangerous_sinks()}
                   | {f["item"] for f in s.fatal_uses()}
                   | {r["item"] for r in s.register_strandings()})
    snap = {
        "start_room": s.em.cfg.start_room,
        "goal_rooms": sorted(s.em.cfg.goal_rooms),
        "death_signal": list(s.em.cfg.death_signal),
        "debug_globals": sorted(s.em.cfg.debug_globals),
        "softlock_items": [s.g.item_name(i) for i in items],
        "groups": sorted(" or ".join(r["item_names"]) + f"@{r['need_room']}"
                         for r in s.group_strandings()),
        "exhaustion": sorted(f"{r['item_name']}@{r.get('at_rooms', r['at_room'])}"
                             f"->{r['still_needed_at']}" for r in s.resource_exhaustion()),
        "joint": sorted(f"{f['item_name']}@{f['stranded_at']}" for f in s.joint_strandings()),
        "tolls": sorted(f"{t['item_name']}@{t['pattern']}"
                        f"/rm{t['toll_edge'][0]}->rm{t['toll_edge'][1]}"
                        for t in s.toll_strandings()),
        # The dangerous ACTIONS. Keyed by the WITNESS room rather than the room the clause was
        # found in: a Main-scope sink is attributed to pseudo-room 0 and `_sink_rooms` widens it
        # to every room, so `at_room` is the first place the consumption actually costs you the
        # game -- which is the fact worth freezing.
        #
        # `still_needed_at` is frozen as a COUNT, not a list. The identity of the finding is
        # (item, witness room); where it is still needed is derived from the room graph, and for
        # a Main-scope sink it is most of the game -- KQ4's Magic_Fruit lists 96 rooms. Pinning
        # those numbers would churn this golden on any room-graph change, which `edge_specs`
        # already tracks properly, and would bury the signal that actually matters here: a
        # dangerous action appearing or disappearing.
        "dangerous": sorted(f"{s.g.item_name(d['item'])}@rm{d['at_room']}"
                            f"->{len(d['still_needed_at'])} rooms" for d in s.dangerous_sinks()),
        "fatal_uses": sorted(f"{s.g.item_name(f['item'])}@rm{f['room']}/{f['machine']}"
                             for f in s.fatal_uses()),
        # The register-flip points of no return -- one frozen row per (register, value, item).
        # Empty on LSL2/KQ4 (measured when the causality conjunct landed: every old row there was
        # region-junk); KQ6 carries the user-confirmed letter.
        "register_strandings": sorted(f"{r['item_name']}@reg{r['register']}={r['value']}"
                                      f"->{r['still_needed_at']}"
                                      for r in s.register_strandings()),
    }
    specs = G.guard_specs(s)
    # REFUSED specs are marked, not hidden and not shown as if we emit them. `pipeline.py` prints
    # them under a REFUSED banner and the patcher skips them, so a snapshot that lists a refused
    # condition beside a real one claims we guard an edge we deliberately leave alone.
    snap["edge_specs"] = sorted(f"rm{sp['from_room']}->rm{sp['to_room']}: {sp['condition']}"
                                + (" [REFUSED]" if sp["refused"] else "")
                                for sp in specs if sp["site"] == "edge")
    snap["gate_specs"] = sorted(f"rm{sp['room']}/{sp['state']}: {sp['condition']}"
                                for sp in specs if sp["site"] == "gate")
    snap["sinks"] = sorted(f"{s.g.item_name(sk['item'])} dest={sk.get('dest')} "
                           f"refused={bool(sk['refused'])}" for sk in G.sink_remedies(s))
    if with_placements:
        # THE OTHER HALF OF THE SURFACE. A spec is a claim; a PLACEMENT is whether the patcher
        # could act on it, and the two move independently -- a correct spec that lands nowhere
        # ships nothing, and the only record of that has been a tool's stdout.
        #
        # The SKIP REASON is frozen alongside the flag, because "it did not place" and "it did not
        # place FOR A DIFFERENT REASON THAN LAST WEEK" are different facts and only the second one
        # tells you a seam moved.
        import shutil
        import tempfile
        import patcher as P
        dest = tempfile.mkdtemp(prefix="snap_" + cfg.name[:4].replace(" ", "_") + "_")
        try:
            sinks = G.sink_remedies(s)
            P.configure(s.em.ir)
            nums = P.assemble(dest, cfg)
            titles = {n: t for t, n in nums.items()}
            edits = P.apply_sink_remedies(dest, sinks, titles)
            gedits = P.apply_guards(dest, specs, titles, nums,
                                    s_drops=lambda it: s.drops.get(it, set()),
                                    rooms=set(s.rooms),
                                    entry_frontier=lambda r: G.commit_entry_frontier(s, r))
            snap["placements"] = sorted(
                # The ITEM is in the key because a sink edit is identified by (script, item) and
                # three of LSL2's land in Main -- without it they are three identical strings and
                # a regression in one of them cannot be told from a regression in another.
                f"{e.get('title') or ('rm%s->rm%s' % (e.get('from_room'), e.get('to_room')))}"
                + (f"/{s.g.item_name(e['item'])}" if e.get("item") is not None else "")
                + f": applied={e['applied']} kind={e.get('placement', {}).get('kind')}"
                + (f" why={e['why']}" if not e["applied"] and e.get("why") else "")
                for e in edits + gedits)
        finally:
            shutil.rmtree(dest, ignore_errors=True)   # a fresh project per run, not per session
    return snap


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "LSL2"
    cfg = config.by_name(name)      # LSL2/KQ4/KQ6, or any build/sweep/<name> title
    if cfg is None:
        raise SystemExit(f"no such game: {name} (and no IR under build/sweep/{name})")
    overrides = {}
    if "--start" in sys.argv:
        overrides["start_room"] = int(sys.argv[sys.argv.index("--start") + 1])
    if "--goal" in sys.argv:
        overrides["goal_rooms"] = frozenset({int(sys.argv[sys.argv.index("--goal") + 1])})
    if overrides:
        cfg = dataclasses.replace(cfg, **overrides)
    print(json.dumps(snapshot(cfg, with_placements="--placements" in sys.argv), indent=2))


if __name__ == "__main__":
    main()
