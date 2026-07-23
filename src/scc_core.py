"""SCC-condensation reachability core -- front-end AGNOSTIC.

The tractable exact method for a game dominated by irreversibility: condense the room movement
graph into strongly-connected components. Inside an SCC you can wander and backtrack freely, so
WHICH items you hold does not matter there -- state only carries forward across the one-way edges
BETWEEN components, the true points of no return. The condensation is a small DAG of "acts", and
we ask per irreversible gate: does crossing it strand something the goal still needs?

This module operates purely on a generic interface -- (edges, edge_kind, sources, required,
comp_of, creach, goal rooms) -- which `missability.IrSccReach` builds from the JSON IR. It was
extracted from the legacy `search.py`, whose __init__ loaded the EricOakford .sc decompilation;
that front-end is gone, and with it the `_sealed` one-way-edge heuristic this class used to carry
(superseded by the gate-aware walk in IrSccReach).
"""
from __future__ import annotations

from collections import defaultdict, deque

REGION_LABELS = {}          # optional room -> label map for reporting; regions are not in the IR


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
    def comp_reach_source(self, item):
        """comps from which item is still obtainable (this comp or a downstream one)."""
        srcs = {self.comp_of[r] for r in self.sources.get(item, set()) if r in self.comp_of}
        out = set()
        for c in range(len(self.comps)):
            if self.creach[c] & srcs:
                out.add(c)
        return out

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

    def _freely_reversible(self, a, b):
        """Whether you can walk b->a back for FREE, which makes the forward a->b not a commit.

        The base graph has no gate information, so any return edge counts as a free walk -- the
        original behaviour. A gate-aware subclass refines this: an item-gated return (KQ4's whale
        sneeze 44->31 needs the Peacock Feather) is NOT a free walk, so the forward swallow 31->44
        stays a one-way commit for that item. Counting an item-gated return as free is the same
        over-merge that once hid the parachute stranding."""
        return a in self.edges.get(b, set())

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
                if self._freely_reversible(a, b):
                    continue                             # free walk back -> not a commit
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

