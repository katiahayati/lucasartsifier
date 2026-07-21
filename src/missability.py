"""Missability sweep on the JSON-IR / smv_emit3 front-end (the canonical one), NOT the stale
model.Game / analyze.py front-end that search.py was left on.

search.py's SCC-condensation *algorithm* (tarjan_scc, reobtainable_rooms/_sealed,
edge_strandings, analyze) is sound and front-end-agnostic -- it operates on a generic
(room-graph, item-sources, required-set, goal) interface. This module builds that interface
from the JSON-IR OpEmitter so the sweep inherits every extraction fix the winnability engine
already has: the revolving-door indirect-newRoom resolution (rm40 -> rm43/44/45, which makes
Matches' room reachable), debug-global pinning, etc. Then it just subclasses SccReach.
"""
from __future__ import annotations

import os
from collections import defaultdict

import ir as I
import config
import smv_emit3 as E
from model import GAnd, GOr, GNot, Pred
from search import tarjan_scc, reachable, SccReach

# item names are a reporting nicety; the IR JSON carries none, so keep a local map (LSL2). The
# ANALYSIS is fully on JSON-IR -- only these labels are game-specific.
_NAMES = {1:"Dollar_Bill",2:"Lottery_Ticket",3:"Cruise_Ticket",4:"Million_Dollar_Bill",
    5:"Swimsuit",6:"Wad_O_Dough",7:"Passport",8:"Grotesque_Gulp",9:"Sunscreen",10:"Onklunk",
    11:"Fruit",12:"Sewing_Kit",13:"Spinach_Dip",14:"Wig",15:"Bikini_Top",16:"Bikini_Bottom",
    17:"Knife",18:"Soap",19:"Matches",20:"Flower",21:"Hair_Rejuvenator",22:"Suitcase",
    23:"Airline_Ticket",24:"Parachute",25:"Bobby_Pin",26:"Pamphlet",27:"Airsick_Bag",
    28:"Stout_Stick",29:"Vine",30:"Ashes",31:"Sand"}


class _NameShim:
    def item_name(self, it):
        return _NAMES.get(it, f"item{it}")


def _own_positive(guard):
    """Item numbers that appear as a POSITIVE own(item) in `guard` (a guard-tree, a list of
    atoms as machine-state guards carry, or None)."""
    out = set()
    def walk(g, pol):
        if g is None:
            return
        if isinstance(g, list):
            for x in g:
                walk(x, pol)
        elif isinstance(g, Pred):
            if g.kind == "OWN" and pol:
                out.add(g.var)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                walk(k, pol)
        elif isinstance(g, GNot):
            walk(g.kid, not pol)
        # ("CTR",...) / ("POS",...) tuples carry no OWN
    walk(guard, True)
    return out


def _death_reachable(info):
    """States of this machine from which a DEATH is reachable (backward closure over
    ADVANCE/JUMP/SETSTATE). Used to spot TRAP gates -- an own(item) branch that walks into a
    death is not a requirement (Spinach_Dip's spoiled mayonnaise)."""
    succ, dead = defaultdict(set), set()
    for K, paths in info["states"].items():
        for (g, w, gg, c, tr) in paths:
            if tr[0] == "DEATH":
                dead.add(K)
            elif tr[0] == "ADVANCE":
                succ[K].add(K + 1)
            elif tr[0] == "JUMP":
                succ[K].add(tr[1])
            elif tr[0] == "SETSTATE":
                succ[K].add(tr[1] + 1)
    out, changed = set(dead), True
    while changed:
        changed = False
        for K, ss in succ.items():
            if K not in out and (ss & out):
                out.add(K); changed = True
    return out


