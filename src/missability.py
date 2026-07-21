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
from collections import defaultdict, deque

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
    # PASS 1 -- TRAP items: an item whose own()-guarded branch walks into a DEATH is a trap, not
    # a requirement (Spinach_Dip: eat it -> "the mayonnaise has spoiled" -> death). Mark them
    # GLOBALLY, because the same item is also consumed on a survivable-looking `Said 'eat'`
    # handler (rm300) that would otherwise re-add it as required.
    # An item is a TRAP only if EVERY own()-guarded use walks into a death. Grotesque_Gulp has a
    # death-bound use (drink it at the wrong moment) AND survivable ones (the raft), so
    # "death-bound anywhere" would wrongly un-require it; Spinach_Dip is death-bound everywhere.
    death_bound, survivable = set(), set()
    for info in em.machines:
        dr = _death_reachable(info)
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                tgt = (K + 1 if tr[0] == "ADVANCE" else tr[1] if tr[0] == "JUMP" else
                       tr[1] + 1 if tr[0] == "SETSTATE" else None)
                owns = _own_positive(g)
                if tr[0] == "DEATH" or (tgt is not None and tgt in dr):
                    death_bound |= owns
                else:
                    survivable |= owns
    trap_items = death_bound - survivable

    required = defaultdict(set)
    def req_item(it, room):
        if it not in trap_items:
            required[it].add(room)
    def req(guard, room):
        for it in _own_positive(guard):
            req_item(it, room)
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
    # consuming an item in a HANDLER requires owning it there -- the Pamphlet handed to the bore
    # on the plane (rm62) is a Said-handler `put: 26 -1`, which the machine-body scan never sees.
    for room, script, it, g in getattr(em, "handler_drops", ()):
        req_item(it, room)
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
            req_item(it, info["room"])

    # NOTE: a CUTSCENE-SPLICE pass used to live here -- it rewrote `pred -> cutscene -> succ`
    # into `pred -> succ` to fix the Airline_Ticket false positive. It is RETIRED (git history
    # has it). It needed three guards, each added only after the sweep collapsed, and it was
    # actively harmful: splicing rm83 out fabricated an rm82 -> rm92 edge that reconnected the
    # volcano to the island hub, hiding the Ashes/Sand stranding. The gate-aware product graph
    # subsumes it -- the ticket FP was really an unguarded duplicate edge shadowing the machine
    # EXIT's own(ticket) guard (see edge_meta's machine_delivered filter).
    return edges, edge_kind, sources, drops, required


_STATUS_REG = 101          # gCurrentStatus -- the register LSL2 gates movement on


def _status_required(guard):
    """gCurrentStatus values this guard REQUIRES (`== v`), or None if it doesn't constrain it."""
    vals = set()
    def w(x, pol=True):
        if isinstance(x, list):
            for y in x:
                w(y, pol)
        elif isinstance(x, Pred):
            if x.kind == "CMP" and x.var == _STATUS_REG and x.op == "==" and pol:
                try:
                    vals.add(int(x.value))
                except (TypeError, ValueError):
                    pass
        elif isinstance(x, (GAnd, GOr)):
            for k in x.kids:
                w(k, pol)
        elif isinstance(x, GNot):
            w(x.kid, not pol)
    w(guard)
    return vals or None


def entry_alts(info):
    """State K -> the ALTERNATIVE ways of arming it: a tuple of item-sets, one per machine entry
    that reaches K (DNF). K is armed iff you satisfy SOME alternative, so an EXIT at K is
    traversable iff some alternative is fully held.

    Disjunction, not conjunction. rm81 (past the vine chasm) is armed only by `throw ash`
    (own 30) OR `throw sand` (own 31): intersecting them gives {} ("free"), unioning them gives
    {30,31} ("needs both") -- both wrong. Keeping them as alternatives is what lets the sweep say
    losing EITHER is survivable while losing BOTH strands you. An empty tuple means no entry
    reaches K (treat as ungated); an alternative that is itself empty means K can be armed with
    no items at all, so the gate is free."""
    succ = defaultdict(set)
    for K, paths in info["states"].items():
        for (g, w, gg, c, tr) in paths:
            if tr[0] == "ADVANCE":
                succ[K].add(K + 1)
            elif tr[0] == "JUMP":
                succ[K].add(tr[1])
            elif tr[0] == "SETSTATE":
                succ[K].add(tr[1] + 1)
    per_entry = []
    for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
        seen, q = {K}, [K]
        while q:
            u = q.pop()
            for v in succ.get(u, ()):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        per_entry.append((seen, frozenset(_own_positive(eg))))
    out = {}
    for K in info["states"]:
        out[K] = tuple({owns for (seen, owns) in per_entry if K in seen})
    return out


