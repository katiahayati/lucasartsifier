"""A3: tractable full reachability via SCC condensation + goal-aware frontier.

Naive explicit-state BFS over (room, item-subset, flag-subset) explodes: LSL2 has
21 winnability-relevant items, so 2^21 item-subsets alone, and the freely-
explorable early game makes a huge fraction reachable. (Run `full_product_search`
to see it blow past the cap -- that's the classic state-explosion the PLAN flags.)

The tractable *exact* method for a game dominated by irreversibility: condense the
room movement graph into strongly-connected components (SCCs). Within an SCC you
can wander and backtrack freely, so *which* items you hold doesn't matter there --
only at the one-way edges *between* SCCs (the true points of no return) does state
carry forward. The condensation is a small DAG of "acts". We then ask, per
irreversible gate: does crossing it strand a resource the goal still needs?

This subsumes analyze.py's region heuristic with exact freely-reachable regions,
and is goal-aware: it only flags resources on a path that can still reach the
winning ending (the Nontoonyt wedding).
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict, deque

sys.path.insert(0, os.path.dirname(__file__))
from model import load_game, Game                       # noqa: E402
from analyze import (movement_graph, derived_maps, region_maps,  # noqa: E402
                     is_room, irreversible_globals, REGION_LABELS)
from slice import coi_slice                              # noqa: E402
from config import ACTIVE as CFG                         # noqa: E402

START_ROOM = CFG.start_room
GOAL_ROOMS = set(CFG.goal_rooms)


# --------------------------------------------------------------------------
def tarjan_scc(nodes, edges):
    """Return list of SCCs (each a set of rooms), plus comp id per node."""
    index = {}
    low = {}
    onstack = {}
    stack = []
    comps = []
    counter = [0]

    # iterative Tarjan (recursion would overflow on long chains)
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(edges.get(root, ())))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        onstack[root] = True
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    onstack[w] = True
                    work.append((w, iter(edges.get(w, ()))))
                    advanced = True
                    break
                elif onstack.get(w):
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            if low[v] == index[v]:
                comp = set()
                while True:
                    w = stack.pop()
                    onstack[w] = False
                    comp.add(w)
                    if w == v:
                        break
                comps.append(comp)
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
    comp_of = {}
    for i, c in enumerate(comps):
        for n in c:
            comp_of[n] = i
    return comps, comp_of


def reachable(edges, start_set):
    seen = set(start_set)
    q = deque(start_set)
    while q:
        u = q.popleft()
        for v in edges.get(u, ()):
            if v not in seen:
                seen.add(v)
                q.append(v)
    return seen


class SccReach:
    def __init__(self, game: Game):
        self.g = game
        self.coi_items, self.coi_flags, self.latches = coi_slice(game)
        self.edges, self.edge_kind = movement_graph(game)
        self.sources, self.drops, self.required, self.gsets = derived_maps(game)
        self.rooms = [n for n in game.scripts if is_room(game, n)]
        # SCCs of the room movement graph
        self.comps, self.comp_of = tarjan_scc(self.rooms, self.edges)
        # condensation DAG (comp -> comps)
        self.cedges = defaultdict(set)
        for a, bs in self.edges.items():
            for b in bs:
                if a in self.comp_of and b in self.comp_of and self.comp_of[a] != self.comp_of[b]:
                    self.cedges[self.comp_of[a]].add(self.comp_of[b])
        # comps reachable from each comp (transitive)
        self.creach = {c: reachable(self.cedges, {c}) for c in range(len(self.comps))}
        # items obtainable inside each comp
        self.items_in_comp = defaultdict(set)
        for it, srcs in self.sources.items():
            for r in srcs:
                if r in self.comp_of:
                    self.items_in_comp[self.comp_of[r]].add(it)

    def comp_reach_source(self, item):
        """comps from which item is still obtainable (this comp or a downstream one)."""
        srcs = {self.comp_of[r] for r in self.sources.get(item, set()) if r in self.comp_of}
        out = set()
        for c in range(len(self.comps)):
            if self.creach[c] & srcs:
                out.add(c)
        return out

    def analyze(self):
        start_c = self.comp_of.get(START_ROOM)
        reach_from_start = self.creach.get(start_c, set()) if start_c is not None else set()
        goal_comps = {self.comp_of[r] for r in GOAL_ROOMS if r in self.comp_of}
        members, room_region, controllers = region_maps(self.g)

        cands = []
        for item in sorted(self.coi_items):
            if item not in self.required:
                continue  # not read by any guard -> can't gate progress
            srcs = self.sources.get(item, set())
            if not srcs:
                continue
            can_get = self.comp_reach_source(item)
            # comps where the item is needed (a guard reads own(item) in a room there)
            need_comps = set()
            for R in self.required[item]:
                if R in controllers:                # region controller (isolated SCC):
                    for m in members.get(R, ()):    # face the need in its member rooms
                        if m in self.comp_of:
                            need_comps.add(self.comp_of[m])
                elif R in self.comp_of:
                    need_comps.add(self.comp_of[R])
            for c in sorted(need_comps):
                if c not in reach_from_start:
                    continue                         # unreachable context, ignore
                if c in can_get:
                    continue                         # can still fetch it -> fine
                if goal_comps and not (self.creach[c] & goal_comps):
                    continue                         # from here you can't reach goal anyway
                cands.append(self._mk_cand(item, c, srcs, room_region))
        # dedup by (item, need-comp)
        seen, uniq = set(), []
        for c in cands:
            k = (c["item"], c["need_component_id"])
            if k not in seen:
                seen.add(k)
                uniq.append(c)
        return uniq

    def _mk_cand(self, item, need_c, srcs, room_region):
        src_c = sorted({self.comp_of[r] for r in srcs if r in self.comp_of})
        # frontier = one-way edges out of comps that can still reach the item into comps that can't
        can_get = self.comp_reach_source(item)
        fr = []
        for a in can_get:
            for b in self.cedges.get(a, ()):
                if b not in can_get:
                    for ra in self.comps[a]:
                        for rb in self.comps[b]:
                            if rb in self.edges.get(ra, ()):
                                fr.append(f"rm{ra}->rm{rb}")
        need_rooms = sorted(self.comps[need_c])
        need_regs = sorted({r for rm in need_rooms for r in room_region.get(rm, set())})
        return {
            "pattern": "missing-prereq-before-gate",
            "item": item, "item_name": self.g.item_name(item),
            "need_component_id": need_c,
            "need_rooms_sample": need_rooms[:8],
            "need_region": [f"{r}={REGION_LABELS.get(r, r)}" for r in need_regs],
            "source_rooms": sorted(srcs),
            "frontier_edges": sorted(set(fr))[:6],
            "goal_still_reachable_from_need": True,
        }


def main():
    game = load_game()
    s = SccReach(game)
    ncomp = len(s.comps)
    nontrivial = [c for c in s.comps if len(c) > 1]
    print(f"rooms={len(s.rooms)}  SCCs={ncomp}  (non-trivial SCCs: {len(nontrivial)})")
    print(f"COI items={len(s.coi_items)} flags={len(s.coi_flags)}")
    # show the "acts" = large SCCs by region
    print("\nlargest freely-explorable components (acts):")
    for c in sorted(range(ncomp), key=lambda i: -len(s.comps[i]))[:6]:
        rooms = sorted(s.comps[c])
        print(f"  comp {c}: {len(rooms)} rooms  e.g. {rooms[:10]}")
    cands = s.analyze()
    print(f"\ngoal-aware softlock candidates: {len(cands)}")
    for c in cands:
        print(f"  '{c['item_name']}' needed in {c['need_region'] or c['need_rooms_sample']}; "
              f"sources {c['source_rooms']}; frontier {c['frontier_edges']}")

    import json
    acts = []
    for c in sorted(range(len(s.comps)), key=lambda i: -len(s.comps[i])):
        if len(s.comps[c]) > 1:
            acts.append({"component": c, "size": len(s.comps[c]),
                         "rooms": sorted(s.comps[c])})
    out = {
        "method": "SCC-condensation + goal-aware frontier (tractable exact reachability)",
        "note": ("Naive product-state BFS over (room, item-subset, flag-subset) is "
                 "intractable here (21 winnability items => 2^21 subsets; hits the state "
                 "cap). SCC condensation collapses freely-explorable room sets into a DAG "
                 "of acts whose one-way edges are the true points of no return."),
        "coi_slice": {"items": len(s.coi_items), "of_items": len(game.items),
                      "flags": len(s.coi_flags), "of_globals": len(game.globals)},
        "rooms": len(s.rooms), "sccs": len(s.comps),
        "acts_freely_explorable": acts,
        "goal_rooms": sorted(GOAL_ROOMS), "start_room": START_ROOM,
        "softlock_candidates": cands,
    }
    path = os.path.join(os.path.dirname(__file__), "..", "reports", "lsl2_reachability.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote {os.path.normpath(path)}")
    return s, cands


if __name__ == "__main__":
    main()
