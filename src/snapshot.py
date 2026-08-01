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
    # `toll_strandings` is in here because for a long time it was NOT, and nothing watched it: four
    # KQ6 rows existed with no golden, no oracle and no diff able to notice one appearing or
    # vanishing. It is a detector like any other and its verdicts are verdicts.
    items = sorted({c["item"] for c in s.analyze()} | {j["item"] for j in s.joint_strandings()}
                   | {r["item"] for r in s.register_flip_strandings()}
                   | {t["item"] for t in s.toll_strandings()})
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
        import os
        import patcher as P
        dest = "/tmp/claude-1001/-home-hayati-coding-sierra-softlock/" \
               "cb80156b-500f-4df2-9e56-07e29b8b3ced/scratchpad/_snap_" + cfg.name[:4]
        sinks = G.sink_remedies(s)
        P.configure(s.em.ir)
        nums = P.assemble(dest, cfg)
        titles = {n: t for t, n in nums.items()}
        edits = P.apply_sink_remedies(dest, sinks, titles)
        gedits = P.apply_guards(dest, specs, titles, nums, s_drops=lambda it: s.drops.get(it, set()))
        snap["placements"] = sorted(
            f"{e.get('title') or ('rm%s->rm%s' % (e.get('from_room'), e.get('to_room')))}: "
            f"applied={e['applied']} kind={e.get('placement', {}).get('kind')}"
            for e in edits + gedits)
    return snap


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "LSL2"
    cfg = getattr(config, name)
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