def build_maps(em):
    """(edges, edge_kind, sources, drops, required) from the JSON-IR OpEmitter."""
    edges, edge_kind = defaultdict(set), defaultdict(set)
    md = em.machine_delivered

    def add(a, b):
        edges[a].add(b); edge_kind[(a, b)].add("goto")   # every JSON-IR movement is a newRoom

    for e in em.ts.edges:
        add(e.src, e.dst)
    for e in em.ts.cs_edges:
        if (e.src, e.dst) not in md:
            add(e.src, e.dst)
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    add(info["room"], tr[1])

    # sources: skip DEAD debug-gated acquires (rm82's `(if gDebugging (get 19 21 27))` bomb
    # hand-out). The JSON-IR TRACKS gDebugging rather than const-pinning it, so gexpr won't
    # fold `gDebugging != 0` to FALSE -- and the IR json carries no global names, so we can't
    # resolve config.debug_globals to indices from it. TODO(generalize): pin debug globals in
    # the emitter / carry a name->index map. For now use the known LSL2 debug indices.
    DEBUG_IDX = frozenset({100, 111})   # gDebugging, gForceAtest
    def _debug_gated(guard):
        refs = set()
        def w(g):
            if isinstance(g, list):
                for x in g: w(x)
            elif isinstance(g, Pred):
                if g.var in DEBUG_IDX:
                    refs.add(g.var)
            elif isinstance(g, (GAnd, GOr)):
                for k in g.kids: w(k)
            elif isinstance(g, GNot):
                w(g.kid)
        w(guard)
        return bool(refs)
    sources, drops = defaultdict(set), defaultdict(set)
    for a in em.ts.acqs:
        if not _debug_gated(a.guard):
            sources[a.item].add(a.room)
    for room, script, it, g in em.handler_gets:
        if not _debug_gated(g):
            sources[it].add(room)
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                for it in gg:
                    sources[it].add(info["room"])

    # required: rooms whose guard tests own(item)==True (across every guard-bearing structure).
    required = defaultdict(set)
    def req(guard, room):
        for it in _own_positive(guard):
            required[it].add(room)
    for e in em.ts.edges:
        req(e.guard, e.src)
    for e in em.ts.cs_edges:
        req(e.guard, e.src)
    for a in em.ts.acqs:
        req(a.guard, a.room)
    for room, script, it, g in em.handler_gets:
        req(g, room)
    for room, script, gi, v, g in em.handler_writes:
        req(g, room)
    for info in em.machines:
        dr = _death_reachable(info)
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                # A path guarded by own(X) that LEADS TO DEATH is a TRAP gate, not a
                # requirement: rm138's day-6 hunger accepts `own(Spinach_Dip)` -> eat it ->
                # "the mayonnaise has spoiled in the hot, tropical sun!" -> death, while the
                # sibling `own(Sewing_Kit)` branch fishes and lives. Counting the trap made
                # Spinach_Dip look required. Skip death-bound paths; keep the survivable one.
                tgt = (K + 1 if tr[0] == "ADVANCE" else
                       tr[1] if tr[0] == "JUMP" else
                       tr[1] + 1 if tr[0] == "SETSTATE" else None)
                if tr[0] == "DEATH" or (tgt is not None and tgt in dr):
                    continue
                req(g, info["room"])
        # machine ENTRY guards too: a `Said 'throw/beach'` success branch is captured as an
        # entry/changeState guarded by own(Sand) -- skipping entries lost Sand/Ash.
        for K, eg in info.get("entries", ()):
            req(eg, info["room"])
        for K, eg in info.get("init_entries", ()):
            req(eg, info["room"])
        # CONSUMING an item requires owning it. Catches requirements carrying no own() guard at
        # all -- the Flower handed to the KGBishnas (rm50) exists only as `gEgo put: 20 -1`.
        for it in info.get("drops", ()):
            required[it].add(info["room"])
    return edges, edge_kind, sources, drops, required


class IrSccReach(SccReach):
    """SccReach fed from the JSON-IR model instead of model.Game (same algorithm)."""
    def __init__(self, em):
        self.em = em
        self.g = _NameShim()
        self.edges, self.edge_kind, self.sources, self.drops, self.required = build_maps(em)
        self.rooms = list(em.rooms)
        self.comps, self.comp_of = tarjan_scc(self.rooms, self.edges)
        self.cedges = defaultdict(set)
        for a, bs in self.edges.items():
            for b in bs:
                if a in self.comp_of and b in self.comp_of and self.comp_of[a] != self.comp_of[b]:
                    self.cedges[self.comp_of[a]].add(self.comp_of[b])
        self.creach = {c: reachable(self.cedges, {c}) for c in range(len(self.comps))}
        self.items_in_comp = defaultdict(set)
        for it, srcs in self.sources.items():
            for r in srcs:
                if r in self.comp_of:
                    self.items_in_comp[self.comp_of[r]].add(it)
        self.reach_rooms = reachable(self.edges, {em.cfg.start_room})
        self.members, self.room_region, self.controllers = {}, {}, set()   # no regions in IR
        self.goal_comps = {self.comp_of[r] for r in em.cfg.goal_rooms if r in self.comp_of}
        self._reob = {}


def load(cfg=None, ir_path=None):
    cfg = cfg or config.ACTIVE
    ir_path = ir_path or os.path.join(os.environ.get("CLAUDE_JOB_DIR", ""), "tmp",
                                      "lsl2_decomp", "lsl2.ir.json")
    ir = I.load_ir(ir_path)
    em = E.OpEmitter(ir, cfg, lambda gi, v: gi == 101 and v == 1001)
    return IrSccReach(em)


if __name__ == "__main__":
    s = load()
    print(f"rooms={len(s.rooms)}  SCCs={len(s.comps)}  goal_comps={sorted(s.goal_comps)}")
    cands = s.analyze()
    flagged = sorted({c["item"] for c in cands})
    print(f"softlock candidates ({len(flagged)} items):",
          [s.g.item_name(i) for i in flagged])