def blocked(alts, banned):
    """Is an edge with these DNF alternatives blocked when `banned` items are unavailable?"""
    return bool(alts) and all(a & banned for a in alts)


def edge_meta(em):
    """(a,b) -> [(required_status_values|None, status_SET|None, alts)] where `alts` is a DNF
    tuple of item-sets (see entry_alts / blocked).

    This is what makes reachability GATE-AWARE. The guard-ignoring graph walks rm82 -> rm152 ->
    rm52 and so welds the volcano to the airport (the mega-SCC that hid the Pamphlet stranding
    and produced the Airline_Ticket FP). But rm82 dumps you into rm152 with gCurrentStatus 14/15
    (bomb botched) while rm152's exit to rm52 REQUIRES status 7 -- an impossible composition."""
    meta = defaultdict(list)
    for e in em.ts.edges:
        meta[(e.src, e.dst)].append((_status_required(e.guard), None, (frozenset(_own_positive(e.guard)),)))
    md = em.machine_delivered
    for e in em.ts.cs_edges:
        if (e.src, e.dst) in md:
            continue          # same newRoom the machine EXIT already carries, but WITHOUT its
        #                       guard -- keeping it shadows the real gate (rm57 -> rm58 needs the
        #                       ticket handed to the agent). build_maps applies this filter too.
        meta[(e.src, e.dst)].append((_status_required(e.guard), None, (frozenset(_own_positive(e.guard)),)))
    for info in em.machines:
        eo = entry_alts(info)
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    setv = next((v for (gi, v) in w if gi == _STATUS_REG), None)
                    exit_own = frozenset(_own_positive(g))
                    alts = eo.get(K) or (frozenset(),)
                    meta[(info["room"], tr[1])].append(
                        (_status_required(g), setv, tuple(exit_own | a for a in alts)))
    return meta


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
        self._reob, self._rw = {}, {}
        self._build_product()

    # ---- gate-aware movement ------------------------------------------------
    def _build_product(self):
        """Product graph over (room, gCurrentStatus) -- the GATE-AWARE movement model.

        The plain room graph ignores guards, so it composes an edge that SETS a register with
        one that REQUIRES a different value, welding unrelated regions into a mega-SCC. In-room
        status changes (handler writes, non-exit machine writes) are added unguarded, so the
        product stays PERMISSIVE: it can only ever remove movement the guards actually forbid.
        Validated: reaches the same 84 rooms as the guard-ignoring walk, in 829 states."""
        em = self.em
        self._emeta = edge_meta(em)
        inroom = defaultdict(set)
        for room, script, gi, v, g in em.handler_writes:
            if gi == _STATUS_REG:
                inroom[room].add(v)
        for info in em.machines:
            for K, paths in info["states"].items():
                for (g, w, gg, c, tr) in paths:
                    for (gi, v) in w:
                        if gi == _STATUS_REG:
                            inroom[info["room"]].add(v)
        self._inroom = inroom
        padj = defaultdict(set)
        start = (em.cfg.start_room, 0)
        seen, q = {start}, [start]
        while q:
            u = q.pop()
            for v in self._psucc(u):
                padj[u].add(v)
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        self._pstates, self._padj = seen, padj
        self._pprev = defaultdict(set)
        for a, bs in padj.items():
            for b in bs:
                self._pprev[b].add(a)

    _FREE = ((frozenset(),),)

    def _psucc(self, node, banned=frozenset()):
        """Successors of a (room, status) node. `banned` is a SET of items you do not hold, so
        edges needing them are false -- the ITEM dimension of gate-awareness, and what the old
        `_sealed` one-way-edge heuristic crudely approximated: you cannot use the parachute to
        walk back to the parachute."""
        r, st = node
        out = {(r, v) for v in self._inroom.get(r, ())}
        for b in self.edges.get(r, ()):
            for (req, setv, alts) in self._emeta.get((r, b), self._FREE):
                if req is not None and st not in req:
                    continue                      # guard forbids this move at this status
                if banned and blocked(alts, banned):
                    continue                      # every way through needs a banned item
                out.add((b, setv if setv is not None else st))
        return out

    def _reach_without(self, item):
        """Rooms reachable from the start WITHOUT ever holding `item` (gate-aware forward walk).
        `item` may be a single item or a frozenset of them (a disjunctive group).

        A room whose own(item) guard can only be reached BY holding item isn't a stranding site
        at all -- you can never stand there lacking it. rm61 tests own(Airline_Ticket) but every
        route in already spends the ticket, which is why the ticket looked missable."""
        ban = item if isinstance(item, frozenset) else frozenset({item})
        if ban in self._rw:
            return self._rw[ban]
        start = (self.em.cfg.start_room, 0)
        seen, q = {start}, [start]
        while q:
            u = q.pop()
            for v in self._psucc(u, banned=ban):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        self._rw[ban] = {r for r, _ in seen}
        return self._rw[ban]

    def _need_rooms(self, item):
        """Rooms where own(item) is actually FACED -- gate-aware. See _reach_without."""
        return {R for R in super()._need_rooms(item) if R in self._reach_without(item)}

    def reobtainable_rooms(self, item):
        """Rooms from which `item` can still be ACQUIRED -- GATE-AWARE.

        Backward walk in the (room, status) product instead of the guard-ignoring room graph.
        This replaces the `_sealed` one-way-edge heuristic: a pocket is sealed when the guards
        actually seal it, which is derived rather than assumed."""
        ban = item if isinstance(item, frozenset) else frozenset({item})
        if ban in self._reob:
            return self._reob[ban]
        srcs = set()
        for it in ban:
            srcs |= self.sources.get(it, set())
        if not srcs:
            self._reob[ban] = set()
            return self._reob[ban]
        prev = defaultdict(set)                   # reverse product edges, minus own(item) gates
        for u in self._pstates:
            for v in self._psucc(u, banned=ban):
                if v in self._pstates:
                    prev[v].add(u)
        back = {p for p in self._pstates if p[0] in srcs}
        q = deque(back)
        while q:
            u = q.popleft()
            for w in prev.get(u, ()):
                if w not in back:
                    back.add(w)
                    q.append(w)
        self._reob[ban] = {r for r, _ in back}
        return self._reob[ban]


    # ---- disjunctive requirement groups -------------------------------------
    def disjunctive_groups(self):
        """room -> {frozenset(items)}: sets that ALTERNATIVELY open the same gate.

        The per-item sweep is blind to these by construction -- no single member is required, so
        every member looks re-obtainable via its sibling. rm81 past the vine chasm is the case:
        `throw ash` (own 30) or `throw sand` (own 31) both arm the exit, and both sources sit
        back in the jungle you can never return to. Losing EITHER is survivable; losing BOTH is
        the softlock."""
        out = defaultdict(set)
        for (a, b), variants in self._emeta.items():
            for (req, setv, alts) in variants:
                uniq = set(alts)
                if len(uniq) < 2 or any(not x for x in uniq):
                    continue          # one alternative is free -> the gate is not a requirement
                if set.intersection(*map(set, uniq)):
                    continue          # a common item is needed -> per-item sweep already sees it
                out[a].add(frozenset().union(*uniq))
        return out

    def group_strandings(self):
        """Disjunctive groups that are faced past a point of no return to ALL their sources."""
        rows = []
        for R, groups in sorted(self.disjunctive_groups().items()):
            for G in sorted(groups, key=sorted):
                if R not in self.reach_rooms or R not in self._reach_without(G):
                    continue          # can never stand here lacking the whole group
                if R in self.reobtainable_rooms(G):
                    continue          # some member is still fetchable from here
                srcs = set()
                for it in G:
                    srcs |= self.sources.get(it, set())
                rows.append({"pattern": "missing-disjunctive-prereq-before-gate",
                             "items": sorted(G),
                             "item_names": [self.g.item_name(i) for i in sorted(G)],
                             "need_room": R, "source_rooms": sorted(srcs)})
        return rows


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
    for row in s.group_strandings():
        print(f"  + disjunctive group {row['item_names']} needed at rm{row['need_room']}, "
              f"all sources {row['source_rooms']} unreachable from there")
