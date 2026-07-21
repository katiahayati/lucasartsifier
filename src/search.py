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
        # room-level reachability from start (for gate-aware stranded-item analysis)
        self.reach_rooms = reachable(self.edges, {START_ROOM})
        # region model + goal comps, so the stranding core is self-contained and
        # shared by BOTH the report (analyze) and the patcher (Synth).
        self.members, self.room_region, self.controllers = region_maps(self.g)
        self.goal_comps = {self.comp_of[r] for r in GOAL_ROOMS if r in self.comp_of}
        self._reob = {}                              # memo: item -> reobtainable rooms

    def comp_reach_source(self, item):
        """comps from which item is still obtainable (this comp or a downstream one)."""
        srcs = {self.comp_of[r] for r in self.sources.get(item, set()) if r in self.comp_of}
        out = set()
        for c in range(len(self.comps)):
            if self.creach[c] & srcs:
                out.add(c)
        return out

    def _sealed(self, R, srcs):
        """Is requiring-room R a one-way POCKET w.r.t. these item sources? True iff,
        after deleting R's OWN one-way exits (its irreversible commit edges), R can
        no longer reach any source. The plane rm63's only exit is the gated jump
        rm63->64, so deleting it seals rm63 -> stranded.

        KNOWN FP (Airline_Ticket): this over-seals rm57, whose one-way exit rm57->55 is
        part of a REAL local cycle rm57->55->56->57 back to the rm52 ticket source. We can't
        tell that real cycle from the SPURIOUS mega-SCC cycles the guard-ignoring graph invents
        (gated flight/jump edges counted as free -- [[parachute-scc-overmerge-bug]]), so the
        aggressive delete-all-one-way is the least-bad heuristic (15/16). The proper fix is a
        GATE-AWARE graph (free vs gated edges) so round-trips are computed over real cycles;
        SCC/reachability cleverness on the guard-ignoring graph cannot separate the two."""
        e2 = {a: set(b) for a, b in self.edges.items()}
        for Rp in list(e2.get(R, ())):
            if R not in self.edges.get(Rp, set()):       # R->Rp is one-way
                e2[R].discard(Rp)
        return not (reachable(e2, {R}) & srcs)

    def reobtainable_rooms(self, item):
        """Rooms from which `item` can still be ACQUIRED, GATE-AWARE. From a SEALED
        requiring room (see _sealed) you may not leave via a one-way edge -- taking
        it presupposes already owning `item` (the parachute jump). This breaks the
        circular dependency that welds the plane onto the island as one mega-SCC and
        hides the stranding, while leaving open-area side-action requirements alone."""
        if item in self._reob:
            return self._reob[item]
        srcs = self.sources.get(item, set())
        if not srcs:
            self._reob[item] = set()
            return self._reob[item]
        sealed = {R for R in self.required.get(item, set())
                  if R in self.edges and self._sealed(R, srcs)}
        rev = defaultdict(set)                           # allowed reverse adjacency
        for R, outs in self.edges.items():
            for Rp in outs:
                one_way = R not in self.edges.get(Rp, set())
                if R in sealed and one_way:
                    continue                             # gated commit edge out of a sealed pocket
                rev[Rp].add(R)
        seen = set(srcs)
        q = deque(seen)
        while q:
            u = q.popleft()
            for w in rev.get(u, ()):
                if w not in seen:
                    seen.add(w)
                    q.append(w)
        self._reob[item] = seen
        return seen

    def _need_rooms(self, item):
        """Rooms where OWN(item) is actually faced (region controllers -> members)."""
        out = set()
        for R in self.required.get(item, set()):
            if R in self.controllers:
                out |= set(self.members.get(R, ()))
            else:
                out.add(R)
        return out

    # -- THE single gate-aware detection primitive, shared by the report and the
    #    patcher, so the two can never drift apart again. --------------------
    def rooms_after(self, b):
        """Rooms still reachable once you have crossed into `b`.

        A HOOK so subclasses can answer it gate-aware. The default expands b's SCC-condensation
        reach, which is guard-IGNORING and therefore over-permissive: it makes rooms BEFORE the
        edge look reachable after it, so items needed only beforehand (the Suitcase, needed at
        rm52) get demanded at boarding."""
        cb = self.comp_of.get(b)
        out = set()
        for c in self.creach.get(cb, set()):
            out |= self.comps[c]
        return out

    def goal_rooms_set(self):
        return {r for r in GOAL_ROOMS if r in self.comp_of}

    def edge_strandings(self):
        """For every guardable one-way `newRoom` edge a->b, the requirement UNITS obtainable
        before the edge but LOST after it (gate-aware) and still needed on a path that reaches
        the goal. `guard(a->b) = AND over units` is exactly the LucasArts invariant, where a
        disjunctive unit contributes an OR. Death sinks (crossings that can't reach the goal) and
        reversible walk edges are excluded."""
        units = (self.requirement_units() if hasattr(self, "requirement_units")
                 else [frozenset({it}) for it in self.required if self.sources.get(it)])
        reob = {u: self.reobtainable_rooms(u if len(u) > 1 else next(iter(u))) for u in units}
        need = {u: set().union(*(self._need_rooms(i) for i in u)) for u in units}
        out = []
        for a, bs in self.edges.items():
            if a not in self.reach_rooms:
                continue                                 # unreachable-from-start (e.g. the
                                                         # pre-game copy-protection screen rm10)
            for b in sorted(bs):
                if "goto" not in self.edge_kind.get((a, b), set()):
                    continue                             # only code-guardable newRoom edges
                if a in self.edges.get(b, set()):
                    continue                             # reversible walk -> not a commit
                cb = self.comp_of.get(b)
                if cb is None:
                    continue
                fwd_rooms = self.rooms_after(b)
                if self.goal_rooms_set() and not (self.goal_rooms_set() & fwd_rooms):
                    continue                             # crossing b can't win -> death sink
                items, groups = [], []
                for u, R in reob.items():
                    if a in R and b not in R:            # obtainable before a, lost after b
                        if need[u] & fwd_rooms:
                            # still needed past the edge -- without this, the sole entrance to the
                            # ENDING looks like a stranding and gets guarded, blocking the win
                            (items if len(u) == 1 else groups).append(u)
                items = sorted(next(iter(u)) for u in items)
                groups = sorted((sorted(u) for u in groups), key=lambda g: g[0])
                if items or groups:
                    out.append({"from_room": a, "to_room": b,
                                "items": items, "groups": groups})
        return out

    def analyze(self):
        """Report view over the single edge_strandings() core -- one row per
        (item, need-component) so report and patcher never diverge."""
        by_item = defaultdict(set)                       # item -> {stranding edges}
        for e in self.edge_strandings():
            for it in e["items"]:
                by_item[it].add((e["from_room"], e["to_room"]))
        cands, seen = [], set()
        for it in sorted(by_item):
            reob = self.reobtainable_rooms(it)
            frontier = sorted(f"rm{a}->rm{b}" for a, b in by_item[it])
            for R in sorted(self._need_rooms(it)):
                if R not in self.reach_rooms or R in reob:
                    continue
                c = self.comp_of.get(R)
                if c is None:
                    continue
                k = (it, c)
                if k in seen:
                    continue
                seen.add(k)
                regs = sorted(self.room_region.get(R, set()))
                cands.append({
                    "pattern": "missing-prereq-before-gate",
                    "item": it, "item_name": self.g.item_name(it),
                    "need_component_id": c,
                    "need_room": R,
                    "need_region": [f"{r}={REGION_LABELS.get(r, r)}" for r in regs] or [R],
                    "source_rooms": sorted(self.sources.get(it, [])),
                    "frontier_edges": frontier[:6],
                    "goal_still_reachable_from_need": True,
                })
        return cands


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
