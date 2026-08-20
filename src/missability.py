"""Missability sweep on the JSON-IR / opmodel front-end (the canonical one), NOT the stale
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
import opmodel as E
import vocab
import grid
from guard_ast import GAnd, GOr, GNot, Pred
from extract import _curroom_impossible
from scc_core import tarjan_scc, reachable, SccReach

# Item names are a reporting nicety; the IR JSON carries only the raw instance name, so derive the
# number -> name map from the game's own class table (vocab.item_names). Previously this was a
# hardcoded LSL2 dict applied to EVERY game, so KQ4's Shovel printed as "Bikini_Top" -- the last
# game-specific catalogue, now gone. The ANALYSIS was always fully on JSON-IR; only these labels
# were game-specific, and now they derive too.
class _ItemNames:
    def __init__(self, names):
        self._names = names        # {number: name}, derived per game

    def item_name(self, it):
        return self._names.get(it, f"item{it}")


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


def _own_required(guard):
    """Items NECESSARILY held whenever `guard` is true -- the REQUIREMENT semantics, stricter than
    `_own_positive`. An item inside an OR-branch is NOT required (another branch may satisfy the
    guard), so GOr INTERSECTS its kids while GAnd UNIONS them (and negation swaps the two, De
    Morgan). This is why KQ4's Obsidian Scarab is NOT required by the nightfall guard `(or (clock)
    (and (>= g109 3) (has:7) (has:25)))`: it is one WAY night falls, not a thing you must hold. A
    disjunctive requirement (ash OR sand) correctly contributes nothing here -- it is caught by
    `disjunctive_groups`, not by per-item `required`."""
    def walk(g, pol):
        if g is None:
            return set()
        if isinstance(g, list):
            out = set()
            for x in g:
                out |= walk(x, pol)
            return out
        if isinstance(g, Pred):
            return {g.var} if (g.kind == "OWN" and pol) else set()
        if isinstance(g, GNot):
            return walk(g.kid, not pol)
        if isinstance(g, (GAnd, GOr)):
            union = pol == isinstance(g, GAnd)     # AND&true or OR&false -> union; else intersect
            sets = [walk(k, pol) for k in g.kids]
            if not sets:
                return set()
            return set().union(*sets) if union else set.intersection(*sets)
        return set()
    return walk(guard, True)


def _loc_placed_required(guard, placed):
    """Items required by a POSITIVE owner-gate `owner == R` where R is a room the item is PLACED at
    (a `put`/`moveTo` writes its owner to R -- see extract.TS.placed). Reaching `owner == R` for a
    placed room means the item was actively put there, which required holding it, so the item is
    required wherever the gate is. A gate on the item's INITIAL resting room -- never written, so
    not in `placed` -- is the 'is it still there?' check (KQ4's fruit `owner == 78`) and contributes
    nothing. Same De Morgan polarity as `_own_required`: an owner-gate inside an OR-branch is not
    required, because another branch may satisfy the guard. This is the state-grounded reading of
    the owner-gate the source heuristic could not give: the writes ARE the owner's transitions, so
    'use it in the room you got it' is a placement like any other and correctly requires the item."""
    def walk(g, pol):
        if g is None:
            return set()
        if isinstance(g, list):
            out = set()
            for x in g:
                out |= walk(x, pol)
            return out
        if isinstance(g, Pred):
            if (g.kind == "LOC" and pol and isinstance(g.value, int)
                    and g.value in placed.get(g.var, ())):
                return {g.var}
            return set()
        if isinstance(g, GNot):
            return walk(g.kid, not pol)
        if isinstance(g, (GAnd, GOr)):
            union = pol == isinstance(g, GAnd)
            sets = [walk(k, pol) for k in g.kids]
            if not sets:
                return set()
            return set().union(*sets) if union else set.intersection(*sets)
        return set()
    return walk(guard, True)


def _loc_values(guard, item, room=None):
    """Owner values `guard` positively DEMANDS for `item`'s object.

    `room` is where the guard was found. LSL2 writes the test as `ownedBy: gCurRoomNum`, which
    says "here" without naming a room; KQ4 names it -- `ownedBy: 78` inside Room78. Both mean the
    same thing, and only the caller knows which room it is in, which is why the atom keeps the
    literal instead of collapsing it at extraction time. An empty result means the guard says
    nothing about where the item is -- NOT that it demands nowhere."""
    out = set()

    def walk(g, pol):
        if isinstance(g, list):
            for x in g:
                walk(x, pol)
        elif isinstance(g, Pred):
            if g.kind == "LOC" and g.var == item and pol:
                # "room" = `ownedBy: gCurRoomNum`. A caller that did not say which room it is
                # standing in gets the sentinel back unresolved -- it still means a location IS
                # demanded, which is all the boolean reading ever asked.
                out.add(room if (g.value == "room" and room is not None) else g.value)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                walk(k, pol)
        elif isinstance(g, GNot):
            walk(g.kid, not pol)
    walk(guard, True)
    return out


def _loc_item_keys(guard, out=None):
    """Which items `guard` says anything about the LOCATION of, polarity ignored.

    The index half of `_loc_values`: that one answers "which owners does this demand for item X",
    this one answers "which X are worth asking about at all". `state_musts` needs the index before
    it can ask the question, exactly as `_ctr_keys` indexes the counters before `_ctr_holds`."""
    out = set() if out is None else out
    if isinstance(guard, (list, tuple)) and not (isinstance(guard, tuple)
                                                 and guard and guard[0] == "CTR"):
        for x in guard:
            _loc_item_keys(x, out)
    elif isinstance(guard, Pred):
        if guard.kind == "LOC":
            out.add(guard.var)
    elif isinstance(guard, (GAnd, GOr)):
        for k in guard.kids:
            _loc_item_keys(k, out)
    elif isinstance(guard, GNot):
        _loc_item_keys(guard.kid, out)
    return out


def _conj_spine(guard):
    """Flatten a guard (tree or list) to its top-level conjunct list -- the atoms that MUST
    hold. The same discipline as `_must_hold`: nothing under an OR or a negation is a
    conjunct."""
    if guard is None:
        return []
    if isinstance(guard, list):
        out = []
        for g in guard:
            out.extend(_conj_spine(g))
        return out
    if isinstance(guard, GAnd):
        out = []
        for k in guard.kids:
            out.extend(_conj_spine(k))
        return out
    return [guard]


#: methods that run without the player doing anything -- the room hands you the item on arrival
#: (`init`) or while you stand there (`doit`). Everything else (`doVerb`, `handleEvent`,
#: `changeState`) needs an act, and an act can be declined.
_NO_INPUT_METHODS = ("init", "doit")


def _unrefusable_grants(em):
    """item -> {room}: handouts you cannot decline.

    A source is normally a CHOICE, which is exactly what `_reach_without`'s banned walk models:
    you can walk past a thing and not pick it up, so the rooms beyond it are rooms you can stand
    in lacking the item. A grant emitted by a room's `init` under no condition but the
    idempotence check is not a choice -- the game runs it before you can act and re-runs it on
    every entry, so there is NO state past that room in which you lack the item.

    KQ5's `rm001.sc:78` is the case that named this: `(if (not (global0 has: 28)) (global0 get:
    28))` in the first room of the game. Without it the Wand -- which Crispin hands Graham in the
    intro, and which exactly one site in 211 scripts ever takes back (the machine tray in rm66,
    where the same room hands it straight back) -- read as an item you can walk to the endgame
    without, and drew two `analyze` rows plus a carry demand on the roc's one-way edge saying
    "carry the thing you cannot not carry".

    STRICT on both halves, because the failure direction here is LOST FINDINGS (a barrier
    shrinks `_reach_without`, and a room dropped from it is a room no detector will judge):
      * the method must run with no player input, and
      * the guard's whole conjunct spine must be the `not (has: X)` itself. One extra conjunct
        means the handout has a condition, and a condition is a way to be past the room without
        the item.
    Measured 2026-08-15 against the deliberately LOOSER reading -- any site whose guard merely
    entails not-own, any method -- which barriers 8 KQ4 sites, 4 KQ6, 2 LB2 and KQ5's own Amulet
    and Elf_Shoes: the full snapshot surface of LSL2, KQ4, KQ6 and LB2 is BYTE-IDENTICAL either
    way, and KQ5 moves by exactly the two Wand rows and the Wand's conjunct in the rm40->rm41
    spec."""
    out = {}
    for a in getattr(getattr(em, "ts", None), "acqs", ()):
        if getattr(a, "method", "") not in _NO_INPUT_METHODS:
            continue
        spine = _conj_spine(a.guard)
        if (len(spine) == 1 and isinstance(spine[0], GNot)
                and isinstance(spine[0].kid, Pred) and spine[0].kid.kind == "OWN"
                and spine[0].kid.var == a.item):
            out.setdefault(a.item, set()).add(a.room)
    return out


def _is_owner_atom(g):
    return isinstance(g, Pred) and g.kind == "LOC" and g.op == "ownedBy"



def _spend_exhausts_sources(s, X, a):
    """Having SPENT X at room `a`, is every source of X now dead?

    `reobtainable_rooms(X)` answers the never-picked-it-up question: banning X, can the walk reach
    a place that hands X over. It is deliberately permissive there -- the SOURCE FLOOR keeps a site
    whose condition nothing satisfies, because ignorance about how a condition is established is
    not evidence that the item cannot be had. A TOLL knows strictly more: `put: X a` wrote
    `owner(X) := a`, and a site guarded `owner(X) == r` offers X only while it still RESTS at r, so
    every such site with `r != a` is dead the moment the toll is paid. That is the "is it still
    there?" check `_loc_placed_required` names and correctly discounts for the REQUIREMENT
    question; for a SOURCE's liveness it is the whole answer.

    KQ5's temple is the case, and it is the reason this exists. The Staff's one source is rm17,
    whose prop inits under `(== ((gInv at: 7) owner:) 17)`; rm214's door breaks the Staff with
    `put: 7 214`. Walking back to rm17 afterwards finds nothing there, so rm18 really is one-visit
    and the Brass_Bottle and Gold_Coin inside it really are stranded -- both USER-CONFIRMED, and
    both were being kept only by a degenerate register projection until `gating_registers` stopped
    promoting object-valued globals (see `_object_valued_globals`).

    REFUSES on any site that could still be live: one with no resting-place demand at all (a
    factory, not a resting place), or one that offers X from `a` itself. A surface with no
    `source_guards` -- the duck-typed fakes the toll unit tests build -- refuses outright, which is
    the pre-existing behaviour."""
    rooms = (getattr(s, "source_guards", None) or {}).get(X) or {}
    if not rooms:
        return False
    for _room, gs in rooms.items():
        for g in gs:
            demands = [c for c in _conj_spine(g) if _is_owner_atom(c) and c.var == X]
            if not demands or any(c.value == a for c in demands):
                return False
    return True


def _entry_owner_conjuncts(info, K):
    """The owner-store atoms EVERY arming of state `K` agrees on, as a conjunct list.

    Same discipline as `entry_musts`, and for the same reason: entries are ALTERNATIVES, so one
    that carries no owner demand frees the whole disjunction. State 0's armings are the machine's
    own way in; a later state reached only by its own entry carries that one."""
    alts = [eg for (k, eg) in info.get("entries", ()) if k in (0, K)]
    if not alts:
        return []
    common = None
    for eg in alts:
        here = {repr(g): g for g in _conj_spine(eg) if _is_owner_atom(g)}
        common = here if common is None else {k: v for k, v in common.items() if k in here}
        if not common:
            return []
    return list((common or {}).values())


def _fold_demands(guard, placed):
    """The negated owner-value conjuncts of a guard's top-level AND spine, as demand groups.

    A conjunct `NOT LOC(i@X)` -- or `NOT (LOC(i1@X1) OR LOC(i2@X2) ...)` -- on a machine that
    cannot be survived says: the machine arms UNLESS one of those owner values holds, so the
    DISJUNCTION of them is demanded of whoever arrives. Only placements count
    (`X in placed[i]`, the `_loc_placed_required` discipline): a negated is-it-still-there
    check on an item's initial resting room is "already taken", not a value the player can
    produce. A group with any non-placement member is dropped whole, because the demand we
    would state for the rest is narrower than the game's.

    Returns `(groups, context)`: each group a list of `(item, owner_room)`, and `context` the
    remaining readable conjuncts (the fold's arming context -- rm86's `prev == 85`)."""
    groups, ctx = [], []
    for c in _conj_spine(guard):
        got = None
        if isinstance(c, GNot):
            kid = c.kid
            if _is_owner_atom(kid):
                got = [(kid.var, kid.value)]
            elif isinstance(kid, GOr) and kid.kids and all(_is_owner_atom(k) for k in kid.kids):
                got = [(k.var, k.value) for k in kid.kids]
        if got is None:
            ctx.append(c)
        elif all(isinstance(x, int) and x in placed.get(i, ()) for (i, x) in got):
            groups.append(got)
    return groups, ctx


def _collapse_by(rows, key, merge_fields, value_key=None):
    """Merge rows that state the SAME FACT, keeping the first row's identity and unioning the
    listed fields. The shared body of `_collapse_flips` and `_collapse_value_flips`.

    They differ in exactly two ways -- what makes two rows the same fact (`key`) and which lists
    union (`merge_fields`) -- and were otherwise the same twenty lines twice, which is this
    codebase's most expensive shape ([[same-rule-two-places]]): the value-flip copy was written
    by adapting the item copy, and a correction to either would have had to be remembered twice.

    `value` keeps the first merged value, so a row that merged nothing is byte-identical to its
    input, and `values` appears only where a merge happened -- the register rows sort those by
    `repr` because a joint's value is a tuple."""
    by, order = {}, []
    for r in rows:
        k = key(r)
        if k not in by:
            by[k] = r
            order.append(k)
            continue
        keep = by[k]
        keep.setdefault("values", [keep["value"]])
        if r["value"] not in keep["values"]:
            keep["values"].append(r["value"])
        for f in merge_fields:
            keep[f] = sorted(set(keep[f]) | set(r[f]))
    for k in order:
        r = by[k]
        if "values" in r:
            r["values"] = sorted(r["values"], key=value_key) if value_key \
                else sorted(r["values"])
            r["value"] = r["values"][0]
    return [by[k] for k in order]


def latch_evidence(em):
    """`(local_home, latch_writers, nonmachine)` -- everything that can RAISE a room's own
    lowered locals (the fifth store's registers).

      * `local_home`  reg -> (room, index), straight off the lowering;
      * `latch_writers` (room, reg) -> [(machine info, value)] for the room's own machines;
      * `nonmachine`  (room, reg) -> {values} written outside any machine (handlers).

    ONE evidence base, TWO questions, and they must not drift apart. `_reg_entry_demands`
    asks how FREE an entry gated on a latch is -- it hops to the machines that raise it and
    inherits their demand. `build_maps` asks whether such an entry can fire AT ALL, because
    an entry that cannot fire must not dissolve the requirement its siblings carry. Both
    answers rest on the same fact ("who writes this latch, and to what"), and this codebase's
    oldest recurring bug is that fact being computed in two places and fixed in one
    ([[same-rule-two-places]]: `asserts_eq`, `_room_object`, `Increment`).

    Bounded to a room's own lowered locals for the reason the fifth store exists: the script
    reloads on entry and resets them, so the writers we can see ARE all the writers
    (vocab.derive_room_locals). No such completeness holds for a global, which is why nothing
    here generalises to one."""
    local_home = dict(getattr(getattr(em, "ir", None), "_room_local_index", None) or {})
    latch_writers = {}                                 # (room, reg) -> [(info, value)]
    for i in em.machines:
        for _K, paths in i["states"].items():
            for (_g, wr, _gg, _c, _tr) in paths:
                for gi, v in wr:
                    if local_home.get(gi, (None,))[0] == i["room"]:
                        latch_writers.setdefault((i["room"], gi), []).append((i, v))
    nonmachine = {}                                    # (room, reg) -> {values written}
    for room, _script, gi, v, _g in getattr(em, "handler_writes", ()):
        if local_home.get(gi, (None,))[0] == room and isinstance(v, int):
            nonmachine.setdefault((room, gi), set()).add(v)
    return local_home, latch_writers, nonmachine


def _entry_cannot_fire(em, room, guard, ev):
    """Is this entry gated on a room-local latch NOTHING in the room can raise?

    The requirement-side half of `_reg_entry_demands._via_latch`'s correction -- "an unfirable
    entry vouches for nothing" -- which that function needed to stop LB2's cobra pass
    dissolving its own demand through an arming that could not happen. The same reading is
    owed wherever entries are read DISJUNCTIVELY, and `build_maps` intersects `_own_required`
    across every entry at a state: one entry the player can never take erases the price all
    the others charge, and a requirement erased is a frontier not computed and a need
    retired.

    DELIBERATELY WEAKER THAN `_via_latch`, which resolves the raiser chain and inherits its
    demands. This one only refuses an entry when the latch has NO writer at all -- no machine
    state in the room, no handler -- because that is the case where "cannot fire" needs no
    reachability argument to be true. An entry whose latch someone raises is left alone
    whatever it would cost to raise it: over-claiming unfirability would ADD requirements from
    ignorance, which is the same fabrication in the other direction."""
    local_home, latch_writers, nonmachine = ev
    regs = {gi for gi, home in local_home.items() if home[0] == room}
    if not regs:
        return False
    need = structural_reqs(guard, regs,
                           {gi: set(em.reg_vals.get(gi, {0, 1})) for gi in regs})
    for R, vals in need.items():
        if nonmachine.get((room, R), set()) & set(vals):
            continue
        if any(v in vals for (_i, v) in latch_writers.get((room, R), ())):
            continue
        return True                                    # nothing can put the latch there
    return False


def _after(info, tr, gr, goal_ok):
    """Can the goal still be reached AFTER taking this transition?"""
    if tr[0] == "DEATH":
        return False                           # death is just one way to fail goal-reachability
    if tr[0] == "EXIT":
        return tr[1] in goal_ok
    if tr[0] == "PARK":
        return info["room"] in goal_ok         # control returns to the player, in this room
    return True                                # ADVANCE/JUMP/SETSTATE resolve via `gr`


def next_state(K, tr):
    """The machine state a transition lands on, or None if it leaves the machine."""
    return (K + 1 if tr[0] == "ADVANCE" else
            tr[1] if tr[0] == "JUMP" else
            tr[1] + 1 if tr[0] == "SETSTATE" else None)


def hopeful(info, K, tr, gr, goal_ok):
    """Can the goal still be reached after taking this path out of state K?

    This is the rule the TRAP test is built on. An own(X)-guarded path you cannot still WIN from
    is not evidence that X is required -- death is merely the commonest way to fail that, and a
    use stranding you in a region with no route to the goal fails it identically."""
    nxt = next_state(K, tr)
    return _after(info, tr, gr, goal_ok) if nxt is None else gr.get(nxt, True)


def goal_reaching(info, goal_ok):
    """State -> can the goal still be reached from it (backward fixpoint over the machine)."""
    gr, changed = {}, True
    while changed:
        changed = False
        for K, paths in info["states"].items():
            cur = any(hopeful(info, K, tr, gr, goal_ok) for (g, w, gg, c, tr) in paths)
            if gr.get(K) != cur:
                gr[K] = cur
                changed = True
    return gr


def goal_reaching_rooms(edges, goal_rooms):
    """Rooms from which a goal room is still reachable (backward walk in the room graph).

    The guard-IGNORING graph is deliberate: over-approximating goal-reachability makes fewer uses
    look hopeless, so we under-call traps and OVER-require -- the safe direction."""
    rev = defaultdict(set)
    for a, bs in edges.items():
        for b in bs:
            rev[b].add(a)
    return reachable(rev, set(goal_rooms))


def _debug_gated_guard(guard, debug_idx=frozenset()):
    """Does this guard depend on QA scaffolding? Those branches are not real availability --
    LSL2's rm82 hands you the entire bomb under `if gDebugging`."""
    refs = []
    def w(g):
        if isinstance(g, list):
            for x in g: w(x)
        elif isinstance(g, Pred):
            if g.var in debug_idx: refs.append(g.var)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids: w(k)
        elif isinstance(g, GNot):
            w(g.kid)
    w(guard)
    return bool(refs)


def _iprop_spec(em):
    """(item, prop) -> {values, counter} for the fourth store, as extraction discovered it."""
    import extract as X
    return dict(getattr(X, "_IPROPS", {}))


_IPROP_SPEC = {}
_WARNED_MODEL = set()


def _degraded_model(msg):
    """Report a place where the model gave up and answered with less than the game contains.

    Budget caps and fallbacks are legitimate, but a SILENT one is indistinguishable from a
    clean analysis -- the failure mode this project keeps naming. Deduplicated so a per-machine
    loop cannot spam."""
    if msg in _WARNED_MODEL:
        return
    _WARNED_MODEL.add(msg)
    import sys as _sys
    print("  [degraded] " + msg, file=_sys.stderr)


def build_maps(em):
    """(edges, edge_kind, sources, drops, required, guard_required) from the JSON-IR OpEmitter.

    `guard_required` is `required` WITHOUT the consumption fallback -- only rooms where the game
    actually tests `has: X`. That is the evidence that an item ARMS something, which is a
    different question from where it is needed, and `real_uses` wants the former."""
    global _IPROP_SPEC
    _IPROP_SPEC = _iprop_spec(em)
    edges, edge_kind = defaultdict(set), defaultdict(set)
    md = em.machine_delivered

    def add(a, b):
        edges[a].add(b); edge_kind[(a, b)].add("goto")   # every JSON-IR movement is a newRoom

    for e in em.ts.edges:
        add(e.src, e.dst)
    for e in em.ts.cs_edges:
        if (e.src, e.dst) not in md:
            add(e.src, e.dst)
    # A machine EXIT to a spliced-out MAZE DISPATCHER means "walk out of this cell", so it
    # resolves to the rooms the grid says you can walk to -- not to the dispatcher, which is only
    # the code that computes where you come out and would otherwise reconnect the levels the maze
    # keeps apart. The flat and cutscene edges were substituted in `extract`; these are built here,
    # so the same rule is applied here rather than left as the one path that leaks.
    disp = getattr(em.ts, "dispatchers", set())
    mreach = getattr(em.ts, "maze_reach", {})
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    if tr[1] in disp:
                        for d in sorted(mreach.get(info["room"], ())):
                            add(info["room"], d)
                    else:
                        add(info["room"], tr[1])

    # SEALED EXITS: a room's own `newRoom:` override that intercepts a destination and arms a
    # turn-back instead of calling super refuses that crossing at the engine funnel itself, so
    # the edge does not exist -- whatever spelling produced it above (nav property, walk-off,
    # machine EXIT). KQ6's Realm interior is the instance (rm670-/->660, rm680-/->670,
    # `dontGoAlex`; findings #15/#16): unsealed, the toll walk deferred the Styx-cup demand
    # past Charon into a pocket with no controllable site, and the placed arm-events hung the
    # game in play. Subtracted HERE, at the one assembly point, so every consumer -- reach,
    # frontiers, the placement walk's last-satisfiable-crossing -- sees the same world.
    ir = getattr(em, "ir", None)
    if ir is not None:
        import extract as X
        for (a, b) in X.sealed_exits(ir):
            edges.get(a, set()).discard(b)
            edge_kind.pop((a, b), None)

    # sources: skip DEAD debug-gated acquires (rm82's `(if gDebugging (get 19 21 27))` bomb
    # hand-out). The JSON-IR TRACKS gDebugging rather than const-pinning it, so gexpr won't
    # fold `gDebugging != 0` to FALSE -- and the IR json carries no global names, so we can't
    # resolve config.debug_globals to indices from it. TODO(generalize): pin debug globals in
    # the emitter / carry a name->index map. For now use the known LSL2 debug indices.
    DEBUG_IDX = frozenset(em.cfg.debug_globals)
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
    # ...and the CONDITION each surviving site was reached under, kept per (item, room) so the
    # reobtainability walk can ask whether the site is live in a given register state. `sources`
    # answers "which rooms give you this", which is a question about PLACES; a room whose giving
    # is gated -- LB2's `rm440` places the work boot only under `(== global123 4)` -- gives it
    # only in some of the states you can stand there in, and dropping the condition here is what
    # made every act-gated source read as available in every act. The site-level filters below
    # (`_own_required`, `_prev_impossible`) already answer the questions that need no fixpoint;
    # this carries the rest to the one consumer that has the product to judge them.
    #
    # A room keeps the PERMISSIVE reading if any of its sites is unconditional: `None` in the
    # list means "this site needs nothing", and `reobtainable_rooms` reads the list that way.
    # A plain dict, not a defaultdict-of-defaultdict: the model is PICKLED into the build
    # cache and a lambda factory cannot be pickled.
    source_guards = {}                                       # item -> room -> [guard | None]
    # AN ACQUISITION YOU CAN ONLY REACH WHILE ALREADY HOLDING THE ITEM IS NOT A SOURCE. Sierra
    # writes "take it back down" with the very same `get:` as "pick it up", and the only thing
    # separating them is the condition: KQ6's hole-in-the-wall sticks onto any wall you like and
    # comes off again, so `get: 18` appears in the labyrinth's shared script and thus in EVERY
    # maze room, and the model believed the hole was freshly obtainable throughout the trap it is
    # needed to escape. The take-back is armed from an object that only exists because you put the
    # hole up (see `cast_conditions`), so its entry demands own(18) -- and something you must
    # already have is not something a room GIVES you.
    #
    # Per SITE, and a room keeps its source if ANY site is free: this only ever removes a
    # re-acquisition, never a first one.
    # ...AND AN ACQUISITION YOU CAN ONLY REACH BY ARRIVING FROM SOMEWHERE THAT CANNOT REACH IT is
    # not a source either. Same "per site, only ever removes an impossible one" discipline; the
    # question it answers -- and why it is the previous-room register rather than a debug global --
    # is in `_prev_impossible`. `edges` is complete by here; nothing below adds to it.
    prev = prev_room_reg(em)
    mg = getattr(em, "machine_gets", set())
    for a in em.ts.acqs:
        # The same `get:` inside a `changeState` body is walked twice -- here with the body's own
        # path condition (nothing) and by the machine lift, which knows what arming it costs.
        # Matched by the emitting object, exactly as `edge_meta` matches a suppressed cs_edge.
        if (a.room, a.via, a.item) in mg:
            continue
        if (not _debug_gated(a.guard) and a.item not in _own_required(a.guard)
                and not _prev_impossible(a.guard, a.room, prev, edges)):
            sources[a.item].add(a.room)
            source_guards.setdefault(a.item, {}).setdefault(a.room, []).append(a.guard)
    for room, script, it, g in em.handler_gets:
        if (not _debug_gated(g) and it not in _own_required(g)
                and not _prev_impossible(g, room, prev, edges)):
            sources[it].add(room)
            source_guards.setdefault(it, {}).setdefault(room, []).append(g)
    for info in em.machines:
        em_ = entry_musts(info)
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                # ...and what EVERY way of arming this machine demands you already hold.
                must = em_.get(K, frozenset())
                # ...and, of the arming, the part `entry_musts` does NOT absorb: its OWNER-STORE
                # conjuncts. `entry_musts` reads item COSTS, so an `own(X)` in the entry is
                # accounted for above and rightly left out of the condition below; a
                # `LOC(X ownedBy R)` is not a cost and was dropped outright. It is what
                # `_loc_placed_required` calls the "is it still there?" check, and for a SOURCE it
                # is the whole answer -- the site offers the item only while the item still rests
                # there. KQ5's temple: `rm017.init` inits the staff prop under
                # `(== ((gInv at: 7) owner:) 17)`, so breaking the Staff on rm214's door
                # (`put: 7 214`) moves the owner and the source dies with it.
                own_at = _entry_owner_conjuncts(info, K)
                for it in gg:
                    if it not in must | _own_required(g):
                        sources[it].add(info["room"])
                        # The state's own path condition, NOT the machine's arming: the arming is
                        # an item cost (`entry_musts`, already applied above), while what a
                        # register walk needs is the condition under which this statement runs.
                        source_guards.setdefault(it, {}).setdefault(info["room"], []).append(
                            GAnd(_conj_spine(g) + own_at) if own_at else g)

    # BULK transfers -- the whole inventory at once, written as a walk of the Inv list setting
    # each item's `owner:`. KQ4 confiscates everything at rm92 (captured) and rm81 (the wedding
    # room) into room 89, and rm89's cupboard hands it all back. No item number appears anywhere
    # in that code, so this is the one case where "no constant" has to mean "every item".
    #
    # Fed to sources/drops only, NOT to the consumption-as-requirement fallback: being taken from
    # you is not evidence that you needed it there.
    all_items = set(em.ts.items) | set(sources) | {it for _r, _s, it, _g in em.handler_gets}
    for room, dest, _g in getattr(em.ts, "bulk_moves", ()):
        for it in all_items:
            (sources if dest == E.EGO else drops)[it].add(room)
            if dest == E.EGO:
                source_guards.setdefault(it, {}).setdefault(room, []).append(_g)

    # THE FOURTH STORE. An item's own property can hold state, and putting it into a state the
    # item's USES reject is the same thing as losing the item:
    #     Room16:249  (if (and (gEgo has: 15) (== 0 ((Inv at: 15) loop:))) ... dig ...)
    #     Room16:592  ((Inv at: 15) loop: 1)            -- the shovel breaks, and stays broken
    #     Room82:625  ((Inv at: 14) loop: (+ ... 1))    -- an arrow is spent, and never comes back
    # The shovel is a CHAIN, and we currently see only its last link:
    #     Room16:611  (= local5 (* (- (++ global113) 1) 3))   ++ per hole dug -- INVISIBLE, since
    #                                                          _hwalk handles Increment on LOCALS
    #                                                          only, never on globals
    #     Room16:589  (if (>= global113 5) ...)                ignored -- relational ops are
    #                                                          deliberately permissive
    #     Room16:592  ((Inv at: 15) loop: 1)                   recorded, as of this change
    # so the drop site is right and its CONDITION is not modelled at all. Over-approximating a
    # loss is the safe direction, but nothing yet turns it into a finding -- see TODO A0g.
    # so these feed `drops`, not the movement product: nothing about them is a room gate.
    #
    # ONE-WAY is the whole question, and the discovered value set answers it without a rule about
    # `loop`: a property written to exactly one value, or incremented with no reset, cannot be put
    # back. KQ4's fishing pole writes BOTH 0 and 1 -- you can re-bait it -- so it is excluded, and
    # excluded for a reason rather than by name.
    for room, it, prop, val, _g, *_rest in getattr(em.ts, "item_prop_writes", ()):
        spec = getattr(E.X, "_IPROPS", {}).get((it, prop)) if hasattr(E, "X") else None
        spec = spec or _IPROP_SPEC.get((it, prop))
        if spec and (spec.get("counter") or len(spec.get("values", ())) == 1):
            drops[it].add(room)

    # DROP sites -- where an item can LEAVE your inventory. Declared since the first version but
    # never populated. Needed to place NEGATIVE guard literals: `!own(Spinach_Dip)` may only be
    # demanded where the dip can still be got rid of (rm131, `throw bread overboard`, +2 score).
    # Guarding it later would convert a death into a permanent wall.
    for room, script, it, g, _dest in getattr(em, "handler_drops", ()):
        drops[it].add(room)
    for info in em.machines:
        for it in info.get("drops", ()):
            drops[it].add(info["room"])

    # required: rooms whose guard tests own(item)==True (across every guard-bearing structure).
    # PASS 1 -- TRAP items: an item whose own()-guarded branch walks into a DEATH is a trap, not
    # a requirement (Spinach_Dip: eat it -> "the mayonnaise has spoiled" -> death). Mark them
    # GLOBALLY, because the same item is also consumed on a survivable-looking `Said 'eat'`
    # handler (rm300) that would otherwise re-add it as required.
    # The rule is GOAL-REACHABILITY, not death: a use you cannot still win from is not evidence
    # that the item is needed. Death is merely the commonest way to fail that -- a use that dumps
    # you in a region with no path to the goal fails it too, and this catches those for free.
    # An item is a TRAP only if EVERY own()-guarded use is hopeless: Grotesque_Gulp has a fatal
    # use (drink it at the wrong moment) AND winnable ones (the raft), so "hopeless anywhere"
    # would wrongly un-require it; Spinach_Dip is hopeless everywhere.
    goal_ok = goal_reaching_rooms(edges, em.cfg.goal_rooms)

    gr_maps, hopefuls, hopeless = {}, set(), set()
    for i, info in enumerate(em.machines):
        gr = gr_maps[i] = goal_reaching(info, goal_ok)
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                target = hopefuls if hopeful(info, K, tr, gr, goal_ok) else hopeless
                target |= _own_positive(g)
    # ...and the uses that live on a MOVEMENT EDGE. The rule below is "a trap is an item whose
    # EVERY own()-guarded use is hopeless", but it only ever looked at machine states, so an item
    # whose real use is an edge could be condemned by an unrelated machine branch -- and being
    # named a trap erases the item's requirements GLOBALLY, including the ones that edge
    # established. KQ4's Peacock_Feather is exactly that: it tickles the whale into sneezing you
    # out (the rm44->rm31 edge, which reaches the goal), but it ALSO picks the longer digestion
    # timer inside the whale, and that branch ends in death whichever way it is taken. Judging it
    # on the timer alone made the feather a trap and dropped a confirmed stranding.
    for e in list(em.ts.edges) + list(em.ts.cs_edges):
        (hopefuls if e.dst in goal_ok else hopeless).update(_own_positive(e.guard))
    trap_items = hopeless - hopefuls

    required = defaultdict(set)
    # THE GUARD BEHIND EACH NEED SITE -- the need-side twin of `source_guards`. `required` is a
    # room-level union and that is right for the frontier walks, but the site a room's entry came
    # from carries a register condition of its own (LB2's sGiveInvite arming is `own(6) AND
    # global123==2` once the delegate rule lands the doorman's init guard), and
    # `crossing_retires_need` must be allowed to see it: a need room whose EVERY site is
    # register-dead at the post-crossing states is not a live need there. One list per (item,
    # room), one entry per evidence site; `None` marks a site with no guard (the consumption
    # fallback, or evidence read without one) and poisons the room PERMISSIVE -- unconditionally
    # live -- which is the strict direction for a filter that deletes demands.
    required_guards = defaultdict(dict)
    # CONSUMPTION is a FALLBACK evidence source, not an additive one -- see the note where it is
    # applied, below. Collected separately so it can be weighed after all guard evidence is in.
    consumed_at = defaultdict(set)
    def req_item(it, room, guard=None):
        if it not in trap_items:
            required[it].add(room)
            required_guards[it].setdefault(room, []).append(guard)
    # THE ALWAYS-LIVE SCOPES CONTRIBUTE EFFECTS, NOT REQUIREMENTS. `required[X]` means "own(X) is
    # FACED here, as a gate" -- it is the evidence a frontier is computed from, so it has to be a
    # claim about a PLACE. An SCI1 inventory `doVerb` is dispatched by the icon bar and so is
    # available in every room at once; attributing its guard per room converts an AVAILABILITY
    # into a universal requirement, every frontier ends up with everything past it, and
    # `edge_strandings` collapses. Measured on KQ6 when it was done that way: five confirmed
    # softlocks LOST (brick, deadMansCoin, handkerchief, skeletonKey, tinderBox), thirteen false
    # positives gained, and a 45-item guard on rm340->rm155.
    #
    # What such a scope legitimately contributes is kept in full, and elsewhere: the register write
    # itself and its PRECONDITIONS, which land on the cost path (`cheapest((gi, room, v), ...)`).
    # "What it costs to make flag 22 true" is exactly where `flag58 AND flag68` belongs, and that
    # is what makes the teacup's Styx water reach the castle door.
    #
    # `opmodel.global_homed` is derived (`vocab.inventory_scripts`), and on SCO0 titles it is empty
    # because their items live in script 0 -- so this test cannot move LSL2 or KQ4.
    globalsc = getattr(em, "global_homed", ())

    def req(guard, room, script=None, only=None):
        if script is not None and script in globalsc:
            return
        # ...AND A REQUIREMENT IS NOT FILED IN A ROOM ITS OWN GUARD EXCLUDES. Evidence is filed
        # under the room the walk attributed it to, and a script with no room of its own is
        # walked into every room it serves -- so an arm that SAYS which room it belongs to was
        # being recorded in all the others too. `_curroom_impossible` is the same test the
        # extraction walk already applies to `newRoom:` (KQ5's ending montage, whose seven
        # `gCurRoom`-keyed arms otherwise became exits out of Mordack's castle); it is owed here
        # for the same reason and on the same evidence.
        #
        # This is the `global_homed` rule above, one scope down and with a place to stand. The
        # icon bar has NO room, so its guards cannot be filed anywhere; a region does have rooms,
        # and its objects say which ones -- so the fix is to read that, not to drop the scope.
        if _curroom_impossible([guard], room):
            return
        for it in _own_required(guard):     # OR-branch items are NOT required -- see _own_required
            if only is None or it in only:
                req_item(it, room, guard)
        for it in _loc_placed_required(guard, em.ts.placed):   # owner-gate on a PLACED room
            req_item(it, room, guard)
    for e in em.ts.edges:
        req(e.guard, e.src)
    for e in em.ts.cs_edges:
        req(e.guard, e.src)
    for a in em.ts.acqs:
        req(a.guard, a.room)
    for room, script, it, g in em.handler_gets:
        req(g, room, script)
    for room, script, gi, v, g in em.handler_writes:
        req(g, room, script)
    # entry guards of machines we chose not to model -- see opmodel.dropped_entries
    for room, eg, _inst, _recv in getattr(em, "dropped_entries", ()):
        req(eg, room)
    # consuming an item in a HANDLER -- the Pamphlet handed to the bore on the plane (rm62) is a
    # Said-handler `put: 26 -1`, which the machine-body scan never sees. Held back; see below.
    for room, script, it, g, _dest in getattr(em, "handler_drops", ()):
        if script in globalsc:
            continue        # ...and the same for the consumption fallback: an inventory `put:` is
        consumed_at[it].add(room)   # spent wherever you do it, which is nowhere in particular.
    latch_ev = latch_evidence(em)                       # for the entry-firability test below
    for i, info in enumerate(em.machines):
        gr = gr_maps[i]
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                # Same GOAL-REACHABILITY rule as the trap pass, applied per use: an own(X) path
                # you cannot still win from is not evidence X is required here. rm138's day-6
                # hunger accepts own(Spinach_Dip) -> eat it -> "the mayonnaise has spoiled in the
                # hot, tropical sun!" -> death, while the sibling own(Sewing_Kit) branch fishes
                # and lives. Counting the hopeless branch made Spinach_Dip look required.
                if not hopeful(info, K, tr, gr, goal_ok):
                    continue
                req(g, info["room"])
        # machine ENTRY guards too: a `Said 'throw/beach'` success branch is captured as an
        # entry/changeState guarded by own(Sand) -- skipping entries lost Sand/Ash.
        #
        # ...BUT AN ITEM ONLY SOME ARMINGS DEMAND IS NOT A GATE. Facing own(X) on one arm of a
        # fork while another arm is free is not facing it at all; you take the other arm. This is
        # the requirement-side twin of the rule `fatal_uses` already carries ("a death armed on
        # one arm of a fork does not condemn the fork") and of `_own_required`'s own OR-branch
        # exclusion -- the same disjunction, spelled as separate entries instead of a `GOr`.
        #
        # LB2's rm300 is the case: the bar door's `doVerb` arms `sEnterBar` from verb 4, verb 6
        # AND verb 14, and 14 is the notebook's `message` -- so a SYNONYM for "talk to the
        # doorman" made the notebook a requirement of the room, and with it a stranding across
        # the intro's ESC-skip edges. The item is one the opening cutscene hands you on every
        # path (user ground truth 2026-08-10); the demand was never real.
        #
        # NOT `entry_musts`, deliberately, though it answers the same shape of question: it reads
        # each alternative with `_own_positive` -- a mention ANYWHERE, "a mention, not a proof",
        # which is the right conservatism for pricing an arming and the wrong one here. Every one
        # of `sAskEnterBar`'s entries CONJOINS the whole `GOr` of its armer's three cases, so
        # own(2) is mentioned in all three and the intersection keeps it. `_own_required` is the
        # reading `req` itself uses, and it is the one that has to intersect.
        #
        # ...AND AN ENTRY THAT CANNOT FIRE IS NOT AN ARM OF THE FORK. The disjunction above is
        # only as good as the ways in it lists: a way in that no player can take dissolves the
        # price every real way in charges, and the erased requirement is a frontier never
        # computed and a need retired downstream. `_reg_entry_demands._via_latch` already
        # refuses to be vouched for by such an entry -- it is the correction that stopped LB2's
        # cobra pass dissolving its own demand -- and it is owed here for the same reason, off
        # the same evidence (`latch_evidence`). Refused only where the proof is free: a lowered
        # room local with NO writer anywhere in the room. If every entry at a state is
        # unfirable the machine cannot be armed there at all, and nothing is subtracted --
        # judging that from ignorance would fabricate a requirement rather than protect one.
        ent_alts, live_alts = defaultdict(list), defaultdict(list)
        ents = list(info.get("entries", ())) + list(info.get("init_entries", ()))
        for K, eg in ents:
            ent_alts[K].append(_own_required(eg))
            if not _entry_cannot_fire(em, info["room"], eg, latch_ev):
                live_alts[K].append(_own_required(eg))
        for K, eg in ents:
            alts = live_alts[K] or ent_alts[K]
            req(eg, info["room"], only=set.intersection(*[set(a) for a in alts]))
        for it in info.get("drops", ()):
            consumed_at[it].add(info["room"])

    # CONSUMPTION as requirement evidence -- a FALLBACK, scoped exactly as its own rationale
    # always stated: it "catches requirements carrying NO own() guard at all", like the Flower
    # handed to the KGBishnas (rm50), which exists in the game only as `gEgo put: 20 -1`.
    # It was being applied unconditionally, which is additive rather than fallback, and that is
    # a different rule: for an item the game DOES test for, every place it is later used up
    # becomes an extra "needed here" room -- including places past a one-way edge.
    #
    # That produced two confirmed false positives the moment `moveTo:` extraction made LSL2's
    # consumptions visible: rm48's "take off the bikini" handler destroys the Soap, the
    # Bikini_Top and the Bikini_Bottom on three adjacent lines, so all three gained `required@48`
    # beyond the one-way rm47 -> rm48. Both the Soap and the Bikini_Bottom are re-obtainable/safe
    # in play (confirmed by the user); the Bikini_Top is a true softlock, but on its own evidence
    # -- the real `has:` test at rm44, across the rm38 -> rm131 boarding frontier.
    #
    # An item the game tests for already tells us where it is needed. Consumption only speaks
    # for items that carry no test at all -- which is every case this rule was built for
    # (Flower, Pamphlet, Bobby_Pin, Airsick_Bag, Matches, Hair_Rejuvenator, Sand, ...), all of
    # which have empty guard evidence and so are untouched.
    guard_required = {it: set(rooms) for it, rooms in required.items()}
    for it, rooms in consumed_at.items():
        if not required.get(it):
            for room in rooms:
                req_item(it, room)

    # NOTE: a CUTSCENE-SPLICE pass used to live here -- it rewrote `pred -> cutscene -> succ`
    # into `pred -> succ` to fix the Airline_Ticket false positive. It is RETIRED (git history
    # has it). It needed three guards, each added only after the sweep collapsed, and it was
    # actively harmful: splicing rm83 out fabricated an rm82 -> rm92 edge that reconnected the
    # volcano to the island hub, hiding the Ashes/Sand stranding. The gate-aware product graph
    # subsumes it -- the ticket FP was really an unguarded duplicate edge shadowing the machine
    # EXIT's own(ticket) guard (see edge_meta's machine_delivered filter).
    return (edges, edge_kind, sources, drops, required, guard_required, source_guards,
            {it: dict(rooms) for it, rooms in required_guards.items()})


def _cmp_atoms(guard, out):
    """Collect (register, op, const, polarity) comparison atoms from a guard tree."""
    def w(x, pol=True):
        if isinstance(x, list):
            for y in x:
                w(y, pol)
        elif isinstance(x, Pred):
            if x.kind == "CMP":
                try:
                    out.append((x.var, x.op, int(x.value), pol))
                except (TypeError, ValueError):
                    pass
        elif isinstance(x, (GAnd, GOr)):
            for k in x.kids:
                w(k, pol)
        elif isinstance(x, GNot):
            w(x.kid, not pol)
    w(guard)


def _movement_guards(em):
    """Every guard that can gate MOVEMENT: room edges, machine EXIT paths, and machine entries
    (an entry gates the state chain that leads to an EXIT)."""
    for e in em.ts.edges:
        yield e.guard
    for e in em.ts.cs_edges:
        yield e.guard
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    yield g
        for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
            yield eg


def gating_registers(em):
    """DISCOVER the registers worth promoting into the movement model, instead of naming one.

    The product exists to catch exactly one thing: an edge that SETS R:=v composed with an edge
    that REQUIRES R==w for w != v. So a register earns promotion iff it is BOTH compared against
    in a movement guard AND written somewhere -- a register that is never written cannot create
    an inconsistent composition, and one that is never compared cannot block anything.

    Purely structural: on LSL2 this rediscovers gCurrentStatus (101) as the widest gater, plus 18
    others, with no game knowledge. See docs/HOW-IT-WORKS.md for why they are kept as independent
    PROJECTIONS rather than one joint product."""
    compared = set()
    for g in _movement_guards(em):
        atoms = []
        _cmp_atoms(g, atoms)
        for (r, op, v, pol) in atoms:
            compared.add(r)
    written = set()
    for room, script, gi, v, g in em.handler_writes:
        written.add(gi)
    # `init` runs on arrival, so a register it sets is genuinely written -- it was only collected
    # apart to keep arrival atomic. Omitting it here meant a flag raised ONLY on entering a room
    # counted as never-written and so was never promoted, however much movement it gated. That is
    # how KQ6 seals the realm of the dead: rm600's init raises flag 15, nothing clears it, and the
    # way in demands it clear.
    for room, vs in getattr(em, "init_writes", {}).items():
        written.update(vs)
    # BOTH lists: an always-live scope's writes are real writes -- KQ6's flag 22 (the magic
    # paint) is written by the inventory `doVerb` and nowhere else, so without this it can never
    # be promoted and the castle's long door reads as free. See opmodel.global_machines for why
    # that scope is kept out of `machines` everywhere else.
    for info in all_machines(em):
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                for (gi, v) in w:
                    written.add(gi)
    # The PREVIOUS-ROOM register is written by no room and by every transition: the Game loop's
    # room switch does `(= <prev> <current>)` before it goes (see extract.prev_room_global), so
    # taking any edge a->b sets it to a. `edge_meta` puts that write on the edge; here it only has
    # to count as written, or the "never written cannot create an inconsistent composition" rule
    # above would keep refusing to promote it while 13 KQ6 edges, 12 KQ4, 53 KQ5 compare against it.
    prev = prev_room_reg(em)
    if prev is not None:
        written.add(prev)
    return sorted((compared & written) - _object_valued_globals(em))


def _object_valued_globals(em):
    """Globals the game stores an OBJECT in -- not numeric registers, whatever else they hold.

    `edge_meta` reads a `!=`/relational demand against `reg_vals` as EXACT, on the stated ground
    that the universe is "the set of values the MODEL can ever produce". That is true only while
    every write is readable. An object pointer is a value the value-model cannot represent at all,
    so such a register's universe is necessarily INCOMPLETE -- and the complement reading of
    `!= 0` is then wrong in the RESTRICTIVE direction: it blocks movement the game allows.

    KQ5's `global322` is the specimen and it cost the game its whole edge analysis. It is a
    scratch slot holding `polyList15` (rm5), `actor_1` (rm67) and `cedric` (script 202), and also
    a plain counter (rm212/213) and the constant 50 (rm12); the constants and the compared values
    made a universe of {0, 50, 100, 200}. rm099 -- the boot room -- branches on the bare
    truthiness `(if global322 (gEgo get: 28) (gCurRoom newRoom: 1))`, which lowered to
    `global322 in {50, 100, 200}` while the start state holds 0, so in THAT projection the walk
    could never leave the start room. `_reach_without` and `reobtainable_rooms` both INTERSECT
    over projections, so one dead projection emptied both for every item: `analyze()` returned
    zero rows for all of KQ5 and could not have returned any.

    Structural and measured, with no game knowledge: LSL2 (8), KQ4 (10), KQ6 (26) and LB2 (20) all
    store objects in globals and NONE of those is promoted, so this is inert on the four; KQ5's
    global322 is the only promoted one in the corpus."""
    got = getattr(em, "_objvalued", None)
    if got is not None:
        return got
    out = set()
    ir = getattr(em, "ir", None)             # the duck-typed emitters the unit tests build carry
    if ir is None:                           #   no IR; with no scripts to read, nothing is refused
        return out
    for _rn, sc in ir.scripts.items():
        bodies = list(sc.procs.values()) + [b for o in sc.objects for b in o.methods.values()]
        for b in bodies:
            for n in I.walk(b):
                if not (isinstance(n, dict) and n.get("t") == "Assignment"):
                    continue
                ks = n.get("kids") or []
                if len(ks) >= 2 and I.is_global(ks[0]) and ks[1].get("t") == "Object":
                    out.add(ks[0]["index"])
    em._objvalued = out
    return out


def all_machines(em):
    """Room machines PLUS the always-live scopes' -- for the three consumers that want both.

    EVERYTHING ELSE TAKES `em.machines` ALONE, DELIBERATELY. A machine the icon bar dispatches has
    no place, and almost everything `machines` feeds is a claim about a place (`required`,
    `sources`/`drops`, EXIT, `death_traps` -- each measured, each broken by lifting it). Only the
    register build wants both lists, because "you can make flag 22 true here, at this cost" IS
    true in every room. See `opmodel.global_machines` for the argument in full.

    Written once so the exception is stated once instead of at each call site, and so the
    defensive `getattr` -- which exists for the duck-typed emitters the unit tests build, not for
    the real one -- lives in one place rather than three."""
    return list(em.machines) + list(getattr(em, "global_machines", ()))


def prev_room_reg(em):
    """The previous-room register for this game, derived once per model. See edge_meta.

    None for a model with no IR behind it -- the derivation reads the Game loop, so a synthetic
    emitter that has no scripts has no previous-room register rather than a default one."""
    if not hasattr(em, "_prev_reg"):
        import extract as X
        ir = getattr(em, "ir", None)
        em._prev_reg = X.prev_room_global(ir) if ir is not None else None
    return em._prev_reg


def asserts_eq(op, pol):
    """Does a `(reg, op, value, polarity)` atom assert `reg == value`?

    Both spellings do: `x == v`, and `not (x != v)`. The second matters because `(if (not gX)
    ...)` is SCI's way of writing "gX is 0" and `atom()` renders a bare global's truthiness as
    `CMP(gX, !=, 0)` -- which is how KQ4's day-only doors are gated.

    Shared deliberately: this test used to be spelled out separately in `required_values` and in
    `edge_meta.reqs`, and fixing one and not the other left the night gate parsed but toothless."""
    return (op == "==" and pol) or (op == "!=" and not pol)


_REL_INV = {"<": ">=", "<=": ">", ">": "<=", ">=": "<"}
_REL_CMP = {"<": (lambda a, b: a < b), "<=": (lambda a, b: a <= b),
            ">": (lambda a, b: a > b), ">=": (lambda a, b: a >= b)}


def _must_hold(guard, out=None):
    """`(reg, value)` pairs the guard REQUIRES along its top-level AND spine.

    `_cmp_atoms` is deliberately flat -- it ignores AND/OR structure and reports every comparison
    it can see. That is fine for collecting positive equalities, which only ever under-constrain,
    but it cannot be used to turn `!= 0` into `== 1`: under a NOT or inside an OR the flag is not
    required at all, and claiming it would BLOCK movement the game allows. So this walks only the
    conjuncts that must hold, stopping at any negation or disjunction."""
    out = set() if out is None else out
    if isinstance(guard, list):
        for g in guard:
            _must_hold(g, out)
    elif isinstance(guard, GAnd):
        for k in guard.kids:
            _must_hold(k, out)
    elif isinstance(guard, Pred) and guard.kind == "CMP" and guard.op == "!=":
        try:
            out.add((guard.var, int(guard.value)))
        except (TypeError, ValueError):
            pass
    elif isinstance(guard, Pred) and guard.kind == "CMP" and guard.op in _REL_INV:
        # A RELATIONAL on the AND spine, keyed with its op so it can never collide with the
        # `!=` pairs above. Same contract: only an atom that MUST hold may constrain.
        try:
            out.add((guard.var, int(guard.value), guard.op))
        except (TypeError, ValueError):
            pass
    elif (isinstance(guard, GNot) and isinstance(guard.kid, Pred)
          and guard.kid.kind == "CMP" and guard.kid.op in _REL_INV):
        # `(not (< x v))` asserts `(>= x v)` -- a computable leaf flip, same as the `==` case.
        try:
            out.add((guard.kid.var, int(guard.kid.value), _REL_INV[guard.kid.op]))
        except (TypeError, ValueError):
            pass
    elif (isinstance(guard, GNot) and isinstance(guard.kid, Pred)
          and guard.kid.kind == "CMP" and guard.kid.op == "=="):
        # `(not (== x v))` is the same assertion as `(!= x v)` -- the two spellings SCI compiles
        # the same test into, and only one of them was read here. Descending a negation is safe
        # exactly when its operand is a leaf: the flip is computable, which is not true of the
        # subtree cases this deliberately stops at.
        try:
            out.add((guard.kid.var, int(guard.kid.value)))
        except (TypeError, ValueError):
            pass
    return out


def _must_equal(guard, out=None):
    """`(reg, value)` pairs the guard REQUIRES to be EQUAL, along its top-level AND spine.

    The mirror of `_must_hold`, which collects the `!=` assertions; same discipline and the same
    reason for it. Stops at any negation or disjunction, because a conjunct under an OR is not
    required and claiming it would let a caller delete something the game allows. The one negation
    it does descend is `(not (!= x v))`, whose flip is computable because the operand is a leaf."""
    out = set() if out is None else out
    if isinstance(guard, list):
        for g in guard:
            _must_equal(g, out)
    elif isinstance(guard, GAnd):
        for k in guard.kids:
            _must_equal(k, out)
    elif isinstance(guard, Pred) and guard.kind == "CMP" and guard.op == "==":
        try:
            out.add((guard.var, int(guard.value)))
        except (TypeError, ValueError):
            pass
    elif (isinstance(guard, GNot) and isinstance(guard.kid, Pred)
          and guard.kid.kind == "CMP" and guard.kid.op == "!="):
        try:
            out.add((guard.kid.var, int(guard.kid.value)))
        except (TypeError, ValueError):
            pass
    return out


def _prev_impossible(guard, room, prev, edges):
    """Does `guard` demand you arrived in `room` from somewhere that cannot reach it?

    The previous-room register is written by no room and by every transition -- taking a->b sets it
    to a -- so `prev == R` inside room X asserts "you got here from R", and the ROOM GRAPH already
    knows whether that is possible. Nothing about items is involved, so this needs no fixpoint: it
    can be asked while the maps are still being built.

    What it is for: Sierra's developer warps. KQ6 hands out five items at once in
    `rm470::init` under `(and global100 (== global12 99) (FileIO 10 {g}))`, and rm99 is the room
    `Main::init` ends on -- so the branch is dead in play, but read permissively it is a free source
    for the old lamp, the skull and the teacup, in a room you can always reach. rm740 and rm750 do
    the same for the peppermint.

    DERIVED, not a debug heuristic, and that distinction is load-bearing. The alternative was to
    recognise KQ6's `(FileIO 10 <marker>)` probe and pin the global it sets, the way
    `config.debug_globals` pins LSL2's. That is worse twice over: KQ6 sets `global90` from the very
    same probe shape to detect the CD, so the recogniser would have to tell two identical idioms
    apart -- and pinning the global also deletes the debug hand-out in `rm740.sc:261`, which sits
    inside a LEGITIMATE `(== global12 180)` branch, leaving `royalRing` with no modelled source and
    inventing a softlock the item oracle says is safe. Reading the previous room leaves that one
    alone, because `prev == 180` IS satisfiable. Measured both ways.

    Three conditions, all of them the conservative direction:
      * the demand is on the top-level AND spine (`_must_equal`), so a `prev` test inside an OR or
        under a negation -- where it is not required -- is ignored;
      * we must actually KNOW where R goes (`R in edges`). A room we extracted no out-edge for is a
        room we learned nothing about, and "no evidence" must not read as "cannot happen" -- that
        is the direction that invents softlocks;
      * and `room` must not be among them."""
    if prev is None:
        return False
    for reg, val in _must_equal(guard):
        if reg == prev and val in edges and room not in edges[val]:
            return True
    return False


def guard_reqs(guard, regs, dom=None):
    """{reg: {values it REQUIRES}} for every reg in `regs` this guard constrains.

    THE one reading of "what does this guard demand of a register", used by both consumers: the
    per-register `required_values` (machine entries, state musts) and `edge_meta`'s per-edge scan.
    They were separate, and only this one knew the flag-SET rule below, so a "this flag is set"
    gate constrained a machine entry and nothing at all on a room edge -- which is how KQ6's realm
    of the dead kept its doors open. See the same-shaped bug in `asserts_eq`'s docstring.

    Only positive equalities are used unconditionally. `!=` and the relational ops constrain
    NOTHING without a complete domain: they would need the value-partition abstraction to stay
    exact, and ignoring them is the PERMISSIVE direction (we never block movement the game
    allows). WITH a complete domain both are exact -- "not v" is "one of the others", and
    `< v` is "one of those below" -- so both lower when `dom` names the register, subject to
    `_must_hold` (an atom inside an OR or under a negation still constrains nothing). The
    relational case is what LB2's street seal needed (docs/LB2-ORACLE.md §7z): the taxi -- the
    museum steps' only exit -- is init:ed under `(< global123 2)`, and the flat reading dropped
    the whole literal, so the exit read free at every act.

    A NEGATED `!=` is a positive equality, though, and that is not a technicality: `(if (not gX)
    ...)` is how SCI writes "gX is 0", and `atom()` turns bare-global truthiness into
    `CMP(gX, !=, 0)`. KQ4's day-only doors are guarded exactly that way -- `(if (not global100)
    <open the door>)` -- so without this the night gate parsed fine and then constrained nothing.

    ...and a POSITIVE `!=` is exact too whenever we know the register's COMPLETE domain, because
    "not v" is then just "one of the others". Two registers qualify and `dom` carries them:

      * a flag global WE minted from a flag store -- our lowering writes 1 to set and 0 to clear
        and nothing else, so `(!= flag 0)` IS `== 1`. The only way a "this flag is SET" gate can
        ever carry, and KQ6's walk out of the catacombs needs the minotaur-defeated flag.
      * the PREVIOUS-ROOM register, whose domain is the set of rooms an edge can leave from -- by
        construction, since `edge_meta` is what writes it. KQ6's realm of the dead is left through
        exactly one door and that door reads `(!= global12 670)`: you may go out only if you came
        back from rm690, which is to say only if you held up the mirror and won.

    Both stay subject to `_must_hold`, so a `!=` under a negation or inside an OR still constrains
    nothing -- claiming otherwise would block movement the game allows.

    One walk of the guard tree for ALL the registers: walking it once per register made edge_meta
    19x slower than it needed to be, and `_must_hold` is only paid for if such an atom shows up.
    """
    atoms = []
    _cmp_atoms(guard, atoms)
    out, must = {}, None
    for (r, op, v, pol) in atoms:
        if r not in regs:
            continue
        if asserts_eq(op, pol):
            out.setdefault(r, set()).add(v)
        elif (op == "!=" and pol) or (op == "==" and not pol):
            # Both spellings of "not equal", the mirror of asserts_eq's two spellings of "equal".
            full = ({0, 1} if (v == 0 and r in vocab.BOOL_GLOBALS)
                    else (dom or {}).get(r))
            if not full or v not in full:
                continue                        # domain unknown, or the test excludes nothing
            if must is None:
                must = _must_hold(guard)        # only conjuncts that MUST hold -- see _must_hold
            if (r, v) in must:
                out.setdefault(r, set()).update(full - {v})
        elif op in _REL_INV:
            full = (dom or {}).get(r)
            if not full:
                continue                        # no domain -> a relational constrains nothing
            eff = op if pol else _REL_INV[op]
            sat = {u for u in full if _REL_CMP[eff](u, v)}
            if not sat or sat == set(full):
                continue                        # a contradiction, or the test excludes nothing
            if must is None:
                must = _must_hold(guard)
            if (r, v, eff) in must:
                out.setdefault(r, set()).update(sat)
    return out


def required_values(guard, reg):
    """Values of `reg` this guard REQUIRES, or None if it doesn't constrain it. See guard_reqs."""
    return guard_reqs(guard, (reg,)).get(reg) or None


def structural_reqs(guard, regs, dom=None):
    """{reg: {values}} NECESSARILY true whenever `guard` is -- the register twin of `_own_required`.

    `guard_reqs` reads the atoms FLAT, which is right for its job (what values may this edge be
    crossed at) and wrong for composing one guard into another, because a disjunction of two ways
    through reads as a conjunction of both their conditions. KQ4's whale is exactly that shape:

        (or (and (not (prev == 43)) (prev == 44))         ; arrived from inside the whale
            (and (g109 == 1) ... (g183 == 0) ...))        ; swam up to it with the flute played

    Flat, that demands prev == 44 AND g109 == 1 to be swallowed -- i.e. you may only enter the
    whale if you have just come out of it. So GOr keeps a register only if EVERY branch constrains
    it, unioning the values, and GAnd unions the registers, intersecting values where both
    constrain one. Negation swaps the two, as in `_own_required`."""
    regs = set(regs)

    def walk(g, pol):
        if g is None:
            return {}
        if isinstance(g, list):
            return walk(GAnd(list(g)), pol)
        if isinstance(g, Pred):
            got = guard_reqs(g if pol else GNot(g), regs, dom)
            return {R: set(v) for R, v in got.items()}
        if isinstance(g, GNot):
            if isinstance(g.kid, Pred):
                got = guard_reqs(g if pol else g.kid, regs, dom)
                return {R: set(v) for R, v in got.items()}
            return walk(g.kid, not pol)
        if isinstance(g, (GAnd, GOr)):
            union = pol == isinstance(g, GAnd)   # AND&true or OR&false -> union; else intersect
            kids = [walk(k, pol) for k in g.kids]
            if not kids:
                return {}
            if union:
                out = {}
                for d in kids:
                    for R, vs in d.items():
                        out[R] = (out[R] & vs) if R in out else set(vs)
                return {R: vs for R, vs in out.items() if vs}
            keep = set(kids[0])
            for d in kids[1:]:
                keep &= set(d)
            return {R: set().union(*(d[R] for d in kids)) for R in keep}
        return {}
    return walk(guard, True)


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
    # Which states each entry reaches -- CARRIED-LOCAL aware. The successor walk threads the locals
    # the arming context wrote (info["entry_locals"], parallel to entries) and prunes an ADVANCE
    # whose guard tests a CARRIED local the entry does not satisfy. knockDoor's "open the door" entry
    # carries no local1, so at the door state its only advancing path (the `if local1` branch) is
    # pruned and no other path advances -- a genuine ABORT -- so it never reaches the newRoom:18
    # state to dilute the staff requirement. Crucially this prunes only on a FULL abort (no path
    # advances): a machine that merely branches on a carried local still advances via its other
    # path. A machine with NO carried locals (the common case, ~all of LSL2/KQ4) threads {} and takes
    # every advance exactly as the old guard-ignoring graph did -- byte-for-byte identical.
    from compile import _ctr_holds, _lreg_test
    def _paired(es_key, loc_key):
        # Pad locals to the entry count with {} rather than zip-truncating: a machine whose entries
        # carry no recorded locals (every synthetic test, and any entry opmodel didn't annotate)
        # must still contribute its entry, threading no carried local -- the old behaviour. A bare
        # zip silently DROPPED such entries, emptying entry_alts and ungating the EXIT.
        es = list(info.get(es_key, ()))
        locs = list(info.get(loc_key, ()))
        locs += [{}] * (len(es) - len(locs))
        return list(zip(es, locs))
    ents = _paired("entries", "entry_locals") + _paired("init_entries", "init_entry_locals")
    # The machine's OWN lowered room locals (vocab.lower_room_locals) thread through this walk as
    # counters keyed by their synthetic-global index: the script reloads on room entry, so every
    # arming starts from the declared reset unless the arming context itself wrote the latch --
    # the same "unset reads as 0" the raw-local counters have always had, with the declared value
    # in place of the guess. The atoms and writes STAY registers for every other consumer.
    lregs = info.get("local_regs") or {}
    if lregs:
        ents = [((K, eg), {**lregs, **loc}) for (K, eg), loc in ents]
    carried = set().union(*[set(loc) for _ke, loc in ents]) if ents else set()

    def _ctr_ok(g, counters):
        for a in g:                                # g is a path's atom list (a conjunction)
            if isinstance(a, tuple) and a and a[0] == "CTR" and a[1] in carried and not _ctr_holds(a, counters):
                return False
            if _lreg_test(a, lregs, counters) is False:
                return False
        return True

    def _apply(counters, cw):
        c = dict(counters)
        for (name, kind, val) in cw:
            if name not in carried:
                continue                           # track only carried locals -> bounded state space
            c[name] = val if kind == "set" and val is not None else \
                c.get(name, 0) + (1 if kind == "inc" else -1 if kind == "dec" else 0)
        return c

    per_entry = _entry_reach_walk(info, ents, carried, _ctr_ok, _apply, lregs)
    # THE ARMING FLOOR. You cannot be executing ANY state of this machine without having armed it,
    # so the machine's full arming disjunction bounds every state -- including one the walk above
    # never reached. Falling off the end of the walk is IGNORANCE about the internal path, not
    # evidence that the state is free; the same lesson `fatal_uses` had to learn ("falling off the
    # end of the state graph is not evidence of survival"), in a different consumer.
    #
    # What stops the walk is idiom-specific and there are several: an elided state, a register
    # handoff, or -- KQ6's `wearClothingScr` -- a state that cues ANOTHER script and is resumed by
    # it, so the advance leaves this machine entirely. state 20 does `(secondGuardDoorScr cue:)`
    # and state 21 is the `newRoom: 730` that puts on Beauty's clothes and walks into the castle.
    # The walk stops at 20, so 21 came out ungated and the disguise requirement vanished from the
    # castle's short door. A floor fixes the whole class at once rather than one idiom at a time.
    #
    # This can only ever ADD a requirement that some arming genuinely demands, never invent one:
    # it is the disjunction OVER the entries, so an EXIT is blocked exactly when every way of
    # arming the machine is blocked. A machine with NO entries keeps the empty tuple -- there we
    # really do not know how it is armed, and free is the only honest answer.
    floor = tuple({frozenset(_own_positive(eg)) for (_seen, eg, _loc) in per_entry})
    out = {}
    for K in info["states"]:
        reached = tuple({frozenset(_own_positive(eg)) for (seen, eg, _loc) in per_entry if K in seen})
        out[K] = reached or floor
    return out


def _entry_reach_walk(info, ents, carried, _ctr_ok, _apply, lregs=None):
    """[(states this entry can reach, its guard)] -- the ONE entry-reachability walk.

    Factored out because two views need it: `entry_alts` (which items arm a state) and
    `entry_reqs` (which registers every arming establishes). An entry-reachability rule
    implemented in two places is this project's most-repeated bug -- see test_walkers."""
    cached = info.get("_entry_reach")
    if cached is not None:
        return cached
    lregs = lregs or {}
    per_entry = []
    for (K, eg), loc in ents:
        seen, visited = set(), set()
        stack = [(K, {n: v for n, v in loc.items() if n in carried})]
        while stack:
            if len(visited) > 4000:                # a carried local inc'd in a loop can blow up the
                seen |= set(info["states"])         # (state, counters) space; fall back to permissive
                break                               # (all states reachable) rather than under-report
            u, counters = stack.pop()
            key = (u, tuple(sorted(counters.items(), key=repr)))
            if key in visited:
                continue
            visited.add(key)
            seen.add(u)
            for (g, w, gg, c, tr) in info["states"].get(u, ()):
                if not _ctr_ok(g, counters):
                    continue
                nc = _apply(counters, c)
                for (gi, v) in (w or ()):
                    if gi in lregs:                # the machine's own lowered-local write: the
                        nc[gi] = v                 # walk tracks it, the register model keeps it
                if tr[0] == "ADVANCE":
                    stack.append((u + 1, nc))
                elif tr[0] == "JUMP":
                    stack.append((tr[1], nc))
                elif tr[0] == "SETSTATE":
                    stack.append((tr[1] + 1, nc))
        per_entry.append((seen, eg, dict(loc)))
    info["_entry_reach"] = per_entry
    return per_entry


# The musts walk explores (state, local-valuation) pairs to a fixpoint; the cap only exists so a
# counter incremented in a loop cannot spin it forever. At 20000 it was low enough that ordinary
# machines hit it (KQ5's walkThruBoy/walkThruW3, plain cutscene walkers) and shipped as UNKNOWN --
# a silent model gap, not a safety win, since running out degrades to permissive anyway.
_STATE_MUSTS_CAP = 200000


def state_musts(info, regs):
    """State -> {register: allowed values} that hold on EVERY path reaching it from an entry.

    A cutscene decides its outcome early and pays it off late. KQ6's minotaur fight branches at
    state 8 -- with the red scarf on the minotaur it charges into the wall and dies, without it you
    are gored -- and only the surviving path walks on to state 14, which sets the minotaur-defeated
    flag and arms the walk-out. We guard each state independently, so state 14's effects looked
    reachable regardless, and the catacombs never sealed.

    Forward dataflow over the machine's own transitions, intersecting where paths rejoin, so a
    constraint survives only if EVERY way of getting here established it. A register the machine
    WRITES on the way loses its constraint at that point -- the machine changed it, so what held
    before says nothing after.

    The dataflow node is `(state, local valuation)`, NOT the state alone, and that distinction is
    the whole point. A cutscene routinely decides something early, remembers it in a LOCAL, and
    acts on it much later. KQ6's tapestry is the case:

        (2  (if (rLab seenSecretLatch:) (= local1 1) ... else (self cue:)))
        (18 (if local1 ... (rLab hiddenDoorOpen: 1) ... else (self cue:)))

    so opening the secret door to the minotaur's lair requires having watched him through the
    hole-in-the-wall. Keyed by state alone, both branches of state 2 reach state 18 and the merge
    -- correctly, for "what holds on EVERY path here" -- throws `seenSecretLatch` away before the
    local can discriminate. Split the node by the local and the two paths never meet: the branch
    that reaches the write is the one that established the latch. (Tracking locals as extra FACTS
    instead of as part of the node does not work, and was tried; the merge still erases them.)

    Locals are the machine's own, resolved exactly as `compile_machine` resolves them -- same
    `_apply_counters` / `_ctr_holds`, same "an UNESTABLISHED local is unknown, not 0" (corrected
    2026-08-06: reading it as 0 answered confidently about a value the walk never saw and killed
    203 KQ6 state-paths, `alexWedding`'s exits among them), same seeding from the arming
    context's `entry_locals` -- so the two views of one machine cannot drift. A path whose counter
    guard is decidably false at the current valuation is not walked at all.

    ⭐ AND IT CARRIES THE OWNER STORE ON THE SAME WALK (`sm.owners(K)`), because "what every path
    here established" is exactly the question an ACQUISITION inside a cutscene needs asked. KQ5's
    haystack is the case and it decided the whole shop market:

        (5  (if (and (or <a throwable is the dog's>) (== ((gInv at: 3) owner:) 27))
                ...the ants repay you...   else (client setScript: 0)))
        (14 (gEgo get: 3))

    The needle is handed over eleven states after the condition that earns it, and state 14's own
    path guard says nothing at all -- so read state-locally the pickup is unconditional, the
    owner graph records it under the WILDCARD owner, and NO destination is ever permanent for the
    needle. `_acq_guards`' machine half used to read the ENTRIES only, which covers a condition on
    the way IN (KQ6's lamp, gated in `rm520::init`) and misses every condition the cutscene checks
    once it is running. One walk, two accumulators; a second walk would be the same rule in two
    places.

    Returns a mapping usable as before (`sm.get(K, {})` merges every valuation reaching K, the
    conservative answer) plus `sm.at(K, guard)`, which keeps only the valuations that guard's own
    counter conditions admit -- what a consumer holding a specific path should ask."""
    import compile as C
    out = {}                                       # (K, loc-key) -> {R: set(values)}
    own = {}                                       # (K, loc-key) -> {item: set(owner values)}
    work = []

    # ⭐ THE NODE IS SPLIT BY THE LOCALS THIS MACHINE ACTUALLY CONSULTS, AND ONLY THOSE.
    # Splitting on a local no guard here reads cannot change an answer -- `loc` is used for
    # exactly two things, `C._ctr_holds` on this machine's own path guards and `_Musts.at`'s
    # filter, both of which ask about locals the machine COMPARES -- but it does change the
    # size of the walk, without limit. KQ4's `deadTimer` is the specimen: 11 states, no counter
    # guard at all, and an unbounded `(++ local3)` nothing ever reads, so every increment minted
    # a fresh valuation and the walk ran to its 200000-step cap and then threw away everything
    # it had learned (the honest fallback below). Eleven states cost 200000 steps and shipped
    # UNKNOWN musts.
    #
    # Measured on KQ4 the day the local-proc fix made those bodies bigger: with the projection
    # the machine converges in a handful of steps and the degradation goes away. An untracked
    # local is simply absent from the valuation, which `_ctr_holds` already reads as UNKNOWN --
    # the permissive direction, and the same reading an unestablished local has always had.
    # ...AND A COUNTER IS ONLY DISTINGUISHABLE UP TO THE CONSTANTS IT IS COMPARED AGAINST, so
    # values past them SATURATE. `==`, `!=` and the relationals against a constant set C all
    # give the same answer for every value above max(C), so collapsing them loses nothing and
    # is what makes an incremented counter's space finite at all. Without it a `(++ local)`
    # inside a loop mints a fresh valuation forever and the walk can only ever end at its cap.
    def _ctr_keys(g, acc):
        if isinstance(g, (list, tuple)) and not (isinstance(g, tuple) and g and g[0] == "CTR"):
            for x in g:
                _ctr_keys(x, acc)
        elif isinstance(g, tuple) and g and g[0] == "CTR":
            acc.setdefault(g[1], set()).add(g[3] if isinstance(g[3], int) else 0)
        elif isinstance(g, GNot):
            _ctr_keys(g.kid, acc)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                _ctr_keys(k, acc)
        return acc

    tracked = {}
    for _K, paths in (info.get("states") or {}).items():
        for p in paths:
            _ctr_keys(p[0], tracked)
    for (_K, eg) in list(info.get("entries", ())) + list(info.get("init_entries", ())):
        _ctr_keys(eg, tracked)
    limit = {k: max(abs(v) for v in vs) + 1 for k, vs in tracked.items()}

    # The items this machine's own guards say anything about -- the same "track only what is read
    # HERE" discipline `tracked` applies to counters, and it keeps the second accumulator empty for
    # the overwhelming majority of machines.
    #
    # ⛔ MINUS EVERY ITEM THIS MACHINE RELOCATES. The step tuple carries the path's GETS but not
    # its moves, so a fact established before a `put:` cannot be expired at the right state. An
    # owner fact that outlives the move it was invalidated by is too TIGHT, and this walk's whole
    # discipline is that a partial intersection is the dangerous direction (see the cap fallback
    # below). Dropping the item outright is the honest answer, and it costs nothing here: a
    # machine that hands the item away is not a machine whose acquisition of it we are conditioning.
    room = info.get("room")
    moved = {it for (it, d, _g) in info.get("moves", ()) if d != E.EGO}   # a move INTO the ego's
                                                                         # hands is the pickup
                                                                         # itself, not a relocation
    loc_items = set()
    for _K, paths in (info.get("states") or {}).items():
        for p in paths:
            _loc_item_keys(p[0], loc_items)
    loc_items -= moved

    def proj(loc):
        got = {}
        for k, v in loc.items():
            if k not in tracked:
                continue                           # nothing here reads it
            lim = limit[k]
            if isinstance(v, int):
                v = lim if v > lim else (-lim if v < -lim else v)
            got[k] = v
        return got

    def key(loc):
        return tuple(sorted(loc.items(), key=repr))

    def seed(K, loc):
        loc = proj(loc)
        k = (K, key(loc))
        if k not in out:
            out[k] = {}
            own[k] = {}
            work.append((K, dict(loc), {}, {}))

    ents = list(info.get("entries", ()))
    elocs = list(info.get("entry_locals", ()))
    for i, (K, _eg) in enumerate(ents):
        seed(K, elocs[i] if i < len(elocs) else {})
    ients = list(info.get("init_entries", ()))
    ilocs = list(info.get("init_entry_locals", ()))
    for i, (K, _eg) in enumerate(ients):
        seed(K, ilocs[i] if i < len(ilocs) else {})
    seen = 0
    while work and seen < _STATE_MUSTS_CAP:
        seen += 1
        K, loc, cur, curo = work.pop()
        for (g, w, gg, c, tr) in info["states"].get(K, ()):
            if any(isinstance(a, tuple) and a and a[0] == "CTR" and not C._ctr_holds(a, loc)
                   for a in (g if isinstance(g, list) else [g])):
                continue                           # this branch is not taken at this valuation
            nxt = dict(cur)
            for R in regs:
                v = required_values(g, R)
                if v:
                    nxt[R] = (nxt[R] & v) if R in nxt else set(v)
            for (gi, _val) in w:
                nxt.pop(gi, None)                  # the machine wrote it; prior facts expire
            nown = dict(curo)
            for it in loc_items:
                v = _loc_values(g, it, room)
                if v:
                    nown[it] = (nown[it] & v) if it in nown else set(v)
            for it in gg:
                nown.pop(it, None)                 # it is in the ego's hands now; where it LAY
                                                   # before this step says nothing after it
            if not tr:
                continue
            if tr[0] == "ADVANCE":
                dst = K + 1
            elif tr[0] == "JUMP":
                dst = tr[1]
            elif tr[0] == "SETSTATE":
                dst = tr[1] + 1
            else:
                continue
            nloc = proj(C._apply_counters(loc, c or ()))
            dk = (dst, key(nloc))
            if dk in out:
                merged = {R: out[dk][R] | nxt[R] for R in set(out[dk]) & set(nxt)}
                mown = {i: own[dk][i] | nown[i] for i in set(own[dk]) & set(nown)}
                if merged == out[dk] and mown == own[dk]:
                    continue                       # fixpoint on this edge
                out[dk], own[dk] = merged, mown
            else:
                out[dk], own[dk] = nxt, nown
            work.append((dst, nloc, out[dk], own[dk]))
    if work:
        # THE CAP RAN OUT WITH WORK LEFT, so `out` holds constraints established by only SOME
        # of the paths that reach each state -- and a MUST is an intersection, so a partial
        # answer is too TIGHT, not too loose. Downstream `edge_meta` intersects it into the
        # crossing's requirements, so an over-tight must removes a crossing the game allows,
        # shrinks `reobtainable_rooms` and INVENTS a stranding. Fall back to no constraints,
        # which is the direction the sibling walk at `_entry_reach_walk` already takes ("fall
        # back to permissive rather than under-report"), and say so: a machine whose musts we
        # could not establish is a real gap in the model, not a normal result.
        _degraded_model("state_musts hit its %d-step cap for %s; treating its musts as "
                        "UNKNOWN (permissive) rather than shipping a partial intersection"
                        % (_STATE_MUSTS_CAP, info.get("inst", "?")))
        return _Musts({}, {})
    return _Musts(out, own)


class _Musts(dict):
    """`state -> musts`, merged over local valuations, with `at()` for a specific path.

    Subclasses dict so every existing `sm.get(K, {})` reads the merged (conservative) answer and
    nothing had to change to keep working."""

    def __init__(self, by_node, own_by_node=None):
        self._by_node = by_node
        self._own_by_node = own_by_node or {}
        merged = {}
        for (K, _lk), d in by_node.items():
            merged[K] = d if K not in merged else \
                {R: merged[K][R] | d[R] for R in set(merged[K]) & set(d)}
        self._own = {}
        for (K, _lk), d in self._own_by_node.items():
            self._own[K] = d if K not in self._own else \
                {i: self._own[K][i] | d[i] for i in set(self._own[K]) & set(d)}
        super().__init__(merged)

    def owners(self, K):
        """`{item: {owner values}}` that every path reaching state K established.

        The ownedBy half of the same walk -- see `state_musts`' haystack. Empty for all but the
        handful of machines whose own guards read where an item is lying."""
        return self._own.get(K, {})

    def at(self, K, guard):
        """The musts at K over only the valuations `guard`'s own counter conditions admit."""
        import compile as C
        conds = [a for a in (guard if isinstance(guard, list) else [guard])
                 if isinstance(a, tuple) and a and a[0] == "CTR"]
        if not conds:
            return self.get(K, {})
        acc = None
        for (K2, lk), d in self._by_node.items():
            if K2 != K or not all(C._ctr_holds(a, dict(lk)) for a in conds):
                continue
            acc = dict(d) if acc is None else {R: acc[R] | d[R] for R in set(acc) & set(d)}
        return acc if acc is not None else self.get(K, {})


def _own_negative(guard, out=None):
    """Items the guard requires you NOT to hold -- `own(X)` under a negation. The mirror of
    `_own_positive`, and what turns "you die here without the brick" into "leaving needs it"."""
    out = set() if out is None else out

    def w(g, neg):
        if isinstance(g, list):
            for k in g:
                w(k, neg)
        elif isinstance(g, GNot):
            w(g.kid, not neg)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                w(k, neg)
        elif isinstance(g, Pred) and g.kind == "OWN" and neg:
            out.add(g.var)
    w(guard, False)
    return out


def _has_opaque(guard):
    """Does the guard contain anything we could not model? Then it is not safe to negate."""
    if isinstance(guard, list):
        return any(_has_opaque(k) for k in guard)
    if isinstance(guard, (GAnd, GOr)):
        return any(_has_opaque(k) for k in guard.kids)
    if isinstance(guard, GNot):
        return _has_opaque(guard.kid)
    if isinstance(guard, Pred):
        return guard.kind not in ("OWN", "CMP", "LOC", "IPROP", "POS")
    return guard is not None            # a bare tuple (CTR) or anything unrecognised


def _trap_rooms(em):
    """`room -> [machine info]`, including the machines we chose not to model.

    A machine we dropped is still a COMPETITOR for the room's script slot. KQ6's `lightItUp` is
    gated `own(tinderBox)` and does nothing we track (it starts a palette fade), so it is dropped --
    and it is the only thing that stops the minotaur killing you in the dark. Carried as a stateless
    stand-in: no states, so it can never be `fatal`, but its NAME still participates in the doomed
    walk, so a dropped machine that re-arms the death is excluded like any other."""
    by_room = {}
    for info in em.machines:
        by_room.setdefault(info["room"], []).append(info)
    for room, eg, inst, recv in getattr(em, "dropped_entries", ()):
        by_room.setdefault(room, []).append(
            {"room": room, "inst": inst, "entries": [(0, eg)], "entry_recv": [recv],
             "entry_armers": [], "states": {}})
    return by_room


def _trap_graph(infos):
    """`(arms, fatal, doomed)` for one room's machines.

    `fatal` names the machines that reach a DEATH transition themselves; `doomed` closes that over
    the arming graph, so a machine that ends by arming the death is doomed too. KQ6's `throwSkull`
    is the specimen -- it throws the skull into the gears, the gears are not jammed, and its last
    state arms `sqwishEm` again.

    `handoff` is the same arming relation keyed by the ARMING STATE,
    `(armer, state) -> {armed name: the entry guard IT gets from this site}`, which is what tells a
    state that ends the machine apart from one that ends it by starting the death. `entry_armers`
    already carries the state; only `arms` was throwing it away. The guard comes along because an
    arming site can carry a condition the armer itself contradicts -- see `_ctr_contradicted`.

    Shared by `death_traps` and `fatal_uses`, which ask opposite questions of the same graph: one
    wants the machines that are NOT doomed (the escapes), the other wants the ones that ARE (the
    actions that kill you). They were one function's local variables, and the second consumer is
    exactly the moment that becomes a bug waiting to happen -- see the codebase's running theme of
    the same rule living in two places."""
    arms, handoff = {}, {}                         # machine name -> names it arms; + by state
    for info in infos:
        for j, a in enumerate(info.get("entry_armers") or ()):
            if a:
                arms.setdefault(a[0], set()).add(info["inst"])
                ents = info.get("entries") or ()
                g = ents[j][1] if j < len(ents) else None
                handoff.setdefault(a, {})[info["inst"]] = g
    fatal = {i["inst"] for i in infos
             if any(tr and tr[0] == "DEATH"
                    for _K, ps in i["states"].items() for (_g, _w, _gg, _c, tr) in ps)}
    doomed, changed = set(fatal), True
    while changed:                                 # ...and anything that arms something fatal
        changed = False
        for a, bs in arms.items():
            if a not in doomed and (bs & doomed):
                doomed.add(a)
                changed = True
    return arms, fatal, doomed, handoff


def _succ_state(K, tr):
    """The state a transition moves to, or None if it ends the machine. The successor rule is the
    game's, and it is spelled the same way in `opmodel._state_info`; keep them in step."""
    if not tr:
        return None
    return (K + 1 if tr[0] == "ADVANCE" else tr[1] if tr[0] == "JUMP" else
            tr[1] + 1 if tr[0] == "SETSTATE" else None)


def _ctr_contradicted(guard, known):
    """Does `guard` demand a local/register value that `known` says it does not have?

    Only the top-level AND spine, and only leaves whose key we actually know -- the same discipline
    as `_must_hold`. A demand under an OR is not a demand, and a key we have no value for tells us
    nothing.

    This exists because SCI's `register` lets ONE machine be two, and the two halves can disagree
    about whether you die. KQ6's rm407 is the case, and it is why putting the hole on the wall --
    the puzzle's solution -- looked like a fatal use:

        rm407.sc:193       (gCurRoom setScript: putHoleOnWall 0 1)     ; armed with REGISTER 1
        putHoleOnWall st4  (if (== register 1) (gEgo setScript: holeTimer) ... (self dispose:)
                            else (client setScript: emptyHandedDeath))

    so the death is armed from `putHoleOnWall` only when its register is NOT 1 -- and it is always
    1. The model had both halves all along: the death's entry from that site carries
    `NOT (R0 == 1)`, and `putHoleOnWall`'s own `entry_locals` carries `{('R',0): 1}`. Nothing was
    missing except putting them together."""
    if not known:
        return False
    out = []

    def walk(g, pol):
        if isinstance(g, list):
            for k in g:
                walk(k, pol)
        elif isinstance(g, GAnd) and pol:
            for k in g.kids:
                walk(k, pol)
        elif isinstance(g, GNot):
            walk(g.kid, not pol)
        elif isinstance(g, tuple) and len(g) == 4 and g[0] == "CTR" and g[1] in known:
            got, op, want = known[g[1]], g[2], g[3]
            holds = (got == want) if op == "==" else (got != want) if op == "!=" else None
            if holds is not None and holds is not pol:
                out.append(True)
    walk(guard, True)
    return bool(out)


def _armer_knowns(info):
    """Local/register values that EVERY arming of this machine establishes.

    Intersected across entries, because one arming setting `register 1` says nothing about a second
    arming that sets 0 -- and suppressing a death on a value only one way in provides is how you
    lose a real hazard."""
    ents, els = info.get("entries") or (), info.get("entry_locals") or ()
    if not ents or len(els) != len(ents):
        return {}
    common = None
    for d in els:
        d = d or {}
        common = dict(d) if common is None else {k: v for k, v in common.items() if d.get(k) == v}
    return common or {}


def _complementary(a, b):
    """Are these two path guards `g` and `NOT g` -- i.e. is the state a real BRANCH?

    Structural and deliberately narrow: one side is a single `GNot` whose kid IS the other side's
    single guard. Anything cleverer would be inventing a satisfiability claim about conditions we
    often cannot evaluate (LB2's arm turns on `(mummy cel:)`, object-property state we do not
    model), and the whole point of the rule is that an UNEVALUABLE arm is still an arm."""
    if len(a) != 1 or len(b) != 1:
        return False
    x, y = a[0], b[0]
    return ((isinstance(x, GNot) and x.kid == y)
            or (isinstance(y, GNot) and y.kid == x))


def _survivable(info, unavoidable, handoff, start=None, preempt=frozenset()):
    """Is there ANY way through this machine, FROM STATE `start`, that does not end in death?

    Per ENTRY, not per machine, because one machine routinely serves both roles. KQ6's
    `emptyHandedDeath` is armed four ways at three different states -- one of them the timer that
    kills you for lingering, another the act of putting the hole UP, which is the puzzle's solution.
    Asking only about the machine's own `start` and then blaming every entry condemned the
    hole-in-the-wall for the death it exists to prevent.

    `doomed` -- death is REACHABLE -- is the wrong test for blaming an item, and getting that wrong
    is instructive: it condemned the shield for the KQ6 archer, the hole-in-the-wall for the
    labyrinth and LSL2's Matches for the volcano, which are precisely the items that SAVE you.
    Those machines all branch on the item and only one arm dies. `throwSkull` does not branch: every
    path reaches state 24, which arms the ceiling again.

    So the question is co-reachability, not reachability. A state survives if any of its paths
    does, and a path survives when it EXITS the room, or ends the machine without handing off to
    something unavoidable, or moves to a state that survives. Cycles resolve to "does not survive"
    by starting pessimistic and only ever adding survivors -- a loop with no way out is exactly the
    timer that kills you.

    PERMISSIVE where we cannot see: a machine with no states at all (a dropped competitor)
    contributes survival, because "we did not learn what happens" must not become "you die here" --
    the same rule `death_traps` states for opaque conjuncts.

    ...with ONE exception, and it is the difference between catching KQ6's skull and not. Running
    off the end of the state graph normally means the machine finished, which is safe. But our
    graph ELIDES states that carry no effect we track, and an arming is not an effect: `throwSkull`
    is modelled as `st23 -> JUMP 25` with a max state of 24, so state 24,
    whose entire body is `(gCurRoom setScript: sqwishEm 0 1)`, is unreachable in our graph and the
    machine reads as survivable. It is not; that state is the crushing ceiling being re-armed.

    So for a machine that DEMONSTRABLY hands off to something unavoidable -- we know it from
    `entry_armers`, which does not depend on state reachability -- falling off the end is not
    evidence of survival, and we decline to call it safe. That is still the conservative direction
    for the machine's own claim: the only machines it can affect are ones already known to arm a
    death."""
    states = info.get("states") or {}
    if not states:
        return True
    inst = info["inst"]
    known = _armer_knowns(info)

    def _lethal_handoff(K):
        """The deaths this state really starts -- an arming whose own guard this machine's
        register contradicts is not one of them."""
        return {m for m, g in (handoff.get((inst, K)) or {}).items()
                if m in unavoidable and not _ctr_contradicted(g, known)}

    def _lethal_guards(K):
        """...and the CONDITIONS those armings carry, which is how an arm is told from its
        siblings. `handoff` is keyed by state, so the fork rule below could only ever ask
        whether the STATE branches; these are what let it ask whether THIS ARM is the one that
        hands you over."""
        return [g for m, g in (handoff.get((inst, K)) or {}).items()
                if m in unavoidable and not _ctr_contradicted(g, known) and g is not None]

    def _carries(pg, hgs):
        """Does this arm's own guard SAY the handoff fires?

        True only when the game spells the arming's condition as the arm's condition -- the
        guard tree is the arm's whole guard, or one of its conjuncts. That is the common
        spelling (LB2's rm620 vat: the arm is `392!=0` and so is the handoff; rm715's question:
        both are `NOT local0`), and where it holds, taking this arm is taking the death,
        whatever transition the arm carries. Where the arming's condition is some larger
        expression we cannot line up with an arm (rm700's `sExitRoom`, whose handoff guard is
        the armer's whole entry disjunction), this says nothing and the fork rule behaves as it
        did -- deliberately, because that case is the play-validated false positive the fork
        rule exists to prevent."""
        return any(hg == pg or (isinstance(pg, list) and hg in pg) for hg in hgs)

    hands_to_death = any(_lethal_handoff(K) for (a, K) in handoff if a == inst)
    # A state that RESTORES PLAYER CONTROL and then waits is PRE-EMPTABLE: the machine occupies
    # a `setScript:` slot, so arming any competitor into the same slot disposes it, pending death
    # and all -- the same slot-race semantics `death_traps` is built on, seen from inside the
    # machine. LB2's `sUnlockTrunk` is the case: state 6 does `handsOn:` + `(= seconds 6)`, and
    # the player who uses the meat arms `sInsertMeat` (same slot, not doomed) before the ferrets
    # wake -- so using the skeleton key is the SOLUTION, not a fatal use, and the meat's own cost
    # rides sInsertMeat's entry like any other requirement. `preempt` is the competitor set the
    # caller computed from `entry_recv`; membership in `unavoidable` is re-checked here because
    # the caller's fixpoint grows it -- a competitor that turns out doomed pre-empts nothing, and
    # neither does one the player cannot arm (the caller's `_armable`, added 2026-08-14).
    # `restores_control` is derived: `machine._restore_sels` keeps the 'restore'-kind selectors
    # of `vocab.derive_control_selectors`, and SCI0 declares none (LSL2/KQ4 derive
    # {'init': 'take'} and nothing else -- re-measured 2026-08-14), so nothing here can move the
    # two golden games; and a machine that never hands control back (KQ6's throwSkull) is
    # exactly as condemned as before.
    restored = info.get("restores_control") or set()
    safe, changed = set(), True
    while changed:
        changed = False
        for K, paths in states.items():
            if K in safe:
                continue
            if K in restored and (preempt - unavoidable):
                safe.add(K)
                changed = True
                continue
            # A state that hands the room's script slot to a death is not safe by ANY path: the
            # `setScript:` replaces whatever this machine would have done next.
            #
            # ...UNLESS THE STATE IS A BRANCH (2026-08-09). `handoff` is keyed by state, not by
            # path, so a death armed on ONE arm of a fork condemned the fork. LB2's `sExitRoom`
            # state 1 is the case: `PARK` under `own(35) OR NOT <mummy cel>` hands off to
            # `sKillRileyKill`, and `JUMP 3` under the exact NEGATION reaches `EXIT 710`. Taking
            # the other arm survives, so blaming the item the ENTRY required (`snakeLasso`) was a
            # false positive -- and its remedy, `(not (gEgo has: 19))`, forbids required progress:
            # Spinach_Dip class, the shape that broke LSL2 in play.
            #
            # The test is COMPLEMENTARY GUARDS, not "more than one path": a fork whose arms are
            # `g` and `NOT g` is a genuine choice the player's state decides, which is a claim
            # about branching rather than about how many rows the state happens to have. Measured:
            # kills exactly this row, keeps KQ6's `throwSkull` (the play-validated positive this
            # detector exists for -- it does NOT branch, every path re-arms the ceiling), and
            # leaves LSL2/KQ4 at zero rows.
            #
            # ...AND THE ARM THAT SPELLS THE ARMING'S OWN CONDITION IS NOT AN ESCAPE, whatever
            # transition it carries. `handoff` is keyed by state, so "the state branches" was
            # the only question this rule could ask, and it let an arm that BOTH hands off and
            # exits stand as the way out -- a death deleted on the strength of the arm that
            # causes it. `_carries` asks the narrower question the guards can answer.
            lethal = _lethal_handoff(K)
            hgs = _lethal_guards(K)
            if lethal and not any(_complementary(a, b) for a, *_x in paths for b, *_y in paths):
                continue
            for (_g, _w, _gg, _c, tr) in paths:
                if lethal and not any(_complementary(_g, b) for b, *_y in paths):
                    continue          # this arm carries the handoff and nothing steers away
                if lethal and _carries(_g, hgs):
                    continue          # ...and this one says so itself
                if tr and tr[0] == "DEATH":
                    continue
                if tr and tr[0] == "EXIT":
                    ok = True
                else:
                    nxt = _succ_state(K, tr)
                    ok = (nxt in safe) if (nxt is not None and nxt in states) \
                        else not hands_to_death
                if ok:
                    safe.add(K)
                    changed = True
                    break
    start = info.get("start", 0) if start is None else start
    return start not in states or start in safe


_NEAR_OPS = {"Lt": 0, "Le": 1}          # `< n` bounds the distance by n, `<= n` by n+1


def _negate(g):
    """De Morgan, COLLAPSING the double negation -- there is no canonical negation in guard_ast.

    It matters because `guard_reqs` deliberately reads nothing under a `GNot` (`_must_hold`), so
    a `GNot(GNot(x))` built by wrapping is not "x", it is a guard that constrains nothing. The
    first cut of the hazard gate did exactly that and lowered its demand to the empty set --
    silently, since an empty requirement is also what a genuinely free edge produces."""
    if isinstance(g, GNot):
        return g.kid
    if isinstance(g, GAnd):
        return GOr([_negate(k) for k in g.kids])
    if isinstance(g, GOr):
        return GAnd([_negate(k) for k in g.kids])
    return GNot(g)


def _temp_measurements(ast):
    """`Temp index -> the expression it was assigned`, for temps assigned exactly ONCE.

    Sierra measures a distance into a temp in one `cond` arm and re-reads the temp in the next:

        (cond ((> (= temp0 (gEgo distanceTo: self)) 70) <settle down>)
              ((< temp0 30) <strike>))

    so the lethal arm's own test is a bare `(< temp0 30)` and the measurement is two arms up.
    Assigned twice, the binding is not a fact about the method and the temp is dropped."""
    seen = defaultdict(list)
    for n in I.walk(ast):
        if isinstance(n, dict) and n.get("t") == "Assignment":
            ks = n.get("kids") or []
            if len(ks) > 1 and isinstance(ks[0], dict) and ks[0].get("vtype") == "Temp":
                seen[ks[0].get("index")].append(ks[1])
    return {k: v[0] for k, v in seen.items() if len(v) == 1}


def _unwrap_assign(n):
    while isinstance(n, dict) and n.get("t") == "Assignment":
        ks = n.get("kids") or []
        n = ks[1] if len(ks) > 1 else None
    return n


def _distance_subject(n):
    """The OTHER party of an ego `distanceTo:` send -- `"SELF"` or an object name.

    Both spellings, because Sierra uses them interchangeably in the same game: KQ6's rm630 asks
    `(gEgo distanceTo: self)` and its rm660 asks `(self distanceTo: gEgo)`."""
    if not (isinstance(n, dict) and n.get("t") == "Send"):
        return None
    try:
        recv, msgs = I.send_pairs(n)
    except Exception:                                       # noqa: BLE001
        return None
    for sel, ps in msgs:
        if sel != "distanceTo" or not ps:
            continue
        if I.is_global(recv, 0):
            other = ps[0]
        elif isinstance(ps[0], dict) and I.is_global(ps[0], 0):
            other = recv
        else:
            continue
        if isinstance(other, dict):
            if other.get("t") == "Self":
                return "SELF"
            if other.get("t") in ("Object", "Ident"):
                return other.get("name")
    return None


def _near_bounds(node, binds, out):
    """Collect `(subject, radius)` for every "the ego is within N of X" this condition ASSERTS.

    Descends `And` only. An `Or` asserts nothing about either side, and a negation asserts the
    complement -- both are the permissive readings, and both keep a zone out of the set, which
    is the direction that does not invent a wall."""
    if not isinstance(node, dict):
        return
    if node.get("t") == "And":
        for k in (node.get("kids") or []):
            _near_bounds(k, binds, out)
        return
    if node.get("t") in _NEAR_OPS:
        ks = node.get("kids") or []
        if len(ks) != 2:
            return
        lhs = _unwrap_assign(ks[0])
        if isinstance(lhs, dict) and lhs.get("vtype") == "Temp":
            lhs = _unwrap_assign(binds.get(lhs.get("index")))
        r, who = I.as_int(ks[1]), _distance_subject(lhs)
        if who and r is not None:
            out.append((who, r + _NEAR_OPS[node["t"]]))


def _conjuncts(node):
    """A condition flattened at its `And`s -- the only connective that composes into "must"."""
    if isinstance(node, dict) and node.get("t") == "And":
        out = []
        for k in (node.get("kids") or []):
            out += _conjuncts(k)
        return out
    return [node]


def _is_distance_cmp(node, binds):
    """Any comparison of the ego's distance against a literal, in either direction."""
    if not (isinstance(node, dict) and node.get("t") in ("Lt", "Le", "Gt", "Ge")):
        return False
    ks = node.get("kids") or []
    if len(ks) != 2:
        return False
    lhs = _unwrap_assign(ks[0])
    if isinstance(lhs, dict) and lhs.get("vtype") == "Temp":
        lhs = _unwrap_assign(binds.get(lhs.get("index")))
    return _distance_subject(lhs) is not None


def _is_ego_onctl(node):
    """Is this node `(gEgo onControl: ...)` -- the ego's control-plane read, either mode?

    Mode 1 samples the ego's origin pixel; mode 0 (or none) ORs its base rect. Both mean "the
    ego is standing on this ground", which is all a zone test needs -- the rect form can only
    touch MORE cells, and the walk's own 4px grid already blocks a cell any lethal pixel is
    in, so the point reading under-claims by at most an ego's footprint."""
    if not (isinstance(node, dict) and node.get("t") == "Send"):
        return False
    try:
        recv, msgs = I.send_pairs(node)
    except Exception:                                      # noqa: BLE001
        return False
    return I.is_global(recv, 0) and any(s == "onControl" for s, _ in msgs)


def _ctl_masks(node, out):
    """Collect the control-color masks this condition ASSERTS the ego is standing on.

    `(& (gEgo onControl: ...) M)` is the SCI idiom for "the ego touches a colour in M"
    (docs/SCI1.1-SEMANTICS.md §3: kOnControl returns the 1<<colour bitmask). Same connective
    discipline as `_near_bounds`: descend `And` only -- an `Or` asserts nothing about either
    side and a negation asserts the complement, and both keep the zone out, which is the
    direction that does not invent a wall. KQ5's harpy patrol is the motivating spelling:
    `(if (& (global0 onControl: 0) $0002) ... (setScript: harpyScript))`."""
    if not isinstance(node, dict):
        return
    if node.get("t") == "And":
        for k in (node.get("kids") or []):
            _ctl_masks(k, out)
        return
    if node.get("t") in ("BinAnd", "BitAnd"):
        ks = node.get("kids") or []
        if len(ks) != 2:
            return
        a, b = ks
        if _is_ego_onctl(a) and I.as_int(b) is not None:
            out.append(I.as_int(b))
        elif _is_ego_onctl(b) and I.as_int(a) is not None:
            out.append(I.as_int(a))


def _is_ctl_cmp(node):
    """The conjunct IS a `(& (gEgo onControl:) mask)` zone test."""
    got = []
    _ctl_masks(node, got)
    return bool(got)


def _is_script_running(node):
    """`(<obj> script:)` or a bare `script` property -- IS A CUTSCENE RUNNING RIGHT NOW.

    The one condition allowed to sit on a lethal arm without disqualifying it, and the reason
    is not convenience: this is transient INTERPRETER state, not game state. The modeling-gap
    census classifies it FREE for exactly this reason ("is a cutscene currently running on this
    object", ~70 of 91 bare-property edge gates), and a player cannot arrange to have a script
    permanently running -- every one of them ends. So "the snake does not strike while a
    cutscene plays" is not a way past the snake."""
    n = node
    while isinstance(n, dict) and n.get("t") == "Not":
        n = (n.get("kids") or [None])[0]
    if isinstance(n, dict) and n.get("t") in ("Eq", "Ne"):
        n = (n.get("kids") or [None])[0]
    if isinstance(n, dict) and n.get("t") == "Property":
        return n.get("name") == "script"
    if not (isinstance(n, dict) and n.get("t") == "Send"):
        return False
    try:
        _r, msgs = I.send_pairs(n)
    except Exception:                                       # noqa: BLE001
        return False
    return any(sel == "script" for sel, _ in msgs)


def _unconditionally_lethal(conds, binds, kind="disc"):
    """Does this arm say "inside the zone, FULL STOP", or only "inside the zone, and..."?

    A gate built on this claims the zone is ground the player may not cross. If the arm carries
    any OTHER condition -- a room local, a view, a `status` -- then the zone is only sometimes
    lethal, and barring the exit outright over-states it. So anything that is not the zone's
    OWN test (a distance comparison for a disc, an onControl mask for a control zone) or a
    cutscene-running test disqualifies the arm, in either polarity: this is a syntactic
    "mentions nothing else" test, which is the reading that refuses rather than the one that
    reasons. The kinds are mutually disqualifying on purpose -- an onControl conjunct on a
    disc arm (or a distance conjunct on a control arm) is exactly the "and..." this exists to
    refuse, and the disc funnel below was measured with onControl in the refusing set.

    ⭐ MEASURED (discs), and this is what makes it a rule rather than a preference: of the 17
    corpus arms that arm something, EXACTLY ONE passes -- KQ5's snake. Every other one is
    conditional. KQ6's `zombie` needs `(not local73)`, its `deadGuy` pair need `(not local61)`
    and a mover, LB2's `rat3` needs `(== (gEgo view:) 732)` and `(not local5)`, QFG's
    `antwerp` needs `(== status 1)`. Those hazards are real, but "walk here and die" is not
    what their scripts say, and a wall is not what we may build out of them.
    ⭐ MEASURED (ctl zones), 2026-08-19b, at this filter 44 arms pass corpus-wide -- KQ4 39,
    KQ5 5, LSL2/KQ6/LB2 0 -- because `onControl` is ALSO how rooms spell walk-out triggers
    (KQ4's stair rooms, KQ5's shop exits: leaveRoom/walkTo7/walkOutScript machines). The
    funnel's next conjunct does the real work: `_room_unavoidable` in `_apply_hazard_gates`
    keeps only arms whose armed machine is an unsurvivable death, and exactly ONE survives --
    KQ5's rm049 harpy patrol, the play-found return kill. Zero gates move on the four frozen
    games."""
    own = (lambda a: _is_distance_cmp(a, binds)) if kind == "disc" else _is_ctl_cmp
    for (test, _pol) in conds:
        for a in _conjuncts(test):
            if not (own(a) or _is_script_running(a)):
                return False
    return True


def positional_hazards(ir, script):
    """[(objname, radius, [machine names])] -- this room's "come closer and it happens" triggers.

    A `doit` runs every game cycle whether the player wants it to or not, so a `doit` branch
    whose condition bounds the ego's DISTANCE to an object is the script saying "walk within N
    pixels of this and the following is done to you". When the following is an unsurvivable
    death, the object is not scenery: it is a wall with a body count, and the disc of radius N
    around it is ground the player may not cross. That is the CONTROL-MAP / POSITIONAL gap --
    #1 by frequency in the modeling-gap census -- in its cleanest form, because nothing here
    is opaque: the radius is a literal, the position is a property, and (for the snake that
    motivated it) the disarming condition is an ordinary flag we already track.

    This is only the SYNTAX, plus `_unconditionally_lethal`. Whether the armed machine actually
    kills, whether the object stands still, and whether the disc actually seals an exit are
    three separate questions asked by `_apply_hazard_gates`, `_room_unavoidable` and
    `polygons.hazard_barred_exits`.

    MEASURED corpus-wide: 27 `doit` arms bound the ego's distance (KQ5 8, KQ6 6, QFG-VGA 8,
    LB2 5); 17 of those ARM something (6/5/4/2); ONE of the 17 is unconditionally lethal. LSL2
    and KQ4 have none at all: SCI0 spells the same idea as `inRect` over the PIC control plane,
    which is `control_oracle.crossing_gates`' half of this rule."""
    out = []
    for o in script.objects:
        doit = o.methods.get("doit")
        if not doit:
            continue
        binds = _temp_measurements(doit)
        for n in I.walk(doit):
            shape = I.control_shape(n)
            if shape[0] != "branch":
                continue
            for conds, body in shape[1]:
                if body is None:
                    continue
                zones, masks = [], []
                for (test, pol) in conds:
                    if pol:                        # a FAILED prior arm says the ego is FAR, and
                        _near_bounds(test, binds, zones)     # far is not a hazard
                        _ctl_masks(test, masks)
                if zones and masks:
                    continue                       # a mixed trigger is conditional either way
                kind = "disc" if zones else ("ctl" if masks else None)
                if kind is None or not _unconditionally_lethal(conds, binds, kind):
                    continue
                armed = []
                for send in I.sends(body):
                    try:
                        _r, msgs = I.send_pairs(send)
                    except Exception:              # noqa: BLE001
                        continue
                    armed += [ps[0]["name"] for sel, ps in msgs if sel == "setScript"
                              and ps and isinstance(ps[0], dict) and ps[0].get("name")]
                if not armed:
                    continue
                for (who, r) in zones:
                    out.append((o.name if who == "SELF" else who, ("disc", r), armed))
                # a control-mask trigger's host is the machine OWNING the doit -- the zone is
                # ground, not an object, so the host matters only for liveness (who arms it)
                for m in masks:
                    out.append((o.name, ("ctl", m), armed))
    return out


def _hazard_is_stationary(script, name):
    """Is this object's `(x, y)` a PLACE, or just where it happens to start?

    A lethal disc is drawn around the object's declared position, so an object anything ever
    gives a motion to -- or re-`posn:`s, or assigns `x`/`y` -- has no fixed disc and gets none.
    A SECOND, INDEPENDENT reason KQ6's catacombs are out: measured before `_unconditionally_
    lethal` existed (which now refuses them first), `deadGuy`, `deadGuy2`, `zombie` and rm670's
    `gate` matched the syntax and all four MOVE, so all four were refused here."""
    for o in script.objects:
        for body in o.methods.values():
            for n in I.walk(body):
                if not (isinstance(n, dict) and n.get("t") == "Send"):
                    continue
                try:
                    recv, msgs = I.send_pairs(n)
                except Exception:                          # noqa: BLE001
                    continue
                rn = recv.get("name") if isinstance(recv, dict) else None
                if rn != name and not (o.name == name and isinstance(recv, dict)
                                       and recv.get("t") == "Self"):
                    continue
                if any(sel in ("setMotion", "posn", "moveTo", "setTarget", "x", "y")
                       for sel, _ps in msgs):
                    return False
    return True


def _nn(a):
    """Collapse a double negation to its kid. `guard_ast` has no canonical negation, so
    `GNot(GNot(x))` is a guard that constrains nothing until it is unwrapped (the same trap
    `_negate` documents)."""
    while isinstance(a, GNot) and isinstance(a.kid, GNot):
        a = a.kid.kid
    return a


def _demands_nonzero(a):
    """Does this comparison assert the register is NOT its zero baseline? The flag store's
    `(proc0_12 N)` lowers to `!= 0`, but a game that spells the same demand `> 0` or `== 1`
    is saying the identical thing."""
    if not (isinstance(a, Pred) and a.kind == "CMP"):
        return False
    try:
        v = int(a.value)
    except (TypeError, ValueError):
        return False
    return ((a.op == "!=" and v == 0) or (a.op == "==" and v != 0)
            or (a.op == ">" and v >= 0) or (a.op == ">=" and v >= 1))


def _bounded_below(g, S, v):
    """Does this write's own guard prove the register is already BELOW the value written?

    `(if (< global353 120) (= global353 120))` -- rm067, when the henchman throws you in the
    dungeon during phase 331 == 5. The guard bounds the register below the value, so the write
    can only RAISE the countdown: it cannot hasten anything, whatever the register held."""
    for a in (_nn(x) for x in _conj_spine(g)):
        if not (isinstance(a, Pred) and a.kind == "CMP" and a.var == S):
            continue
        try:
            lim = int(a.value)
        except (TypeError, ValueError):
            continue
        if (a.op == "<" and lim <= v) or (a.op == "<=" and lim < v):
            return True
    return False


def _positive_rooms(g, cur, pol, out):
    """Collect the rooms an `== cur` atom names in POSITIVE position, descending through both
    connectives and flipping polarity at each negation. A room named only under a negation is
    one the guard rules out, and reporting it as a place the machine arms is exactly backwards."""
    if isinstance(g, list):
        for k in g:
            _positive_rooms(k, cur, pol, out)
    elif isinstance(g, (GAnd, GOr)):
        for k in g.kids:
            _positive_rooms(k, cur, pol, out)
    elif isinstance(g, GNot):
        _positive_rooms(g.kid, cur, not pol, out)
    elif pol and isinstance(g, Pred) and g.kind == "CMP" and g.op == "==" and g.var == cur:
        try:
            out.add(int(g.value))
        except (TypeError, ValueError):
            pass


def _entry_excludes(g, prev, from_room):
    """Does ONE arming guard rule out an arrival from `from_room`? A `prev != X` conjunct
    excludes X; a `prev == Y` conjunct excludes everything else. Anything less readable
    excludes nothing. Whether the MACHINE is disarmed is a question about all of its entries
    together -- see `_fold_disarmed`."""
    for a in (_nn(x) for x in _conj_spine(g)):
        neg = isinstance(a, GNot)
        k = a.kid if neg else a
        if not (isinstance(k, Pred) and k.kind == "CMP" and k.var == prev):
            continue
        try:
            v = int(k.value)
        except (TypeError, ValueError):
            continue
        if k.op == "==" and ((v == from_room) if neg else (v != from_room)):
            return True
        if k.op == "!=" and ((v != from_room) if neg else (v == from_room)):
            return True
    return False


def _fuse_machines(infos, fuses):
    """Machines whose own states LIGHT one of `fuses`. Running one is a COMMITTED death: the
    expiry is nondeterministic (the KQ4-clock doctrine -- it may fire at any qualifying
    moment), so a localized defuse downstream cannot un-fire it.

    ⛔ LIGHTING IS NOT TOPPING UP (the 2026-08-19d review's F9). A write whose own guard proves
    the register is already below the value written can only hand the player MORE time, and
    condemning it costs something real: a condemned machine is barred from ever being an
    ESCAPE, so a benign clock touch deletes a way out. Only a write we cannot prove
    non-hastening reads as a commitment -- KQ5's cat (`353 := 3` while 353 runs) shortens the
    clock from whatever it held and is one; rm067's `(< 353 120) -> 353 := 120` is not.

    Shared by `fuse_death_armings` and `capture_fold_armings`, which spelled it twice inline
    ([[same-rule-two-places]])."""
    out = set()
    for i in infos:
        for _K, ps in (i.get("states") or {}).items():
            for (g, w, _gg, _c, _t) in ps:
                for (S, v) in (w or ()):
                    if S in fuses and isinstance(v, int) and v != 0 \
                            and not _bounded_below(g, S, v):
                        out.add(i["inst"])
    return out


# Every DIVERGENT falsification question this process has been asked: `(var, op, want, neg,
# values)`. Empty on all five games -- and the day it is not, the suite says so, because which
# way to read one is undecided (see `_falsifies`, N4).
_DIVERGENT = []


def _falsifies(g, writes):
    """Do `writes` -- everything a chain has already committed -- contradict this entry guard?

    Read along the AND spine only (`_must_hold`'s discipline), in both stores the pricing walk
    reads: a register equality the writes overwrite with something else, and a flag polarity
    the writes invert. Anything less readable contradicts nothing.

    WHY THE PRICING WALK NEEDS IT (review F10). An escape that re-arms the encounter it
    answered is priced by conjoining the price of the NEXT encounter's escapes, DISCHARGED of
    what its own chain wrote. Discharge only ever makes an alternative cheaper. The same
    writes can make it IMPOSSIBLE -- and an impossible alternative admitted at its discharged
    price is the cheapest one on offer, so `_minimal` keeps it and the demand collapses to
    less than the game asks for.

    ⛔ A SET OF WRITES IS NOT A REGISTER STATE (2026-08-20 review, R4). `chain_writes` is an
    unordered UNION over every state of a machine AND of the machine that armed it: it says
    what the run TOUCHES, never what a register HOLDS when the run ends. Discharge may read
    that union, because the flag store is monotone -- a flag once set stays set. A register may
    not. The first cut asked "does SOME write contradict this conjunct?", so a chain writing
    S := 2, 3 and 4 falsified `S == 2` as readily as `S == 7`, deleting an escape the game
    really offers; and a deleted escape raises the demand into a wall or vanishes the row into
    a shipped softlock. The question this asks instead is "can the conjunct still hold?" -- it
    is falsified only when the register IS written and NO write of it satisfies the conjunct.
    The negated form falls out of the same reading: `¬(S == v)` is impossible only when `v` is
    the one thing S can hold.

    ⚠️ STILL AN OVER-APPROXIMATION. A write reached on only SOME paths through the chain is in
    the union all the same, so a register the chain MIGHT leave untouched is treated as though
    it were certainly written -- and answering that needs an ORDERED, path-sensitive write
    model, which `chain_writes` is not.

    ⛔⛔ AND IT HAS TWO ERROR DIRECTIONS, NOT ONE (2026-08-20 THIRD review, N4 -- the half R4's
    cure did not declare). The two readings differ on EXACTLY ONE case, and it is the case R4's
    own example is: the register is written, some write satisfies the conjunct and some
    contradicts it -- DIVERGENT. There, `chain_writes` says the run can leave the register
    either way and nothing here can say which.

        keep it (what ships)  -- an escape that exists only on the path not taken is admitted,
                                 at its DISCHARGED price, so `_minimal` prefers it to every
                                 real one and the hold ships WEAKER than the game needs. That
                                 is F10's failure, in the function written to prevent F10.
        drop it (before R4)   -- an escape the game really offers on some path is deleted, so
                                 the demand rises into a wall, or the row vanishes and the
                                 softlock ships unguarded. That is what R4 objected to.

    Neither is a deduction, and the corpus cannot choose between them: measured on KQ5 the day
    R4 landed, `_falsifies` fires 26 times and every firing is the conjunct `global332 == 7`
    against the write set {2, 3, 4} -- NOT divergent, so both readings agree on all 26 and the
    shipped demand does not move either way. R4 is latent here exactly as F1 and F2 were, and
    so is its reversal. `_DIVERGENT` below records the case so the choice stops being invisible:
    a game that produces one says so in the suite BEFORE the hold built on it ships.

    ⭐ PARKED [USER, 2026-08-20]. The permissive reading ships, deliberately, and this is NOT an
    open question blocking anything -- there is nothing in the corpus to decide it with, so it
    waits for a game that asks. ⛔ Do not flip it on a derivation; the tripwire is the point."""
    for a in (_nn(x) for x in _conj_spine(g)):
        neg = isinstance(a, GNot)
        k = a.kid if neg else a
        if not (isinstance(k, Pred) and k.kind == "CMP" and k.op in ("==", "!=")):
            continue
        try:
            want = int(k.value)
        except (TypeError, ValueError):
            continue
        vals = [v for (S, v) in writes if S == k.var and isinstance(v, int)]
        if not vals:
            continue                          # this register is not the chain's business
        holds = [((v == want) if k.op == "==" else (v != want)) != neg for v in vals]
        if not any(holds):
            return True                       # nothing the chain can leave makes it hold
        if not all(holds):
            # DIVERGENT: the chain can leave this register either way, so "the escape exists"
            # and "the escape does not" are both consistent with what we know (N4). Recorded,
            # never guessed at silently -- the reading that ships is the permissive one.
            _DIVERGENT.append((k.var, k.op, want, neg, tuple(sorted(set(vals)))))
    return False


def _minimal(alts):
    """Drop every alternative another one is a subset of -- the cheapest way to pay is the
    only way worth reporting."""
    keep = []
    for a in sorted(set(alts), key=lambda a: (len(a), sorted(a))):
        if not any(k <= a for k in keep):
            keep.append(a)
    return keep


class _Escapes:
    """One room's encounter machines: the ways out of each, and what they cost.

    Lifted out of `fuse_death_armings` the day `capture_fold_armings` needed the identical
    pricing fixpoint ([[same-rule-two-places]]). Both detectors ask one question of one room
    -- KQ5's cat re-arms a remote death fuse when unanswered, KQ5's henchman CARRIES you into
    a lethal arrival fold -- and in both the answer is "what must the player already hold for
    a way out to exist?".

    `lethal` is the caller's: machines whose running is itself the commitment (the room's
    unavoidable deaths, plus -- for both callers -- machines that arm a death fuse, since an
    escape that lights one trades a death for a death; KQ5's organ at rm58 is exactly that)."""

    def __init__(self, s, infos, handoff, lethal):
        self.s, self.infos, self.handoff, self.lethal = s, infos, handoff, lethal
        self.by_name = defaultdict(list)
        self.slots = defaultdict(set)
        for i in infos:
            self.by_name[i["inst"]].append(i)
            for rc in (i.get("entry_recv") or ()):
                if rc is not None:
                    self.slots[rc].add(i["inst"])
        ir = getattr(s.em, "ir", None)
        self.fbase = getattr(ir, "flag_synth_base", None) if ir is not None else None
        self.flags = getattr(ir, "flag_indices", None) or frozenset()
        self._pcache = {}                  # (name, discharged, seen) -> alternatives. `price`
        #   builds a cross-product per register equality and recurses through both the writer
        #   and the continuation walks, so the same (machine, discharge) is asked for many
        #   times over one room; the answer is a pure function of the key.

    def is_flag(self, S):
        return self.fbase is not None and S >= self.fbase and (S - self.fbase) in self.flags

    def armable(self, name):
        """Can the player arm this at all? (`_room_unavoidable`'s own test, same reason: a
        rival gated on something unobtainable buys no escape.)"""
        copies = self.by_name.get(name, ())
        if not copies:
            return False
        for i2 in copies:
            ents = list(i2.get("entries") or ()) + list(i2.get("init_entries") or ())
            if not ents:
                return True                    # no arming we can read: [[arming-floor]]
            musts = entry_musts(i2)
            if any(all(self.s.sources.get(it, set()) & self.s.reach_rooms
                       for it in musts.get(K, ()))
                   for (K, _g) in ents):
                return True
        return False

    def hands_lethal(self, name):
        return {m for (a, K) in self.handoff if a == name
                for m in (self.handoff.get((a, K)) or {}) if m in self.lethal}

    def slot_escapes(self, name):
        """Machines armed into the SAME script slot -- the slot race `death_traps` and
        `_survivable`'s pre-emption rule are both built on."""
        rcs = {rc for i2 in self.by_name.get(name, ())
               for rc in (i2.get("entry_recv") or ()) if rc is not None}
        return sorted({m for rc in rcs for m in self.slots[rc]
                       if m != name and m not in self.lethal and self.armable(m)})

    def chain_writes(self, name):
        """Everything this machine's own run -- and the run that armed it -- commits, so a
        re-armed encounter is not charged again for what has already been paid (KQ5's fish
        answer writes flag 62 on its way to re-arming the cat)."""
        wset = set()
        for i2 in self.by_name.get(name, ()):
            for _K, ps in (i2.get("states") or {}).items():
                for (_g, w, _gg, _c, _t) in ps:
                    wset |= set(w or ())
            for a in (i2.get("entry_armers") or ()):
                if a:
                    for i3 in self.by_name.get(a[0], ()):
                        for _K, ps in (i3.get("states") or {}).items():
                            for (_g, w, _gg, _c, _t) in ps:
                                wset |= set(w or ())
        return wset

    def tokens(self, g, discharged):
        """(tokens, register equalities, unsatisfiable) off one entry guard's AND spine.

        PLAYER-SIDE STORES ONLY, in whichever polarity the game wrote them: possession, the
        flag store, and the ITEM-PROPERTY store -- KQ5 spells "the bag is empty" as
        `(cel == 4)` on the item itself, which extraction already types as an IPROP atom
        rather than an opaque, so it can be demanded verbatim.

        A negated REGISTER comparison is deliberately NOT a token: `¬(global333 == 4)` is the
        encounter's own scene state ("he has not grabbed you yet"), which no player arranges
        in advance. Positive register equalities are priced through their WRITERS instead
        (below), which is how the cat's `332 == 7` arm resolves to the bag answer that
        establishes it. A negated OWN atom is not a token either -- "not holding X" is not
        something the demand can ask the player to arrange, since the guard it becomes would
        forbid an item rather than require one (the Spinach_Dip shape,
        [[spinach-dip-trap-shipped-patch-breaks-lsl2]]).

        ⛔ DISCHARGE HAS A POLARITY (the 2026-08-19d review's F11). A chain that has already
        set flag N discharges a POSITIVE demand for N -- it is paid. It does the opposite to a
        NEGATIVE one: `¬N` can no longer hold at all, so that alternative is UNSATISFIABLE,
        and dropping the token instead reports it as FREE. A free alternative is the cheapest
        on offer, so `_minimal` keeps it and discards every real one. The third return value
        is that verdict; the caller must discard the alternative, not price it."""
        toks, eqs, bad = set(), set(), False
        for a in (_nn(x) for x in _conj_spine(g)):
            neg = isinstance(a, GNot)
            k = a.kid if neg else a
            if not isinstance(k, Pred):
                continue
            if k.kind == "OWN" and k.want and not neg:
                toks.add(("own", k.var))
            elif k.kind == "IPROP" and k.op == "==" and isinstance(k.var, tuple):
                toks.add(("niprop" if neg else "iprop", (k.var[0], k.var[1], k.value)))
            elif k.kind == "CMP" and self.is_flag(k.var) and _demands_nonzero(k):
                written = any(s2 == k.var and v2 for (s2, v2) in discharged)
                if written and neg:
                    bad = True                 # `¬N` under a chain that sets N: impossible
                elif not written:
                    toks.add(("nflag" if neg else "flag", k.var - self.fbase))
        for (S, V) in _must_equal(g):
            if self.is_flag(S):
                if V != 0 and not any(s2 == S and v2 for (s2, v2) in discharged):
                    toks.add(("flag", S - self.fbase))
            elif S in self.s.regs:
                eqs.add((S, V))
        return toks, eqs, bad

    def price(self, name, discharged=frozenset(), seen=frozenset()):
        """Minimal alternatives (frozensets of tokens) that arm `name` AND survive what its
        own run commits to. `[]` = no payable answer.

        The recursion is the fixpoint the cat needed: an escape that itself hands off into the
        lethal set is only HALF an answer -- KQ5's fish throw disposes the cat and then
        re-arms the very encounter it answered -- so its price conjoins the price of the
        escapes of the encounter it re-arms, discharged of everything its own chain wrote. It
        terminates because those writes are monotone; a cycle prices as no answer.

        ⛔ AND WHAT THE CHAIN WRITES CAN DISARM AS WELL AS DISCHARGE (the 2026-08-19d review's
        F10). An entry the discharged writes CONTRADICT cannot fire in the continuation at all,
        so it is not an alternative at any price -- admitting it at its discharged price
        reports a way through the game does not offer, and because the discharge makes it
        cheap, `_minimal` prefers it to every real one. `_falsifies` is that check, and it is
        the mechanism docs/KQ5-ORACLE.md §23 described before the code had it."""
        ckey = (name, discharged, seen)
        if ckey in self._pcache:
            return self._pcache[ckey]
        if name in seen:
            return []
        alts, cont = [], None
        if self.hands_lethal(name):
            d2 = frozenset(set(discharged) | self.chain_writes(name))
            cont = []
            for m2 in self.slot_escapes(name):
                if m2 not in seen:
                    cont += self.price(m2, d2, seen | {name})
            if not cont:
                self._pcache[ckey] = []
                return []
        for i2 in self.by_name.get(name, ()):
            for (_K, g) in (list(i2.get("entries") or ())
                            + list(i2.get("init_entries") or ())):
                if _falsifies(g, discharged):
                    continue                   # this way in cannot fire any more
                toks, eqs, bad = self.tokens(g, discharged)
                if bad:
                    continue
                base = [frozenset(toks)]
                for (S, V) in sorted(eqs):
                    writers = sorted({i3["inst"] for i3 in self.infos
                                      if i3["inst"] != name and i3["inst"] not in self.lethal
                                      for _K3, ps in (i3.get("states") or {}).items()
                                      for (_g3, w, _gg3, _c3, _t3) in ps
                                      for (s3, v3) in (w or ()) if (s3, v3) == (S, V)})
                    sub = []
                    for wn in writers:
                        sub += self.price(wn, discharged, seen | {name})
                    if not sub:
                        bad = True
                        break
                    base = [a | b for a in base for b in sub]
                if bad:
                    continue
                if cont is not None:
                    base = [a | b for a in base for b in cont]
                alts += base
        self._pcache[ckey] = _minimal(alts)
        return self._pcache[ckey]


def _room_unavoidable(infos, sources, reach_rooms):
    """`(doomed, handoff, unavoidable, preempt)` for one room's machines -- the shared front
    half of every detector that must tell a death the player can still dodge from one they
    cannot. Lifted out of `fatal_uses` the day `ownedby_death_folds` needed the identical
    twenty lines ([[same-rule-two-places]]); the corrections recorded below were paid for
    once and must not fork.

    Same-slot competitors, for the pre-emption rule in `_survivable`: the slot a machine's
    arming wrote (`entry_recv`) is the slot a rival `setScript:` steals.

    ...AND ONLY THE ONES THE PLAYER CAN ACTUALLY ARM. Stealing the slot is an ACTION, so a
    competitor is an escape only while the player can perform it: `entry_musts` is the price
    of arming a machine by any route, and a price that cannot be paid buys no escape. The
    pre-emption rule was reading the slot map alone, which says who COULD hold the slot,
    never who the player can PUT there -- so a rival gated on something unobtainable deleted
    a death the player still dies of.

    The test is deliberately the weakest one that is still a proof: an item with no reachable
    source at all. LB2's trunk -- the case the rule exists for -- keeps every one of its
    escapes, `sInsertMeat`'s meat included, because the meat has a source; what it cannot
    keep is an escape whose price does not exist in the game."""
    _arms, _fatal, doomed, handoff = _trap_graph(infos)
    slots = defaultdict(set)
    for i in infos:
        for rc in (i.get("entry_recv") or ()):
            if rc is not None:
                slots[rc].add(i["inst"])
    by_inst = {i["inst"]: i for i in infos}

    def _armable(m):
        i = by_inst.get(m)
        ents = list((i or {}).get("entries") or ()) \
            + list((i or {}).get("init_entries") or ())
        if i is None or not ents:
            return True                        # no arming we can read: not a proof of
                                               # anything ([[arming-floor]]), so as before
        musts = entry_musts(i)
        return any(all(sources.get(it, set()) & reach_rooms
                       for it in musts.get(K, ())) for K, _g in ents)

    def preempt(i):
        return frozenset(m for rc in (i.get("entry_recv") or ()) if rc is not None
                         for m in slots[rc] if m != i["inst"] and _armable(m))
    unavoidable = {i["inst"] for i in infos
                   if i["inst"] in doomed
                   and not _survivable(i, doomed, handoff, preempt=preempt(i))}
    # ...and settle the mutual dependency the same way `_trap_graph` settles `doomed`: a
    # state that hands off to a machine we have just condemned is not an escape either.
    changed = True
    while changed:
        changed = False
        for i in infos:
            if i["inst"] in unavoidable or i["inst"] not in doomed:
                continue
            if not _survivable(i, unavoidable, handoff, preempt=preempt(i)):
                unavoidable.add(i["inst"])
                changed = True
    return doomed, handoff, unavoidable, preempt


def death_traps(em, regs, dom):
    """`room -> [(req, alts), ...]` -- the ALTERNATIVE ways to leave a room whose arrival kills you.

    A room you cannot survive offers no exits, and SCI writes that as a race for one slot. A Script
    object holds exactly one `setScript:` slot, so whichever machine is set last is the one that
    runs, and a player action that grabs the room's slot cancels the timer that was in it. KQ6's
    crushing ceiling is the pure case:

        rm420 walkIn  (9  (global2 setScript: sqwishEm))       ; arrival -> the ceiling comes down
        rm420 theGears doVerb 39 -> (global2 setScript: useBrick)   ; jam it: needs the brick
        rm420 theGears doVerb 51 -> (global2 setScript: throwSkull) ; needs the skull, and ENDS
                                    (global2 setScript: sqwishEm 0 1)  ; ...by dying anyway

    So the slot alone is not enough -- `throwSkull` takes it and hands it straight back to the
    death. An ESCAPE is a competitor from which the death is NOT reachable, following the arming
    graph the machines already record in `entry_armers`. That distinction is the whole rule: with it
    the brick is required to leave rm420 and the skull is not.

    Returns a DISJUNCTION per room, since any one of these gets you out:
      * one alternative per escape (its items), and
      * one per register the death CONDITION pins, requiring the complement -- rm411's collapsing
        floor kills you only while the minotaur lives (`(if (proc913_0 1) <corridor> else
        (setScript: dieAlready))`), so leaving needs flag 1 set.
    Empty when the death is unconditional and no escape was found: refusing to model it is the
    permissive answer, and blocking every exit on a non-observation is how you invent a softlock."""
    out = {}
    for room, infos in _trap_rooms(em).items():
        arms, fatal, doomed, _handoff = _trap_graph(infos)
        rows = []
        for info in infos:
            if info["inst"] not in fatal:
                continue
            slots = {r for r in (info.get("entry_recv") or ()) if r}
            if not slots:
                continue                           # not slot-armed -> no competitor story
            esc = []
            for other in infos:
                if other["inst"] in doomed or other["inst"] == info["inst"]:
                    continue
                for j, (_k, g) in enumerate(other["entries"]):
                    recv = (other.get("entry_recv") or [None] * (j + 1))[j] \
                        if j < len(other.get("entry_recv") or ()) else None
                    items = _own_positive(g) if g is not None else set()
                    if recv in slots and items:
                        esc.append(frozenset(items))
            # The death fires if ANY entry does, so surviving means EVERY entry is false -- and we
            # may only say that when we can read them all. An OPAQUE conjunct makes an entry
            # NARROWER than what we can see, so negating what we can see over-restricts, and
            # "we do not know when this fires" must never become "you die here". KQ4 is the
            # warning: the ogre's `grabbed` is gated on opaques, and negating its readable half
            # demanded the Axe to walk out of four ordinary rooms. Two cases are decidable:
            ents = list(info["entries"])
            if any(g is None for _k, g in ents):
                #  (a) some arming is UNCONDITIONAL, so the death is certain and only an escape
                #      helps. KQ6's ceiling: `walkIn` state 9 arms `sqwishEm` with no guard.
                rows.extend(({}, (a,)) for a in esc)
            elif len(ents) == 1 and not _has_opaque(ents[0][1]):
                #  (b) one arming, fully modelled, so its negation is exactly the way to survive --
                #      a disjunction over its conjuncts, since falsifying any one is enough.
                g = ents[0][1]
                rows.extend(({}, (a,)) for a in esc)
                rows.extend(({}, (frozenset({it}),)) for it in _own_negative(g))
                # The NECESSARY reading, not the flat one. `guard_reqs` reports every comparison it
                # can see, which is right for "what values may this edge be crossed at" and wrong
                # for composing a guard into another -- the same lesson KQ4's whale taught, where
                # the flat reading of a disjunction demanded both its arms. Negating the flat
                # reading of a big `not (or prev==a prev==b ...)` left KQ6's rm480 -> rm490 needing
                # `prev == 490` to reach rm490, so the scarf's own source became unreachable and the
                # scarf stopped being a softlock at all.
                sreq = structural_reqs(g, regs, dom)
                # ...but a register the trap room's OWN machinery writes is the trap's CLOCK, not
                # an escape lever. The complement row asserts "hold the register at another value
                # and the death never fires" -- true for PLOT state written elsewhere (KQ4's dawn
                # is Room82's to bring), and false for a value the room's machines advance on
                # their own: the walk would 'escape' the whale by standing in the state the timer
                # is actively leaving. KQ4's whale taught this the day room locals were lowered
                # into visibility -- the sneeze timer's states pinned the death, their complement
                # priced free, and the feather stopped being required.
                clock = {gi for i2 in infos for _K, paths in i2["states"].items()
                         for p in paths for (gi, _v) in p[1]}
                for R, vs in sreq.items():
                    if R in clock:
                        continue
                    d = dom.get(R)
                    if vs and d and set(vs) < set(d):
                        rows.append(({R: set(d) - set(vs)}, (frozenset(),)))
        if rows:
            out[room] = rows
    return out


def entry_reqs(info, regs, dom=None):
    """State K -> {register: allowed values} that EVERY entry reaching K establishes.

    The REGISTER twin of `entry_alts`, and deliberately the opposite composition. Items are a
    DISJUNCTION -- arm the machine any way you can, so holding one alternative suffices. A
    register requirement is a MUST: it may be carried onto the exit only if every way of arming
    the machine pins it, because a single unconstrained entry means the machine can be reached
    with the register at any value (the same soundness rule `_build_product` applies to ordered
    writes).

    Without this the exit edge inherited its entry's ITEM gates but silently dropped its FLAG
    gates -- so a cutscene armed only while a flag is clear (KQ6's sacred-water rm350->rm370,
    armed only when flag 174 is still 0) came out a free walk.

    Read with `structural_reqs`, the NECESSARY reading, because carrying an entry onto an exit is
    COMPOSING one guard into another -- the third place that distinction has mattered and the same
    lesson KQ4's whale taught (see `structural_reqs`, and `death_traps` case (b)). Flat, a
    disjunction of alternative armings reads as a conjunction of all their conditions: once an
    object's cast condition became a real disjunction, KQ6's `gates` was `arrived from rm490 OR
    NOT arrived from rm490` -- a tautology -- and the flat read turned it into a requirement to
    have already been in rm490 to reach rm490, which strands the red scarf behind its own door."""
    from compile import _ctr_holds, _lreg_test
    reach = _entry_reach_walk_of(info)
    lregs = info.get("local_regs") or {}
    per = []
    for (seen, eg, loc) in reach:
        per.append((seen, loc, {R: v for R, v in structural_reqs(eg, regs, dom).items() if v}))

    def _consistent(loc, guard):
        """Could an arming carrying `loc` have produced a path guarded by `guard`?

        One machine can serve several exits, chosen by the `register` its arming passed --
        KQ6's `walkOut` leaves to the surface when armed with 1 (behind the minotaur flag) and
        back into the maze when armed with 0. Both armings reach the same STATE, so a per-state
        answer intersects them to nothing and the gated escape reads as free. The exit's own
        guard says which arming it belongs to, so honour it. A lowered own-script room local
        (`local_regs`) is the same question in register spelling."""
        for a in (guard or ()):
            if isinstance(a, tuple) and a and a[0] == "CTR" and a[1] in loc \
                    and not _ctr_holds(a, loc):
                return False
            if _lreg_test(a, lregs, loc) is False:
                return False
        return True

    def reqs_for(K, guard=None):
        ds = [d for (seen, loc, d) in per if K in seen and _consistent(loc, guard)]
        if not ds:
            return {}
        common = {R: set().union(*(d[R] for d in ds))
                  for R in set(ds[0]).intersection(*(set(d) for d in ds))}
        return common
    out = {K: reqs_for(K) for K in info["states"]}
    out = {K: v for K, v in out.items() if v}
    out["_by_guard"] = reqs_for
    return out


def _entry_reach_walk_of(info):
    """`entry_alts` populates the cache; call it if nothing has yet."""
    if info.get("_entry_reach") is None:
        entry_alts(info)
    return info.get("_entry_reach") or []


def entry_musts(info):
    """State K -> the items you must be holding to arm this machine at all, by ANY route.

    `entry_alts` is the DNF of ways in; an item you cannot avoid is one that appears in every
    alternative, which is exactly `blocked(alts, {item})`. Stated as a set so callers that need
    the items rather than the yes/no can have them.

    What it is for: a cutscene's body usually carries no path condition at all -- the decision was
    made where the machine was started -- so read alone its effects are free. KQ6's `lookInHole`
    writes `seenSecretLatch`, which is what eventually opens the minotaur's lair and so the only
    way out of the catacombs, and it is armed by clicking a hole that exists only because you
    carried the hole-in-the-wall in and put it up. Its sibling `getTheHole` hands item 18 straight
    back, which is not the labyrinth GIVING you the hole.

    The reading inside one entry is `_own_positive`, inherited from `entry_alts` and deliberately
    the same one `edge_meta`/`blocked` have always used to gate an EXIT on its machine's arming: a
    positive mention of own(X) anywhere in the guard is evidence the action presupposes X. That is
    a mention, not a proof, so it can over-state -- which is why it is intersected over every
    alternative, and why the consumers that subtract on it (a source, a register's cost) keep the
    room or the write whenever ANY other site is free.

    ⛔ TWO CURES MEASURED AND REVERTED HERE, 2026-08-15, both aimed at KQ5's Wand FP (rm066 puts
    the wand down with `put: 28 gCurRoom` and `getCWandScript` picks it back up, so rm66 sits in
    `drops[28]` while this function's mention reading keeps it OUT of `sources[28]`):

      * reading one entry with `_own_required` (OR-branches intersect) -- drops KQ6's
        **holeInTheWall** outright, because rm420..440's `lookInHole` carries own(18) inside a
        large register OR, so every labyrinth cell became a source and the rm420->rm435 carry-in
        toll died;
      * subtracting only an item the entry says is LYING IN THIS ROOM (a positive
        `LOC(X ownedBy room)` disjunct, the "is it still there?" atom read on the arming side) --
        narrower, and it leaves all five frozen surfaces byte-identical, but it still adds rm230
        to `sources[18]`, breaking the enforced KQ6 fact that the hole has ONE source. rm230's
        `removeHoleScr` is "take the hole back off the wall": the SAME put-then-get shape as the
        wand, already ruled not-a-source. The two are not distinguishable by arming structure, so
        there is nothing here to fix -- the Wand wants the NEVER-STRANDABLE class instead.

    Note the second attempt was invisible to `snapshot.py`: `sources` is not in the frozen surface,
    so only test_kq6_ground_truth's structural pin caught it. Detector-adjacent state needs its own
    assertions."""
    ea = entry_alts(info)
    return {K: (frozenset(set.intersection(*[set(a) for a in alts])) if alts else frozenset())
            for K, alts in ea.items()}


def blocked(alts, banned):
    """Is an edge with these DNF alternatives blocked when `banned` items are unavailable?"""
    return bool(alts) and all(a & banned for a in alts)


def _saturating_matching(left, adj):
    """Assign every node in `left` a DISTINCT partner from `adj[node]`, or None if impossible.

    Textbook Kuhn augmenting-path matching. The distinctness IS the content: one shopkeeper
    eats one token, which is what separates a market from a mere disjunction. Deterministic --
    callers pass `left` and each `adj` list sorted -- so a reported witness does not wander
    between runs."""
    matchL, matchR = {}, {}

    def augment(u, seen):
        for v in adj.get(u, ()):
            if v in seen:
                continue
            seen.add(v)
            if v not in matchR or augment(matchR[v], seen):
                matchR[v], matchL[u] = u, v
                return True
        return False

    for u in left:
        if not augment(u, set()):
            return None
    return matchL


def edge_meta(em, regs):
    """(a,b) -> [(req, sets, alts)] for the discovered gating `regs`.

    req  = {reg: {allowed values}}   what the edge's guard demands -- see guard_reqs
    sets = {reg: value}              writes the edge performs on the way out
    alts = DNF tuple of item-sets    (see entry_alts / blocked)

    This is what makes movement GATE-AWARE. The guard-ignoring graph walks rm82 -> rm152 -> rm52
    and so welds the volcano to the airport (the mega-SCC that hid the Pamphlet stranding and
    produced the Airline_Ticket FP). But rm82 dumps you into rm152 having set gCurrentStatus to
    14/15 (bomb botched) while rm152's exit to rm52 REQUIRES 7 -- an impossible composition."""
    regset = set(regs)
    # The previous-room register's COMPLETE domain: every room an edge leaves from, plus the 0 it
    # starts at. Complete by construction -- the writes below are the only ones -- which is what
    # lets `guard_reqs` read `(!= prev 670)` exactly instead of dropping it.
    pdom = {r for e in em.ts.edges for r in (e.src,)} | \
           {r for e in em.ts.cs_edges for r in (e.src,)} | \
           {i["room"] for i in em.machines} | {0}
    # ...and every promoted register's OWN value universe. `reg_vals` is the set of values the
    # MODEL can ever produce -- the same completeness `compile._fan_globals` already commits to
    # when it fans an increment over it -- so a `!=`/relational read against it is exact within
    # the abstraction: a value outside the universe exists in no walk, so no movement is
    # wrongly credited or blocked. This is what lets LB2's taxi guard `(< global123 2)` reach
    # the exit row as {0, 1} instead of being dropped flat (docs/LB2-ORACLE.md §7z).
    dom = {R: set(em.reg_vals[R]) for R in regset if em.reg_vals.get(R)}
    if prev_room_reg(em) in regset:
        dom[prev_room_reg(em)] = pdom

    def reqs(guard):
        return guard_reqs(guard, regset, dom)
    # THE PREVIOUS-ROOM WRITE. `(= <prev> <current>)` in the Game loop's room switch runs on every
    # transition, so every edge a->b carries `prev := a`. Modelled here rather than as a room write
    # because it is a property of the EDGE, and that is the whole point of it: a room whose exit
    # asks where you came from is a router, not a hub. KQ6's rm155 is the flight to the Realm of
    # the Dead -- `(if (== global12 340) (newRoom 600) else (newRoom 200))` -- and with prev
    # unwritten both branches read as free, which welded the realm to the rest of the world in
    # both directions. rm680's only way out asks the same question (`global12 != 670`, i.e. you
    # came back from rm690 having held up the mirror), so "solve the level or stay" is spelled in
    # this one register too.
    prev = prev_room_reg(em) if prev_room_reg(em) in regset else None
    def sets_of(src, base=None):
        s = dict(base) if base else {}
        if prev is not None:
            s[prev] = src
        return s
    meta = defaultdict(list)
    for e in em.ts.edges:
        meta[(e.src, e.dst)].append(
            (reqs(e.guard), sets_of(e.src), (frozenset(_own_positive(e.guard)),)))
    md = em.machine_delivered
    # A cs_edge whose (room, dst) a machine delivers is the SAME `newRoom` statement the machine
    # EXIT carries -- the cutscene walk knows the machine's gate, the flat edge knows the room's
    # path condition to the statement. Keeping both as separate rows makes the flat one a free
    # bypass of the gate (rm57 -> rm58 must hand the ticket to the agent), which is why it is
    # suppressed. But suppressing DROPPED its path condition, and a machine EXIT is not
    # automatically the stronger of the two: KQ6's realm of the dead is entered by a cutscene
    # armed under `flag14 and flag4 and not flag15`, the machine kept none of that, and the
    # one-visit seal on the whole region vanished at this line.
    #
    # So the two are COMPOSED instead: same statement, both conditions hold. Matched by the object
    # that emitted them (`via` == the machine's instance), because a room can deliver one (a,b) from
    # several instances and only the matching one is the same statement -- 105 of KQ6's 108
    # suppressed edges match, and the three that do not are left dropped rather than guessed.
    # Composed with the NECESSARY reading of both (structural_reqs / _own_required), not the flat
    # one: this guard is about to be ANDed into another, and a flat read turns "either of two
    # armings" into "both". That distinction is the whole of KQ4's whale -- see structural_reqs.
    suppressed = defaultdict(list)
    for e in em.ts.cs_edges:
        if (e.src, e.dst) in md:
            suppressed[(e.src, e.dst, e.via)].append(
                (structural_reqs(e.guard, regset, dom), frozenset(_own_required(e.guard))))
            continue
        meta[(e.src, e.dst)].append(
            (reqs(e.guard), sets_of(e.src), (frozenset(_own_positive(e.guard)),)))

    def _merged(key):
        """The conditions EVERY suppressed statement of this (room, dst, instance) demanded.

        Several statements are ALTERNATIVE ways to make the same move, so a register survives only
        if all of them constrain it, and then its allowed values are the union -- the same merge
        `chain` does over a machine's armers below."""
        rows = suppressed.get(key)
        if not rows:
            return {}, frozenset()
        rq, own = None, None
        for (r, o) in rows:
            rq = dict(r) if rq is None else {R: rq[R] | r[R] for R in set(rq) & set(r)}
            own = o if own is None else (own & o)
        return rq, own
    # Per-machine "what held on every path to this state", keyed so a machine armed by ANOTHER
    # can inherit the armer's facts at the arming state. Cutscene chains hand off mid-sequence:
    # KQ6's `freeCeleste` walks you out of the catacombs and is armed at state 14 of
    # `minotaurCharging`, whose state 8 is where the red scarf decided you survived at all.
    _musts = {}
    for _i in em.machines:
        key = (_i.get("script"), _i.get("inst"), _i.get("room"))
        _musts[key] = state_musts(_i, regs)
    for info in em.machines:
        eo = entry_alts(info)
        er = entry_reqs(info, regs, dom)
        sm = state_musts(info, regs)
        # What EVERY arming of this machine had already established.
        chain = None
        for armer in info.get("entry_armers", ()) or ():
            got = _musts.get((info.get("script"), armer[0], info.get("room")), {}).get(armer[1], {}) \
                if armer else {}
            chain = dict(got) if chain is None else \
                {R: chain[R] | got[R] for R in set(chain) & set(got)}
        chain = chain or {}
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    exit_own = frozenset(_own_positive(g))
                    alts = eo.get(K) or (frozenset(),)
                    sets = sets_of(info["room"],
                                   {gi: v for (gi, v) in w if gi in regset})
                    # The exit inherits its ENTRY's register requirements as well as its item
                    # ones. Both must hold, so a register constrained in both places INTERSECTS.
                    rq = reqs(g)
                    # Ask for THIS exit's entries, not the state's: a machine serving two exits
                    # via `register` reaches one state from both armings, and only the exit guard
                    # says which arming it belongs to.
                    by_guard = er.get("_by_guard")
                    inherited = by_guard(K, g) if by_guard else er.get(K, {})
                    # ...whatever every path THROUGH the machine to this state established, and
                    # the path condition of the flat edge this EXIT suppressed (see `suppressed`).
                    supp_rq, supp_own = _merged((info["room"], tr[1], info.get("inst")))
                    for R, vals in (list(sm.at(K, g).items()) + list(chain.items())
                                    + list(inherited.items()) + list(supp_rq.items())):
                        rq[R] = (rq[R] & vals) if R in rq else set(vals)
                    meta[(info["room"], tr[1])].append(
                        (rq, sets, tuple(exit_own | supp_own | a for a in alts)))
    return meta


class IrSccReach(SccReach):
    """SccReach fed from the JSON-IR model instead of model.Game (same algorithm)."""
    def __init__(self, em):
        self.em = em
        self._gfx_game = None          # lazy resource reader for control-zone hazard gates
        self.g = _ItemNames(vocab.item_names(em.ir))
        (self.edges, self.edge_kind, self.sources, self.drops, self.required,
         self.guard_required, self.source_guards, self.required_guards) = build_maps(em)
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
        self._reob, self._rw, self._after, self._avoid, self._xreach = {}, {}, {}, {}, {}
        # `_reg_cost`'s memo and its (register, value) -> [item-set] index, both pure functions
        # of `_inroom_own`; `_psucc`'s memo over the movement model -- see those methods.
        self._regcost_cache, self._own_by_regval = {}, None
        self._psucc_cache = {}
        self._build_product()

    # ---- gate-aware movement ------------------------------------------------
    def _build_product(self):
        """Build one PROJECTION per discovered gating register -- the gate-aware movement model.

        Not one joint product. Promoting all 19 of LSL2's gating registers jointly explodes past
        4,000,000 reachable states (the flags are near-independent, so they multiply); the same 19
        as separate projections cost 3,679 states total. Precision is monotone and soundness is
        preserved: a genuinely walkable path is walkable in EVERY projection, so intersecting the
        answers can only remove spurious movement, never invent it. Adding a register can only
        sharpen the result, which is why we promote every register that qualifies rather than
        judging which ones matter.

        In-room register changes (handler writes, non-exit machine writes) are added UNGUARDED, so
        each projection stays permissive and can only remove movement the guards actually forbid."""
        em = self.em
        self.regs = gating_registers(em)
        self._emeta = edge_meta(em, self.regs)
        self._inroom = {R: defaultdict(set) for R in self.regs}
        # OWN requirements on each in-room write. The writes themselves stay PERMISSIVE for
        # registers (see below), but a write you can only perform by USING an item is not
        # available when that item is banned: KQ6 sets `scarfOnMino` from `doVerb 72`, i.e. only
        # if you hold the red scarf, and that single write is what eventually opens every exit
        # from the catacombs. Ignoring it made the scarf look re-obtainable from inside the very
        # trap that needs it.
        self._inroom_own = {}
        regset = set(self.regs)
        dbg = frozenset(em.cfg.debug_globals)

        def cheapest(key, cost):
            """Record what this write costs, keeping the CHEAPEST route when a room has several.

            Same composition `_reg_cost`/`value_cost` already apply across rooms -- you may make
            the register take the value whichever way suits you, so the requirement is the
            intersection. Per room it used to be first-writer-wins, which is arbitrary in a room
            where one script gates the write and another does not."""
            cost = frozenset(cost)
            self._inroom_own[key] = (self._inroom_own[key] & cost
                                     if key in self._inroom_own else cost)
        for room, script, gi, v, g in em.handler_writes:
            # A debug-gated write is not real availability -- the same reason `build_maps` skips
            # debug-gated ACQUISITIONS (rm82's `if gDebugging` hands over the whole bomb). Applied
            # here it also restores single-writer structure: KQ4's `Said 'enter/night'` cheat sets
            # global109 := 3 from Main, which is the only thing stopping Lolotte's task counter
            # from having exactly one writer -- see register monotonicity below.
            # LSL2 has 62 debug-gated writes and NONE touches a gating register, so this cannot
            # move it; KQ4 has 12 across 8 registers, among them global100 (night) and global109.
            if gi in regset and not _debug_gated_guard(g, dbg):
                self._inroom[gi][room].add(v)
                cheapest((gi, room, v), _own_positive(g))
        # MACHINE writes, with the machine's own entry guard on the SAME register kept as an
        # ordering. KQ4 dispatches Lolotte's conversations with `(switch global109 (1 lotTalk3)
        # (2 lotTalk4) (3 lotTalk5))`, and each writes the next value -- so lotTalk4 is a
        # transition 2 -> 3, not "3 becomes available". Collapsing it to a free value is what let
        # the model walk back from task 3 to task 1 and made every flip look reversible.
        #
        # But this ordering is only sound when EVERY entry establishes the from-value. If any entry
        # leaves R unconstrained, the machine can be entered with R at any value, so a write reached
        # from that entry is a transition FROM anything -- pinning it to the OTHER entries' values
        # deletes real movement. KQ4's uniActions writes global123:=1 from its arrow-taming entry
        # (which constrains nothing on 123) yet also has a bit-placement entry needing 123==1;
        # unioning to {1} lost the 0->1 step, so global123 never reached 2, the unicorn-ride room
        # (entered at 123==2) vanished from the projection, and reobtainability read that absence as
        # a seal -- fabricating a 32-item "carry your whole inventory" guard. When the entries
        # DISAGREE (some constrain R, some do not), we cannot pin the from-value, so we honour the
        # permissive default above and leave the write unguarded. This is a no-op for the Lolotte
        # counter (lotTalk3/4/5 each have a single 109-constraining entry, so they still order).
        # ROOM-ENTRY writes. `init` runs on arrival, so a register it sets really does change in
        # that room -- but init writes were collected separately (for the atomic-arrival ordering)
        # and never reached the projections, so a flag raised ONLY on arrival looked never-written
        # and did not even qualify as a gating register. KQ6 seals the realm of the dead exactly
        # that way: rm600's init sets flag 15, nothing clears it, and the entry needs it clear.
        for room, vs in getattr(em, "init_writes", {}).items():
            for gi, v in vs.items():
                if gi in regset:
                    self._inroom[gi][room].add(v)
                    cheapest((gi, room, v), ())
        # ⭐ ...AND THE CONDITIONAL ONES, WHICH ARE *POSSIBLE* IN-ROOM WRITES.
        #
        # `init_writes` holds only the UNCONDITIONAL entry writes -- `opmodel._init_leaf` files a
        # write there solely when its path condition is None -- and the loop above was the only
        # thing seeding `_inroom` from room `init`. So a register a room writes under ANY
        # condition was, for projection purposes, a register that room never wrote. That is the
        # unsound direction: `_inroom` means "settable here, from a value we could not recover",
        # which is exactly what we know about such a write. Dropping it instead asserts the game
        # never makes it.
        #
        # It cost LB2 a third of its act structure. `rm630`'s `(= global123 4)` is the only
        # reachable producer of act 4 (`rm26` has no `(3,4)` step -- act 3's destination is an
        # `If`-valued `newRoom:` that `_fan_exit` cannot resolve, so `compile._contradicts` kills
        # that branch and the write with it, docs/LB2-ORACLE.md §7b). The moment anything gives
        # rm630's write a path condition, acts 4/5/6 become unreachable, rooms 521/525/750 leave
        # the projection, and SIX findings vanish -- five of them play-confirmed. Two independent
        # consumers absorb it in silence: `_need_rooms` drops need-room 750 while
        # `required[bifocals]` still literally reads `[750]`, and `reobtainable_rooms` -- an
        # INTERSECTION over every projection -- returns the empty set for anything sourced at
        # rm525, which downstream is indistinguishable from "the item is safe".
        #
        # NOT a latent LB2 quirk waiting on a future change: `rm350.sc:81`'s `(= global123 2)`
        # already sits in a `switch global12` else-arm with numeric labels, is already
        # conditional, and is already missing from `_rstep` today. This is a present bug.
        #
        # A SEPARATE CHANNEL on purpose. `init_writes` is documented UNCONDITIONAL BY
        # CONSTRUCTION and eight other places lean on that for COMMIT semantics (`_psucc`'s
        # `commit=`, the placement walk, `guards`); widening it would quietly assert that
        # entering the room FORCES the value, which is the rm79 seal bug in reverse.
        #
        # Set-valued and cost-carrying, both load-bearing. A room may write the same register to
        # several values down different arms, so one value per (room, gi) -- what `init_writes`
        # can hold -- would drop the rest (measured: 13 such collisions on LSL2, 7 KQ4, 4 KQ6,
        # 5 LB2). And the write's guard may demand items, which `cheapest` is exactly there to
        # record; seeding it free would make a gated entry write look like a free one.
        #
        # Measured inert on today's corpus -- LSL2, KQ4, KQ6 and LB2 all byte-identical on the
        # full snapshot surface -- so it is groundwork that pays off under
        # `vocab.lower_property_case_labels`, not a verdict change.
        for room, seq in getattr(em, "init_seq", {}).items():
            for (gi, v, g) in seq:
                if gi in regset and g is not None:
                    self._inroom[gi][room].add(v)
                    cheapest((gi, room, v), _own_positive(g))
        self._rstep = {R: defaultdict(set) for R in self.regs}
        # ...and here, the one consumer an always-live scope is lifted FOR: what its action makes
        # true, and what that costs. `cheapest` below is where "mixing the paint costs the Styx
        # water" enters the model.
        for info in all_machines(em):
            entries = list(info.get("entries", ())) + list(info.get("init_entries", ()))
            emust = entry_musts(info)
            gates = {}
            for R in self.regs:
                rvs = [required_values(eg, R) for _, eg in entries]
                if rvs and all(rv for rv in rvs):        # every entry pins R -> ordering is sound
                    gates[R] = set().union(*rvs)
            for K, paths in info["states"].items():
                for (g, w, gg, c, tr) in paths:
                    for (gi, v) in w:
                        if gi not in regset:
                            continue
                        # THE WRITE'S OWN PATH CONDITION FIRST. A write reached only under
                        # `R == k` is executed only at `R == k`, so ordering it from there is
                        # sound with no argument about entries at all -- and it is the ONLY
                        # thing that can order a counter. `compile._fan_globals` turns `(++ R)`
                        # into exactly this shape (guard `R == k`, write `R := k+1`), and until
                        # this line read it, the fan's whole point was thrown away one step
                        # later: LB2's act break delivered six writes with six pinning guards
                        # and they all landed in `_inroom`, making the act-break card a room
                        # where any act may be selected. Entry-derived `gates` stay as the
                        # fallback for the case they were written for (KQ4's Lolotte counter,
                        # where the ordering lives in the machine's arming, not its body).
                        #
                        # STRUCTURAL, not flat. `required_values`/`guard_reqs` read the atoms
                        # flat and UNION the equalities -- right for "what values may this edge
                        # be crossed at", wrong here: a fanned branch carries both the counter's
                        # own `R == k` and the chosen destination's `R == j`, and flat those
                        # union to {j, k}, which yields the full 6x6 cross product of act steps
                        # instead of the six real ones. `structural_reqs` COMPOSES (AND
                        # intersects, OR keeps only what every branch constrains), so a
                        # contradictory branch yields the empty set and orders nothing.
                        own = structural_reqs(g, (gi,)).get(gi)
                        need = own or gates.get(gi)
                        if need:
                            for frm in need:
                                self._rstep[gi][info["room"]].add((frm, v))
                        else:
                            self._inroom[gi][info["room"]].add(v)
                        # ...and the write's PRECONDITIONS either way. Learning that a write is an
                        # ordered transition says nothing about what it costs, but `_rstep` recorded
                        # only the ordering, so an ordered write became free: KQ6's tapestry sets
                        # `hiddenDoorOpen` -- the secret door to the minotaur's lair -- and every
                        # arming of that cutscene pins the same flag, so the write went to `_rstep`
                        # and the hole-in-the-wall it depends on was dropped on the floor.
                        #
                        # A write inside a cutscene costs whatever ARMING the cutscene costs, too
                        # -- see `entry_musts`. The path condition inside a `changeState` body is
                        # usually empty, the decision having been made where the machine was
                        # started, so reading only that made every cutscene effect free.
                        cheapest((gi, info["room"], v),
                                 _own_positive(g) | emust.get(K, frozenset()))
        # ⭐ A COUNTER MAY NOT BE WOUND BACKWARDS.
        #
        # A write whose from-value we could not recover lands in `_inroom`, which means "settable
        # here from ANY value" -- and for a counter that is a claim the game never makes. LB2's act
        # is the case: `rm630` does a bare `(= global123 4)` inside a `(switch global12 …)` on the
        # arrival direction, with no act test anywhere near it, so no path condition supplies the
        # from-value. Read permissively, the model may stand at act 5, step into `rm630`, wind the
        # act back to 4, walk to `rm525` and collect the smelling salts -- so the item stops being
        # stranded. `rm355`'s `(= global123 0)` resets it outright. Measured: this, and not the
        # source condition or the room graph, is the whole reason that item is missed.
        #
        # The from-value IS recoverable -- from the STEP RELATION rather than the source. Every
        # ordered step of such a register is `k -> k+1`, so the rule is read off `_rstep` itself
        # and asserts nothing about any particular game:
        #
        #     a register that COUNTS -- two or more ordered steps, every one of them consecutive,
        #     and more than two values in play -- may not be DECREASED by an unordered write.
        #
        # ALL THREE QUALIFIERS ARE LOAD-BEARING, and the first census without them was wrong. A
        # boolean flag has exactly one step `(0, 1)`, and its `_inroom` writes of 0 are ordinary
        # CLEARS; forbidding those would forbid every flag reset whose guard we failed to recover
        # -- 20+ registers across KQ6 and LB2, a behaviour change with no evidence behind it. With
        # the qualifiers, the corpus census is three registers: LB2's act, LB2's `111`, KQ6's
        # `162`. LSL2 and KQ4 have none, so they cannot move [standing ruling, 2026-08-01].
        #
        # `<= v`, not `< v`: a write of the value it already holds is a harmless self-write, and
        # refusing it would be a second unevidenced claim.
        for gi in list(self._rstep):
            steps = {st for room in self._rstep[gi].values() for st in room}
            vals = ({v for st in steps for v in st}
                    | {v for vs in self._inroom.get(gi, {}).values() for v in vs})
            if len(steps) < 2 or len(vals) <= 2 or not all(t == f + 1 for (f, t) in steps):
                continue
            for room, wr in list(self._inroom.get(gi, {}).items()):
                for v in sorted(wr):
                    self._rstep[gi][room] |= {(u, v) for u in vals if u <= v}
                    wr.discard(v)
        self._joints = []
        self._apply_hazard_gates()
        self._apply_death_traps()
        self._own_fixpoint()
        # Projections = one per register, PLUS the few joints the death traps ask for. See
        # _trap_joints: `self.regs` stays scalar because everything else iterates it expecting a
        # register, and only the four reachability walks look at `self.proj`.
        self.proj = list(self.regs) + list(self._joints)
        self._pstates = {R: self._walk(R, frozenset()) for R in self.proj}

    def _trap_joints(self, traps, dom):
        """The register TUPLES a death trap needs evaluated together.

        Negating a conjunction gives a disjunction, so a trap whose death condition is
        `prev == 435 AND minotaur alive` becomes two ALTERNATIVE ways out -- and per-register
        projections let each one through in the projection that cannot see the other. KQ6's dark
        room is exactly that: in the prevRoom projection the flag alternative is unconstrained, in
        the flag projection the prevRoom one is, so the trap never bites and the tinderbox you must
        light to survive the fall never looks required.

        Self-selecting, which is what keeps this from being "promote everything": the pair comes
        from the trap that needs it, and a game with no such trap gets no joints at all (LSL2, KQ4
        and every other title in the corpus). Bounded twice over -- by how many trap rooms name two
        or more registers, and by the size of the product -- because a joint projection is the
        expensive kind."""
        want, seen = [], set()
        for room in sorted(traps):
            named = tuple(sorted({R for (req, _alts) in traps[room] for R in req}))
            if len(named) < 2 or named in seen:
                continue
            size = 1
            for R in named:
                size *= max(1, len(dom.get(R) or (0,)))
            if size > 4000 or len(want) >= 8:
                continue                          # a joint is the expensive projection; bound it
            seen.add(named)
            want.append(named)
        return want

    def _register_dom(self):
        """Every value each promoted register is ever given -- the COMPLETE domain `guard_reqs`
        needs before it may read a `!=` or a relational op exactly."""
        dom = defaultdict(set)
        for R in self.regs:
            dom[R] |= {v for vs in (self._inroom.get(R) or {}).values() for v in vs}
            dom[R] |= {t for pairs in self._rstep[R].values() for (_f, t) in pairs}
            dom[R].add(0)                          # registers start at 0
        for metas in self._emeta.values():
            for (_req, sets, _alts) in metas:
                for R, v in sets.items():
                    if R in dom:
                        dom[R].add(v)
        return dom

    def _ctl_zone_cells(self, script, mask):
        """The pixels of this room's PIC whose control colour is in `mask` -- a hazard zone.

        `onControl` returns `1 << colour` bits (docs/SCI1.1-SEMANTICS.md §3), so mask $0002 is
        control colour 1. The PIC number is the room object's own `picture` property, and the
        plane is `sci_gfx.render_control` -- the KQ4-era renderer, which reads SCI1 pics too
        (the extended-op table dispatch, 2026-08-19b). Anything unreadable -- no room object,
        no picture literal, a pic the renderer refuses -- returns nothing, and the caller
        makes no wall claim: refusal toward NOT barring, like every other conjunct here."""
        import polygons as PG_
        rm = PG_._room_object(script, self.em.ir)
        pic = rm.props.get("picture") if rm is not None else None
        if not isinstance(pic, int):
            return None
        rd = getattr(self.em.cfg, "resource_dir", None)
        if not rd:
            return None
        try:
            import sci_gfx
            from sci_resource import Sci0Game
            game = self._gfx_game
        except Exception:                                  # noqa: BLE001
            return None
        if game is None:
            try:
                game = self._gfx_game = Sci0Game(rd)
            except Exception as e:                         # noqa: BLE001
                _degraded_model("hazard zone: resources unreadable (%s)" % e)
                return None
        try:
            con = sci_gfx.render_control(game, pic)
        except Exception as e:                             # noqa: BLE001
            _degraded_model("hazard zone: pic %s control plane (%s)" % (pic, e))
            return None
        W = 320
        return {(i % W, i // W) for i, c in enumerate(con) if c < 16 and (1 << c) & mask}

    def _apply_hazard_gates(self):
        """A POSITIONAL DEATH IS A WALL. Gate the exits a stationary killer's radius seals.

        The gap this closes is #1 in the modeling-gap census and the oracle names the instance
        (docs/KQ5-ORACLE.md §15). KQ5's rm2 is the road out of town, and a snake sits on it:

            (if (not (proc0_12 47)) (snake ... init:))     ; it is there while flag 47 is clear
            (method (doit) ... ((< temp0 30)               ; ...and inside 30px...
                (global2 setScript: strike)))              ; ...strike st3 = (proc0_26 243), death
            (34 ... (proc0_9 47) ... )                     ; the tambourine sets 47, and NO `put:`

        The player cannot leave town eastward without charming it, so everyone past that point
        is carrying the tambourine -- which is exactly what the user ruled. But the snake blocks
        by KILLING YOU AT A DISTANCE rather than by guarding an edge, so all four of rm2's exits
        read FREE, and the tool claimed you might cross the roc without the tambourine and be
        stranded. That was a FALSE POSITIVE with a geometric cause.

        FOUR THINGS MUST HOLD, and each is asked of a part of the model that already exists:
          1. the trigger is positional             -- `positional_hazards`
          2. what it arms cannot be survived       -- `_room_unavoidable`, the SAME classifier
             `fatal_uses` and `ownedby_death_folds` answer to, with the same pre-emption rule
          3. the killer stands still               -- `_hazard_is_stationary`
          4. its radius seals the exit             -- `polygons.hazard_barred_exits`, which
             proves it over the room's own obstacle polygons

        The demand placed on the sealed edge is the NEGATION OF THE HAZARD'S CAST CONDITION --
        "it is not here" -- and nothing more. Not the death's own guard, not the branch the
        `doit` took: the only fact that makes the exit passable is that the killer is gone, and
        `cast_conditions` is where this codebase already keeps "under what condition does this
        object exist". For the snake that is `not (flag 47)` negated to `flag 47`, whose price
        `_reg_cost` independently derives as the Tambourine.

        REFUSALS, all toward leaving the edge free, because this REMOVES movement:
          * an object with no cast condition (unconditionally present) states no way to be rid
            of it, so gating on its absence would wall the exit forever;
          * a cast condition containing an unreadable atom lowers to no requirement at all
            (`guard_reqs`), and an empty requirement is applied as nothing rather than as
            "impossible" -- the row is dropped instead;
          * everything `positional_hazards` and `hazard_barred_exits` refuse on their own.

        MEASURED across the corpus: 27 candidate arms, ONE surviving gate. KQ6 supplies four
        candidates and loses all four to (3) -- its zombies walk. LSL2 and KQ4 have no such
        arms at all and no obstacle polygons to prove one with. That the survivor is the snake
        is the geometry's answer, not a clause about KQ5: the disc is 30px at (298,64), the
        walkable slice of rm2's east handoff is the y in (48,81) gap poly1 and poly4 leave, and
        every cell of it is inside the disc."""
        import extract as X
        import polygons as PG
        self.hazard_gates = []
        ir = self.em.ir
        by_room = defaultdict(list)
        for i in self.em.machines:
            by_room[i["room"]].append(i)
        dom = self._register_dom()
        regset = set(self.regs)
        for room in sorted(by_room):
            script = ir.scripts.get(room)
            if script is None:
                continue
            found = positional_hazards(ir, script)
            if not found:
                continue
            _d, _h, unavoidable, _p = _room_unavoidable(
                by_room[room], self.sources, self.reach_rooms)
            try:
                cast = X.cast_conditions(script)
            except Exception as e:                          # noqa: BLE001
                _degraded_model("hazard gate: cast conditions rm%d (%s)" % (room, e))
                continue
            for (name, zone, armed) in found:
                lethal = sorted(m for m in armed if m in unavoidable)
                if not lethal:
                    continue
                if zone[0] == "disc":
                    # a disc is drawn around the OBJECT, so the object must stand still and
                    # its absence condition comes from the cast (the snake's shape, unchanged)
                    if not _hazard_is_stationary(script, name):
                        continue
                    obj = next((o for o in script.objects if o.name == name), None)
                    x, y = (obj.props.get("x"), obj.props.get("y")) if obj else (None, None)
                    if not isinstance(x, int) or not isinstance(y, int):
                        continue
                    gs = cast.get(name)
                    discs, cells = [(x, y, zone[1])], ()
                    where = {"at": (x, y), "radius": zone[1]}
                else:
                    # a control zone is GROUND -- it cannot move, and its trigger's host is a
                    # machine, live exactly when something arms it (KQ5's harpy patrol:
                    # harpyInitScript armed in init under flag 54). The liveness condition is
                    # the cast condition when the host has one, else the arming sites' own
                    # guards (`extract.arming_conditions`) -- and every site must carry one,
                    # the same "always live means no absence to demand" contract as the cast.
                    gs = cast.get(name) or X.arming_conditions(script, name)
                    zc = self._ctl_zone_cells(script, zone[1])
                    if not zc:
                        continue        # unreadable pic or empty zone: no wall claim
                    discs, cells = [], zc
                    where = {"mask": zone[1], "zone_px": len(zc)}
                if not gs or any(g is None for g in gs):
                    continue                    # always in the cast: no absence to demand
                absent = _negate(gs[0] if len(gs) == 1 else GOr(list(gs)))
                req = guard_reqs(absent, regset, dom)
                if not req:
                    continue                    # nothing readable to demand -> leave it free
                for edge, dst in sorted(PG.hazard_barred_exits(
                        ir, room, discs, cells=cells).items()):
                    self.hazard_gates.append({
                        "room": room, "edge": edge, "dst": dst, "hazard": name,
                        **where, "machine": lethal,
                        "req": {R: sorted(v) for R, v in sorted(req.items())}})
                    key = (room, dst)
                    out = []
                    for (breq, sets, alts) in list(self._emeta.get(key) or [self._FREE]):
                        r2 = dict(breq)
                        for R, vals in req.items():
                            r2[R] = (r2[R] & set(vals)) if R in r2 else set(vals)
                            if not r2[R]:
                                break
                        else:
                            out.append((r2, sets, alts))
                    if out:
                        self._emeta[key] = out
                # A HAZARD PRICES IN-ROOM PICKUPS LIKE IT PRICES EXITS. An item whose pickup
                # spot is walkable with the hazard gone and sealed with it live is exactly as
                # gone as a room past a barred edge -- KQ5's Shell: the conch sits at
                # (120, 100) on the harpy beach, the kill zone stands between it and the boat
                # landing, so a player who sailed off without it cannot safely return for it,
                # which is the play-found death of 2026-08-19b. The absence condition is
                # CONJOINED onto every acquisition guard for (item, room) -- the source-side
                # store `reobtainable_rooms` and `register_strandings` already read -- so the
                # value-trapped walk sees the pickup die at the flip with no new machinery.
                # The pickup spot is the literal position of the object the get-performing
                # machine itself stages (refused when ambiguous), and the same
                # some-layout-free / no-layout-hurt rule as the edges applies.
                for item, spot in sorted(PG.item_pickup_spots(script).items()):
                    if room not in self.sources.get(item, ()):
                        continue
                    verdict = PG.hazard_bars_point(ir, room, spot, discs, cells=cells)
                    if not verdict:
                        continue
                    slots = self.source_guards.setdefault(item, {})
                    gs2 = slots.get(room) or [None]
                    slots[room] = [absent if g is None else GAnd([g, absent]) for g in gs2]
                    self.hazard_gates.append({
                        "room": room, "pickup": item, "at": spot, "hazard": name,
                        **where, "machine": lethal,
                        "req": {R: sorted(v) for R, v in sorted(req.items())}})

    def _apply_death_traps(self):
        """Conjoin `death_traps`' disjunction onto every way OUT of a room whose arrival kills you.

        The rows are alternatives and each existing meta is an alternative, so the two cross: a
        crossing is possible when some (existing way) and some (way to survive) both hold."""
        dom = self._register_dom()                 # values each register is ever given
        traps = death_traps(self.em, self.regs, dom)
        self._joints = self._trap_joints(traps, dom)
        # ⭐ WHICH REGISTER VALUES MEAN "YOU ARE DEAD" (2026-08-09). A room's rows are ALTERNATIVE
        # ways to survive, so death is "every alternative failed". Only when there is exactly ONE
        # alternative naming exactly ONE register does a single value of a single register mean
        # death by itself -- and then the excluded values are precisely the death signal.
        #
        # The rule came from KQ6's flag 44: `proc0_1` is the imperative death procedure (`Main.sc`
        # -- set global160, set flag 44, `newRoom: 640`), `rm640` plays the death cartoon iff
        # flag 44 is set, and `free_running_traps` was classifying that signal as an adversarial
        # plot clock (see its guard). Deliberately NOT claiming LB2's `123 == 5`: act 5's rooms
        # kill you only in conjunction with `12 == 420`, two alternatives, so no single value is
        # death -- being in act 5 is a place you can stand, being dead is not.
        #
        # ⚠️ RE-MEASURED 2026-08-14 (review §2.4, "single-instance calibration"), and the recorded
        # instance was no longer the instance: this now yields `{173: {0}}` on KQ6 and nothing on
        # the other three. Register 173 is FLAG 1 (`flag_synth_base` 172), written by
        # `minoTrigger` and demanded by the labyrinth's rm411 as its SOLE survival row -- so in
        # rm411 flag 1 == 0 means dead, which is a truer instance of this rule than flag 44 ever
        # was (a real hazard rather than the bookkeeping the death proc does on its way out).
        # Flag 44's register is 216 and it no longer produces a single-row single-register trap.
        # The claim above was written when it did; `test_deletion_soundness` now pins the
        # measured set, because a rule whose applicability moves silently is the same defect as
        # a census that no longer reproduces.
        self._death_values = defaultdict(set)
        for room, rows in traps.items():
            if len(rows) != 1:
                continue
            (treq, _talts) = rows[0]
            if len(treq) != 1:
                continue
            (R, vals), = treq.items()
            self._death_values[R] |= (set(dom.get(R, ())) - set(vals))
        for room, rows in traps.items():
            for b in self.edges.get(room, ()):
                base = list(self._emeta.get((room, b)) or [self._FREE])
                out = []
                for (req, sets, alts) in base:
                    for (treq, talts) in rows:
                        r2 = dict(req)
                        for R, vals in treq.items():
                            r2[R] = (r2[R] & set(vals)) if R in r2 else set(vals)
                            if not r2[R]:
                                break
                        else:
                            out.append((r2, sets,
                                        tuple(a | t for a in alts for t in talts)))
                if out:
                    self._emeta[(room, b)] = out

    def _reg_cost(self, R, vals):
        """Items you must hold to make register R take any of `vals` -- the cheapest route.

        MEMOISED, and indexed rather than scanned (2026-08-14). This is a pure function of the
        built model, and it used to walk all of `_inroom_own` on every call -- affordable only
        while `_reg_unreachable` (its sole caller) was reached rarely, because that function
        returns immediately when nothing is banned. Item-banned walks made banned the common
        case, and this became 37% of the detector's runtime at 2.8M calls. Neither the index
        nor the cache can change an answer: both read the same `_inroom_own`, which nothing
        mutates after the build."""
        key = (R, frozenset(vals))
        got = self._regcost_cache.get(key)
        if got is not None:
            return got
        if self._own_by_regval is None:
            idx = defaultdict(list)
            for (Rk, _room, vk), own in self._inroom_own.items():
                idx[(Rk, vk)].append(own)
            self._own_by_regval = idx
        best = None
        for v in sorted(vals):
            if v == 0:
                out = frozenset()                # registers start at 0
                break
            ways = self._own_by_regval.get((R, v))
            if not ways:
                out = frozenset()                # nothing writes it -> initial value -> free
                break
            cost = ways[0]
            for w in ways[1:]:
                cost &= w
            best = cost if best is None else (best & cost)
        else:
            out = best or frozenset()
        self._regcost_cache[key] = out
        return out

    def _reg_unreachable(self, req, banned):
        """Is some register requirement on this edge impossible while `banned` items are held back?

        Projections are per-register, so an edge with two ways through -- KQ6's lair exit opens
        once the minotaur is dead OR once the victory cutscene has run, testing two DIFFERENT
        registers -- looks free in BOTH projections: each sees its own register unconstrained on
        the other alternative and lets it by. Item bans are global, so ask the question here
        instead, where every register on the edge is visible at once.

        Deliberately NOT folded into the edge's item set. `alts` means "items you must be HOLDING
        to cross", while a register's cost is "items you needed EARLIER" -- conflating them made
        LSL2 demand you still carry the Vine long after spending it."""
        if not banned:
            return False
        return any(self._reg_cost(R, vals) & banned for R, vals in req.items())

    def _own_fixpoint(self):
        """Let item requirements flow ALONG register chains.

        A write is often gated not on an item but on another register, and that register only
        became what it is because you used an item. KQ6's catacombs are the case: showing the
        minotaur the red scarf sets `scarfOnMino`, the path that guards opens the state that sets
        "minotaur defeated", and THAT is what every exit tests. Each link we already had; the chain
        we did not, because projections are built one per REGISTER (a joint product over LSL2's 19
        explodes past 4,000,000 states, while the projections cost 3,679) so `scarfOnMino` and
        "minotaur defeated" never meet.

        So propagate instead of joining: if a write is guarded by `S == v`, it inherits whatever
        every way of making S equal v requires. Repeated to a fixpoint, that carries an item
        requirement as far along the chain as the chain goes, and projections stay independent.

        Both compositions are the conservative one. A register value costs the INTERSECTION over
        the writes that produce it -- you may use whichever is cheapest -- and a value that no
        write produces is free, because it is the value the register starts at."""
        # (R, room, val) -> {other register: allowed values} the write depends on. For a machine
        # write that means the path guard AND everything every route to that state established --
        # a cutscene decides early and pays off late, so the constraint that matters is usually in
        # an earlier state (KQ6 branches on the scarf at state 8 and sets the flag at 14).
        regs = set(self.regs)
        guards = {}
        for room, script, gi, v, g in self.em.handler_writes:
            if gi in regs:
                d = {S: vs for S in self.regs if (vs := required_values(g, S))}
                if d:
                    guards[(gi, room, v)] = d
        # ...and the ALWAYS-LIVE scopes, exactly as `_build_product` iterates them. A machine the
        # icon bar dispatches records its own cost through `cheapest` up there but was never a
        # source of register-chain DEPENDENCIES down here, so half of what that scope contributes
        # was landing: KQ6 mixes the magic paint from the inventory under
        # `own(spellBook) AND flag68 AND flag58 AND NOT flag22`, and the cost of "the paint is
        # mixed" came out as the spell book ALONE -- the Styx water and the mud, which are what
        # the teacup buys, were dropped on the floor. The rule this scope shipped under is
        # "effects AND THEIR COSTS"; a cost that cannot propagate along a chain is not the second
        # half of it. Inert on SCO0 titles, whose items live in script 0 and which therefore have
        # no global machines at all.
        for info in all_machines(self.em):
            sm = state_musts(info, self.regs)
            # ...and what ARMING the machine established. `state_musts` walks the machine's own
            # transitions and seeds each entry with nothing, so a decision made in the ENTRY GUARD
            # -- which is where a cutscene's preconditions almost always live -- reached no write.
            # This is the register twin of the `entry_musts` term `_build_product` already puts on
            # the ITEM side of the very same write, and it is composed exactly as `edge_meta`
            # composes it onto an EXIT: intersect, because both must hold.
            er = entry_reqs(info, self.regs)
            by_guard = er.get("_by_guard")
            for K, paths in info["states"].items():
                for (g, w, gg, c, tr) in paths:
                    for (gi, v) in w:
                        if gi not in regs or (gi, info["room"], v) not in self._inroom_own:
                            continue
                        d = dict(sm.at(K, g))
                        inherited = by_guard(K, g) if by_guard else er.get(K, {})
                        for S, vs in list(inherited.items()):
                            if vs:
                                d[S] = (d[S] & vs) if S in d else set(vs)
                        for S in self.regs:
                            vs = required_values(g, S)
                            if vs:
                                d[S] = (d[S] & vs) if S in d else set(vs)
                        if d:
                            guards[(gi, info["room"], v)] = d

        def value_cost(R, val, own):
            """Items needed to make R == val: the cheapest write, or free if none writes it."""
            if val == 0:
                return frozenset()        # registers start at 0; no action needed
            ways = [own.get(k, frozenset()) for k in own if k[0] == R and k[2] == val]
            if not ways:
                return frozenset()        # nothing writes it -> initial value -> free
            out = ways[0]
            for w in ways[1:]:
                out &= w
            return out

        own = dict(self._inroom_own)
        for _round in range(6):           # chains in practice are 2-3 links; bound the walk
            changed = False
            for key, deps in guards.items():
                extra = set(own.get(key, frozenset()))
                for S, vals in deps.items():
                    if S == key[0] or not vals:
                        continue          # a write ordering itself is _rstep's business
                    # reaching ANY allowed value suffices, so take the cheapest
                    costs = [value_cost(S, v, own) for v in sorted(vals)]
                    need = costs[0]
                    for c in costs[1:]:
                        need &= c
                    extra |= need
                if frozenset(extra) != own.get(key, frozenset()):
                    own[key] = frozenset(extra)
                    changed = True
            if not changed:
                break
        self._inroom_own = own

    _FREE = ({}, {}, (frozenset(),))

    def _psucc(self, R, node, banned, commit=frozenset()):
        """Successors of a (room, value-of-R) node in projection R. `banned` is a set of items you
        do not hold, so edges needing them are false -- the ITEM dimension of gate-awareness, and
        what the old `_sealed` heuristic crudely approximated: you cannot use the parachute to
        walk back to the parachute.

        `commit` reverses the direction of soundness for the registers it names, and exists for
        the PLACEMENT question only. Detection over-approximates movement (in-room writes are
        optional successors) so it can never miss a stranding; a placement proof must not CREDIT
        movement the game does not have, or "the player can walk back and comply" is asserted of a
        player who cannot. The one class of write that can be committed exactly is the
        UNCONDITIONAL entry write -- `em.init_writes`, unconditional by construction (a guarded
        init write goes to `init_seq` instead): entering the room forces the value, so a state
        that carries the old value past that door does not exist in play. For a register in
        `commit`, crossing into such a room arrives AT the written value instead of keeping the
        carried one. Every detection caller leaves `commit` empty and is bit-for-bit unchanged.

        MEMOISED (2026-08-14). This is a pure function of the built model, and the walks call it
        with the SAME (state, banned) over and over -- once per walk that passes through the
        state, and there is one walk per (flip, value, item, seed room). Measured on LSL2: 3.7M
        calls covering a few thousand distinct arguments. The cache is invalidated wherever
        `_emeta` is (see `guards.apply_guards`), because that is the only thing under it that
        ever changes."""
        key = (R, node, banned, commit)
        got = self._psucc_cache.get(key)
        if got is not None:
            return got
        out = self._psucc_cache[key] = self._psucc_uncached(R, node, banned, commit)
        return out

    def _psucc_uncached(self, R, node, banned, commit=frozenset()):
        if isinstance(R, tuple):
            return self._psucc_joint(R, node, banned, commit)
        r, st = node
        out = {(r, v) for v in self._inroom[R].get(r, ())
               if not (banned and self._inroom_own.get((R, r, v), frozenset()) & banned)}
        # ...plus writes the game only makes FROM a particular value of R -- see _build_product.
        # Same item cost as any other write: knowing WHEN the game makes it does not make it free.
        out |= {(r, to) for (frm, to) in self._rstep[R].get(r, ()) if frm == st
                and not (banned and self._inroom_own.get((R, r, to), frozenset()) & banned)}
        for b in self.edges.get(r, ()):
            for (req, sets, alts) in self._emeta.get((r, b), (self._FREE,)):
                need = req.get(R)
                if need is not None and st not in need:
                    continue                      # guard forbids this move at this value of R
                if banned and blocked(alts, banned):
                    continue                      # every way through needs a banned item
                if self._reg_unreachable(req, banned):
                    continue                      # a register it needs can never reach that value
                arrive = sets.get(R, st)
                if R in commit:
                    # the destination's own unconditional entry write wins over anything carried
                    # or set in transit -- init runs LAST on the way in.
                    arrive = self.em.init_writes.get(b, {}).get(R, arrive)
                out.add((b, arrive))
        return out

    def _psucc_joint(self, Rs, node, banned, commit=frozenset()):
        """`_psucc` over a TUPLE of registers tracked together -- see `_trap_joints`.

        Same rules, one value per register (`commit` included -- see `_psucc` for its contract).
        Deliberately a separate body rather than a generalised
        one: the scalar path is walked millions of times and every corpus baseline is pinned to it,
        so it stays untouched."""
        r, st = node
        out = set()
        for i, Ri in enumerate(Rs):
            for v in self._inroom[Ri].get(r, ()):
                if banned and self._inroom_own.get((Ri, r, v), frozenset()) & banned:
                    continue
                nv = list(st)
                nv[i] = v
                out.add((r, tuple(nv)))
            for (frm, to) in self._rstep[Ri].get(r, ()):
                if st[i] != frm or (banned and
                                    self._inroom_own.get((Ri, r, to), frozenset()) & banned):
                    continue
                nv = list(st)
                nv[i] = to
                out.add((r, tuple(nv)))
        for b in self.edges.get(r, ()):
            for (req, sets, alts) in self._emeta.get((r, b), (self._FREE,)):
                if any(req.get(Ri) is not None and st[i] not in req[Ri]
                       for i, Ri in enumerate(Rs)):
                    continue
                if banned and blocked(alts, banned):
                    continue
                if self._reg_unreachable(req, banned):
                    continue
                ivs = self.em.init_writes.get(b, {})
                out.add((b, tuple(ivs.get(Ri, sets.get(Ri, st[i])) if Ri in commit
                                  else sets.get(Ri, st[i]) for i, Ri in enumerate(Rs))))
        return out

    def _walk(self, R, banned, starts=None, commit=frozenset(), barrier=frozenset()):
        """Forward reachable (room, value) states in projection R.

        `barrier` rooms are entered and not left: the walk keeps the state but expands no
        successor. Its one caller is `_reach_without`, where a room that hands the banned item
        over unrefusably ends the "without it" story -- see `_unrefusable_grants`."""
        if starts:
            seen = set(starts)
        else:
            # The start room's own unconditional entry write is as committed as any other room's:
            # the game runs its init before the player moves, so 0 is only the initial value of a
            # register the start room does not write.
            iv = self.em.init_writes.get(self.em.cfg.start_room, {})
            if isinstance(R, tuple):
                zero = tuple(iv.get(Ri, 0) if Ri in commit else 0 for Ri in R)
            else:
                zero = iv.get(R, 0) if R in commit else 0
            seen = {(self.em.cfg.start_room, zero)}
        q = list(seen)
        while q:
            u = q.pop()
            if u[0] in barrier:
                continue
            for v in self._psucc(R, u, banned, commit):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        return seen

    def reach_avoiding(self, rooms):
        """Rooms reachable from the start WITHOUT ever ENTERING `rooms` -- gate-aware, intersected
        over every projection. The room-pruning twin of `_reach_without` (which bans an ITEM).

        Gate-awareness is the whole point and the flat graph gives the opposite answer: KQ6's Realm
        of the Dead sits behind `flag14`, and rm580 is the ONLY room that writes it, so refusing
        rm580 makes the entire Realm unreachable -- while the guard-ignoring graph happily routes
        around rm580 and says the Realm is still there."""
        key = frozenset(rooms)
        if key in self._avoid:
            return self._avoid[key]
        out = None
        for R in self.proj:
            zero = tuple(0 for _ in R) if isinstance(R, tuple) else 0
            start = (self.em.cfg.start_room, zero)
            seen, q = {start}, [start]
            while q:
                u = q.pop()
                for v in self._psucc(R, u, frozenset()):
                    if v[0] in key or v in seen:
                        continue
                    seen.add(v)
                    q.append(v)
            got = {r for r, _ in seen}
            out = got if out is None else (out & got)
        self._avoid[key] = out if out is not None else set(self.reach_rooms)
        return self._avoid[key]

    def _crossing_reach(self, a, b):
        """Per `_emeta` row of a->b: {projection: STATES reachable AFTER the crossing, or None}.

        The post-crossing walk for the NEED-RETIREMENT question (`crossing_retires_need`). For
        each way of making the move (each meta row), each candidate projection starts from the
        states the crossing itself produces: every value the walk believes at `a` that passes the
        row's requirement, with the row's writes applied -- the same arrival rule as `_psucc`'s
        edge clause, restricted to this one edge. Deliberately a mirror of that clause rather than
        a call: `_psucc` enumerates all edges on a hot path every corpus baseline is pinned to.

        Candidate projections are the ones the meta itself touches (a register in its req or
        sets; a joint qualifies through any component) -- the question is what the crossing's OWN
        register commit seals, so a projection the edge neither tests nor writes is not evidence
        about this crossing. Positional registers (previous-room, current-room) are dropped the
        same way `defer_to_entry` drops them from stages: they name where the player stands, not
        which crossing this is.

        `None` for a projection means NO EVIDENCE -- the walk believes no value at `a` that
        passes the row -- and the consumer must treat it as "keep" ([[arming-floor]]: falling off
        the end of a walk is ignorance, not evidence). Detection semantics throughout (empty
        `commit`, no ban): the walk over-approximates movement, so a room absent from it is
        genuinely unreachable within the abstraction, which is the only direction a retirement
        may rest on."""
        got = self._xreach.get((a, b))
        if got is not None:
            return got
        metas = self._emeta.get((a, b))
        if not metas:
            self._xreach[(a, b)] = []
            return []
        import extract as X
        positional = {prev_room_reg(self.em), getattr(X, "_CURROOM", None)}
        out = []
        for (req, sets, _alts) in metas:
            touched = (set(req) | set(sets)) - positional
            cands = [R for R in self.proj
                     if (any(Ri in touched for Ri in R) if isinstance(R, tuple)
                         else R in touched)]
            per = {}
            for R in cands:
                vals = {v for (r, v) in self._pstates[R] if r == a}
                starts = set()
                if isinstance(R, tuple):
                    for v in vals:
                        if any(req.get(Ri) is not None and v[i] not in req[Ri]
                               for i, Ri in enumerate(R)):
                            continue
                        starts.add((b, tuple(sets.get(Ri, v[i]) for i, Ri in enumerate(R))))
                else:
                    for v in vals:
                        need = req.get(R)
                        if need is not None and v not in need:
                            continue
                        starts.add((b, sets.get(R, v)))
                per[R] = self._walk(R, frozenset(), starts=starts) if starts else None
            out.append(per)
        self._xreach[(a, b)] = out
        return out

    def _site_musts(self, guard, regs):
        """{reg: allowed values} a need SITE's guard requires of `regs` -- the LIVENESS reading.

        Deliberately NOT `guard_reqs`: its positive-equality pass reads `_cmp_atoms` FLAT, so a
        `(== reg v)` inside an OR would constrain here too -- and for liveness that is the unsafe
        direction (an OR-branch constraint would read a site dead that another branch keeps
        alive, and a dead site is what lets `crossing_retires_need` delete a demand). Only
        conjuncts that MUST hold may narrow a site, so this is built on `_must_equal` and
        `_must_hold` alone. A `!=` constrains nothing without a domain except the boolean
        globals ({0,1} -- the same special case `guard_reqs` carries); relationals constrain
        nothing (no domain is threaded here; permissive = live = the strict direction).
        Contradictory musts yield an empty allowed set -- a site that can never fire, honestly
        dead."""
        out = {}
        for (r, v) in _must_equal(guard):
            if r in regs:
                out[r] = (out[r] & {v}) if r in out else {v}
        for t in _must_hold(guard):
            if len(t) != 2:
                continue                        # relational: no domain -> constrains nothing
            r, v = t
            if r in regs and v == 0 and r in vocab.BOOL_GLOBALS:
                allowed = {1}                   # "must be != 0" on a boolean IS "== 1"
                out[r] = (out[r] & allowed) if r in out else allowed
        return out

    def _need_live(self, item, room, R, states):
        """Is the need for `item` at `room` live at any of these projection-R states?

        Room-level first: a room the walk never stands in is dead outright. Then per SITE
        (`required_guards`, one guard per evidence site): a site with no guard (`None`) or
        no musts over R's registers is live wherever the room is reached -- the permissive
        poison -- and a conditioned site is live only at a state consistent with its musts.
        LB2's rm335 is the case the distinction exists for: the pass's one site there is the
        sGiveInvite arming, `own(6) AND global123==2 AND trigger-25-unfired`, so the room being
        walkable at acts 3-5 keeps no need alive -- (335, act 2) is the only live shape, and
        whether the post-crossing walk contains it is exactly the retirement question."""
        hit = [v for (r, v) in states if r == room]
        if not hit:
            return False
        alts = self.required_guards.get(item, {}).get(room)
        if not alts or any(g is None for g in alts):
            return True
        regs = set(R) if isinstance(R, tuple) else {R}
        for g in alts:
            musts = self._site_musts(g, regs)
            if not musts:
                return True
            for v in hit:
                vals = dict(zip(R, v)) if isinstance(R, tuple) else {R: v}
                if all(vals[r] in allowed for r, allowed in musts.items() if r in vals):
                    return True
        return False

    def crossing_retires_need(self, a, b, item, need_rooms):
        """A why-string when crossing a->b's own register commit leaves EVERY need site of
        `item` in `need_rooms` dead -- an unreachable need is a RETIRED need -- else None (keep).

        The register half of `edge_strandings`' "still needed past the edge" conjunct. The flat
        walk answers it with `rooms_after(b)`, which is register-blind, so LB2's act-break edges
        kept demanding the pressPass at the 2->3 and 4->5 breaks (`rm26->rm355`/`rm26->rm420`)
        to protect needs at rm250/rm335 -- and the pass is surrendered at the act-2 door, a
        required story step, so either demand would have WALLED the break for every player, the
        failure this project holds to be worse than the bug. Two register facts close them, one
        each: rm250 is room-dead past act 1 (the street seal), and rm335's one need site is the
        sGiveInvite arming, condition `global123==2` (the doorman's init guard, carried by the
        delegate rule + `required_guards`), so the room being walkable at acts 3-4 keeps no
        need alive. `rm26->rm330` keeps its demand: (335, act 2) is in its post-crossing walk.

        Quantifiers, each in the strict direction: retired only when EVERY way of making the
        move (every meta row) has SOME projection with positive evidence (`_crossing_reach`
        returned a walk, not None) in which every need room is dead (`_need_live`). One row with
        no candidate register, or whose every candidate projection lacks evidence, keeps the
        demand whole. The detection rows are NOT touched -- detection deliberately
        over-approximates ("in-room writes are optional successors so it can never miss a
        stranding"); this is a demand-side filter in the same family as `unholdable_at`, and
        the drop is recorded in `_stranding_drops` where specs surface it as dropped_why.

        MEASURED 2026-08-10 (room-level half, at 61817b7): LSL2 0 of 16, KQ4 0 of 3, KQ6 0 of
        24 edge rows retired and 0 register-frontier demands anywhere -- the mechanism
        self-selects for edges that commit a register against a sealed need, which outside LB2's
        act breaks none does. The site-condition half is measured in the same session's
        follow-up commit (docs/LB2-ORACLE.md §7ai)."""
        need = set(need_rooms)
        if not need:
            return None
        per_meta = self._crossing_reach(a, b)
        if not per_meta:
            return None
        evidence = []
        for per in per_meta:
            got = [R for R, states in per.items()
                   if states is not None
                   and not any(self._need_live(item, r, R, states) for r in need)]
            if not got:
                return None
            evidence.append(got[0])
        return ("need %s unreachable past the crossing's own register commit "
                "(projections %s)" % (sorted(need), evidence))

    def edge_strandings(self):
        """The shared core, minus the rows three existing rules already refute.

        FORCED, NOT MISSABLE -- the crossing ITSELF demands the unit, so nobody crosses without
        it and the crossing cannot strand it. The toll carry-in detector has stated this rule
        since it existed (`if Y in self.edge_demands(a, b): continue`); the edge detector never
        applied it to its own rows, which is why a guarded door kept "stranding" the very item
        its guard demands and `verify` could not see its own fix.

        UNHOLDABLE -- the crossing's demand EXCLUDES the item (`guards.unholdable_at`: a room
        cost, or an exchange over one counter), so nobody arrives holding it and there is nothing
        to lose. KQ6's castle is one of each: the short door's dress costs the Realm (so the
        handkerchief and skeleton key cannot be in hand there), and the long door's route rides
        the pawn chain (so the nightingale IS the brush). Their real boundaries -- the Realm exit
        for the carry-outs, the short door for the nightingale -- carry the real guards.

        RETIRED -- the crossing's own register commit leaves every need room unreachable
        (`crossing_retires_need`), so the row's "still needed past the edge" conjunct fails in
        the register view even though the flat `rooms_after` passes it. LB2's act breaks are the
        case: `rm26->rm420` writes act 5, the pass's need rooms cap at acts 1-2, and the demand
        would have walled the break for every player (the pass is surrendered at the act-2 door).

        GROUPS pass through untouched, twice over. `edge_demands` is the intersection over DNF
        alternatives, so a demanded group's members distribute across alternatives and never
        survive the intersection -- the filter could only ever fire on a group via a SINGLE
        member demanded outright, and MEASURED (2026-08-02) that fires exactly once across the
        corpus: LSL2's play-validated rm79->rm80 raft guard, which it deletes. That baseline is
        ruled untouchable, and a filter whose one observable effect is wrong stays off."""
        import guards as _G                    # module-level would be a cycle; resolved by now
        out = []
        drops = {}                             # (a, b) -> {item: why} -- a dropped row is never
        #   silent: `guard_specs` folds these into the spec's dropped_incompatible/dropped_why,
        #   which is where the castle-door tests pin the reasons.
        for e in super().edge_strandings():
            a, b = e["from_room"], e["to_room"]
            dem = self.edge_demands(a, b)
            why = {it: "the crossing itself demands it -- forced, not missable"
                   for it in e["items"] if it in dem}
            rest = set(e["items"]) - set(why)
            why.update(_G.unholdable_at(self, a, b, rest) if rest else {})
            # RETIRED -- the crossing's own register commit leaves every need room unreachable,
            # so the demand would protect a need no post-crossing player can face. Items only:
            # groups pass through untouched here for the same measured reason as the FORCED
            # filter above.
            for it in set(e["items"]) - set(why):
                w = self.crossing_retires_need(a, b, it,
                                               self._unit_need_rooms(frozenset({it})))
                if w:
                    why[it] = w
            if why:
                drops.setdefault((a, b), {}).update(why)
            items = [it for it in e["items"] if it not in why]
            if items or e["groups"]:
                out.append({**e, "items": items, "groups": e["groups"]})
        self._stranding_drops = drops
        return out

    def edge_demands(self, a, b):
        """Items the edge a->b ITSELF requires -- the NECESSARY reading.

        `_emeta` holds one row per way of making the move and each row's `alts` is a DNF of
        item-sets, so an item is genuinely required only if it appears in EVERY alternative of
        EVERY row. Anything weaker would read one arming's demand as the edge's."""
        rows = self._emeta.get((a, b))
        if not rows:
            return frozenset()
        need = None
        for (_req, _sets, alts) in rows:
            for alt in (alts or (frozenset(),)):
                need = frozenset(alt) if need is None else (need & alt)
        return need or frozenset()

    def _reach_without(self, item):
        """Rooms reachable from the start WITHOUT ever holding `item` (gate-aware forward walk),
        intersected over every projection. `item` may be one item or a frozenset (a group).

        A room whose own(item) guard can only be reached BY holding item isn't a stranding site
        at all -- you can never stand there lacking it. rm61 tests own(Airline_Ticket) but every
        route in already spends the ticket, which is why the ticket looked missable.

        ...and a room that HANDS THE ITEM OVER unrefusably ends the walk for the same reason from
        the other side: you can arrive there without it, and you cannot leave without it. See
        `_unrefusable_grants` -- KQ5's rm1 gives Graham Crispin's wand on every entry, so no
        state past rm1 lacks it."""
        ban = item if isinstance(item, frozenset) else frozenset({item})
        if ban in self._rw:
            return self._rw[ban]
        grants = getattr(self, "_unref", None)
        if grants is None:
            grants = self._unref = _unrefusable_grants(getattr(self, "em", None))
        barrier = set()
        for it in ban:
            barrier |= grants.get(it, set())
        out = None
        for R in self.proj:
            rooms = {r for r, _ in self._walk(R, ban, barrier=barrier)}
            out = rooms if out is None else (out & rooms)
        self._rw[ban] = out if out is not None else set(self.reach_rooms)
        return self._rw[ban]

    def _need_rooms(self, item):
        """Rooms where own(item) is actually FACED -- gate-aware. See _reach_without.

        Deliberately RAW with respect to disjunctions -- see `_unit_need_rooms`, which is where a
        single item stops counting a room its group already covers. Subtracting here instead
        emptied the GROUP's need as well (a group's need is the union over its members), and LSL2's
        glacier guard `(or has:30 has:31)` disappeared entirely."""
        return {R for R in super()._need_rooms(item) if R in self._reach_without(item)}

    def _unit_need_rooms(self, u):
        """Rooms a requirement UNIT is faced in.

        A GROUP keeps every room its members are faced in -- the group IS the requirement there.
        A SINGLE item drops the rooms where it is merely one alternative of a group, because you
        are not required to bring THAT member; the group unit already demands one of them. Without
        this a guard asks for every solution to a puzzle at once: KQ6's castle demanded the mint
        AND the peppermint, LSL2's glacier the Sand AND the Ashes."""
        raw = set().union(*(self._need_rooms(i) for i in u)) if u else set()
        if len(u) > 1:
            return raw
        it = next(iter(u))
        groups = self.disjunctive_groups()
        return {R for R in raw
                if not any(it in G and len(G) > 1 for G in groups.get(R, ()))}

    def _source_live(self, ban, node, R):
        """Can any of `ban`'s sites in this room actually hand the item over in THIS state?

        The register half of the site filters `build_maps` already applies. A source is a place
        AND a condition: LB2's `rm440` places the work boot under `(== global123 4)`, so
        `(rm440, act 5)` is a state you can stand in where the boot is not on offer. Seeding the
        backward walk from every state whose ROOM is a source ignored the condition entirely, and
        with it the whole act structure -- every act-gated pickup read as available in every act.

        Same shape and same direction as `_prev_impossible`, which asks this question for the
        previous-room register alone and can answer it without the product; this one needs the
        product, so it is asked here rather than in `build_maps`.

        PERMISSIVE by construction, three times over: an unconditional site (`None`) keeps the
        room live; a site whose guard does not mention R keeps it live; and a room is live if ANY
        of its sites is. So this can only ever remove a state the game genuinely gates away."""
        room, st = node
        vals = st if isinstance(R, tuple) else (st,)
        regs = R if isinstance(R, tuple) else (R,)
        for it in ban:
            gs = self.source_guards.get(it, {}).get(room)
            if not gs:
                return True                   # no recorded condition -> the old, permissive read
            for g in gs:
                if g is None:
                    return True
                need = structural_reqs(g, regs)
                if all(v in need[Ri] for Ri, v in zip(regs, vals) if Ri in need):
                    return True
        return False

    def reobtainable_rooms(self, item):
        """Rooms from which `item` can still be ACQUIRED -- GATE-AWARE, intersected over every
        projection.

        Backward walk in each (room, register) projection instead of the guard-ignoring room
        graph. This replaces the `_sealed` one-way-edge heuristic: a pocket is sealed when the
        guards actually seal it, which is derived rather than assumed."""
        ban = item if isinstance(item, frozenset) else frozenset({item})
        if ban in self._reob:
            return self._reob[ban]
        srcs = set()
        for it in ban:
            srcs |= self.sources.get(it, set())
        if not srcs:
            self._reob[ban] = set()
            return self._reob[ban]
        out = None
        for R in self.proj:
            # For a JOINT projection the universe is the states you can actually BE in without the
            # item. `_pstates` is the UNBANNED walk, so it holds states you could only have reached
            # by already surviving WITH the item, and a backward walk starting from one of those
            # says the item is re-obtainable from a place you could never have stood. KQ6's dark
            # room is the case: lit, you walk on and eventually kill the minotaur, so
            # `(rm406, minotaur dead)` exists and reaches the pawn shop; unlit you die there.
            #
            # This is the more correct universe for EVERY projection, and it is applied only to the
            # joints deliberately. WIDENED TO SCALARS AND REVERTED 2026-08-01: measured, it moves
            # LSL2 (two Vine dangerous-sinks, a refused rm101->rm102 spec) and KQ4 (three
            # rm20/26/27->rm333 specs demanding item 21), and the USER RULED those verdicts
            # incorrect -- "anything that moves LSL2 and KQ4 is incorrect and should not be
            # relitigated". The direction of the error: a banned walk UNDER-approximates movement
            # (blocked() over-requires), and reobtainability read from an under-approximation
            # invents sinks. Do not widen this again; a trap that needs the tight universe must
            # come through a JOINT, which exists precisely to be judged tightly -- KQ6's catacombs
            # (the brick) is the standing case, see test_toll.
            states = self._walk(R, ban) if isinstance(R, tuple) else self._pstates[R]
            prev = defaultdict(set)               # reverse edges, minus own(item)-gated ones
            for u in states:
                for v in self._psucc(R, u, ban):
                    if v in states:
                        prev[v].add(u)
            back = {p for p in states if p[0] in srcs and self._source_live(ban, p, R)}
            # THE SOURCE FLOOR, and it is the same lesson as `entry_reqs`' arming floor: a room
            # where NO reachable state satisfies any site is IGNORANCE about how the site's
            # condition gets established, not evidence that the item cannot be had there.
            # Measured: LSL2's Knife has one site, in rm43, gated on `498 != 0`, and the 498
            # projection reaches rm43 only at 498 == 0 -- so the strict reading concluded the
            # Knife has no source at all and deleted a play-validated softlock. `sources` being
            # condition-blind had been COMPENSATING for that gap; making it condition-aware turns
            # every such gap into a lost finding, which is the wrong direction to be wrong in.
            # So the filter only ever DISCRIMINATES BETWEEN states of a room it already believes
            # in: it prunes act 5 from LB2's rm440 because act 4 IS reachable there and satisfies
            # the boot's `123 == 4`, and it leaves rm43 alone because nothing there satisfies
            # anything.
            for r in srcs:
                if not any(p[0] == r for p in back):
                    back |= {p for p in states if p[0] == r}
            q = deque(back)
            while q:
                u = q.popleft()
                for w in prev.get(u, ()):
                    if w not in back:
                        back.add(w)
                        q.append(w)
            rooms = {r for r, _ in back}
            out = rooms if out is None else (out & rooms)
        self._reob[ban] = out if out is not None else set()
        return self._reob[ban]

    def _freely_reversible(self, a, b):
        """Gate-aware override: b->a is a FREE walk only if some DNF alternative on it needs no
        item. An item-gated return -- the whale sneeze rm44->rm31 needs the Peacock Feather
        (alts={8}) -- is not free, so the forward swallow rm31->rm44 stays a one-way commit and the
        feather it demands is correctly stranded. Register gates are left alone here: the stranding
        test bans ITEMS, so an item-free-but-flag-gated return is still a walk you can make."""
        if a not in self.edges.get(b, set()):
            return False
        metas = self._emeta.get((b, a))
        if not metas:
            return True                          # return edge exists but carries no gate -> free
        # A register gate whose VALUE costs an item is not a free walk either. The docstring's
        # "flag-gated returns are still walkable" holds only while the flag is free to set: KQ6's
        # way back out of the catacombs tests "minotaur defeated", and the only thing that sets it
        # is showing him the red scarf, so the walk back is not free to someone who never had one.
        return any((not alts or any(not alt for alt in alts))
                   and not any(self._reg_cost(R, vals) for R, vals in req.items())
                   for (req, sets, alts) in metas)

    def rooms_after(self, b):
        """Rooms still reachable after crossing into `b` -- GATE-AWARE, intersected over
        projections. The condensation default counts the whole mega-SCC, which is what made
        rm52/rm57 look reachable from rm58 and inflated the boarding guard."""
        if b in self._after:
            return self._after[b]
        out = None
        for R in self.proj:
            starts = {p for p in self._pstates[R] if p[0] == b}
            if not starts:
                continue
            rooms = {r for r, _ in self._walk(R, frozenset(), starts)}
            out = rooms if out is None else (out & rooms)
        self._after[b] = out if out is not None else {b}
        return self._after[b]

    def goal_rooms_set(self):
        return {r for r in self.em.cfg.goal_rooms if r in self.comp_of}

    def _clause_key(self, room, guard):
        """Correlate effects belonging to the SAME source clause. Guard TEXT cannot be used --
        sibling branches of one `cond` share most conjuncts but differ (the rm82 bomb clause and
        its machine entry differ only in a counter term) -- so key on the room plus the clause's
        positive item preconditions, which a clause and the state it arms necessarily share."""
        return (room, frozenset(_own_positive(guard)))

    def _armed_wrote(self):
        """(armed clause-keys, wrote-map): the clauses that DO something -- arm a machine state,
        get an item, or write a register. Cached; the shared core of the arms-nothing test."""
        if getattr(self, "_aw", None) is None:
            armed, wrote = set(), defaultdict(list)
            for info in self.em.machines:
                for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                    armed.add(self._clause_key(info["room"], eg))
            for room, script, gi, v, g in self.em.handler_writes:
                wrote[self._clause_key(room, g)].append(gi)
            for room, script, it, g in self.em.handler_gets:
                armed.add(self._clause_key(room, g))
            self._aw = (armed, wrote)
        return self._aw

    def _clause_productive(self, room, guard):
        """Does the clause at (room, guard) ARM something -- a machine state, a get, or a gating
        register? The per-CLAUSE version of `real_uses` (which is per-room and too coarse: it calls
        the Lolotte shot wasteful and the shovel break productive). Tells a wasteful resource drain
        (KQ4's shoot-into-the-air) from a productive one (taming the unicorn, killing Lolotte)."""
        armed, wrote = self._armed_wrote()
        k = self._clause_key(room, guard)
        return k in armed or any(gi in set(self.regs) for gi in wrote.get(k, ()))

    def pure_sinks(self):
        """Consumptions that ACCOMPLISH NOTHING: a handler clause that removes an item from
        inventory while arming no machine state and writing no register any guard reads.

        Adventure games are full of these (drop it, eat it, throw it) and most are harmless, so
        this is a candidate set, not a finding -- see dangerous_sinks."""
        armed, wrote = set(), defaultdict(list)
        for info in self.em.machines:
            for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                armed.add(self._clause_key(info["room"], eg))
        for room, script, gi, v, g in self.em.handler_writes:
            wrote[self._clause_key(room, g)].append(gi)
        for room, script, it, g in self.em.handler_gets:
            armed.add(self._clause_key(room, g))
        gate = set(self.regs)
        out = []
        for room, script, it, g, dest in self.em.handler_drops:
            if script in self.GLOBAL_SCRIPTS:
                # Clause identity is (room, positive-owns), which pins a clause inside a small
                # room but COLLIDES badly in Main -- one giant script where unrelated clauses
                # share an own-set, so a real use elsewhere in Main masks a sink here. We cannot
                # attribute reliably, so assume the worst and let the danger test decide. That is
                # the over-require direction, and it is how "open parachute" (Main destroys the
                # chute needed for the rm63 jump) surfaced at all.
                out.append({"room": room, "script": script, "item": it, "dest": dest})
                continue
            k = self._clause_key(room, g)
            if k in armed or any(gi in gate for gi in wrote.get(k, ())):
                continue                          # the clause DOES something -> a real use
            out.append({"room": room, "script": script, "item": it, "dest": dest})
        return out

    def real_uses(self):
        """item -> rooms where holding it ARMS something -- the uses `dangerous_sinks` weighs a
        consumption against: a machine state armed by own(item), and a GATING REGISTER written from
        a handler guarded by own(item). Wearing the parachute at rm63 is the second -- it sets
        global142, arming no machine state -- so destroying the chute elsewhere looked harmless
        until this counted it.

        NOT `guard_required` (the broader "the game TESTS has: X"). This split -- sinks weigh
        against `real_uses`, `resource_exhaustion` weighs against `guard_required` -- is what makes
        LSL2's `dangerous_sinks` reproduce the v1.0-lsl2 tag EXACTLY (Matches / Hair_Rejuvenator /
        Parachute / Airsick_Bag; NOT the Grotesque_Gulp, which is drunk to death, NOR the Fruit).

        THAT TAG BEHAVIOUR IS A CORRECT ORACLE, frozen in test_golden.py. It was broken once by a
        later commit folding guard_required in here, and I nearly broke it again "fixing the smell"
        of the split. So: the split is load-bearing, not a mistake to derive away. Do NOT change it
        (or anything that moves LSL2's golden) without re-running test_golden AND checking with the
        user first -- the tag is the oracle, not something to re-litigate."""
        out = defaultdict(set)
        for info in self.em.machines:
            for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                for it in _own_positive(eg):
                    out[it].add(info["room"])
        gate = set(self.regs)
        for room, script, gi, v, g in self.em.handler_writes:
            if gi in gate:
                for it in _own_positive(g):
                    out[it].add(room)
        return out

    def _loc_required(self, guard, item, room=None):
        """Does this guard REQUIRE item `item`'s object to still be lying in THIS room?

        The BOOLEAN half of `_loc_values`, which answers WHICH owners it demands -- one reading,
        asked two ways, so the pair cannot drift ([[same-rule-two-places]]). Note the question is
        "is THIS room among them", not "does it demand a location at all": a guard naming some
        OTHER room requires nothing here. With no room to resolve against, the `"room"` sentinel
        is the only thing that can be about here."""
        return (room if room is not None else "room") in _loc_values(guard, item, room)

    def _machine_musts(self, info):
        """`state_musts` for one machine, memoised. The walk is per-machine and the owner-graph
        callers ask it once per ITEM, so without this the corpus pays for it forty times over."""
        if not hasattr(self, "_mmusts"):
            self._mmusts = {}
        key = (info.get("script"), info.get("inst"), info.get("room"))
        if key not in self._mmusts:
            self._mmusts[key] = state_musts(info, self.regs)
        return self._mmusts[key]

    def _acq_guards(self, item):
        """Every acquisition of `item`, as `(guard, room-it-was-found-in)`."""
        mg = getattr(self.em, "machine_gets", set())
        guards = [(a.guard, a.room) for a in self.em.ts.acqs
                  if a.item == item and (a.room, a.via, a.item) not in mg]
        guards += [(g, room) for room, script, it, g in self.em.handler_gets if it == item]
        # ...and a pickup the game performs inside a CUTSCENE, whose condition is on the way IN.
        # The flat walk sees `(gEgo get: N)` in a `changeState` body with no path condition at all,
        # so read alone every cutscene pickup looks unconditional and NOTHING is ever permanent.
        # KQ6's old lamp is the case: `rm520.init` only puts `theHuntersLamp` in the cast under
        # `((gInv at: 19) owner:) == gCurRoomNum`, and `getLamp` -- armed from that object's doVerb
        # -- is what actually hands it over. Trade the lamp to the peddler and he LEAVES (flag 12,
        # one writer, never cleared), so the destruction is final and this is the only place that
        # can know it. Entries are ALTERNATIVES, so the acquisition is location-gated only if every
        # one of them is; a machine with no entry contributes an unconditional acquisition, which is
        # the permissive answer.
        #
        # ...AND ITS CONDITION CAN ALSO BE ON THE WAY THROUGH, which is the second half and the
        # one KQ5's whole shop market turned on. `searchHay` is armed by clicking the haystack --
        # no condition at all -- and the ants only repay their debt at state 5 under
        # `(== ((gInv at: 3) owner:) 27)`, the needle still lying in the hay; the `(gEgo get: 3)`
        # is nine states later, on a path guard that says nothing. Read at the entries alone the
        # pickup is unconditional, so the owner graph records it under the WILDCARD owner, every
        # owner reaches EGO and NO destination is permanent -- the needle, the game's tightest
        # shop token, read as infinitely re-suppliable. `state_musts` already computes exactly
        # "what every path reaching this state established"; it now carries the ownedBy store on
        # the same walk, so this is a lookup rather than a second traversal.
        for info in self.em.machines:
            got = [K for K, paths in info["states"].items()
                   if any(item in gg for (_g, _w, gg, _c, _tr) in paths)]
            if not got:
                continue
            # One conjunct per getting state, because two states that both hand the item over are
            # ALTERNATIVE acquisitions and the permissive reading takes them apart, not together.
            musts = self._machine_musts(info)
            ents = [eg for (_seen, eg, _loc) in _entry_reach_walk_of(info)] or [None]
            for K in got:
                vals = musts.owners(K).get(item) or ()
                at = [Pred("LOC", var=item, op="ownedBy", value=v) for v in sorted(vals, key=str)]
                on = at[0] if len(at) == 1 else (GOr(tuple(at)) if at else None)
                for eg in ents:
                    guards.append((GAnd(tuple(_conj_spine(eg) + [on])) if on else eg,
                                   info["room"]))
        dbg = frozenset(self.em.cfg.debug_globals)
        guards = [(g, r) for (g, r) in guards if not _debug_gated_guard(g, dbg)]
        # ...and the same for an acquisition you could only reach by arriving from somewhere that
        # cannot reach it. This list is re-derived from `ts.acqs` rather than read off `sources`,
        # so `build_maps`' filters do NOT apply to it and each one has to be repeated here -- the
        # recurring shape in this codebase, and the reason the skull's throw looked survivable:
        # rm470's developer warp contributes an unconditional acquisition, and one unconditional
        # alternative is all it takes to make a destruction look undoable.
        prev = prev_room_reg(self.em)
        return [(g, r) for (g, r) in guards if not _prev_impossible(g, r, prev, self.edges)]

    def _owner_graph(self, item):
        """`owner -> {owner}`, the little transition system the ownedBy store IS for one item.

        Nodes are owner values (room numbers, SCI's -1/limbo, and EGO); every transfer of the item
        is an edge. An edge's SOURCE is what the transfer's guard demands about where the item is
        (`_loc_values`); a site that demands nothing can fire from ANY owner and is recorded under
        `None`, the wildcard -- the permissive reading, and the direction that refuses to invent a
        loss. Edges into EGO are the acquisitions.

        Reading transfers this way is what stops `moveTo:` being confused with destruction. KQ4's
        Cupid parks his bow in room 202 whenever you leave it lying in room 3 (`Room3::newRoom`),
        and re-appears one visit in three to drop it back (`doCupid`) -- so owner 202 is
        "Cupid has it", the state the bow is SUPPOSED to rest in, and the one-step test that asked
        only "does any acquisition demand owner == 202" called it destroyed."""
        if not hasattr(self, "_ograph"):
            self._ograph = {}
        if item in self._ograph:
            return self._ograph[item]
        out = defaultdict(set)
        for (g, r) in self._acq_guards(item):
            for src in (_loc_values(g, item, r) or {None}):
                out[src].add(E.EGO)
        moves = [(room, g, dest) for room, script, it, g, dest in self.em.handler_drops
                 if it == item]
        moves += [(room, g, dest) for room, script, it, g, dest, _inst
                  in getattr(self.em, "machine_moves", ()) if it == item and dest != E.EGO]
        for (room, g, dest) in moves:
            for src in (_loc_values(g, item, room) or {None}):
                out[src].add(dest)
        self._ograph[item] = dict(out)
        return self._ograph[item]

    def drop_is_permanent(self, item, dest):
        """Handing `item` to owner `dest`, can the player ever hold it again?

        `False` while EGO is reachable from `dest` in the item's owner graph -- following the
        game's own re-homing moves, not just the acquisitions. An item with NO acquisition at all
        cannot be regained and would be trivially permanent everywhere, so an empty graph answers
        `False`: silence about how an item is obtained is ignorance, not evidence."""
        graph = self._owner_graph(item)
        if not any(E.EGO in v for v in graph.values()):
            return False
        seen, stack = {dest}, [dest]
        while stack:
            node = stack.pop()
            for nxt in graph.get(node, set()) | graph.get(None, set()):
                if nxt == E.EGO:
                    return False
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return True

    def destroyed_is_permanent(self, item):
        """Once destroyed with `put: X -1`, is `item` gone for good?

        The special case of `drop_is_permanent` where the destination is NOWHERE: owner -1 is not
        a room, so no `(gInv at: X) ownedBy: gCurRoomNum` acquisition can ever be satisfied from
        it and nothing in the world can pick it back up. This is the one-time-pickup idiom, and it
        is why barfing into the Airsick_Bag costs you the game at rm82 even though rm62 is still
        walkable. Note it does NOT make the item unobtainable for someone who simply never took
        it, so it is deliberately scoped to DESTRUCTION and leaves the stranding sweep alone."""
        return self.drop_is_permanent(item, self.NOWHERE[0])

    # Main: its handleEvent runs in EVERY room. Hardcoded, and legitimately so -- script 0 IS
    # Main in every SCI dialect, which is a fact about the format rather than about a game.
    #
    # ⚠️ THERE ARE TWO NOTIONS OF "ALWAYS-LIVE SCOPE" IN THIS CODEBASE AND THIS IS THE OLDER ONE.
    # The other is `opmodel.global_homed`, DERIVED from the item class table
    # (`vocab.inventory_scripts`), which covers SCI1's icon bar -- on KQ6 that is scripts
    # {84, 90, 96, 97, 101, 907, 915}. The two do not intersect and neither consults the other:
    #   * this one homes a scope's sinks to every room (`_sink_rooms` below) but is only ever
    #     script 0, so it says nothing about the icon bar;
    #   * `global_homed` homes its scope's REGISTER effects everywhere and deliberately drops its
    #     item transfers entirely, so no sink from it ever reaches `_sink_rooms` to begin with.
    # That is why the gap is currently inert rather than wrong. Unifying them is a REAL change
    # (an icon-bar sink would become visible for the first time) and is deliberately not part of
    # the cleanup pass -- see docs/KQ6-STATUS.md, known inconsistencies.
    GLOBAL_SCRIPTS = frozenset({0})

    def _sink_rooms(self, sk):
        """Rooms a consumption can actually happen in.

        Normally the room it was found in. But Main (script 0) handles events in every room, so a
        `put: X -1` there is reachable from anywhere -- and being attributed to pseudo-room 0, which
        has no outgoing edges, it could never satisfy the "still needed downstream" test and was
        silently skipped. That is how four generic destroy-the-item verbs in Main went unnoticed
        until someone played the game and poured the rejuvenator out on an arbitrary screen."""
        if sk["script"] in self.GLOBAL_SCRIPTS:
            return sorted(r for r in self.reach_rooms if r in self.rooms and r != 0)
        return [sk["room"]]

    NOWHERE = (-1, None)     # `(gEgo put: N)` with no destination -- SCI's owner = -1

    def destroying_sinks(self):
        """Consumptions admitted because the item goes NOWHERE, whatever else the clause does.

        The SECOND way into `dangerous_sinks`, and it exists because `pure_sinks`' arms-nothing test
        is a PROXY. What that test is really trying to say is "spending it here was the intended
        move"; what it actually asks is "does this clause do anything at all", and a TRADE answers
        yes. KQ6's old lamp is the counterexample:

            lamps::doVerb 5   (gEgo put: 19)        ; the old lamp goes nowhere...
                              (gEgo get: 25)        ; ...and you are handed a new one

        The `get:` in the same clause makes it non-pure, so the destruction was invisible -- and the
        peddler then LEAVES (`lampTradeScr.sc:192` sets flag 12, one writer, never cleared), so
        there is no second trade. Meanwhile the old lamp is what `rm580::init` demands to cast the
        rain spell instead of caging you: `(if (and (gEgo has: 19) (== global161 15)) makeRain else
        inTheCage)`.

        The test is `drop_is_permanent`: can the player ever hold the item again once it belongs to
        this destination? `put:` with NO destination -- SCI's owner = -1 -- is the case that needs
        no reasoning at all, since -1 is not a room and no `owner == gCurRoomNum` acquisition can
        ever be satisfied from it. But it is only the DEGENERATE case, and reading it as the whole
        rule is what left KQ5's throwable pool unread: `(gEgo put: 5 6)` gives the fish to the cat's
        room, which is every bit as final as limbo -- nothing in rm6 hands it back, and the fish's
        one acquisition wants it lying in rm4. Asking the owner graph instead admits the trade and
        still refuses KQ4's Cupid, who moves his bow to room 202 and brings it back.

        The "was it the intended move" worry is answered by `dangerous_sinks` itself rather than
        here: an intended use does not leave the item still needed in a room you can still reach.

        ⛔ HANDLERS ONLY, and the boundary is a KNOWN GAP rather than a principle. A shop counter
        is a CUTSCENE -- KQ5's tailor takes his fee in `soldCloak` state 0, a `changeState` body --
        so none of that game's four shop payments is visible here, and the Heart (whose other
        consumer, the enchanted princess at rm9, accepts nothing else and is the Harp's only
        source) is a real one-payment walking dead we do not catch. MEASURED 2026-08-17: walking
        `machine_moves` as well finds those 3 rows and 19 false ones -- 13 `Cat_Fish` and 3
        `Beeswax` where the spend and the "still needed" use are THE SAME SITE seen in every room
        its region serves, plus a `Wand@rm66` that re-creates an FP the user ruled on 2026-08-15.
        The missing conjunct is a same-scope test (a consumer in the spend's own script is one
        event, not two competing ones); it did not cover the Wand, so nothing shipped. Declared red
        in `test_kq5_ground_truth`."""
        seen = {(sk["room"], sk["script"], sk["item"]) for sk in self.pure_sinks()}
        out, emitted = [], set()
        for room, script, it, g, dest in self.em.handler_drops:
            if (room, script, it) in seen or (room, script, it, dest) in emitted:
                continue          # ...or two objects running one clause: KQ5's cat and catStrip
            if dest in self.NOWHERE or self.drop_is_permanent(it, dest):    # both handle `put: 5 6`
                emitted.add((room, script, it, dest))
                out.append({"room": room, "script": script, "item": it, "dest": dest})
        return out

    def fatal_uses(self):
        """USING an item somewhere that kills you: the dangerous ACTION, in its purest form.

        Not a stranding and not a sink -- nothing is stranded and nothing is spent, because you do
        not survive to notice. It is still the thing the tool exists to prevent. KQ6's crushing
        ceiling offers the player two things to do with the gears, and one of them is a trap that
        looks exactly like the solution:

            theGears doVerb 39 -> useBrick     ; jam them with the brick -- you live
            theGears doVerb 51 -> throwSkull   ; throw the skull in -- the gears eat it and
                                               ; state 24 arms `sqwishEm` again: you are crushed

        `sqwishEm` is armed `0 1`, and its register only chooses whether one extra line is spoken
        (`(if register (say: ...) else (self cue:))`); both arms fall through to `(proc0_1 9)`,
        which is KQ6's imperative death proc. So there is no register value, no branch and no
        timing under which throwing the skull works.

        **Deaths are IN SCOPE, and the reasoning that says otherwise is the trap.** "You die, so you
        restore, so the item was never really lost" is true and irrelevant -- the player still spent
        a real attempt on a move the game invited them to make, and a tool that can see the move is
        fatal and says nothing is failing at its job. Recording that here because I talked myself
        out of this exact finding once, on exactly that argument.

        Derived, with no room or item named: an item appears here when some entry that requires
        holding it arms a machine that cannot be survived. "Cannot be survived" is `_survivable`,
        NOT `_trap_graph`'s `doomed` -- doomed means death is REACHABLE, and using it here condemned
        the shield for the KQ6 archer, the hole-in-the-wall for the labyrinth and LSL2's Matches for
        the volcano, i.e. exactly the items that keep you alive. Those machines branch on the item;
        this one does not.

        The complement of `death_traps`, which asks the same graph for the machines that are NOT
        doomed. That is why the brick is a REQUIREMENT to leave rm420 and the skull is a HAZARD in
        it, from one arming graph and one death set."""
        out, seen = [], set()
        for room, infos in _trap_rooms(self.em).items():
            if room not in self.reach_rooms:
                continue
            doomed, handoff, unavoidable, _preempt = _room_unavoidable(
                infos, self.sources, self.reach_rooms)
            for info in infos:
                if info["inst"] not in doomed:
                    continue
                # PER ENTRY, because the state an arming enters at decides whether it is
                # survivable: LSL2's bore talks you to death from state 0 and is SHUT UP by
                # `(boreScript changeState: 10)`, which is what giving him the pamphlet does.
                lethal = [(i, K, g) for i, (K, g) in enumerate(info.get("entries") or ())
                          if not _survivable(info, unavoidable, handoff, start=K,
                                             preempt=_preempt(info))]
                if not lethal:
                    continue
                # WHAT NO LETHAL ARMING AVOIDS -- `entry_musts` read over the fatal entries. An
                # item is the CAUSE of a death only if the death cannot happen without it; if some
                # other arming kills you just the same, holding it was incidental. KQ6's
                # `emptyHandedDeath` is the case and it is the exact inverse of the truth: one of
                # its armings is unconditional, and the hole-in-the-wall reaches it only through
                # the composed chain of PUTTING THE HOLE UP, which is the puzzle's solution. Blame
                # per entry and you condemn the item that exists to prevent the death.
                #
                # (`_own_required` inside each, for the usual reason: an item in one arm of an OR
                # is a way to arm this, not a thing you must hold.)
                #
                # ...AND READ AT THE ARMING SITE, NOT THROUGH THE INHERITED CHAIN -- the SIXTH
                # correction, and it is a new polarity. Every one before it assumed the item is
                # named because the player DID something with it. `entries[i]` is not that: the
                # strengthening passes conjoin the armer's preconditions (`_chain_entries`) and
                # the latch writes onto it, so an item that merely had to be in your pocket for
                # the SCENE to exist lands in the same conjunction as one you clicked.
                #
                # KQ5's tambourine is the case and the row it produced was advice you cannot
                # follow. Dink is `init:`ed only under `(has: 34)` (rm055 `localproc_5`), his own
                # script arms `hugScript`, and hugScript's state 5 is `(proc0_26 545)` -- so
                # own(34) reached the lethal entry as DINK'S EXISTENCE CONDITION. Meanwhile the
                # tambourine's actual use, `giveTamboScript`, is the ESCAPE from that machine and
                # the hairpin's source. Blaming the item told the player to drop the one thing
                # that saves them -- the same shape as condemning the hole-in-the-wall, one scope
                # further out. `entry_site` is the guard as built at the site, so the item has to
                # be part of what was DONE here to be blamed. Falls back to the full entry guard
                # when a machine predates the field, which is the previous reading.
                sites = info.get("entry_site") or ()
                blame = set.intersection(*[
                    set(_own_required(sites[i] if i < len(sites) else g))
                    for i, _K, g in lethal])
                for it in blame:
                    if (it, room) not in seen:
                        seen.add((it, room))
                        out.append({"item": it, "room": room, "machine": info["inst"],
                                    "states": sorted(K for _i, K, _g in lethal)})
        return out

    def ownedby_death_folds(self):
        """Arrivals that fork on an OWNER VALUE, where the losing arm is a death the player
        cannot dodge -- the value is therefore DEMANDED at the room's entry. KQ5 is the
        specimen game; the class is the ownedBy store read much later than it is written:

          * ENTRY fold: rm86 kidnapped-arrival runs `yourStuck` -- a pure-timer death --
            unless some throwable's owner is 6 (the cat scene banked a throw). `yourStuck`'s
            init-entry guard carries `NOT (LOC(8@6) OR ...)` on its AND spine, so the
            disjunction is the demand and `prev == 85` is the context.
          * STATE fork: rm42's `hatch` (one machine, the roc cutscene) branches state 6 on
            `owner(19) == 34` -- lamb fed to the eagle -> EXIT 43; anything else ->
            `(++ state)` into the death chain. One arm survives, its complement does not, so
            the owner value is demanded by the arrival that runs the machine.

        Three disciplines keep this honest:
          * "cannot be survived" is `_room_unavoidable` -- `_survivable` with pre-emption,
            the same classifier `fatal_uses` answers to, not `doomed` (death merely
            reachable), which is the mistake that once condemned the items that SAVE you.
          * a machine with a CHASE state makes no claim (`machine._chases`): its death
            completes only by catching the moving player, a race the player can decline by
            leaving -- KQ4's rm49 dog is escapable in play and must not condemn the Bone,
            and KQ5's rm36 yeti is caught compositionally by rm35's entry fold instead
            (arriving from 36 unfed is a scripted kill, no race).
          * only PLACEMENT values are demanded (`_fold_demands`): a value the player cannot
            produce is not advice.

        Rows are demands, not yet windows: whether the value is still producible when you
        get there is the window-closure question (phase 3), read over these rows'
        `demand_group`/`context`."""
        out, seen = [], set()
        for room, infos in _trap_rooms(self.em).items():
            if room not in self.reach_rooms:
                continue
            doomed, handoff, unavoidable, preempt = _room_unavoidable(
                infos, self.sources, self.reach_rooms)

            def _emit(info, groups, ctx, state=None):
                for grp in groups:
                    for (it, dst) in grp:
                        key = (it, dst, room, info["inst"], state)
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append({
                            "item": it, "item_name": self.g.item_name(it),
                            "dest": dst, "need_room": room, "machine": info["inst"],
                            "state": state,
                            "pattern": "entry-fold" if state is None else "state-fork",
                            "demand_group": sorted((i2, d2) for (i2, d2) in grp),
                            "context": {r: v for (r, v) in _must_equal(ctx)}})

            for info in infos:
                states = info.get("states") or {}
                if not states or not info.get("init_entries") or info.get("chase_states"):
                    continue
                # ---- ENTRY fold: the whole machine is the losing arm ----------------------
                if info["inst"] in unavoidable:
                    for (_k, g) in info["init_entries"]:
                        groups, ctx = _fold_demands(g, self.em.ts.placed)
                        _emit(info, groups, ctx)
                # ---- STATE fork: the fork lives inside one machine ------------------------
                surv = {K: _survivable(info, unavoidable, handoff, start=K,
                                       preempt=preempt(info)) for K in states}
                hands = any(m in unavoidable for (a, K) in handoff if a == info["inst"]
                            for m in (handoff.get((a, K)) or {}))

                def _cont_ok(K, tr):
                    if tr and tr[0] == "DEATH":
                        return False
                    if tr and tr[0] == "EXIT":
                        return True
                    nxt = _succ_state(K, tr)
                    return (surv[nxt] if (nxt is not None and nxt in states)
                            else not hands)

                for K, paths in states.items():
                    for i, (g1, _w1, _gg1, _c1, tr1) in enumerate(paths):
                        f1 = _conj_spine(g1)
                        for a in [x for x in f1 if _is_owner_atom(x)]:
                            n = GNot(kid=a)
                            rest1 = [x for x in f1 if x != a]
                            for (g2, _w2, _gg2, _c2, tr2) in paths:
                                f2 = _conj_spine(g2)
                                if n not in f2 or [x for x in f2 if x != n] != rest1:
                                    continue
                                if _cont_ok(K, tr1) and not _cont_ok(K, tr2) \
                                        and isinstance(a.value, int) \
                                        and a.value in self.em.ts.placed.get(a.var, ()):
                                    _emit(info, [[(a.var, a.value)]], [], state=K)
                # ---- DELEGATED fork: the arms commit by ARMING SIBLINGS -------------------
                # KQ5's rm67 `henchCaught` st8 (USER-confirmed 2026-08-18b: locketless capture
                # = death): `(if (and (not flag96) (owner(25)==57)) (stone setScript: moveStone)
                # else (stone setScript: dieScumScript))`. The transitions say nothing -- BOTH
                # arms JUMP on, because the commitment is the `setScript:`, one machine away --
                # so the spine matcher above is blind twice over: the arms are WHOLE-GUARD
                # complements (a GAnd and its GNot, not a spine pair), and the death lives in
                # the ARMED sibling, recorded only in `handoff[(inst, K)]`. The fork is read
                # where the facts are: a state arming complementary-guarded siblings, one
                # unavoidable and one not, demands the placed owner atoms on the SURVIVING
                # arming's own spine; its register conjuncts (flag 96 clear) are the context.
                # `_complementary` is _survivable's own branch test, shared, not copied.
                for K in states:
                    hmap = handoff.get((info["inst"], K)) or {}
                    lethal_gs = [g for m2, g in hmap.items()
                                 if m2 in unavoidable and g is not None]
                    for m2, gsafe in sorted(hmap.items()):
                        if m2 in unavoidable or gsafe is None:
                            continue
                        sspine = _conj_spine(gsafe if isinstance(gsafe, list) else [gsafe])
                        for gl in lethal_gs:
                            lspine = _conj_spine(gl if isinstance(gl, list) else [gl])
                            # the machine's own entry context rides both armings as a
                            # shared prefix; the fork is the RESIDUES -- one side a single
                            # GNot whose kid's spine IS the other side (whole-guard
                            # complement), or _survivable's bare g/NOT-g pair.
                            shared = [x for x in sspine if x in lspine]
                            sres = [x for x in sspine if x not in shared]
                            lres = [x for x in lspine if x not in shared]
                            comp = (_complementary(sres, lres)
                                    or (len(lres) == 1 and isinstance(lres[0], GNot)
                                        and _conj_spine([lres[0].kid]) == sres))
                            if not comp:
                                continue
                            owners = [a for a in sres if _is_owner_atom(a)
                                      and isinstance(a.value, int)
                                      and a.value in self.em.ts.placed.get(a.var, ())]
                            if not owners:
                                continue
                            rest = [x for x in sres if not _is_owner_atom(x)]
                            _emit(info, [[(a.var, a.value)] for a in owners], rest,
                                  state=K)
                            break
        return out

    def _death_fuses(self):
        """`(fuses, live_phases, deaths, per_room)` -- the adversarial-clock classification,
        shared by `fuse_death_armings` (which gates the encounters that LIGHT a fuse) and
        `capture_fold_armings` (which must not mistake a fuse-lighting machine for an escape:
        KQ5's organ disposes the henchman and starts Mordack's countdown, trading a death for
        a death). Cached; see `fuse_death_armings` for the derivation of each step."""
        if getattr(self, "_fusecache", None) is not None:
            return self._fusecache
        ir = getattr(self.em, "ir", None)
        fbase = getattr(ir, "flag_synth_base", None) if ir is not None else None
        known_flags = getattr(ir, "flag_indices", None) or frozenset()

        def _own_atoms(spine):
            return {a.var for a in spine
                    if isinstance(a, Pred) and a.kind == "OWN" and a.want}

        def _is_flag(S):
            return fbase is not None and S >= fbase and (S - fbase) in known_flags

        # ---- 1. death phases + the per-room classification kept for the system pass ------
        phases, per_room = {}, {}
        for room, infos in sorted(_trap_rooms(self.em).items()):
            if room not in self.reach_rooms:
                continue
            _doomed, handoff, unavoid, _pre = _room_unavoidable(
                infos, self.sources, self.reach_rooms)
            per_room[room] = (infos, handoff, unavoid)
            for i in infos:
                if i["inst"] not in unavoid:
                    continue
                for (_K, g) in list(i.get("entries") or ()) + list(i.get("init_entries") or ()):
                    spine = [_nn(a) for a in _conj_spine(g)]
                    if _own_atoms(spine):
                        continue
                    for (S, V) in _must_equal(g):
                        if S in self.regs:
                            phases.setdefault((S, V), set()).add(i["inst"])
        # ---- 2. clock expiry writes + 3. the fuse fixpoint --------------------------------
        #
        # ⭐ A COUNTDOWN IS A REGISTER THE SAME HANDLER COUNTS DOWN. That is the whole
        # discriminator, and reading it off the DECREMENT rather than off "some register on
        # the spine is compared nonzero" is what the 2026-08-19d review's F4 corrected. The
        # old reading could not tell KQ5's expiry clock (`global353`, decremented every game
        # minute) from the henchman's MODE register (`global333`, merely compared) -- which is
        # why the fixpoint below had to carry an exclusion for a write re-arming "its own"
        # countdown, a clause whose only function was to keep a known answer still
        # ([[clause-that-protects-a-known-answer]]). With the decrement read, that clause is
        # unreachable and is gone. The same correction is what stops a game whose region clock
        # writes a phase under `(== gPrevRoom N)` or `(== gAct 2)` promoting the realm seal, or
        # the act, to a FUSE: `_demands_nonzero` accepts `== <nonzero>`, and nothing decrements
        # a previous-room register.
        decs = getattr(self.em, "handler_decs", None) or frozenset()
        clock, seen_cw = [], set()
        for (room, script, S, V, g) in self.em.handler_writes:
            spine = [_nn(a) for a in _conj_spine(g)]
            if not any(isinstance(a, tuple) and a and a[0] == "CTR" for a in spine):
                continue
            if _own_atoms(spine) or any(_is_owner_atom(a) for a in spine) \
                    or any(isinstance(a, tuple) and a and a[0] == "POS" for a in spine):
                continue
            cds = frozenset(a.var for a in spine if isinstance(a, Pred) and a.kind == "CMP"
                            and a.var in self.regs and _demands_nonzero(a)
                            and (room, script, a.var) in decs)
            if cds and (S, V, cds) not in seen_cw:
                seen_cw.add((S, V, cds))
                clock.append((S, V, cds))
        fuses, changed = set(), True
        while changed:
            changed = False
            for (S, V, cds) in clock:
                if ((S, V) in phases or (S in fuses and V != 0)) and not (cds <= fuses):
                    fuses |= cds
                    changed = True
        if not fuses:
            self._fusecache = (set(), [], [], per_room)
            return self._fusecache          # no clock in this game; the room map still stands
        live_phases = sorted({(S, V) for (S, V) in phases
                              if any((S, V) == (cs, cv) and (cds & fuses)
                                     for (cs, cv, cds) in clock)})
        deaths = sorted({m for (S, V) in live_phases for m in phases[(S, V)]})

        self._fusecache = (fuses, live_phases, deaths, per_room)
        return self._fusecache

    def fuse_death_armings(self):
        """Encounters whose unanswered outcome writes a REMOTE DEATH FUSE -- the demand rides
        the encounter's ARMING. KQ5's castle cat is the specimen and docs/KQ5-ORACLE.md §23
        the derivation; the class is the adversarial clock ([[softlock-mechanism-taxonomy]]
        class 5, KQ4's day/night, KQ6's wedding fuse) grown a third hop: the clock does not
        seal an item, it arms a DEATH, and the countdown is not free-running, it is ARMED by
        the encounter the player failed to answer.

        Three derived classifications compose, each read from structure nothing here names:

          1. DEATH PHASES -- (S, V) register values whose holding arms a machine
             `_room_unavoidable` already condemns, off an entry spine that offers the player
             nothing (no own() atom: a priced arming is an act, and an act can be declined).
             KQ5: (331, 3) arms theWizardScript in nine castle rooms; (331, 6) arms
             wakeUpScript in rm63.
          2. THE CLOCK -- a handler write of S := V gated by a LOCAL LATCH (a CTR atom on the
             spine: `(if local5 ...)`, the boolean a per-real-second `(!= local8 (GetTime 1))`
             test raises one cycle in sixty) and by a RUNNING COUNTDOWN: a register the SAME
             HANDLER DECREMENTS and whose nonzero-ness the write demands. No item, no owner
             and no positional atom anywhere on the spine, so the write fires on wall time and
             not on anything the player does. The countdown register of a phase-writing clock
             is a FUSE, and the set closes under chaining -- KQ5's global353 is a fuse because
             its expiry writes global352 := 3, and 352's expiry writes the phase.

             ⛔ THE DECREMENT IS THE WHOLE DISCRIMINATOR, and until 2026-08-19e this read "any
             register compared nonzero on the spine" instead. That could not tell a clock from
             a MODE register the write happens to be scoped by, so the henchman's global333
             classified as a fuse and an exclusion had to be invented to remove it again --
             `S not in cds`, a clause in src/ whose only job was to keep a known answer still
             ([[clause-that-protects-a-known-answer]]). Reading the decrement makes that
             clause unreachable, and stops a game whose region clock scopes its phase write
             with `(== gPrevRoom N)` or `(== gAct 2)` from promoting the realm seal, or the
             act, to a fuse. The decrement is read by a second walk of the handler body
             (`opmodel._hwalk`) because SCI routinely spells the tick inside the TEST of the
             very `if` it gates, where no statement walk can see it. Contributed by the
             2026-08-19d contextless review, F3 and F4.
          3. FUSE-ARMING MACHINES (`_fuse_machines`) -- a machine one of whose states writes a
             fuse to a nonzero literal that its own guard does not prove is a top-up
             (theCatRunScript st3: `global353 := 3` while 353 runs, which SHORTENS whatever
             the clock held). Running one is a COMMITTED death: the expiry is nondeterministic
             (the KQ4-clock doctrine -- it may fire at any qualifying moment), so a localized
             defuse downstream cannot un-fire it.
             ⚠️ A BOUNDED GAP, unchanged: the same `if`'s else arm writes
             `global352 := (Random 5 10)`, and a non-literal right-hand side is invisible to
             the write extractor. The 353 branch covers KQ5; a game whose only fuse lighting
             is spelled with a Random has none of this classification.

        The row is the demand at the arming of the SYSTEM that can fall into a fuse-arming
        machine: the ROOT is a spawned machine (every `entry_armers` empty -- armed by its
        host's init, not chained from another machine) with a state handoff into the lethal
        set; its ESCAPES are the armable same-slot competitors outside that set (the
        `setScript:` slot race `death_traps` and `_survivable`'s preempt rule are built on).
        An escape's price is read off its own chain-composed entry guards -- own() atoms plus
        positive flag demands -- with two closures that make the price the FIXPOINT the oracle
        derives rather than the bare disjunction:

          * a non-flag register equality on the spine (catInBag's `332 == 7` init arm, "the
            cat is already bagged") prices as the demands of its WRITERS -- the value is not a
            thing you hold, it is a thing some other answer establishes;
          * an escape that itself hands off into the lethal set (catGetFish ends in
            theCatRunScript -- the fish answer re-arms the fuse) is only half an answer: its
            price conjoins the price of the escapes of the encounter it re-arms, DISCHARGED of
            every atom its own chain already writes (theThrowFishScript writes flag 62, so the
            re-armed encounter's 62-demand is already paid). Each escape's writes are monotone
            here, which is what terminates the recursion; a cycle prices as no answer.

        KQ5 derives `(own37 ∧ 63 ∧ own24) ∨ (63 ∧ 62 ∧ own24)` = flag63 ∧ own(24) ∧
        (flag62 ∨ own(37)) -- the USER's ruling verbatim, and NOT the bag-only collapse the
        naive "fuse write = death" reading produces (which would wall the cat's first spawn
        forever, flag 62's only writer being the fish answer inside an encounter).

        Rows are emitted once per (root machine, demanded item, DEMAND) -- the demand is part
        of the row's identity, because `keep` is derived per room off the escapes that room
        offers and a second room deriving a STRONGER one used to be dropped in silence (review
        R5). The arming rooms are the CALL SITES of the host-script procedure that inits the
        root's host object (the [[a-procedure-is-not-a-handler]] attribution, walked directly),
        which is also where a guard goes: one wrap on that procedure holds every spawn site at
        once -- around the `setScript:` that arms the machine or the `init:` that proxies for
        it, whichever the game spells (review R3), and never by conjoining onto an `(if` whose
        `else`, `cond` arm or `switch` case the game runs in the arming's place (R2, N2).

        NOT a snapshot key (that is a bless); consumed by the KQ5 oracle test and by
        `guards.fuse_arming_remedies`. Measured corpus-wide the day it landed: LSL2, KQ4, KQ6
        and LB2 all return [] -- KQ6's wedding fuse writes a flag no unavoidable machine's
        entry pins, so it has no death phase and stays `register_strandings`' item-seal."""
        fuses, live_phases, deaths, per_room = self._death_fuses()
        if not fuses:
            return []
        ir = getattr(self.em, "ir", None)
        fbase = getattr(ir, "flag_synth_base", None) if ir is not None else None
        known_flags = getattr(ir, "flag_indices", None) or frozenset()

        def _own_atoms(spine):
            return {a.var for a in spine
                    if isinstance(a, Pred) and a.kind == "OWN" and a.want}

        def _is_flag(S):
            return fbase is not None and S >= fbase and (S - fbase) in known_flags

        # ---- 4. per room: the lethal set, the root, its escapes, their prices -------------
        out, emitted = [], set()
        for room, (infos, handoff, unavoid) in sorted(per_room.items()):
            fusem = _fuse_machines(infos, fuses)
            if not fusem:
                continue
            lethal = unavoid | fusem
            esc = _Escapes(self, infos, handoff, lethal)

            for i in infos:
                nm = i["inst"]
                if nm in lethal or not i.get("states"):
                    continue
                if any(a for a in (i.get("entry_armers") or ()) if a):
                    continue                       # chained: priced inside, not a root
                if not esc.hands_lethal(nm):
                    continue
                ways = esc.slot_escapes(nm)
                if not ways:
                    continue
                alts = []
                for m in ways:
                    alts += esc.price(m, frozenset(), frozenset({nm}))
                keep = _minimal(alts)
                if not keep:
                    continue
                items = sorted({it for a in keep for (kind, it) in a if kind == "own"})
                fl = sorted({n for a in keep for (kind, n) in a if kind == "flag"})
                host_sn = i.get("script")
                rooms, procs = self._arming_call_rooms(host_sn, i.get("entry_recv"))
                # ⛔ THE DEMAND IS PART OF THE ROW'S IDENTITY (2026-08-20 review, R5). `emitted`
                # lives outside this per-room loop, but `keep` is derived PER ROOM, off the
                # escapes THAT room offers. Keyed `(machine, item)` alone, the first room to
                # emit won and a second room deriving a STRONGER demand was dropped in silence
                # -- so the guard shipped the weaker hold and that room's softlock shipped open.
                # The clash gate in `guards.fuse_arming_remedies` could not see it either: it
                # only ever sees rows this set let through. With the demand in the key both rows
                # reach it, and it refuses the pair rather than conjoining a hold neither room
                # derived. Measured on KQ5 the day this landed: 13 rooms reach
                # `(theCatScript, 24)` and `(theCatScript, 37)` and all 13 derive the SAME
                # demand, so the row count and the shipped condition are unmoved.
                demand_key = tuple(sorted(tuple(sorted(a)) for a in keep))
                for it in items:
                    key = (nm, it, demand_key)
                    if key in emitted:
                        continue
                    emitted.add(key)
                    out.append({
                        "pattern": "fuse-death-arming", "item": it,
                        "item_name": self.g.item_name(it), "machine": nm,
                        # the HOST OBJECTS the arming procedure `init:`s -- the spawn
                        # statement the guard must sit around. Without them the applier can
                        # only guess, and its guess was "the procedure's first `(if`", which
                        # holds no spawn at all in any procedure with an earlier branch
                        # (review F2).
                        "hosts": sorted({rc[1] for rc in (i.get("entry_recv") or ())
                                         if rc and rc[0] == "O"}),
                        "arm_rooms": rooms,
                        # EVERY spawning procedure, not the first one sorted. A machine spawned
                        # from two procedures and held at one of them is not held (findings #4
                        # and #8's shape, review F13) -- and the surface reported
                        # `applied=True sites=1` either way.
                        "arm_procs": [{"script": host_sn, "name": p} for p in procs],
                        # `fuse`/`phases`/`death` are the GAME-WIDE classification -- every
                        # countdown, every phase value, every machine those phases arm. `lit`
                        # is this row's own: the fuse registers the lethal machines IN THIS
                        # ROOM actually write. The distinction is why the red that declared
                        # this detector could only assert `352 in fuse` (review F15): a
                        # per-row claim had nowhere to live.
                        "fuse": sorted(fuses), "phases": live_phases,
                        "lit": sorted({S for m in sorted(fusem) for i2 in infos
                                       if i2["inst"] == m
                                       for _K2, ps in (i2.get("states") or {}).items()
                                       for (g2, w, _gg2, _c2, _t2) in ps
                                       for (S, v) in (w or ())
                                       if S in fuses and isinstance(v, int) and v != 0
                                       and not _bounded_below(g2, S, v)}),
                        "death": deaths, "flags": fl, "escapes": ways,
                        "demand_alts": [{"items": sorted(x for (k, x) in a if k == "own"),
                                         "flags": sorted(x for (k, x) in a if k == "flag")}
                                        for a in keep]})
        return out

    def capture_fold_armings(self):
        """Encounters that CARRY the player into a lethal arrival fold -- the demand rides the
        encounter's ARMING. KQ5's castle henchman is the specimen; docs/KQ5-ORACLE.md §24.

        `ownedby_death_folds` already says what the arrival demands: reaching KQ5's rm67 alive
        needs `owner(25) == 57` -- the locket already given to Cassima -- with flag 96 clear,
        since the game sets 69 and 96 TOGETHER at the rescue, so 96 means "she has spent her
        one rescue". `fold_carryins` places such a demand on the crossing that arms the fold,
        but only when the fold's context NAMES that crossing as a previous room. This context
        names a REGISTER, and the crossing is not a walk at all: `theHenchManScript` state 12
        carries `('EXIT', 67)`. The machine that carries you is the machine to gate.

        ⭐ THAT IS ALSO THE DISCRIMINATOR AGAINST THE CHASE EXCLUSION, which elsewhere stops
        this project condemning a race the player declines by leaving (KQ4's rm49 dog, KQ5's
        rm36 yeti -- both of which end where they start, and neither of which moves the player
        anywhere). A chase whose own machine performs a room crossing does not offer that
        decline: leaving is how you LOSE it. USER 2026-08-19d, from play: "if he catches you a
        second time you die... got that without even trying."

        THE SECOND DISJUNCT IS NOT OPTIONAL. The fold's condition is monotone-unsatisfiable
        once the rescue writes flag 96, so a demand built from it alone would seal the
        encounter forever -- and the encounter is REQUIRED past that point, its answer being
        the only writer of the empty bag the cat catch needs. A demand that cannot be met is a
        wall, so it admits the ANSWER's own price as an alternative: `(fold survivable) ∨
        (answer payable)`. That is the USER's ruling ("if you have the peas, we should let it
        happen, otherwise we should block it") derived rather than transcribed.

        AN ANSWER is a machine that DISPOSES the encounter's host (`setScript: 0`; KQ5's pea
        throw is armed into the ROOM's slot and reaches over to the henchman, so no slot map
        records it), and that
          * does not itself leave the room -- a machine carrying an EXIT transition DEFERS
            rather than answers, because the host is armed region-wide and re-rolls next door
            ([[arm-event-soundness]]'s flag-105 lesson: a "decline" that only postpones is a
            deferral), and
          * is not itself lethal -- `unavoidable`, or a machine that arms a death fuse
            (`_death_fuses`' classification, which is what excludes rm58's organ: it disposes
            the henchman and lights Mordack's countdown).

        ⚠️ MEASURED LIMIT, stated because it errs toward OVER-demanding: a disposal written
        through `(ScriptID N K)` indirection is not resolved to its object, so only
        same-script disposers are seen. On KQ5 that costs nothing -- the indirect ones are
        rm54's `falling`, rm58's organ and rm59's frozen-beast display, each already excluded
        by a rule above -- but a game whose only answer is written indirectly would get a
        demand with no alternative, which is reported as `answerless` and refused by
        `guards.capture_fold_remedies` rather than shipped as a wall.

        Rows are per (machine, fold), deduped across the region's rooms."""
        folds = {}
        for r in self.ownedby_death_folds():
            folds.setdefault(r["need_room"], []).append(r)
        if not folds:
            return []
        fuses, _lp, _d, per_room = self._death_fuses()
        out, emitted = [], set()
        for room, (infos, handoff, unavoid) in sorted(per_room.items()):
            lethal = unavoid | _fuse_machines(infos, fuses)
            esc = _Escapes(self, infos, handoff, lethal)
            disposers = self._disposers(infos)
            leaves = {i["inst"] for i in infos
                      for _K, ps in (i.get("states") or {}).items()
                      for (_g, _w, _gg, _c, t) in ps if t and t[0] == "EXIT"}
            for i in infos:
                nm = i["inst"]
                if nm in lethal or not i.get("states"):
                    continue
                exits = {t[1] for _K, ps in (i.get("states") or {}).items()
                         for (_g, _w, _gg, _c, t) in ps if t and t[0] == "EXIT"}
                hosts = {rc for rc in (i.get("entry_recv") or ()) if rc is not None}
                answers = sorted({m for h in hosts for m in disposers.get(h, ())
                                  if m != nm and m not in lethal and m not in leaves
                                  and esc.armable(m)})
                for R in sorted(exits & set(folds)):
                    if R == room:
                        continue
                    # ...only if the FOLD ACTUALLY ARMS on this arrival. KQ5's rm67 dispatches
                    # on where you came from -- `(switch prevRoom (55 <enterHole>) (else
                    # <henchCaught>))` -- so the maze's own `goHoleScript` carries the player
                    # into rm67 without ever arming the fork, and demanding the locket of it
                    # would be a false positive. The fold machine's own entry guard is the
                    # authority, read against the room the crossing starts in -- and PER FOLD,
                    # because a room with two fold machines is two different claims and only
                    # the first was being tested (review F15).
                    if all(self._fold_disarmed(R, fr["machine"], room) for fr in folds[R]):
                        continue
                    # ...and only for the machine the player's arming CONTROLS. A machine
                    # gated on a register value another carrier of this same crossing
                    # establishes is that carrier's CONTINUATION, staged one room over --
                    # KQ5's rm59 `caughtScript` runs on `global333 == 5`, which
                    # `theHenchManScript` writes when the rm60 chase reaches the stairs. Gating
                    # the root covers it compositionally (the same relationship the yeti's
                    # staged catch has to its chase); emitting both would double-patch one
                    # encounter.
                    if self._continuation_of(i, infos, R, folds):
                        continue
                    for fr in folds[R]:
                        if self._fold_disarmed(R, fr["machine"], room):
                            continue
                        key = (nm, R, fr["machine"], tuple(sorted(
                            tuple(x) for x in fr["demand_group"])))
                        if key in emitted:
                            continue
                        emitted.add(key)
                        # a fold's `demand_group` members are ALTERNATIVES -- any one banked
                        # throwable satisfies the cellar -- so each becomes its own way to
                        # survive, and the context rides all of them.
                        #
                        # ...and a context atom that is NOT a flag is not silently dropped
                        # (review F15): the context is what SCOPES the demand -- rm86's row
                        # carries `prev == 85`, "the losing arm arms exactly on the kidnap" --
                        # so a row that renders only the flags ships a scoped demand as an
                        # unscoped one, which is the wall-shaped failure. It rides the row and
                        # `guards.capture_fold_remedies` refuses on it.
                        ctx = [(("flag" if v else "nflag"), S - esc.fbase)
                               for (S, v) in sorted((fr.get("context") or {}).items())
                               if esc.is_flag(S)]
                        unrendered = [[S, v] for (S, v)
                                      in sorted((fr.get("context") or {}).items())
                                      if not esc.is_flag(S)]
                        alts = [frozenset([("owner", (it, dst))] + ctx)
                                for (it, dst) in fr["demand_group"]]
                        for m in answers:
                            alts += esc.price(m, frozenset(), frozenset({nm}))
                        keep = _minimal(alts)
                        out.append({
                            "pattern": "capture-fold-arming", "machine": nm,
                            "need_room": R, "fold_machine": fr["machine"],
                            "fold_state": fr.get("state"), "escapes": answers,
                            "answerless": not answers,
                            "arm_rooms": self._entry_rooms(i),
                            "host": sorted(h[1] for h in hosts if h[0] == "O"),
                            "script": i.get("script"),
                            "context_unrendered": unrendered,
                            "demand_alts": [{
                                "owners": sorted([list(x) for (k, x) in a if k == "owner"]),
                                "items": sorted(x for (k, x) in a if k == "own"),
                                "flags": sorted(x for (k, x) in a if k == "flag"),
                                "not_flags": sorted(x for (k, x) in a if k == "nflag"),
                                "iprops": sorted([list(x) for (k, x) in a if k == "iprop"]),
                                "not_iprops": sorted([list(x) for (k, x)
                                                      in a if k == "niprop"])}
                                for a in keep]})
        return out

    def _fold_disarmed(self, fold_room, fold_machine, from_room):
        """Does the fold machine's own arming EXCLUDE an arrival from `from_room`?

        Read off the previous-room register the model already derives, and only along the AND
        spine (`_must_hold`'s discipline): a `prev != X` conjunct excludes X, a `prev == Y`
        conjunct excludes everything else. Anything less readable excludes nothing.

        ⛔ ENTRIES ARE ALTERNATIVES (the 2026-08-19d review's F8). The machine arms if ANY of
        them fires, so it is disarmed for this arrival only when EVERY one of them excludes it
        -- and this rule DELETES a finding, so reading the disjunction conjunctively suppresses
        real carry-in demands, which is a softlock shipped rather than a false positive
        avoided. KQ5 is unaffected either way: `henchCaught`'s two entries are the same
        `(not (== prev 55))`."""
        prev = prev_room_reg(self.em)
        if prev is None:
            return False
        seen_entry = False
        for i in _trap_rooms(self.em).get(fold_room, ()):
            if i["inst"] != fold_machine:
                continue
            for (_K, g) in (list(i.get("init_entries") or ())
                            + list(i.get("entries") or ())):
                seen_entry = True
                if not _entry_excludes(g, prev, from_room):
                    return False               # this way in admits the arrival
        return seen_entry

    def _continuation_of(self, info, infos, fold_room, folds):
        """Is this machine a STAGED CONTINUATION of another carrier of the same crossing?

        Its entry demands a register value that some other machine -- one that also exits into
        the fold's room -- writes. That makes it the second half of one encounter, and the
        encounter is gated at its root."""
        want = {(S, V) for (_K, g) in (list(info.get("entries") or ())
                                       + list(info.get("init_entries") or ()))
                for (S, V) in _must_equal(g) if S in self.regs}
        if not want:
            return False
        for other in infos:
            if other["inst"] == info["inst"]:
                continue
            exits = {t[1] for _K, ps in (other.get("states") or {}).items()
                     for (_g, _w, _gg, _c, t) in ps if t and t[0] == "EXIT"}
            if fold_room not in exits:
                continue
            writes = {(S, v) for _K, ps in (other.get("states") or {}).items()
                      for (_g, w, _gg, _c, _t) in ps for (S, v) in (w or ())}
            if want & writes:
                return True
        return False

    def _disposers(self, infos):
        """`entry_recv slot -> {machines whose body DISPOSES that slot's object}`.

        An encounter lives in its host's `setScript:` slot, so the machines that can end it
        are not only the ones armed INTO that slot (the pre-emption rule's competitors) but
        the ones that write 0 to it from outside -- KQ5's pea throw is armed into the ROOM's
        slot and reaches over to the henchman. Same-script sends only; see
        `capture_fold_armings` for what that costs."""
        ir = getattr(self.em, "ir", None)
        out = defaultdict(set)
        if ir is None:
            return out
        want = {i["inst"]: i.get("script") for i in infos}
        for sn in sorted({v for v in want.values() if v is not None}):
            sc = ir.scripts.get(sn)
            if sc is None:
                continue
            for o in sc.objects:
                if o.name not in want:
                    continue
                for body in o.methods.values():
                    for n in I.walk(body):
                        if not (isinstance(n, dict) and n.get("t") == "Send"):
                            continue
                        try:
                            recv, msgs = I.send_pairs(n)
                        except Exception:                      # noqa: BLE001
                            continue
                        rn = recv.get("name") if isinstance(recv, dict) else None
                        if not rn:
                            continue
                        for sel, ps in msgs:
                            if sel == "setScript" and ps and I.as_int(ps[0]) == 0:
                                out[("O", rn)].add(o.name)
        return out

    def _entry_rooms(self, info):
        """The rooms this machine's own entry disjunction names -- a region machine says
        where it can arm by testing the current-room global, and that is where a guard's
        effect will be felt.

        POSITIVELY names (review F15). This used to run on a polarity-blind node walk, so a
        `(not (== gCurRoom 67))` -- "everywhere but there" -- reported rm67 as an arming room,
        which is the one room that conjunct provably rules out. A region machine's arming is
        usually a DISJUNCTION of per-room arms with the cond-ordering negations still on them
        (`(and (not (== cur 57)) (not (== cur 58)) (== cur 59))`), so the read has to descend
        through both connectives keeping polarity rather than stop at the AND spine."""
        import extract as X
        cur = getattr(X, "_CURROOM", None)
        rooms = set()
        for (_K, g) in list(info.get("entries") or ()) + list(info.get("init_entries") or ()):
            _positive_rooms(g, cur, True, rooms)
        return sorted(rooms & set(self.reach_rooms))

    def _arming_call_rooms(self, host_sn, entry_recv):
        """(rooms, proc names): the reachable rooms whose scripts call a procedure of script
        `host_sn` that `init:`s the object the entries name -- the spawn's real sites, and
        the one place a guard wraps them all. Empty when the arming is not proc-shaped."""
        ir = getattr(self.em, "ir", None)
        host = ir.scripts.get(host_sn) if ir is not None else None
        objs = {rc[1] for rc in (entry_recv or ()) if rc and rc[0] == "O"}
        if host is None or not objs:
            return [], []
        targets = set()
        for pname, body in (host.procs or {}).items():
            for n in I.walk(body):
                if not (isinstance(n, dict) and n.get("t") == "Send"):
                    continue
                try:
                    recv, msgs = I.send_pairs(n)
                except Exception:                          # noqa: BLE001
                    continue
                rn = recv.get("name") if isinstance(recv, dict) else None
                if rn in objs and any(sel == "init" for sel, _ps in msgs):
                    targets.add(pname)
                    break
        if not targets:
            return [], []
        rooms = set()
        for sn, sc in ir.scripts.items():
            if sn == host_sn or sn not in self.reach_rooms:
                continue
            bodies = [m for o in sc.objects for m in o.methods.values()] \
                + list((sc.procs or {}).values())
            for body in bodies:
                if any(isinstance(n, dict) and n.get("t") in ("PublicCall", "LocalCall")
                       and n.get("name") in targets for n in I.walk(body)):
                    rooms.add(sn)
                    break
        return sorted(rooms), sorted(targets)

    def window_closures(self):
        """Demands whose PRODUCERS all die when a register flips -- the one-shot window.

        `ownedby_death_folds` states the demand: arriving at KQ5's rm86 from the kidnap, some
        throwable must be owned by room 6 or `yourStuck` is a pure-timer death. It does not state
        that the only way to satisfy it is behind a door that shuts by itself, and that is the
        half a player actually loses the game to. rm006 is the case and it is the game's worst
        softlock:

            (if (and (or (has: 8) (has: 16)) (not (proc0_12 83)))   ; the cat and the rat exist
                (rat init:) (cat init:))                            ; only while the window is open
            ...
            ((and (global5 contains: rat) (> (gEgo x:) 290) ...)    ; rm006::doit -- the trigger
                (proc0_9 83) (self setScript: catAndMouse))         ; SETS 83 as the chase STARTS

        Flag 83 goes up when the chase begins, not when it is won, so losing the race is silently
        terminal -- and what kills you is a timer in a cellar hours later and half the map away.

        THE CONJUNCT A ROOM-REACHABILITY TEST CANNOT SUPPLY is producer liveness. rm6 stays
        walkable forever; what stops being possible is the throw. So a producer is read through
        `guard_reqs` against the register being flipped: a site whose own guard needs R to be
        anything but `w` is dead in the post-flip world, and a row needs EVERY producer dead --
        one survivor and there is no closure.

        The rest is `register_strandings`' three conjuncts, unchanged in meaning and for the same
        reasons: the flip must be REACHABLE (`_flip_seeds`, not "every room ever seen at w"), the
        room that READS the demand must still be ahead of the post-flip player (a read behind you
        demands nothing), and the goal must still be reachable (else this is a dead end, which is
        a different finding). The pre-flip conjunct is the causality one: if no producer was
        reachable before the flip either, the flip did not close anything.

        ⚠️ DEPENDS ON `extract.feature_adders`, and would be blind without it. Three of the seven
        `put: <item> 6` sites live on `catStrip`, which reaches the cast only through
        `(gGame setFeatures: catStrip)` inside the chase's own state 0; read without that cast
        event they carry none of the scene's arming, three producers look alive at flag 83 = 1,
        and the closure disappears.

        Rows are per demand-group MEMBER, like the fold rows they extend, and carry every closer
        found rather than the first: KQ5's window has two, flag 83 (closes on ARMING) and rm6's
        `local0` (closes on LOSING the race, after which the throws answer "too late"). Both are
        true and a remedy has to know about both."""
        out = []
        goal = self.goal_rooms_set()
        demands = {}
        for r in self.ownedby_death_folds():
            key = (tuple(sorted(tuple(x) for x in r["demand_group"])), r["need_room"])
            demands.setdefault(key, r)
        for (group, need_room), row in sorted(demands.items(), key=lambda kv: kv[0][1]):
            gset = {tuple(x) for x in group}
            prods = [(rm, g) for (rm, _sc, it, g, dst) in self.em.handler_drops
                     if (it, dst) in gset]
            if not prods:
                continue                       # nothing we can see produces it: no claim
            prod_rooms = {rm for rm, _g in prods}
            closers, flips = [], set()
            for R in self.proj:
                if not isinstance(R, int):
                    continue                   # scalars; a joint closure has no instance yet
                states = self._pstates.get(R) or set()
                vals = {v for (_r, v) in states}
                if len(vals) < 2:
                    continue
                for w in sorted(vals):
                    if any(self._producer_live(g, R, w) for _rm, g in prods):
                        continue               # a producer survives this value: no closure
                    seeds = self._flip_seeds(R, w, states)
                    if not seeds:
                        continue
                    after = {q for (q, _v) in self._walk(R, frozenset(), starts=seeds)}
                    if goal and not (goal & after):
                        continue               # already unwinnable: a dead end, not a softlock
                    if need_room not in after:
                        continue               # the read is behind you; nothing is demanded
                    pre = {(q, v) for (q, v) in states if v != w}
                    if not pre:
                        continue               # never seen at another value: an arrival, not a flip
                    before = {q for (q, _v) in self._walk(R, frozenset(), starts=pre)}
                    if not (prod_rooms & before):
                        continue               # unreachable before too: the flip closed nothing
                    closers.append((R, w))
                    flips |= {q for (q, _v) in seeds}
            if not closers:
                continue
            for (it, dst) in sorted(gset):
                out.append({"pattern": "window-closure",
                            "item": it, "item_name": self.g.item_name(it), "dest": dst,
                            "need_room": need_room,
                            "demand_group": sorted(gset),
                            "producer_rooms": sorted(prod_rooms),
                            "closes_on": sorted(closers),
                            "flip_rooms": sorted(flips)})
        return out

    def _producer_live(self, guard, R, w):
        """Can this producer still fire while register `R` holds `w`?

        `guard_reqs` is the one reading of "what does this guard demand of a register" this
        codebase keeps ([[same-rule-two-places]]), and its permissiveness is the right direction
        here too: a guard it cannot read constrains nothing, so the producer counts as ALIVE and
        the closure is not claimed.

        NO DOMAIN IS PASSED, deliberately. With one, `guard_reqs` also lowers `!=` and the
        relational ops ("not v" is "one of the others"), which would let more guards be judged
        dead -- and killing a producer is the direction that INVENTS a closure. Positive
        equalities are enough for the shape this detector is about: SCI writes a closed window as
        `(not (proc0_12 <flag>))`, and a negated `!=` is already read as the positive equality it
        is. KQ5's seven producers all yield `485: {0}` without a domain."""
        if guard is None:
            return True
        req = guard_reqs(guard, {R})
        return w in req[R] if R in req else True

    def dangerous_sinks(self):
        """Consumptions that COST you the game: the item is still needed somewhere you can still
        reach, and once wasted it cannot be re-obtained. The action-shaped sibling of a room-gate
        stranding -- nothing about it is a movement edge, so `edge_strandings` cannot see it.

        LSL2: rm63 `apply rejuvenator to bolt` (-5 points, and the bolt does NOT open) and rm81
        `drop rejuvenator` (-5) both destroy the bomb ingredient rm82 needs.

        Candidates come from two places, one danger test over both: `pure_sinks` (the clause
        accomplishes nothing) and `destroying_sinks` (the item goes NOWHERE, whatever else the
        clause accomplishes)."""
        uses = self.real_uses()
        out = []
        for sk in self.pure_sinks() + self.destroying_sinks():
            it = sk["item"]
            for room in self._sink_rooms(sk):
                ahead = (uses.get(it, set()) - {room}) & self.rooms_after(room)
                if not ahead:
                    continue
                # a one-time pickup destroyed here is gone regardless of which rooms stay walkable
                if not self.destroyed_is_permanent(it) and room in self.reobtainable_rooms(it):
                    continue
                # ...but a DISJUNCTIVE alternative rescues you: throwing the Ashes away is
                # survivable while the Sand is still gettable, since rm81 accepts either.
                #
                # ⭐ AN ALTERNATIVE IS ONLY AN ALTERNATIVE FOR THE GATE IT OPENS, so the group is
                # read at the CONSUMER -- the room where the item is still needed -- not at the
                # spend site. Both KQ5 scenes that trade throwables draw on one pool, and asking
                # the question at the spend site conflates them: spending the Fish at the cat is
                # excused by "the cat takes a Shoe too" while the room that still needs the Fish
                # is rm11, where the bear takes nothing else. Read at the consumer, the Shoe and
                # the Stick keep their rescue (each scene accepts the other's ammunition, the
                # user's own 2026-08-16b ruling) and the Fish loses it.
                live = {r for r in ahead
                        if not any(it in G
                                   and any(room in self.reobtainable_rooms(o) for o in G - {it})
                                   for G in self.disjunctive_groups().get(r, ()))}
                if not live:
                    continue
                out.append({**sk, "at_room": room, "still_needed_at": sorted(live)})
                break          # one witness room is enough to condemn the site
        return out

    def register_strandings(self):
        """Softlocks caused by a REGISTER flipping, not by walking through a one-way door.

        PRODUCTION SINCE 2026-08-02: `guards.guard_specs` consumes these rows into
        `register-write` remedies (hold the flip until the sealed items are in hand), so the
        snapshot's spec/placement surface carries them; `test_scopes` Part 7 (LSL2) and
        `test_toll.test_register_strandings_is_degenerate_on_sci11` (KQ6) pin the rows
        themselves. The one KQ6 row -- flag 166, the `letter` -- is user-confirmed (oracle unit
        #19) and remeasured 2026-08-05 as BOTH castle routes' seal: the flip is the wedding
        fuse's expiry in rgCastle::doit, region-homed into every castle room by the rFlag
        lowering (same class as KQ4's day/night -- an adversarial-clock phase change).

        CAUSAL SINCE 2026-08-02 (was: degenerate on SCI1.1, 323 junk rows on KQ6 -- above all
        reg12, `prevRoom`, whose every crossing-write was read as an irreversible plot advance).
        The cure is the causality conjunct below, derived from the projection alone; the history
        and the diagnosis live in the promoted test's docstring.

        The second class in the taxonomy, and one `edge_strandings` structurally cannot see: it
        reasons about crossing an edge, and here nothing is crossed. A plot flag advances -- you
        finish Lolotte's first errand, the sun goes down -- and a region that was open closes
        behind you while something you still need is inside it.

        Same shape as an edge stranding otherwise, so the same three conjuncts:
          1. the flip is a POINT OF NO RETURN: from every state at the new value, no state at any
             other value is reachable. (Nightfall in KQ4 is NOT one -- Room82 brings the dawn --
             which is why it correctly reports nothing.)
          2. the goal is still reachable afterwards, or this is a dead end rather than a softlock;
          3. every source of the item is outside the post-flip region, and a use is inside it.

        Runs on the projections `_build_product` already made, so it costs a walk per (register,
        value) and no new model.

        ⭐ JOINT PROJECTIONS SINCE 2026-08-09. This iterated `self.regs` -- scalars only -- while
        `self.proj` (scalars PLUS the joints the death traps ask for) is what the four reachability
        walks use. So a seal expressed in TWO registers was invisible to the one detector that
        reports seals, even when the joint it needed had already been built. LB2 is the case: act 5
        is a chase whose only two exits kill you, `_apply_death_traps` correctly writes the way out
        as the disjunction `12 != 420 OR 123 != 5`, and each alternative passes freely in the
        projection that cannot see the other. Measured: LSL2 0->0, KQ4 0->0, KQ6 1->1 (its one
        joint, `(12, 173)`, adds nothing), LB2 2 -> 9 findings including cheese and snakeOil, the
        two act-5 carries this project has been chasing since 2026-08-06. Nothing is lost anywhere.

        Three scalar assumptions had to be generalised, all of them "the flip landed on w":
        component-wise, a joint flips into w when SOME register of the tuple is written to its
        component of w. See `_flip_seeds`.

        ⭐ THE FETCH WALKS BAN THE ITEM THEY FETCH (2026-08-14, phase 2 of the KQ5 window
        plan). The source test asked "can the post-flip player still reach a source?" with the
        PERMISSIVE walk -- which crosses an own(X)-priced edge while judging whether X is still
        obtainable, i.e. it assumes the hammer while fetching the hammer. That is the exact
        assumption `_psucc`'s ban parameter exists to refuse ("you cannot use the parachute to
        walk back to the parachute"), and it is why KQ5's kidnap corral never produced a row:
        from (rm86, prev==85) the only exit prices own(Hammer), the permissive walk sailed
        through it, and the Hammer read as obtainable from inside the room it unlocks.

        The ban is applied exactly where the defect was: a flip the permissive walk already
        strands keeps its permissive verdict, region and causality test bit-for-bit (the
        detector's stance is over-approximated movement, and those rows never rested on the
        bad assumption); a flip the permissive walk EXCUSES -- "still obtainable" -- is
        re-asked with the item banned, and a row born this way reads its region, causality and
        need sites from the banned walk (the stuck player's world, which is how the Hammer's
        need lands on the cellar door and not on every hammer site an equipped player could
        visit). The dead-end test stays permissive throughout: a flip is a softlock only if
        some equipped player still wins. Banning an item no alternative prices cannot change a
        walk (`banned` reaches `_psucc` via edge alts and `_inroom_own`, and
        `_reg_unreachable`'s `_reg_cost` reads `_inroom_own` too), so the `priced` precheck
        skips every other item, and the result is cached on the surface.

        ⭐ AND THE PRE-FLIP HALF IS ASKED THE SAME WAY, of a player who can actually be there.
        The conjunct asks what someone who had not yet crossed could still have reached, and
        both halves of that carried the circularity: the walk fetched the item while holding
        it, and the states it started from came from `_pstates` -- the permissive product,
        which inside a sealed region contains arrivals no item-less player ever makes. So the
        pre-flip states are intersected with what is REACHABLE under the same ban, and then
        walked under it.

        Both corrections matter, and a POSITIONAL register is where they bite: "this room at
        another prevRoom value" is not an earlier moment but a DIFFERENT ARRIVAL, often one
        from deeper inside the seal. KQ6 supplies both shapes -- rm155's only other arrival is
        coming back OUT of the Realm at rm680, and rm405's are the labyrinth cells, whose
        "still obtainable" coin (rm430) is itself inside the maze. Under both clauses those
        read as arrivals (`b is None`, the rule this detector already states) and their real
        boundary is left to the toll detector, which already carries it. A room with a genuine
        two-way arrival keeps its row: KQ5's cellar is enterable normally as well as by the
        kidnap, and that normal arrival is a real hammer-less player who can still reach rm5.

        This DELETES findings, so it is stated narrowly: a comparison that assumes possession
        of the item, or that starts from a state the item-less player cannot occupy, cannot
        witness the loss of that item.

        ⚠️ COST, stated rather than buried: the ban makes the per-seed-room walk memo
        item-specific, so this is walks per (flip, value, item, room) where it used to be per
        (flip, value, room). The mitigations are the `priced` set (an item no alternative
        prices anywhere cannot move any walk), the REGION-LOCAL skip below (the same fact
        asked of the region actually being walked), and the surface-level cache."""
        if getattr(self, "_regstrand_cache", None) is not None:
            return self._regstrand_cache
        out = []
        goal = self.goal_rooms_set()
        # The items whose absence can change ANY walk: everything named by an edge alternative
        # or an in-room write cost -- the two places `_psucc` consults `banned` directly, and
        # `_reg_unreachable`'s `_reg_cost` reads `_inroom_own` too, so this covers all three.
        priced = set()
        for metas in self._emeta.values():
            for (_req, _sets, alts) in metas:
                for alt in alts:
                    priced |= set(alt)
        for own in self._inroom_own.values():
            priced |= set(own)
        # ...and the same fact indexed BY ROOM, which is what makes the re-asks affordable: an
        # item nothing inside a region prices cannot change any walk through that region, so
        # the question "is it still obtainable from here" has the same answer banned or not,
        # and neither walk needs running. Global `priced` is far too coarse to skip on (most
        # items are priced somewhere); region-local, KQ6's labyrinth and Realm price a handful.
        own_by_room, alts_by_room = defaultdict(set), defaultdict(set)
        for (_Rk, rk, _vk), own in self._inroom_own.items():
            own_by_room[rk] |= set(own)
        for (a2, _b2), metas in self._emeta.items():
            for (_rq, _st, alts) in metas:
                for alt in alts:
                    alts_by_room[a2] |= set(alt)
        live_cache = {}

        def _live(R, ban):
            """The states a player NOT holding the banned item can actually be in."""
            if (R, ban) not in live_cache:
                live_cache[(R, ban)] = set(self._walk(R, ban))
            return live_cache[(R, ban)]
        for R in self.proj:
            states = self._pstates[R]
            vals = {v for (_r, v) in states}
            if len(vals) < 2:
                continue
            for w in sorted(vals):
                seeds = self._flip_seeds(R, w, states)
                if not seeds:
                    continue
                after = self._walk(R, frozenset(), starts=seeds)
                # NOTE there is deliberately no separate "is this irreversible" test. An earlier
                # version required that no state at another value be reachable, which rejects
                # every plot counter -- moving FORWARD is not getting back out. `after` already
                # includes whatever the register does next, so if a source is still reachable the
                # flip stranded nothing, and if it is not, the flip stranded it. The source test
                # below IS the irreversibility test.
                #
                # ...but THE FLIP MUST BE THE CAUSE, and that half was missing -- the SCI1.1
                # degeneracy (2026-08-02, was 323 rows on KQ6). A seed inside an already-sealed
                # region cannot reach the outside sources WHATEVER the register does, so blaming
                # the flip reported every register ever written inside the Realm -- and prevRoom,
                # which every crossing writes, once per room value. The causality test is the
                # same walk from the PRE-flip states at the same rooms: what the pre-flip player
                # could not reach either, the flip did not strand (that is the REGION's doing,
                # and the edge/toll detectors own it). A room only ever seen at `w` has no
                # pre-flip player, and its "flip" is an arrival -- an edge crossing wearing a
                # register, owned by edge_strandings. Derived from the projection alone; no
                # register is named.
                seed_rooms = {r for (r, _v) in seeds}
                rooms_after = {r for (r, _v) in after}
                # ...and THE QUANTIFIER over WHERE the flip happens must be EXISTENTIAL. The
                # union walk asks "does every flip strand?", invisible while registers had one
                # or two write sites -- the moment the rFlag lowering gave the wedding flag its
                # region-homed writer (every castle room, rm781 itself included), the union
                # reached the letter through the flip-at-the-source seed and the confirmed row
                # dissolved. A softlock needs only SOME reachable flip whose player can no
                # longer reach a source their pre-flip self could: the wedding starting while
                # you stand in the throne room strands the letter regardless of the flip that
                # could have happened in the letter's own room. Per-seed-room walks; the
                # arrival exclusion and the causality conjunct apply per room, same as before.
                per_room, region_priced = {}, {}

                def _priced_in_region(r):
                    """Items priced anywhere the post-flip player can walk. Banning anything
                    else leaves both walks identical, which is what lets the loop below skip
                    the whole (room, item) pair instead of walking it twice."""
                    if r not in region_priced:
                        rooms = _flip_at(r)[0]
                        region_priced[r] = set().union(
                            *(own_by_room[x] | alts_by_room[x] for x in rooms)) if rooms else set()
                    return region_priced[r]

                def _flip_at(r, ban=frozenset()):
                    key = (r, ban)
                    if key not in per_room:
                        a_st = self._walk(R, ban, starts={(r, w)})
                        a = {q for (q, _v) in a_st}
                        # ...and the pre-flip player must be one who can BE there without the
                        # item. `states` is the permissive product; inside a sealed region it
                        # contains arrivals no item-less player ever makes, and those vouch
                        # for sources that are themselves inside the seal (KQ6's rm405 with
                        # prev==410 "reaching" the coin at rm430, both in the labyrinth).
                        b0 = ({(r2, v) for (r2, v) in states if r2 == r and v != w}
                              & _live(R, ban))
                        b_st = self._walk(R, ban, starts=b0) if b0 else None
                        b = ({q for (q, _v) in b_st}
                             if b0 else None)       # None: no pre-flip player -> an arrival
                        per_room[key] = (a, b, a_st, b_st)
                    return per_room[key]

                def _live_srcs(it, srcs, walk_states):
                    """Source rooms this walk reaches WITH A LIVE ACQUISITION -- reaching the
                    room is not reaching the item when every acquisition guard there is dead
                    at the walked value (`_source_live`, the same standard `reobtainable_rooms`
                    applies). KQ5's Shell forced the distinction: the beach stays reachable
                    after the departure flip, but the pickup's guard now carries the harpy
                    wall's flag-54-clear demand, so the post-flip walk stands in the source
                    room and cannot have the item."""
                    if walk_states is None:
                        return set()
                    fit = frozenset({it})
                    return {q[0] for q in walk_states
                            if q[0] in srcs and self._source_live(fit, q, R)}
                if goal and not (goal & rooms_after):
                    continue                        # already unwinnable: a dead end, not a softlock
                for it in sorted(self.required):
                    srcs = self.sources.get(it, set())
                    if not srcs:
                        continue                    # never obtainable: not this detector's story
                    ban = frozenset({it}) if it in priced else frozenset()
                    strand_at = []
                    for r in sorted(seed_rooms):
                        # THE CHEAP ANSWER FIRST. If the permissive walk already reaches a
                        # source and nothing in that region prices this item, the banned walk
                        # reaches it too -- identical walk -- so the flip stranded nothing and
                        # neither walk is worth running. Pure speed: the rows are the same
                        # either way, and it is the difference between one walk pair per
                        # (flip, room) and one per (flip, room, item).
                        _ap, _bp, ast_p, _bs = _flip_at(r)
                        if _live_srcs(it, srcs, ast_p) \
                                and it not in _priced_in_region(r):
                            continue
                        # ONE standard for both halves of the comparison. The question the row
                        # asks is about a player who does NOT hold the item -- can they still
                        # reach a source after the flip (`a`), could they before it (`b`) --
                        # so both walks withhold it. Splitting them, which an earlier cut of
                        # this change did to leave old rows untouched, keeps the very
                        # circularity the ban exists to remove: LB2's pressPass rows survived
                        # only because the pre-flip walk fetched the pass while holding it.
                        a, b, a_st, b_st = _flip_at(r, ban)
                        if b is None:
                            continue                # no item-less pre-flip player -> arrival
                        if goal and not (goal & _flip_at(r, frozenset())[0]):
                            continue                # that flip is a dead end, not a softlock
                        #   ^ PERMISSIVE deliberately: a flip is a softlock only if some
                        #     equipped player still wins; the item-less one provably cannot.
                        if _live_srcs(it, srcs, a_st) \
                                or not _live_srcs(it, srcs, b_st):
                            continue                # still obtainable, or never was from here
                        if self.required[it] & a:
                            strand_at.append(r)
                    if strand_at:
                        sealed = set().union(*(_flip_at(r, ban)[0] for r in strand_at))
                        ahead = self.required[it] & sealed
                        out.append({"pattern": "register-flip-point-of-no-return",
                                    "register": R, "value": w, "item": it,
                                    "item_name": self.g.item_name(it),
                                    "flip_rooms": strand_at,
                                    "source_rooms": sorted(srcs),
                                    "still_needed_at": sorted(ahead),
                                    "_sealed": frozenset(sealed)})
        self._regstrand_cache = self._collapse_flips(out)
        return self._regstrand_cache

    def _flip_seeds(self, R, w, states):
        """The reachable states where the flip INTO `w` can itself happen.

        Rooms that write `w`, plus edges that set it on the way out -- NOT every room already seen
        at `w`. Seeding a room with its own post-flip state is how a first attempt at this "proved"
        that KQ4's start room was sealed by nightfall.

        Component-wise for a joint: a tuple value is entered when SOME register of the tuple is
        written to its component. Requiring the whole tuple to be written at once would find
        nothing, because no single write sets two registers -- which is exactly why a joint seal
        was invisible here."""
        if isinstance(R, tuple):
            def writes(r):
                return any(w[i] in self._inroom[Ri].get(r, ()) for i, Ri in enumerate(R))

            def sets_it(sets):
                return any(sets.get(Ri) == w[i] for i, Ri in enumerate(R))
            seeds = {(r, v) for (r, v) in states if v == w and writes(r)}
        else:
            def sets_it(sets):
                return sets.get(R) == w
            seeds = {(r, w) for r, vs in self._inroom[R].items() if w in vs}
        for (_a, b), metas in self._emeta.items():
            for (_req, sets, _alts) in metas:
                if sets_it(sets):
                    seeds.add((b, w))
        return seeds & states

    @staticmethod
    def _collapse_flips(rows):
        """One SEAL of one item is one finding, however many states you can enter it from.

        A joint that contains `prevRoom` inherits prevRoom's degeneracy in multiplied form: every
        crossing writes reg 12, so a sealed region reports once per (room-you-came-from, value)
        cell. Measured on LB2 before this: 163 rows carrying **9** distinct facts, the same item
        repeated across 19 prevRoom values. That is the scalar detector's 2026-08-02 problem (323
        junk rows on KQ6) wearing a tuple.

        The collapse is derived from the model and names no register: rows for the same ITEM whose
        SEALED REGION is identical are one row, and the flip rooms/values merge. Two rows that seal
        genuinely different regions stay two. `value` keeps the lowest merged value so a row that
        merged nothing is byte-identical to before; `values` appears only when a merge happened."""
        return _collapse_by(rows, lambda r: (r["item"], str(r["register"]), r.pop("_sealed")),
                            ("flip_rooms", "still_needed_at"))

    def _reg_entry_demands(self, S):
        """room -> [(machine inst, frozenset(accepted values of S))] for machines whose EVERY way
        of being armed presupposes S in that set -- the register twin of a `has:` use site.

        Read per entry with `structural_reqs` (the NECESSARY reading; a value inside an OR-branch
        is not presupposed), then across entries: an entry with no constraint accepts the whole
        domain, and the machine's accepted set is the UNION over its entries -- every way in
        vouches for the values it accepts, and a demand exists only if the union still excludes
        something.

        A CHAINED entry (armed from inside another machine's changeState -- `entry_armers`)
        resolves through the ARMER's own demand rather than its guard. Its guard is the armer's
        entry disjunction with the recursion cut at the arming floor, and that floor arm is
        IGNORANCE, not an atom-free way in ([[arming-floor]]: ignorance is not evidence) -- read
        flat it dissolves every demand it embeds. LB2's cobra pass is the case: `sSprinkleOil`'s
        direct doVerb entries both presuppose `150 != 0`, and its third entry, armed from
        `sRepelSnakes` (whose own entries presuppose the same), reduced the intersection to
        nothing. Coinductively -- a back-edge on the armer chain contributes nothing new, because
        entering the cycle at all passes some member's direct entry -- the group's direct entries
        decide, which is the honest reading of a closed arming loop. An armer we cannot resolve
        accepts the whole domain: that kills the demand, the safe direction.

        A direct entry silent on S but gated on a LOWERED ROOM LOCAL (the fifth store) resolves
        the same way, through the machines that RAISE the latch: `snake1::doit` arms
        `sRepelSnakes` under `local3`, and `local3 := 1` is written in `sSprinkleOil` state 2, so
        that arming is exactly as free as the sprinkle that precedes it. The hop is bounded to
        this room's own lowered locals because their writer set is COMPLETE by construction (the
        script reloads on entry, resetting the latch -- see vocab.derive_room_locals); a global
        latch may be written anywhere, and resolving it through the writers we happen to see
        would fabricate demands from ignorance. Any non-machine write of a satisfying value
        bails to the whole domain, the safe direction again."""
        dom = frozenset(self.em.reg_vals.get(S, ())) | {v for (_r, v) in
                                                        self._pstates.get(S, ())}
        if len(dom) < 2:
            return {}
        domd = {S: set(dom)}
        by_name = {(i["room"], str(i.get("inst"))): i for i in self.em.machines}
        local_home, latch_writers, nonmachine = latch_evidence(self.em)
        memo, stack = {}, set()

        def accepted(info):
            key = id(info)
            if key in memo:
                return memo[key]
            if key in stack:
                return None                            # back-edge: the cycle's directs decide
            stack.add(key)
            ents = list(info.get("entries", ()))
            armers = list(info.get("entry_armers", ()))
            armers += [None] * (len(ents) - len(armers))
            ents += list(info.get("init_entries", ()))  # init entries are direct by construction
            armers += [None] * (len(ents) - len(armers))
            acc = set()
            for (K, eg), arm in zip(ents, armers):
                if arm:
                    tgt = by_name.get((info["room"], arm[0]))
                    got = accepted(tgt) if tgt is not None else dom
                    if got is None:
                        continue
                    acc |= got
                else:
                    sr = structural_reqs(eg, {S}, domd).get(S)
                    acc |= frozenset(sr) if sr else _via_latch(info, eg)
                if acc >= dom:
                    break
            stack.discard(key)
            memo[key] = frozenset(acc) if ents else frozenset(dom)
            return memo[key]

        def _via_latch(info, eg):
            room = info["room"]
            regs = {gi for gi, home in local_home.items() if home[0] == room}
            if not regs:
                return dom
            need = structural_reqs(eg, regs, {gi: set(self.em.reg_vals.get(gi, {0, 1}))
                                              for gi in regs})
            for R2, vals in sorted(need.items()):
                if nonmachine.get((room, R2), set()) & set(vals):
                    continue                           # a handler can raise it: no bound
                raisers = [i2 for (i2, v2) in latch_writers.get((room, R2), ()) if v2 in vals]
                got, resolved = set(), False
                for i2 in raisers:
                    g2 = accepted(i2)
                    if g2 is None:
                        continue                       # back-edge: bounded by the group's directs
                    resolved = True
                    got |= g2
                    if got >= dom:
                        break
                if not raisers or not resolved:
                    # No machine ever raises the latch, or every raiser is upstream on this very
                    # chain (a pure cycle). Either way this entry opens no way in that the group's
                    # direct entries do not already account for -- an unfirable entry vouches for
                    # nothing, and returning `dom` here was how the cobra pass's whole demand
                    # dissolved (sRepelSnakes' doit arming resolved through sSprinkleOil, which
                    # was on the stack, and the empty union read as freedom).
                    return frozenset()
                return frozenset(got)
            return dom

        merged = {}
        for info in self.em.machines:
            if info.get("global_scope"):
                continue                               # the icon bar has no place -- see opmodel
            if any(info["room"] in self.required.get(it, ()) for it in info.get("drops", ())):
                # A machine that CONSUMES an item still required where it stands is the loss,
                # not the way past -- LB2's `sThrowBottle` (the 150 == 0 arm of the cobra pass)
                # destroys the very bottle rm730 requires. Reading its arming condition as a
                # demand inverts the finding: the detector would report "you can never throw
                # the bottle away" as the softlock.
                continue
            acc = accepted(info)
            if acc is not None and acc:
                # UNION per (room, machine): a region-homed machine appears once per room COPY,
                # each with the copy's own entry conditions, and the copies are alternative
                # armings of the SAME machine -- exactly what the per-entry union already says.
                # KQ6's `walkGuardsOnScreen` at rm850 is the case: one copy resolves to
                # `{flag == 1}` and another to `{flag == 0}`, which is no demand at all, and read
                # separately each copy fabricated a choreography "stranding".
                key = (info["room"], str(info.get("inst")))
                merged[key] = (merged.get(key, frozenset()) | acc)
        out = {}
        for (room, inst), acc in merged.items():
            if acc and not (acc >= dom):
                out.setdefault(room, []).append((inst, acc))
        for room in out:
            out[room].sort()
        return out

    def register_value_strandings(self):
        """Crossing a SEAL while a register holds a value the far side rejects -- the REGISTER
        twin of `register_strandings`' item rows, built on the same flips and the same walks.

        The case that forced it [user rulings, 2026-08-09/10]: LB2's snake-oil bottle. The bottle
        ITEM is already caught (the joint (12,123) row), but the bottle can be EMPTY -- global150,
        spent by shakes at rm520/rm610, poured out whole by `sDumpIt` -- and entering act 5 with
        `150 == 0` is its own stranding: rm730's cobra pass presupposes `150 != 0` in every arming
        (`_reg_entry_demands`; the `== 0` arm throws the bottle away and passes nothing), the one
        raise is rm610's vat (`= global150 4`, three refills metered by flags 105-107), and the
        act-5 seal cuts rm610 off. The user ruled the spend ARITHMETIC out of scope -- "you should
        have enough snake oil left before entering act 5" -- so the boundary value is the whole
        question, which is exactly what the projections can answer.

        Same conjuncts as the item rows, register-shaped:
          1. the flip can happen while S == b -- `(flip_room, b)` is a reachable product state;
          2. past the flip, some machine's every arming presupposes S in a set excluding b, at a
             room the post-flip player reaches;
          3. no write past the flip -- room write or edge write -- puts S into the accepted set,
             and some pre-flip write could have (the causality half: what the pre-flip player
             could not fix either, this flip did not break);
          4. the goal is still reachable, or it is a dead end rather than a softlock.

        prevRoom is excluded as the DEMANDED register outright: it is rewritten by movement
        itself, so it is not state the player can HOLD across a seal -- a prevRoom demand the
        sealed region cannot satisfy means a ROOM became unreachable, which is the flat graph's
        fact (and the act partition's), not a value you failed to bring. Measured before the
        exclusion: LB2's `sFinishIt` at rm454 demands `prev == 455` and rm455 is outside the
        act-5 region, which is true, is not a register stranding, and is already the act seal's
        own finding. Derived per game via `prev_room_reg`, not a number."""
        out = []
        goal = self.goal_rooms_set()
        demand_cache = {}
        prev = prev_room_reg(self.em)
        for R in self.proj:
            states = self._pstates[R]
            vals = {v for (_r, v) in states}
            if len(vals) < 2:
                continue
            comps = set(R) if isinstance(R, tuple) else {R}
            for w in sorted(vals, key=repr):
                seeds = self._flip_seeds(R, w, states)
                if not seeds:
                    continue
                seed_rooms = {r for (r, _v) in seeds}
                per_room = {}

                def _flip_at(r, R=R, w=w, states=states, per_room=per_room):
                    if r not in per_room:
                        a = {q for (q, _v) in self._walk(R, frozenset(), starts={(r, w)})}
                        b0 = {(r2, v) for (r2, v) in states if r2 == r and v != w}
                        b = ({q for (q, _v) in self._walk(R, frozenset(), starts=b0)}
                             if b0 else None)          # None: no pre-flip player -> an arrival
                        per_room[r] = (a, b)
                    return per_room[r]

                for S in sorted(self.regs):
                    if S in comps or S == prev:
                        continue
                    if S not in demand_cache:
                        demand_cache[S] = self._reg_entry_demands(S)
                    sites = demand_cache[S]
                    if not sites:
                        continue
                    sst = self._pstates.get(S, set())
                    dom = frozenset(self.em.reg_vals.get(S, ())) | {v for (_r, v) in sst}
                    writes = {r2: set(v2) for r2, v2 in self._inroom.get(S, {}).items()}
                    esets = [(x, m[1].get(S)) for (x, _y), ms in self._emeta.items()
                             for m in ms if m[1].get(S) is not None]
                    for r in sorted(seed_rooms):
                        a, b = _flip_at(r)
                        if b is None:
                            continue                   # an arrival, owned by edge_strandings
                        if goal and not (goal & a):
                            continue                   # a dead end, not a softlock
                        for room_d in sorted(set(sites) & a):
                            for inst, acc in sites[room_d]:
                                bad = dom - acc
                                # attainable at THIS flip: S can hold a rejected value here
                                bad_here = {v for v in bad if (r, v) in sst}
                                if not bad_here:
                                    continue
                                # THE REGISTER MUST BE FROZEN PAST THE SEAL -- no reachable write
                                # of ANY value, not merely none of an accepted one. If the sealed
                                # region itself touches the register, its value there is the
                                # region's working state and blaming what you carried across is
                                # wrong attribution -- the same "the flip must be the cause"
                                # conjunct the item rows carry. This is what separates the snake
                                # oil (nothing in act 5 writes 150; what you bring is what you
                                # have) from KQ6's guard choreography (the wedding-sealed castle
                                # keeps toggling its own guard flags) and from LB2's flag 63 (a
                                # set-in-the-inset / cleared-on-return handshake, rewritten by
                                # the very room that reads it).
                                if any(writes.get(q) for q in a) or any(x in a for x, _v in esets):
                                    continue
                                fix_in_b = (any(writes.get(q, set()) & acc for q in b)
                                            or any(x in b and v in acc for x, v in esets))
                                if not fix_in_b:
                                    continue           # never fixable before: not this flip's doing
                                out.append({"pattern": "register-value-at-seal",
                                            "register": R, "value": w,
                                            "reg": S, "bad": sorted(bad_here),
                                            "accepted": sorted(acc),
                                            "demanded_at": [room_d], "via": inst,
                                            "raise_rooms": sorted(q for q in b
                                                                  if writes.get(q, set()) & acc),
                                            "flip_rooms": [r],
                                            "_sealed": frozenset(a)})
        return self._collapse_value_flips(out)

    @staticmethod
    def _collapse_value_flips(rows):
        """One (register, rejected value, sealed region) is one finding -- `_collapse_flips` for
        the register rows, keyed by the demanded register instead of the item."""
        return _collapse_by(rows,
                            lambda r: (r["reg"], tuple(r["bad"]), str(r["register"]),
                                       r.pop("_sealed")),
                            ("flip_rooms", "demanded_at", "raise_rooms"), value_key=repr)

    def resource_exhaustion(self):
        """Items you USE UP rather than throw away -- the fourth store's softlock shape.

        `dangerous_sinks` asks for a PURE sink: a clause that wastes the item and does nothing
        else, like pouring the rejuvenator on a bolt. Breaking the shovel is not that. It happens
        inside a perfectly legitimate dig, so the clause plainly does something, and the purity
        test rejects it -- correctly, for what that test is for.

        The shape here is different: a finite item, degraded ONE-WAY by ordinary use, and still
        required somewhere else. KQ4's shovel snaps after five holes (`Room16:589`,
        `(if (>= global113 5) ((Inv at: 15) loop: 1))`), and it is needed in BOTH the graveyard
        and the crypt -- and global113 is a global, so holes dug in one count against the other.
        Cupid's bow is the same shape with a counter instead of a flag.

        Conjuncts, deliberately the same three `dangerous_sinks` uses, minus purity:
          1. the degradation is one-way (decided upstream, by the discovered value set);
          2. the item is still needed somewhere reachable from the degradation site;
          3. that somewhere is not the site itself -- using it where it is needed is the point.
        """
        spec = _IPROP_SPEC
        oneway = {it for (it, _p), sp in spec.items()
                  if sp.get("counter") or len(sp.get("values", ())) == 1}
        # "still NEEDED" here means the game tests `has: X` at a room the player can still reach --
        # `guard_required` is exactly that, and it is the RIGHT notion for a degraded item (the bow
        # is needed at Lolotte rm82 because rm82 tests has: bow). NOT `real_uses`, which is the
        # narrower "arms something" the SINK test wants; see real_uses on why the two differ.
        uses = self.guard_required
        out = []
        for room, it, prop, val, g, *_rest in getattr(self.em.ts, "item_prop_writes", ()):
            if it not in oneway:
                continue
            # ...and this particular write must BE the degradation. For a counter only the
            # increment degrades -- DebugMenu resets the bow's arrow count to 0, which is the
            # opposite. For a single-valued property the write of that value is the degradation.
            sp = spec.get((it, prop), {})
            if sp.get("counter"):
                if val != "inc":
                    continue
            elif val not in sp.get("values", ()):
                continue
            # room 0 is MAIN -- a scope, not a place. A degradation there can happen wherever the
            # player is standing, so widen it exactly as `_sink_rooms` does for global sinks.
            # KQ4's `Said 'launch'` lives in Main and spends an arrow through `ScriptID 305`, so
            # this is the difference between seeing the bow's real waste and seeing only its two
            # legitimate uses.
            sites = self._sink_rooms({"script": 0, "room": 0}) if room == 0 else [room]
            for site in sites:
                ahead = (uses.get(it, set()) - {site}) & self.rooms_after(site)
                if not ahead:
                    continue
                out.append({"pattern": "resource-exhaustion", "item": it,
                            "item_name": self.g.item_name(it), "property": prop,
                            "at_room": site, "global_scope": room == 0,
                            "still_needed_at": sorted(ahead)})
                if room == 0:
                    break        # one witness room is enough to condemn a global-scope site
        return self._collapse_roaming(out)

    def _roaming_regions(self):
        """`{region-script: frozenset(member rooms)}` for regions that ROAM -- whose script writes
        a global to two or more of its OWN member rooms. That global is the encounter's location
        register (KQ4's regUnicorn sets `global124` to 20/26/27), so the region's rooms are where
        ONE moving thing may appear, not distinct places. The graveyard and crypt (a fixed region)
        write no such register and are correctly NOT roaming, so the shovel -- needed in both -- is
        left as two findings."""
        out = {}
        for rgn, rooms in self.em.region_rooms.items():
            sc = self.em.ir.script(rgn)
            if sc is None:
                continue
            writes = defaultdict(set)
            bodies = [b for o in sc.objects for b in o.methods.values()] + list(sc.procs.values())
            for body in bodies:
                for n in I.walk(body):
                    if n.get("t") == "Assignment":
                        ks = n.get("kids") or []
                        if len(ks) >= 2 and I.is_global(ks[0]) and ks[1].get("t") == "Number":
                            writes[ks[0]["index"]].add(ks[1]["value"])
            if any(len(vals & rooms) >= 2 for vals in writes.values()):
                out[rgn] = frozenset(rooms)
        return out

    def _collapse_roaming(self, rows):
        """Collapse exhaustion rows for one item whose sites are all within a single ROAMING region
        into one finding -- the roaming encounter is one thing, not three. `still_needed_at` drops
        the region's own rooms (they are the same encounter). Non-roaming multi-room findings (the
        shovel across graveyard and crypt) and out-of-region sites (rm1 ANYWHERE, rm82 Lolotte) are
        untouched. See TODO A0n(2): the unicorn ROAMS, its rooms are one shot from three positions."""
        roam = self._roaming_regions()
        if not roam:
            return rows
        by_item = defaultdict(list)
        for r in rows:
            by_item[(r["item"], r["property"])].append(r)
        out = []
        for _key, group in by_item.items():
            used = set()
            for rgn, members in roam.items():
                inside = [r for r in group if r["at_room"] in members and id(r) not in used]
                if len(inside) < 2:
                    continue
                for r in inside:
                    used.add(id(r))
                sites = sorted({r["at_room"] for r in inside})
                need = sorted(set().union(*(set(r["still_needed_at"]) for r in inside)) - members)
                if not need:
                    # every use is INSIDE the one roaming encounter -- degrading the item where it
                    # is used is not a softlock. The per-site rows only looked like findings because
                    # a roaming region attributes the same encounter to each of its rooms, so each
                    # site is "still needed at" the OTHERS; once collapsed they cancel. Drop the
                    # whole group (rows stay consumed, nothing emitted) -- the same net judgement as
                    # `resource_exhaustion`'s `if not ahead: continue`, applied after the merge.
                    continue
                out.append({**inside[0], "at_room": sites[0], "at_rooms": sites,
                            "still_needed_at": need, "roaming_region": rgn})
            out.extend(r for r in group if id(r) not in used)
        return out

    def joint_strandings(self):
        """Softlocks only a JOINT projection can see: an item behind a gate whose two conditions
        live in DIFFERENT registers, so every single-register projection lets it through.

        KQ4's Golden Bridle is the case. It is on Genesta's island (rm43), reachable only through
        the whale, and the whale is one-time. Reaching the island needs BOTH "you arrived from the
        whale or the island" (the previous-room global) AND "the whale is unspent" (a monotone
        flag). The independent projections `_build_product` makes cannot express that conjunction:
        in the previous-room projection the whale edge is free, in the flag projection the island
        edge is free, so each says the island is still reachable and their intersection agrees. Only
        the two TOGETHER show the single window closing behind you.

        And it is a STATE-level property, not a room-level one: you CAN reach the unicorn before the
        whale (flag still 0, island still reachable), so `reobtainable_rooms` -- which collapses to
        rooms -- calls the island reobtainable and reports nothing. The softlock is that you can
        ALSO reach the unicorn AFTER the whale (flag 1) with no bridle and no way back. So the test
        is: is there a reachable joint state at a room where the item is required, from which no
        source of it is reachable, while the goal still is (so it is the ITEM that is missing, not a
        generic dead end)?

        Everything derived: the island's previous-room gate comes from `grid.analyze` (the ocean's
        virtual map summarised to an edge gate); the whale flag is the monotone register gating a
        previous-room the gate names. Runs only when a grid gate exists, so LSL2 (no grid) reports
        nothing and cannot be moved by it."""
        prev_global = self._prev_room_global()
        gates = grid.analyze(self.em, prev_global)
        if not gates:
            return []
        prev_universe = set().union(*(set().union(*ex.values()) for ex in gates.values()))

        # DERIVE the joint monotone flags: registers that gate an in-edge to a previous-room the
        # grid names, and that only ever advance (domain {0} or {0, v}, set by an entry write).
        def edge_eqs(guard):
            out = defaultdict(set)
            atoms = []
            _cmp_atoms(guard, atoms)
            for (r, op, v, pol) in atoms:
                if asserts_eq(op, pol):
                    out[r].add(v)
            return out

        entry_writes = defaultdict(dict)
        for room, vs in self.em.init_writes.items():
            for gi, v in vs.items():
                entry_writes[gi][room] = v

        def monotone(gi):
            dom = self.em.reg_vals.get(gi, set())
            return len(dom) <= 2 and 0 in dom and gi in entry_writes

        flags = set()
        in_eqs = defaultdict(list)                      # (src,dst) -> {reg:{vals}}
        for e in list(self.em.ts.edges) + list(self.em.ts.cs_edges):
            eqs = edge_eqs(e.guard)
            in_eqs[(e.src, e.dst)].append(eqs)
            if e.dst in prev_universe:
                for gi in eqs:
                    if monotone(gi):
                        flags.add(gi)
        flags = sorted(flags)
        if not flags:
            return []

        # --- joint reachability over (room, previous-room-abstract, flag values) ------------
        def succ(state):
            r, pa, fv = state
            out = set()
            for b in self.edges.get(r, ()):
                gate = gates.get(r, {}).get(b)
                if gate is not None and pa not in gate:
                    continue                            # grid gate: wrong entry cell
                blocked_flag = False
                nfv = list(fv)
                for reqs in in_eqs.get((r, b), ()):
                    for i, gi in enumerate(flags):
                        if gi in reqs and fv[i] not in reqs[gi]:
                            blocked_flag = True
                if blocked_flag:
                    continue
                for i, gi in enumerate(flags):
                    w = entry_writes[gi].get(b)
                    if w is not None:
                        nfv[i] = w
                out.add((b, r if r in prev_universe else "o", tuple(nfv)))
            return out

        start = (self.em.cfg.start_room, "o", tuple(0 for _ in flags))
        F = {start}
        q = deque([start])
        rev = defaultdict(set)
        while q:
            u = q.popleft()
            for v in succ(u):
                rev[v].add(u)
                if v not in F:
                    F.add(v)
                    q.append(v)

        def backward(targets):
            seen = set(targets)
            dq = deque(seen)
            while dq:
                u = dq.popleft()
                for w in rev.get(u, ()):
                    if w not in seen:
                        seen.add(w)
                        dq.append(w)
            return seen

        goal = self.goal_rooms_set()
        can_win = backward({s for s in F if s[0] in goal}) if goal else F

        out = []
        for it in sorted(self.required):
            srcs = self.sources.get(it, set())
            need = self.required[it]
            if not srcs or not need:
                continue
            # DELIVERABILITY, not mere obtainability. A source only helps if a need-room is still
            # reachable AFTER visiting it -- otherwise you can obtain the item but never carry it to
            # where it is used. `can_get` demands you can still reach a source FROM WHICH a need is
            # reachable. This is a strict generalisation of the old "can still reach a source":
            #   * Golden_Bridle -- its source (island rm43) can always reach its need (unicorn), so
            #     every source is "good" and the test is unchanged.
            #   * Dead_Fish -- its source (rm95) can NOT reach its need (island rm43) once the
            #     one-time whale is spent, so a fishless island state is correctly stranded. The old
            #     test called rm95 reachable and stopped, missing that you cannot get back to rm43.
            need_reachers = backward({s for s in F if s[0] in need})
            good_sources = {s for s in F if s[0] in srcs} & need_reachers
            can_get = backward(good_sources)
            # a reachable state at a required room, from which no DELIVERABLE source is reachable but
            # the goal still is (so it is the item that is missing, not a dead end).
            stuck = sorted({s[0] for s in F
                            if s[0] in need and s not in can_get and s in can_win})
            if stuck:
                out.append({"pattern": "joint-window-point-of-no-return",
                            "item": it, "item_name": self.g.item_name(it),
                            "source_rooms": sorted(srcs), "flags": flags,
                            "stranded_at": stuck})
        return out

    def _prev_room_global(self):
        if not hasattr(self, "_prg"):
            import extract as X
            self._prg = X.prev_room_global(self.em.ir)
        return self._prg

    def requirement_units(self):
        """Every unit that must be satisfied to win: single items, plus disjunctive GROUPS.

        `edge_strandings` iterates these rather than bare items, so a group inherits all of its
        conjuncts -- irreversibility, non-death-sink, and "still needed past the edge" -- instead
        of needing a parallel frontier walk that would drift from the canonical rule."""
        units = [frozenset({it}) for it in self.required if self.sources.get(it)]
        for R, groups in self.disjunctive_groups().items():
            for G in groups:
                if any(self.sources.get(i) for i in G):
                    units.append(frozenset(G))
        return units

    # ---- mutually EXCLUSIVE items (the other half of disjunctive_groups) ----
    def _or_own_sets(self):
        """room -> {frozenset(items)}: every `(or own(a) own(b) ...)` the model holds.

        Pure OR of positive own()s only. Anything mixed in (a register test, a negation) means
        the disjunction is about something else, so the set is not a statement about items."""
        out = defaultdict(set)

        def collect(g, room):
            def w(x):
                if isinstance(x, list):
                    for y in x:
                        w(y)
                elif isinstance(x, GOr):
                    if all(isinstance(k, Pred) and k.kind == "OWN" for k in x.kids):
                        fs = frozenset(k.var for k in x.kids)
                        if len(fs) > 1:
                            out[room].add(fs)
                    for k in x.kids:
                        w(k)
                elif isinstance(x, GAnd):
                    for k in x.kids:
                        w(k)
                elif isinstance(x, GNot):
                    w(x.kid)
            w(g)

        for info in self.em.machines:
            for _K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                collect(eg, info["room"])
            for _K, paths in info["states"].items():
                for (g, _w, _gg, _c, _tr) in paths:
                    collect(g, info["room"])
        for e in list(self.em.ts.edges) + list(self.em.ts.cs_edges):
            collect(e.guard, e.src)
        for a in self.em.ts.acqs:
            collect(a.guard, a.room)
        return out

    def exchange_slots(self):
        """Item sets at most ONE member of which you can be HOLDING -- `[(frozenset, room)]`.

        The twin of `disjunctive_groups`: that one finds items the game accepts as alternatives to
        each other, this one finds items the game will not let you have at the same time. Both are
        reasons a guard must stop reading a set of item literals as a shopping list.

        KQ6's pawn shop is the case, and it is a chain three trades long: the mechanical
        nightingale buys the flute, the flute buys the tinderbox, the tinderbox buys the paint
        brush. So the brush that paints the castle's magic door IS the nightingale, and a guard on
        that door cannot demand both.

        THREE facts, each already in the model and none sufficient alone:

        1. A MENU -- one `get:` statement whose item is chosen at run time from a fixed set
           (`vocab.item_menus`). One statement moves one item, so the set is a choice. This alone
           does not stop you coming back for a second.
        2. ONE COUNTER -- every member's sole source is the same room, and that room also DROPS
           every member. So there is no other supply, and the supply takes members back. This is
           why "sole" is not a hedge: a member obtainable elsewhere could be held alongside
           another, and the exclusion would be false.
        3. A REFUSAL -- that room guards on `(or own(a) own(b) ...)` over exactly the menu set:
           the shopkeeper declining to deal while you already hold one. This is the coupling that
           1 and 2 cannot supply, and it is only evidence because it names EXACTLY a menu --
           MEASURED, KQ6 has 13 OR-of-own guard sets and 12 of them mean "show him anything"
           (one is eight unrelated items), so the refusal alone would over-group wildly.

        Inert wherever a game has no runtime-selected transfer: LSL2, KQ4 and the Dagger of Amon
        Ra have zero menu sites, so this returns [] and cannot move their output."""
        if hasattr(self, "_slots"):
            return self._slots
        menus = {S for (S, dest) in getattr(self.em.ts, "item_menus", ()) if dest == E.EGO}
        refusals = self._or_own_sets()
        out = []
        for S in sorted(menus, key=sorted):
            rooms = {r for it in S for r in self.sources.get(it, ())}
            if len(rooms) != 1:
                continue                       # not one counter: some member is sourced elsewhere
            R = next(iter(rooms))
            if not all(R in self.drops.get(it, ()) for it in S):
                continue                       # the counter does not take every member back
            if S not in refusals.get(R, ()):
                continue                       # the game never refuses a second one
            out.append((S, R))
        self._slots = out
        return out

    # ---- disjunctive requirement groups -------------------------------------
    def disjunctive_groups(self):
        """room -> {frozenset(items)}: sets that ALTERNATIVELY open the same gate.

        The per-item sweep is blind to these by construction -- no single member is required, so
        every member looks re-obtainable via its sibling. rm81 past the vine chasm is the case:
        `throw ash` (own 30) or `throw sand` (own 31) both arm the exit, and both sources sit
        back in the jungle you can never return to. Losing EITHER is survivable; losing BOTH is
        the softlock."""
        out = defaultdict(set)

        def offer(room, alts):
            uniq = set(alts)
            if len(uniq) < 2 or any(not x for x in uniq):
                return                # one alternative is free -> the gate is not a requirement
            if set.intersection(*map(set, uniq)):
                return                # a common item is needed -> per-item sweep already sees it
            out[room].add(frozenset().union(*uniq))

        for (a, b), variants in self._emeta.items():
            for (req, setv, alts) in variants:
                offer(a, alts)
        # A disjunction does not have to gate a MOVEMENT. SCI1.1's item-use idiom is a `doVerb`
        # switch on the item's message, so rival ways of solving one puzzle are sibling cases that
        # arm the SAME machine -- and that machine's ENTRIES are then exactly the DNF an edge's
        # `alts` would be. KQ6's genie is the case: `rm750`'s doVerb has `(63 put:23 ... 753)` and
        # `(67 put:31 ... 753)`, so `giveGenieMint` has entries [own(mint), own(peppermint)] and
        # the two are ALTERNATIVES -- the walkthroughs agree ("you can also defeat Shamir by giving
        # him some mint leaves"). Read off the entries rather than the edges, this is the same
        # shape and the same rule; reading only edges made every such puzzle look like a
        # conjunction of all its solutions.
        #
        # TWO readings this needs and neither is the obvious one.
        #
        # BY STATE. Entries are alternatives only when they arm the SAME thing, and a machine's
        # entries do not all enter the same state. KQ5's cat has seven entries at the throw state
        # -- one per pool item -- and one at state 0 that requires no item at all; pooled flat,
        # that free entry says "one alternative is free" and the whole disjunction is discarded.
        # Bucketing by target state keeps the throw's alternatives together and lets the free
        # entry speak only for its own state.
        #
        # BY REQUIREMENT, not by mention. An entry's guard carries BOTH the scene's arming
        # condition and the specific act: throwing the Shoe at the cat reads
        # `(has 8 or has 16) and not flag83 and ... and own(8)`. `_own_positive` returns {8, 16}
        # from that -- the arming disjunction hoisted in alongside the throw -- so every entry
        # looks like every other and the shared intersection kills the group. `_own_required` is
        # the reading that already answers the question being asked: an item inside an OR is not
        # required, so this entry demands {8} and its sibling {16}. Measured, the two together
        # derive rm6 -> {Fish, Shoe, Stick, Leg_of_Lamb} and rm12 -> {Shoe, Stick, Leg_of_Lamb} --
        # the asymmetric throwable pool, dog refusing the Fish, exactly as play-tested.
        for info in self.em.machines:
            ents = list(info.get("entries", ())) + list(info.get("init_entries", ()))
            if len(ents) < 2:
                continue
            by_state = defaultdict(list)
            for K, eg in ents:
                by_state[K].append(frozenset(_own_required(eg)))
            for K in sorted(by_state, key=str):
                if len(by_state[K]) >= 2:
                    offer(info["room"], tuple(by_state[K]))
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

    def _market(self):
        """The game's MARKET: who must be paid, out of which one-copy tokens.

        A CONSUMER is a site that permanently absorbs an item and must be satisfied on every
        winning path. A TOKEN is a single-copy item some consumer accepts. KQ5's town is the
        motivating instance and the USER's own framing (2026-08-17b): four merchants and the
        enchanted princess, five one-use tokens, zero slack --

            gypsy   {Needle, Gold_Coin}          -> the Amulet
            tailor  {Needle, Gold_Coin, Heart}   -> the Cloak
            toy maker  + Marionette              -> the Sled
            baker      + Coin                    -> the Pie
            princess {Heart, and nothing else}   -> the Harp

        Returns (consumers, tokens): consumers as a list of dicts with `accept` / `rooms` /
        `dests` / `keys` (the (kind, script, inst) site identities behind it) / `why`, split by
        `constrains` -- a consumer whose accept-set contains a RESTOCKABLE token can never
        starve, so it exerts no pressure on the matching and is kept only so its own payment
        edges read as satisfaction rather than as waste.

        HOW A SITE BECOMES A CONSUMER -- one absorbing-site sweep, then four independent
        derivations of "must be satisfied", each with its corpus witness:

          (a) it SELLS a required product: the machine that takes the fee also performs the
              `get:` of an item `required` somewhere (KQ5's tailor -- `soldCloak` takes
              needle/coin/heart and hands over the Cloak, demanded at rm29/30).
          (b) banning its whole accept-set SEALS a required item, and this site is on the
              BOUNDARY of the sealed region (its rooms are in the lost region or open the door
              into it). The gypsy: without ever holding {3, 11} the walk never reaches rm680,
              the amulet handover, and rm13 is the door. ⛔ The boundary conjunct is the
              attribution: banning a token kills EVERY consumer of it at once, and without the
              conjunct KQ6's gears DEATH TRAP inherited the night mare's skull requirement.
          (c) every acquisition of a required item happens AT THIS SITE and demands one of its
              tokens (KQ5's toy chain: the Marionette is acquired at rm10 and every acquisition
              demands the Spinning_Wheel).
          (c2) an acquisition READS THE OWNER STORE as "paid here or still unspent": the Harp's
              one acquisition guard demands owner(Heart) in {9, 21} -- given to the princess, or
              still at the witch's house -- so a foreign spend (owner := a shop) makes it
              permanently false. The game wrote the market constraint down itself.
          (d) a DEATH FOLD is a consumer: `ownedby_death_folds` rows demand owner(t) == dest on
              the surviving arm -- "the yeti must have been thrown the Pie" (rm35), "the eagle
              must have been fed the Lamb" (rm42). Same read as (c2) with the death standing in
              for the acquisition.

        Sites are merged twice: alternative armings of one purchase (same rooms + accept --
        changePrincess/slowChangePrincess), then machine/fold views of one counter (a shared
        POSITIVE destination with overlapping accepts -- the rm86 fold and the rm6 cat handler
        are one bank). ⛔ -1/limbo is not a counter and never merges: "everything ever destroyed"
        is not a consumer, and merging on it swallowed KQ6's `useBrick` whole."""
        if getattr(self, "_market_cache", None) is not None:
            return self._market_cache
        pockets = self._single_copy_pockets()
        single = lambda t: self.destroyed_is_permanent(t) or t in pockets
        lost = lambda it, dest: dest != E.EGO and (
            dest in self.NOWHERE or self.drop_is_permanent(it, dest) or it in pockets)
        mg = getattr(self.em, "machine_gets", set())

        raw = {}
        for info in self.em.machines:
            ents = list(info.get("entries", ())) + list(info.get("init_entries", ()))
            spend = {it for (it, dest, g) in info.get("moves", ()) if lost(it, dest)}
            if not spend or not ents:
                continue
            accept = set()
            for K, eg in ents:
                accept |= _own_required(eg)
            if not (accept & spend):
                continue
            c = raw.setdefault(("m", info["script"], info["inst"]),
                               {"accept": set(), "rooms": set(), "products": set(),
                                "dests": set(), "fold": None})
            c["accept"] |= accept
            c["rooms"].add(info["room"])
            c["dests"] |= {d for (it, d, g) in info.get("moves", ()) if d != E.EGO}
            c["products"] |= {it for (r, i, it) in mg
                              if r == info["room"] and i == info["inst"]}
        for room, script, it, g, dest in self.em.handler_drops:
            if lost(it, dest):
                c = raw.setdefault(("h", script, dest),
                                   {"accept": set(), "rooms": set(), "products": set(),
                                    "dests": {dest}, "fold": None})
                c["accept"].add(it)
                c["rooms"].add(room)
        for r in self.ownedby_death_folds():
            by_dest = defaultdict(set)
            for (t, d) in r.get("demand_group", ()):
                by_dest[d].add(t)
            for d, ts in by_dest.items():
                c = raw.setdefault(("f", d, None),
                                   {"accept": set(), "rooms": set(), "products": set(),
                                    "dests": {d}, "fold": None})
                c["accept"] |= ts
                c["rooms"].add(r["need_room"])
                c["fold"] = "the rm%s death fold demands owner in %s" % (
                    r["need_room"], sorted(ts))

        merged = {}
        for key, c in sorted(raw.items(), key=str):
            sig = (frozenset(c["rooms"]), frozenset(c["accept"]))
            if sig in merged:
                merged[sig]["keys"].append(key)
                for f in ("products", "dests"):
                    merged[sig][f] |= c[f]
                merged[sig]["fold"] = merged[sig]["fold"] or c["fold"]
            else:
                merged[sig] = {**c, "keys": [key]}
        by_dest, out = {}, []
        for sig, c in sorted(merged.items(), key=str):
            real = sorted(d for d in c["dests"] if isinstance(d, int) and d > 0)
            hit = next((by_dest[d] for d in real
                        if d in by_dest and (by_dest[d]["accept"] & c["accept"])), None)
            if hit is not None:
                for f in ("accept", "rooms", "products", "dests"):
                    hit[f] |= c[f]
                hit["keys"] += c["keys"]
                hit["fold"] = hit["fold"] or c["fold"]
            else:
                out.append(c)
            for d in real:
                by_dest.setdefault(d, hit if hit is not None else c)

        # ⭐ SCARCITY IS CONSUMER-RELATIVE, and this is what closed the lamb red -- by refuting
        # its stated cure. The red said the eagle's consumer is auto-satisfiable "because the
        # lamb reads restockable (the cupboard pickup is not owner-gated in the model)", and
        # the fix it prescribed was at the acquisition read. Both halves miss the true fact:
        # the eagle's fold is at rm42, PAST THE ROC's point of no return, and
        # `reobtainable_rooms(19)` -- the same gate-aware walk `analyze`'s carry-across row
        # already rests on -- excludes rm42. Even a cupboard that restocked lambs forever
        # could not supply the eagle. So a token waives a consumer's pressure only when it is
        # BOTH re-suppliable in the model AND re-suppliable FROM THE CONSUMER'S OWN ROOMS;
        # the cat's bank (rm6/rm86, in town) keeps its waiver and the pool stays safe, the
        # eagle loses it and starts to constrain.
        consumers = []
        for c in out:
            why = self._required_consumer(c)
            if why is None:
                continue
            restock = sorted(t for t in c["accept"] if not single(t)
                             and (c["rooms"] & self.reobtainable_rooms(t)))
            c["constrains"] = not restock
            c["why"] = why if not restock else why + " [auto-satisfiable: %s restock]" % (
                [self.g.item_name(t) for t in restock])
            consumers.append(c)
        tokens = sorted({t for c in consumers if c["constrains"] for t in c["accept"]})
        self._market_cache = (consumers, tokens)
        return self._market_cache

    def _single_copy_pockets(self):
        """Items whose ONE copy is one-visit-pocketed: the second way a world holds one of a
        thing. `drop_is_permanent` asks the owner graph, and for KQ5's Gold_Coin it honestly
        answers NO -- `rm018::init` re-inits the coin on every entry and nothing gates
        `getCoin`. What makes yours the only one is that the temple door already ate the Staff:
        `toll_strandings`' one-visit-toll-pocket rows, which is the only store that knows."""
        if getattr(self, "_pocketed", None) is None:
            self._pocketed = frozenset(t["item"] for t in self.toll_strandings()
                                       if t.get("pattern") == "one-visit-toll-pocket")
        return self._pocketed

    def _required_consumer(self, c):
        """Why this absorbing site must be satisfied on every winning path, or None."""
        A = frozenset(c["accept"])
        if c.get("fold"):
            return "(d) " + c["fold"]
        for P in sorted(c["products"]):
            if self.required.get(P) and self.sources.get(P):
                return "(a) sells %s" % self.g.item_name(P)
        for P in sorted(self.required):
            if P in A or not (self.sources.get(P, set()) & self.reach_rooms):
                continue
            dem = []
            for (g, r) in self._acq_guards(P):
                dem.append((r, set(_own_required([g] if g is not None
                                                 and not isinstance(g, list) else (g or [])))))
            dem = [d for d in dem if d[0] in self.reach_rooms]
            if dem and all(r in c["rooms"] and (d & A) for (r, d) in dem):
                return "(c) every acquisition of %s is here and demands the tokens" % (
                    self.g.item_name(P))
            for t in sorted(A):
                good = {d for d in c["dests"] if isinstance(d, int)} | \
                    self.sources.get(t, set())
                ok = []
                for (g, r) in self._acq_guards(P):
                    if g is None:
                        ok = []
                        break
                    V = _loc_values(g, t, r)
                    if not V or not (V & c["dests"]) or not (V <= good):
                        ok = []
                        break
                    ok.append(sorted(V, key=str))
                if ok:
                    return "(c2) %s's acquisition reads owner(%s) in %s" % (
                        self.g.item_name(P), self.g.item_name(t), ok[0])
        rw = self._reach_without(A)
        for P in sorted(self.required):
            srcs = self.sources.get(P, set())
            if P in A or not (srcs & self.reach_rooms):
                continue
            if not (srcs & rw):
                lost_rooms = (self.reach_rooms - rw) | srcs
                boundary = {a for (a, b) in self._emeta if b in lost_rooms and a in rw}
                if c["rooms"] & (lost_rooms | boundary):
                    return "(b) banning the slot seals %s; this site is the boundary" % (
                        self.g.item_name(P))
        return None

    def market_squeezes(self):
        """A payment that leaves some merchant UNPAYABLE -- the market squeeze.

        THE SHAPE, in the USER's framing (2026-08-17b): *"the 3 vendors and the gypsy each
        accepting some payments that can starve other merchants, when everything you get from
        the merchants is required."* No single-spend detector can state this -- every token is
        excused by its siblings at its own slot -- and no per-group detector states it either
        without re-deriving half the market. The whole question is one matching: the game is
        winnable iff every required consumer can be assigned a DISTINCT token it accepts, and

            a spend is FATAL iff the residual market has no such assignment.

        Residual: spending token t at a consumer that accepts it satisfies that consumer (remove
        both); spending t anywhere else -- a merchant that merely tolerates it, an EAT verb --
        removes t alone. First-order from the fresh market, which is exactly the guard question:
        with the Cloak, the Harp and the pies all required, KQ5's seven fatal payments are fatal
        from the very first token, not only after an earlier mistake.

        ⛔ A spend you do not SURVIVE is excluded (`fatal_uses` sites): there is no surviving
        world to starve, and the harm is already stated -- and remedied -- as a fatal use. KQ6's
        skull-into-the-gears is a death, not a payment.

        MEASURED 2026-08-17b: LSL2 0, KQ4 0, KQ6 0, LB2 0, KQ5 9 -- the squeeze (needle/gold
        coin to the toy maker or baker starves the gypsy-tailor-princess triangle), the Heart at
        any shop (starves the princess, the Harp's sole source), and the pie eaten or fed to the
        eagle (starves the yeti, riding the rm35 fold). Every USER-ruled safe play stays silent:
        needle->gypsy, coin->tailor, marionette->toy maker, heart->princess, the whole throwable
        pool.

        RE-MEASURED 2026-08-17b WITH CONSUMER-RELATIVE SCARCITY (see `_market`): +3 Leg_of_Lamb
        rows -- eaten (Main's second bite), thrown at the cat, thrown at the dog -- each
        starving the eagle's rm42 fold, whose surviving arm demands owner(19) == 34 and which
        sits past the roc where no lamb can be re-fetched. USER-ruled real ("you need both the
        pie and the lamb"); the cat and dog throws are oracle §1a's long-standing TRUE softlock,
        caught here for the first time. The corpus stays 0 everywhere else."""
        consumers, tokens = self._market()
        cons = [c for c in consumers if c["constrains"]]

        def pm(cs, toks):
            adj = {i: sorted(c["accept"] & set(toks)) for i, c in enumerate(cs)}
            return _saturating_matching(list(range(len(cs))), adj)

        if pm(cons, tokens) is None:
            # the fresh market is already unsolvable: that is a defect in THIS derivation (an
            # over-included consumer), never a finding. Loud, and no rows.
            _degraded_model("market_squeezes: no baseline matching -- consumer derivation "
                            "over-includes; emitting nothing")
            return []
        fatal_sites = {(f["room"], f["machine"]) for f in self.fatal_uses()}
        edges = [(it, room, script, None, dest)
                 for room, script, it, g, dest in self.em.handler_drops]
        edges += [(it, room, script, inst, dest)
                  for room, script, it, g, dest, inst in self.em.machine_moves]
        # An edge is a LOSS worth testing when the token is gone for good (destroyed, kept by
        # its taker, or pocket-sealed) -- OR when some constraining consumer could never
        # re-supply it anyway: the eagle cannot tell a permanently spent lamb from one lying
        # in a town it can never walk back to, and neither kind returns to rm42.
        starved_for = {t for c in cons for t in c["accept"]
                       if not (c["rooms"] & self.reobtainable_rooms(t))}
        rows, seen = [], set()
        for (it, room, script, inst, dest) in sorted(edges, key=str):
            if it not in tokens or (room, inst) in fatal_sites:
                continue
            if dest == E.EGO:
                continue
            if not (dest in self.NOWHERE or self.drop_is_permanent(it, dest)
                    or it in self._single_copy_pockets() or it in starved_for):
                continue
            ekey = ("m", script, inst) if inst is not None else ("h", script, dest)
            # ...and a spend SATISFIES a consumer by identity (its own arming took the fee) or
            # by DESTINATION: a fold consumer demands `owner(t) == dest`, and an edge that puts
            # t exactly there has just established it -- feeding the lamb TO THE EAGLE is the
            # solution, whatever machine performed it.
            sat = [c for c in consumers
                   if ekey in c["keys"] or (dest in c["dests"] and it in c["accept"])]
            rest = [c for c in cons if c not in sat]
            toks = [t for t in tokens if t != it]
            if pm(rest, toks) is not None:
                continue
            sig = (it, script, inst)
            if sig in seen:
                continue
            seen.add(sig)
            starved = [c for c in rest
                       if pm([x for x in rest if x is not c], toks) is not None]
            rows.append({
                "pattern": "market-squeeze", "item": it,
                "item_name": self.g.item_name(it),
                "at_room": room, "script": script, "inst": inst,
                "pays": sorted(str(k[2] if k[2] is not None else k[1])
                               for c in sat for k in c["keys"])[:3],
                "starves": sorted({r for c in starved for r in c["rooms"]}),
                "starved_accepts": sorted({t for c in starved for t in c["accept"]}),
            })
        return rows

    def free_running_traps(self):
        """Free-running POINT-OF-NO-RETURN registers -- softlock class 2, the register-flip trap.

        A register the player CANNOT keep at a safe value: written pervasively by the always-live
        Game loop (KQ4's `KQ4::newRoom` sets global100:=1 -- nightfall -- in ~every room, driven by
        the wall clock), whose SAFE value (0, the start value) is restored in only a FEW rooms.
        Night falls everywhere and lifts nowhere but dawn (rm82, itself gated behind Lolotte's
        death). That asymmetry -- TRAP value pervasive, RESET localized -- IS the point-of-no-return
        signature, and it is exactly what separates KQ4's g100 from LSL2's g127: g127 is also
        Game-written across ~100 rooms, but its SAFE value 0 is the pervasive one and the trap 1 is
        written in just rm34/35 -- reset everywhere, so it can never trap you. Derived, not fitted:
        the rule reads the shape (which value is pervasive vs. localized), and LSL2's g127 fails it.

        Returns {R: {trap, safe, reset_rooms, set_in}}. This only CLASSIFIES the register; whether
        an item is actually sealed by the flip is a separate stranding query (which still needs the
        reset guard recovered -- the dawn write's Lolotte-dead condition -- and a joint over
        (R x possession), the remaining Phase-1b build)."""
        out = {}
        SAFE = 0     # SCI globals default-init to 0 and the opmodel seeds every register {0}; that
                     # start value is the SAFE baseline. Being FORCED to it is never a trap. (A game
                     # whose register has a non-zero start would need that init read from Main -- a
                     # documented limit, not a silent fudge.)
        for R in self.regs:
            loop_vals = {v for (room, script, gi, v, g) in self.em.handler_writes
                         if gi == R and script in self.GLOBAL_SCRIPTS}   # the always-live forcing
            if not loop_vals:
                continue                        # not written by the Game loop (script 0), so no trap
            byval = defaultdict(set)
            for r, vs in self._inroom.get(R, {}).items():
                for v in vs:
                    byval[v].add(r)
            # The trap value is one the Game loop FORCES that is NOT the safe baseline, and that
            # DOMINATES the room set -- so the reset to safety is the minority, i.e. localized. That
            # shape is what separates KQ4 g100 (loop forces 1=night, reset 0=day confined to rm82)
            # from LSL2 g127 (loop forces 0=safe -- forcing you to stay safe is no trap). The old
            # code baked reset<=3 and trap>=10x; here it is a derived dominance, no magic constant.
            for T in sorted(loop_vals):
                if T == SAFE:
                    continue
                if T in getattr(self, "_death_values", {}).get(R, ()):
                    # ⭐ THE DEATH SIGNAL IS NOT A PLOT CLOCK (2026-08-09). A value that MEANS "you
                    # are dead" cannot also be an adversarial state you get stranded in: you do not
                    # recover from death, you restore. KQ6's flag 44 (reg216) is set by the death
                    # procedure itself, and `death_traps` then makes every exit from the death room
                    # require `216 == 0` -- which is exactly the "door gated on the trap's safe
                    # value" shape `register_flip_strandings` hunts for. It produced a row blaming
                    # flag 44 for sealing the `gauntlet`: a REDUNDANT REASON on an already-true
                    # verdict (the gauntlet is genuinely caught by `toll_strandings`, the
                    # deadMansCoin pocket carry-in) with an unplaceable `applied=False` spec. Wrong
                    # reasons on right answers are invisible to a name-scored oracle, which is how
                    # it reached a committed baseline.
                    #
                    # The dominance test below did not stop it because `1 > 0` passes VACUOUSLY:
                    # reg216 is written in one place and reset nowhere. That is a real second
                    # weakness, but it is NOT this defect -- flag 44 would still not be a plot
                    # clock if the game set it in fifty rooms -- so it is left alone rather than
                    # cured with a threshold. Measured: KQ4's nightfall g100 (set_in=111, the
                    # play-validated positive) has NO death values and is untouched; LSL2 has no
                    # traps; LB2's 18 trap registers name none.
                    #
                    # (RE-MEASURED 2026-08-14: the set this reads is now `{173: {0}}` -- flag 1,
                    # rm411's sole survival row -- not flag 44's reg216, which no longer produces
                    # a single-row single-register trap. The rule and its direction are unchanged;
                    # only the instance moved. See `_apply_death_traps` for the measurement.)
                    continue
                forced = byval.get(T, set())
                reset = set().union(*(byval[v] for v in byval if v != T)) if byval else set()
                if forced and len(forced) > len(reset):
                    out[R] = {"trap": T, "safe": SAFE, "reset_rooms": sorted(reset),
                              "set_in": len(forced)}
                    break
        return out

    def register_flip_strandings(self):
        """Items sealed by a free-running TRAP register's flip -- softlock class 2.

        For each classified trap R (`free_running_traps`: safe value 0, an adversarial value written
        pervasively by the Game loop, reset confined to a few rooms), a door gated on `R == safe`
        SHUTS when the flip fires -- and the player cannot prevent the flip (it is the wall clock,
        not a choice). So there is a reachable state, R flipped and the item not yet taken, from
        which the item -- now behind a closed door whose reset is localized and downstream -- is no
        longer obtainable. By the one rule (is what you need still obtainable from here?) that is a
        softlock. KQ4: night (g100) shuts the dwarves' door rm22->54 (Diamond_Pouch) and the
        shanty door rm7->42 (Fishing_Pole); dawn is only at rm82, behind Lolotte's death.

        We flag an item only when EVERY one of its sources sits behind a trap-gated door (removing
        those doors makes the source unreachable) -- otherwise there is a trap-free way in and no
        seal. LSL2 has no trap register, so this returns [] and cannot move its golden."""
        traps = self.free_running_traps()
        if not traps:
            return []
        out = []
        for R, info in sorted(traps.items()):
            safe = info["safe"]
            doors = {(a, b) for (a, b), metas in self._emeta.items()
                     for (req, sets, alts) in metas if req.get(R) == {safe}}
            if not doors:
                continue
            # rooms still reachable if every trap-gated door is shut (the flipped world)
            shut = {x: (set(y) - {b for (a, b) in doors if a == x}) for x, y in self.edges.items()}
            reach_shut = reachable(shut, {self.em.cfg.start_room})
            for it in sorted(self.required):
                srcs = self.sources.get(it, set())
                if not srcs or (srcs & reach_shut):
                    continue                 # no source, or a source reachable without the door
                out.append({"pattern": "free-running-trap-seal", "item": it,
                            "item_name": self.g.item_name(it), "register": R,
                            "trap": info["trap"], "reset_rooms": info["reset_rooms"],
                            "source_rooms": sorted(srcs), "doors": sorted(doors)})
        return out

    def _uses_in(self, item, rooms):
        """Everything using `item` in `rooms` does: `({(reg, value)}, items moved, exits)`.

        A use is a machine those rooms arm whose ENTRY presupposes the item -- `_own_positive`,
        the same reading `_build_product` prices a write with -- plus the handler forms of the
        same act. Machine BODIES are read whole: a cutscene decides at its entry and pays off
        several states later."""
        key = (item, frozenset(rooms))
        cached = getattr(self, "_uses", None)
        if cached is None:
            cached = self._uses = {}
        if key in cached:
            return cached[key]
        writes, moved, exits = set(), set(), False
        for info in self.em.machines:
            if info["room"] not in rooms:
                continue
            own = set()
            for _K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                own |= _own_positive(eg)
            if item not in own:
                continue
            moved |= set(info.get("drops", ()))
            for _K, paths in info["states"].items():
                for (_g, w, _gg, _c, tr) in paths:
                    writes |= {(gi, v) for (gi, v) in w}
                    if tr and tr[0] == "EXIT":
                        exits = True
        for a in self.em.ts.acqs:
            if a.room in rooms and item in _own_positive(a.guard):
                moved.add(a.item)
        for room, _script, gi, v, g in self.em.handler_writes:
            if room in rooms and item in _own_positive(g):
                writes.add((gi, v))
        for room, _script, it, g in self.em.handler_gets:
            if room in rooms and item in _own_positive(g):
                moved.add(it)
        for room, _script, it, g, _dest in getattr(self.em, "handler_drops", ()):
            if room in rooms and item in _own_positive(g):
                moved.add(it)
        cached[key] = (writes, moved, exits)
        return cached[key]

    def _use_escapes(self, item, pocket):
        """Does using `item` inside `pocket` LEAVE A TRACE, or is it only a joke?

        The conjunct that separates a carry-in from a souvenir. A one-visit pocket is full of
        things the game lets you do with what you brought, and some of them are flavour: KQ6 lets
        you play Charon the flute and the mechanical nightingale while you wait for the ferry, and
        both scripts write NOTHING, move nothing and go nowhere. Demanding those at the entrance
        would be inventing a requirement out of a joke.

        Three traces, and the test is that there is one -- not where it ends up:
          1. it writes a register;
          2. it moves an item that is needed outside the pocket;
          3. it is a CROSSING. Paying Charon and holding up the mirror go somewhere, and movement
             you must make is not optional.

        ⚠️ (1) USED TO ASK WHERE THE REGISTER IS READ, and that qualifier was FITTED TO A WRONG
        ANSWER. It was justified by KQ6's gauntlet -- thrown down at the Lord of the Dead, writing
        a register only rm690 itself reads -- which I read out of the scripts as flavour worth two
        points. The user tested it: **you need the gauntlet, because without it the game refuses to
        show Death the mirror.** `lord::doVerb 13` is `(if local0 <brush-off> else holdUpMirror)`,
        `introScript` sets `local0 := 1` before handing you control, and the ONLY thing that clears
        it while you still have control is `issueChallenge` -- the gauntlet. So the challenge is
        the precondition of the pocket's only exit.

        We keep the gauntlet now, but on trace (1) -- an INCIDENTAL register write that merely
        picks which death message you get -- and not on the reason the game actually has. The real
        link runs through a room LOCAL, which we do not model at all; it is the third recorded
        instance of that gap (`liftTapestry`'s L1 on the catacombs latch, `huntersLamp`'s rm520
        approach-idiom `doit`). `test_toll` carries a RED assertion naming it so the verdict cannot
        look better founded than it is."""
        writes, moved, exits = self._uses_in(item, pocket)
        if exits:
            return "it is a crossing you cannot make later"
        if writes:
            R, v = min(writes)
            return f"it sets reg{R}:={v}, and that write outlives the use"
        for it in sorted(moved):
            if self.required.get(it, set()) - pocket:
                return f"it moves {self.g.item_name(it)}, which is needed outside"
        return None

    def _pocket_leavable(self, pocket, Y):
        """Can you exit `pocket` to an outside room WITHOUT owning Y? False only if every
        pocket-exit edge REQUIRES Y in all its alternatives (Y forced, so not missable)."""
        for p in pocket:
            for q in self.edges.get(p, set()):
                if q in pocket:
                    continue
                metas = self._emeta.get((p, q))
                if not metas:
                    return True                  # ungated exit -> leavable
                if any(any(Y not in alt for alt in alts) for (req, sets, alts) in metas):
                    return True                  # some alternative needs no Y
        return False

    def toll_strandings(self):
        """One-visit-pocket strandings -- the consumed-gate class (softlock class 4).

        An edge a->b whose LONE item-gate X is SPENT crossing it (X dropped or one-way placed at a,
        and no longer re-acquirable from a) is a TOLL: it can be paid once. Cutting the toll edge
        leaves a POCKET of rooms reachable ONLY through it (b is dominated by the toll -- a pure
        room-graph fact, so the desert grid that walls off the gate-aware projections cannot
        confound it). A required item whose every source sits in that pocket, still needed outside
        it, and leavable without taking it, is stranded: you can walk out empty-handed and the toll
        is already spent.

        KQ5's temple: the Staff(7) breaks opening rm18 (`put: 7 214`), so rm18 is a one-visit
        pocket and the Brass_Bottle(6)/Gold_Coin(11) inside become unreachable once you leave
        without them. The reobtainable(X) filter keeps this silent on LSL2/KQ4 -- every candidate
        gate item there (Vine, Ashes, Sand, Lottery_Ticket, Talisman) is re-obtainable, so neither
        game has a one-way toll and this returns [] for both."""
        placed = getattr(self.em.ts, "placed", {})
        start = self.em.cfg.start_room
        full = self.reach_rooms
        out, seen = [], set()
        for (a, b), metas in sorted(self._emeta.items()):
            if a not in full:
                continue
            gates = {next(iter(alt)) for (req, sets, alts) in metas
                     for alt in alts if len(alt) == 1}
            # A toll need not be an ITEM. The same "you may cross this once" shape arises when the
            # gate is a set-once FLAG the far side raises: KQ6's realm of the dead is entered only
            # while flag 15 is clear, and arriving in rm600 sets flag 15 and nothing ever clears
            # it. Item-spent and flag-raised are two spellings of one fact, so they share the
            # pocket logic below rather than getting a second detector.
            inroom = getattr(self, "_inroom", {})
            flag_tolls = sorted(_selfsealing_flags(metas, inroom))
            for X in sorted(gates) + [("flag", F) for F in flag_tolls]:
                if isinstance(X, tuple):
                    pass                         # a flag toll is one-time by construction
                else:
                    if not self.sources.get(X):
                        continue                 # A TOLL YOU NEVER PICKED UP IS NOT A TOLL. An item
                        #   with no source anywhere is a CAPTURE GAP, not a one-way spend -- KQ6's
                        #   pawn-shop trades have no `get:` at all -- and reading one as a paid toll
                        #   invents a sealed pocket around whatever lies past the edge that mentions
                        #   it. Everything downstream (the carry-out rows, and the carry-in rows
                        #   below) is then reasoning about a room the player can walk back into.
                    spent = a in self.drops.get(X, set()) or a in placed.get(X, set())
                    if not spent or (a in self.reobtainable_rooms(X)
                                     and not _spend_exhausts_sources(self, X, a)):
                        continue                 # not spent here, or spent but re-gettable -> benign
                cut = {u: (v - {b} if u == a else v) for u, v in self.edges.items()}
                pocket = full - reachable(cut, {start})
                if b not in pocket:
                    continue                     # b reachable another way -> not a sealed pocket
                if isinstance(X, tuple) and not _flag_set_inside(X[1], pocket, inroom):
                    continue                     # the flag is not raised in there -> re-enterable
                for Y in sorted(self.required):
                    if Y == X:
                        continue
                    srcs = self.sources.get(Y, set())
                    if not srcs or not (srcs <= pocket):
                        continue                 # obtainable outside the pocket
                    if not (self.required.get(Y, set()) - pocket):
                        continue                 # only needed inside -> taking it there suffices
                    if not self._pocket_leavable(pocket, Y):
                        continue                 # every exit demands Y -> forced, not missable
                    k = (Y, a, b)
                    if k in seen:
                        continue
                    seen.add(k)
                    out.append({"pattern": "one-visit-toll-pocket", "item": Y,
                                "item_name": self.g.item_name(Y),
                                "toll_item": None if isinstance(X, tuple) else X,
                                "toll_item_name": (f"flag{X[1]}" if isinstance(X, tuple)
                                                   else self.g.item_name(X)),
                                # the sealing register, exactly as the carry-in rows carry it: a
                                # consumer judging the pocket's EXITS (the carry-out placement)
                                # needs the seal in its joint or every walk re-enters freely.
                                "toll_reg": X[1] if isinstance(X, tuple) else None,
                                "toll_edge": [a, b], "pocket": sorted(pocket),
                                "source_rooms": sorted(srcs)})
                # ...AND THE OTHER DIRECTION, which is the same fact read the other way round. A
                # pocket you may enter once strands what you obtain inside and need outside -- and
                # equally what you must USE inside and can only obtain OUTSIDE. Every conjunct
                # below is the mirror of one above; the fourth has no mirror because it has no
                # counterpart in the carry-out case, where merely HOLDING the item on the way out
                # is the whole requirement.
                #
                # KQ6's teacup is the case. Its only source is a room outside the Realm of the
                # Dead; the Styx water is drawn at rm660, inside; the Realm admits you once
                # (flag 15, raised on arrival, never cleared); and you may walk in without it. Come
                # out with an empty cup and the magic paint can never be mixed.
                for Y in sorted(self.required):
                    if Y == X or not (self.required.get(Y, set()) & pocket):
                        continue                 # not used in there
                    srcs = self.sources.get(Y, set())
                    if not srcs or (srcs & pocket):
                        continue                 # no source, or obtainable INSIDE -> fetch it there
                    if Y in self.edge_demands(a, b):
                        continue                 # the crossing itself demands it -> forced, not
                                                 # missable (the mirror of `_pocket_leavable`)
                    why = self._use_escapes(Y, pocket)
                    if not why:
                        continue                 # what it does in there, the pocket keeps
                    k = ("in", Y, a, b)
                    if k in seen:
                        continue
                    seen.add(k)
                    out.append({"pattern": "one-visit-pocket-carry-in", "item": Y,
                                "item_name": self.g.item_name(Y),
                                "toll_item": None if isinstance(X, tuple) else X,
                                "toll_item_name": (f"flag{X[1]}" if isinstance(X, tuple)
                                                   else self.g.item_name(X)),
                                # the REGISTER that seals the pocket, kept as a number and not only
                                # as a label: it is what a consumer must put in a joint projection
                                # to see the pocket as one-visit at all. Without it every walk
                                # cheerfully re-enters and concludes you can go back for anything.
                                "toll_reg": X[1] if isinstance(X, tuple) else None,
                                "toll_edge": [a, b], "pocket": sorted(pocket),
                                "source_rooms": sorted(srcs),
                                "need_rooms": sorted(self.required[Y] & pocket),
                                "why": why})
        return out


def _selfsealing_flags(metas, inroom):
    """Registers this edge needs at 0 which the FAR SIDE then raises for good.

    The self-disabling one-visit entry: you may cross while F is clear, and crossing leads
    somewhere that sets F and nothing ever clears it, so the crossing happens exactly once. Only
    registers we synthesized from a flag store qualify -- their domain really is {0,1}, so "needs
    0" and "raised to 1" are the same axis -- and only if nothing writes 0 anywhere, which is what
    makes it permanent rather than a toggle."""
    out = set()
    for (req, sets, alts) in metas:
        for R, vals in req.items():
            if vals != {0} or R not in vocab.BOOL_GLOBALS:
                continue
            writes = {v for rooms in (inroom.get(R) or {}).values() for v in rooms}
            if 0 in writes or 1 not in writes:
                continue                         # cleared somewhere, or never raised -> no seal
            out.add(R)
    return out


def _flag_set_inside(R, pocket, inroom):
    """Is R raised somewhere in the pocket -- i.e. does going in seal the way back?"""
    return any(1 in vs for room, vs in (inroom.get(R) or {}).items() if room in pocket)


_MODEL_MEMO = {}                       # in-process: key -> built model


def _model_cache_key(cfg, ir_path, here=None):
    """Identity of a BUILT MODEL: the config that shapes it, the IR it is built from, and the
    code that builds it.

    The code hash is the load-bearing part. A cached model is only sound while every module
    that participates in building or querying it is byte-identical to the one that produced
    the pickle -- otherwise an edit to a detector would be silently answered from a model built
    by the previous version, and the suite would gate on a stale analysis. So every non-test
    source file in this directory goes into the hash: touching any of them misses the cache and
    rebuilds. (Test files are excluded on purpose -- editing a test must not throw away the
    models it is about to read.)

    `here` names the directory to hash, and exists so the "a source change misses the cache"
    property can be MEASURED without mutating the live one (2026-08-20 fourth review, P7). The
    test that proves it used to write a `.py` into this package's own directory, which changes
    every game's cache key for as long as it is there, and leaves a stray module behind if the
    process dies between the write and the cleanup. Callers leave it None."""
    import hashlib
    here = here or os.path.dirname(os.path.abspath(__file__))
    h = hashlib.sha1()
    h.update(repr((cfg.name, cfg.src_dir, cfg.ir_path, cfg.resource_dir, cfg.start_room,
                   sorted(cfg.goal_rooms), tuple(cfg.death_signal),
                   sorted(cfg.debug_globals), repr(cfg.promote_registers))).encode())
    try:
        st = os.stat(ir_path)
        h.update(("%d:%d" % (st.st_size, st.st_mtime_ns)).encode())
    except OSError:
        return None
    for fn in sorted(os.listdir(here)):
        if fn.endswith(".py") and not fn.startswith("test_"):
            with open(os.path.join(here, fn), "rb") as f:
                h.update(f.read())
    return h.hexdigest()


# Module-level state a BUILD installs and a QUERY later reads. It must travel with a cached
# model or the model answers against whichever game was loaded last. This list is the cache's
# one fragile seam -- it is a hand-maintained mirror of every `global` a build assigns -- so
# `test_model_cache.py` pins it by diffing a cache-hit's state against a fresh build's, which
# is what caught `_IPROP_SPEC` missing here (four KQ4 resource-exhaustion checks went empty).
# Derived from `grep -rn "^\s*global [_A-Z]" src/`: extract's vocabulary (one `global`
# statement, seven names), extract's doVerb parameter, and missability's item-property spec.
_BUILD_STATE = (("extract", ("_VOCAB", "_IPROPS", "_EGO", "_CURROOM", "_ITEM_MSG", "_ONEOF",
                             "_MENUS", "_VERB_PARAM")),
                ("missability", ("_IPROP_SPEC",)))


def _vocab_state():
    """The module-level state a build INSTALLS, so a cached model can restore it.

    Several query paths read this state at ANSWER time -- `guards.sink_survival_carryins`
    reads `extract._CURROOM`, `resource_exhaustion` reads `_IPROP_SPEC` -- so a model handed
    back without it answers against another game. `vocab.BOOL_GLOBALS` is snapshotted rather
    than re-derived because it is a byproduct of the lowering passes, and restoring it also
    fixes a bug that predates caching: it only ever GREW, so loading LSL2 after KQ6 left
    KQ6's synthetic registers in the set (measured elsewhere at 57 KQ4 / 28 LSL2 registers
    wrongly marked boolean)."""
    import importlib
    return ({mod: {k: getattr(importlib.import_module(mod), k, None) for k in names}
             for mod, names in _BUILD_STATE},
            set(vocab.BOOL_GLOBALS))


def _restore_vocab_state(state):
    import importlib
    mods, bools = state
    for mod, names in mods.items():
        m = importlib.import_module(mod)
        for k, v in names.items():
            setattr(m, k, v)
    vocab.BOOL_GLOBALS.clear()
    vocab.BOOL_GLOBALS.update(bools)


class DeathSignal:
    """`(global, value)` -> "is this write a death", as a PICKLABLE callable.

    A closure would be the obvious spelling and was the original one, but the emitter and the
    MachineBuilder both hold this object, so a local lambda made the entire analysis model
    unpicklable -- and that is what blocked caching a built model between callers. `value`
    None means "any non-zero" (KQ4's global127 is a plain boolean set in 37 death rooms;
    LSL2 raises death as the magic constant `gCurrentStatus == 1001`)."""
    __slots__ = ("gi", "val")

    def __init__(self, gi, val):
        self.gi, self.val = gi, val

    def __call__(self, gi, v):
        return gi == self.gi and (v == self.val if self.val is not None else bool(v))

    def __eq__(self, other):
        return (isinstance(other, DeathSignal)
                and (self.gi, self.val) == (other.gi, other.val))

    def __hash__(self):
        return hash((self.gi, self.val))


_UNSET = object()      # "argument omitted", which is NOT the same request as `cfg=None`


def load(cfg=_UNSET, ir_path=None, cache=True):
    """The analysed model for `cfg`, built once and REUSED.

    Building is expensive (measured: LSL2 27s, KQ4 78s, KQ6 171s) and the suite asks for the
    same three models 26 times across six processes, which was ~96% of a 39-minute run. The
    model is pure derived data, so it is cached: in-process first, then a pickle under
    `build/.model_cache` keyed by `_model_cache_key` (config + IR + the hash of every
    non-test source file here). Round-tripping is ~164x faster than rebuilding.

    Set `cache=False`, or `SOFTLOCK_NO_MODEL_CACHE=1` in the environment, to force a build --
    and note the cache is per (cfg, IR, code), so a source edit invalidates every entry by
    construction rather than by anyone remembering to clear it.

    An EXPLICIT `cfg=None` is an error, while omitting the argument still means "the active
    config". The two are not the same request: `config.sweep_config(name)` returns None for a
    title with no IR built, and `cfg or config.ACTIVE` silently turned that into a full,
    confident analysis of whatever was active -- measured, five swept titles each reported
    LSL2's rooms, items and softlock count under their own name."""
    if cfg is _UNSET:
        cfg = config.ACTIVE
    elif cfg is None:
        raise ValueError(
            "load(cfg=None): no config. `config.sweep_config(name)` returns None when that "
            "title has no IR under build/sweep/<name>/ -- build it first, or pass a real "
            "GameConfig. (Omit the argument entirely to analyse config.ACTIVE.)")
    ir_path = ir_path or cfg.ir_path
    use_cache = cache and not os.environ.get("SOFTLOCK_NO_MODEL_CACHE")
    key = _model_cache_key(cfg, ir_path) if use_cache else None
    if key is None:
        return _build(cfg, ir_path)
    import pickle
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "build", ".model_cache", key + ".pkl")
    blob = _MODEL_MEMO.get(key)
    if blob is None and os.path.exists(path):
        try:
            with open(path, "rb") as f:
                blob = f.read()
            pickle.loads(blob)                     # reject a truncated/stale file here, not later
            _MODEL_MEMO[key] = blob
        except Exception:                          # noqa: BLE001 -- a bad pickle is not a
            blob = None                            # failure: fall through and rebuild
    if blob is None:
        model = _build(cfg, ir_path)
        blob = pickle.dumps((model, _vocab_state()), protocol=5)
        _MODEL_MEMO[key] = blob
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".%d.tmp" % os.getpid()   # atomic: parallel test processes race here
            with open(tmp, "wb") as f:
                f.write(blob)
            os.replace(tmp, path)
        except Exception:                          # noqa: BLE001 -- caching is an optimisation
            pass
        _restore_vocab_state(_vocab_state())
        return model
    # EVERY CALLER GETS ITS OWN COPY, which is why the memo holds bytes rather than the object.
    # `guards.apply_guards(s, specs)` mutates the model IN PLACE to build the guarded world it
    # verifies against (`s._emeta[key] = ...`, `s._pstates = ...`, and four `.clear()`s), so a
    # shared instance would hand the next caller a model with someone else's guards already
    # applied. Unpickling costs ~0.2s against a ~27-170s rebuild, so isolation is nearly free.
    model, state = pickle.loads(blob)
    _restore_vocab_state(state)
    return model


def _build(cfg, ir_path):
    # A BUILD OWNS ITS OWN BOOL_GLOBALS. The set is a module-level accumulator the lowering
    # passes add to, and it only ever grew: a process that loaded KQ6 and then KQ4 left KQ6's
    # synthetic registers in it, and since each game allocates its synthetic block from
    # `max_gi+1` the ranges overlap (KQ6 172..558 against KQ4's real 0..400), so registers of
    # the second game were read as boolean when they are nothing of the kind -- which widens a
    # `(!= gN 0)` into a hard `== 1` requirement and can invent a stranding. Clearing here
    # makes the set exactly this game's, which is also what lets a cached model restore a
    # clean one instead of freezing whatever contamination existed when it was built.
    vocab.BOOL_GLOBALS.clear()
    ir = I.load_ir(ir_path)
    # DERIVE both of the old per-game constants; config is now only a fallback/override.
    # See vocab.derive_death / derive_debug -- the anchors are engine vocabulary (the Game
    # subclass's route to Restore/Restart/Quit, and the `^=` toggle a debug checkbox compiles to),
    # which is why they survive a change of game. The old claim here was that death "cannot be
    # derived; LSL2 and KQ4 disagree on both index and shape" -- true only if you guess the shape
    # instead of reading it out of the test.
    import vocab as V
    # Death detection is DISPATCHED on the engine generation (vocab.is_sci11), a sharp and principled
    # divide: SCI0/SCI1 offer Restart/Restore ONLY on death, so any reachable Restart offer IS a
    # death; SCI1.1 also surfaces it from an always-available control panel, so that assumption breaks
    # and death must be recognised at the hazard instead. The signal is normalised to one (global,
    # value) either way, so nothing downstream knows which path ran.
    sig = tuple(cfg.death_signal) if cfg.death_signal else ()
    if not sig and V.is_sci11(ir):
        # SCI1.1: death = reaching a death DIALOG (a non-menu object offering both restart: and
        # restore:), either inline in a hazard script or via a proc that newRooms into a death room
        # (KQ6 proc0_1 -> rm640, called from the archer/minotaur/... hazards). See derive_death_sci11.
        dialogs, dprocs = V.derive_death_sci11(ir)
        if dialogs or dprocs:
            # the death SCREENS among those dialogs -- rooms that ARE the offer, so `newRoom:` into
            # one is a death (see extract.death_screen_rooms and lower_death_sci11 mechanism 3)
            import extract as _X
            synth, _n = V.lower_death_sci11(ir, dialogs, dprocs,
                                            screens=_X.death_screen_rooms(ir))
            sig = (synth, 1)
    if not sig and not V.is_sci11(ir):
        found = V.derive_death(ir)          # the global-flag shape (LSL2 gCurrentStatus, KQ4 g127)
        if found:
            sig = found[0][0]
        if not sig:
            # Imperative death: no "you died" global -- death is a call to a dialog PROCEDURE
            # (Camelot proc128_0, TCB proc0_19, KQ5 proc0_26). Lower each call to a synthetic
            # death-flag write so the (gi, v) machinery below applies unchanged.
            dprocs = V.derive_death_proc(ir)
            if dprocs:
                synth, _n = V.lower_death_procs(ir, dprocs)
                sig = (synth, 1)
    if not sig:
        raise SystemExit("could not derive a death signal, and config.death_signal is unset. "
                         "Expected the Game subclass to test a global on the way to restart:/"
                         "restore:, a public death procedure that offers it, or (SCI1.1) a death "
                         "dialog offering both restart: and restore:.")
    import dataclasses
    if not cfg.debug_globals:
        cfg = dataclasses.replace(cfg, debug_globals=frozenset(V.derive_debug(ir)))
    if not cfg.death_signal:
        cfg = dataclasses.replace(cfg, death_signal=sig)   # so reports show what was derived
    # Flag store: lower the game's boolean-flag bit-array into synthetic per-flag globals, so each
    # flag becomes an ordinary gating register with nothing downstream aware of "flags" (see
    # vocab.derive_flags). Runs after death lowering so the synthetic block clears the death flag
    # too. A no-op on games with no bit-array store -- LSL2/KQ4 have none, so they are untouched.
    flags = V.derive_flags(ir)
    if flags:
        synth_base = V.lower_flags(ir, flags[0], flags[1])[0]
        # Keep the mapping back. Lowering is deliberately one-way for the ANALYSIS -- nothing
        # downstream should know what a "flag" is -- but a PATCH has to be written in the game's
        # own spelling, and a synthetic register has none. `guards.render_register` reverses it:
        # register R is flag `R - synth_base`, tested by the proc the derivation already named.
        ir.flag_synth_base = synth_base
        ir.flag_test_proc = next((n for n, op in flags[1].items() if op == "test"), None)
        # ...and the SET spelling, for the WRITE side of the same reversal: a window remedy
        # holds the closer flag's raise (`(proc0_9 83)`) until the demand is banked, and the
        # proc that performs a raise is a fact the derivation already named.
        ir.flag_set_proc = next((n for n, op in flags[1].items() if op == "set"), None)
    # SECOND flag store: the same bit-in-a-word abstraction kept in an object's PROPERTY words
    # instead of a global array (SCI1.1 regions do this). Lowered to the same synthetic globals,
    # after lower_flags so the two synthetic blocks cannot overlap. Games without it are
    # untouched -- LSL2/KQ4/KQ5/QFG-VGA/Dagger have zero sites, KQ6 has 329.
    V.lower_prop_flags(ir, V.derive_prop_flags(ir))
    # THIRD container: state kept in an ordinary object's PROPERTY. SCI1.1 leans on it because a
    # region object outlives the rooms inside it -- KQ6's minotaur fight is decided entirely by
    # `(ScriptID 30 0) scarfOnMino:` / `seenByMino:`. Same "written with a constant AND read back"
    # rule as every other store, lowered to the same synthetic globals.
    # ...and the SAME container reached through a global. A game keeps its singletons in globals
    # and addresses them there, which resolves as statically as a `ScriptID` export -- but the
    # objects so held are usually the ENGINE's (the ego, the icon bar, User, a Sound), so the
    # widening carries its own bound: only a property the class INTRODUCES and the class library
    # never itself uses (`vocab._introduced_unused`). Measured corpus-wide that is LSL2 none,
    # KQ4 none, KQ6 none, LB2 two -- so it cannot renumber a register in the other three, which
    # matters here (see lower_prop_flags: allocation order IS register identity). Lowered in the
    # SAME call as the ScriptID/singleton half so both spellings share one allocation, and it is
    # the half allowed to split chained sends, because its one load-bearing write is inside one.
    _gprops = V.derive_global_props(ir)
    V.lower_obj_props(ir, V.derive_obj_props(ir) | _gprops, split_chains=_gprops)
    # FOURTH store, in the spelling item_property_registers cannot see: an item keeping its own
    # state as BIT FLAGS in its own property, written from inside its own methods via `self` and
    # read as a bare property. KQ6's skull gates the realm-of-the-dead cutscene on exactly that.
    import extract as _X
    # FIFTH store, BUILT AND STILL NOT WIRED after TWO measured rounds: a ROOM script's LOCAL
    # shared between that room's machines -- KQ6 rm690's local0, the gauntlet latch
    # (`vocab.derive_room_locals` / `lower_room_locals`, entry-reset via ir._room_local_resets ->
    # init_writes; rm690 derives exactly).
    #
    # THREE measured rounds, ONE blocker left:
    # ROUND 1 (2026-08-01): KQ4 whale items + KQ6 huntersLamp lost -> trap-clock rule and
    #   store-aware render_register landed on their own merits.
    # ROUND 2 (2026-08-02): still lost. Round 2's `_joints == []` lead was a red herring
    #   (`_joints` is [] on KQ4 stock too); the whale rows come from `joint_strandings` = the
    #   OCEAN GRID x monotone flags, and the grid died because the derivation lowered its data:
    #   `++`/`--` are Increment/Decrement nodes the taint missed (rm31's stepped cells), and
    #   rm31's local12 is `grid._counter_bound`'s CONST-LOCAL drown threshold (init-only writes).
    #   Both derivation fixes are IN (`derive_room_locals`), and with them KQ4 wired is
    #   byte-identical to stock -- whale, bridle, all five joint rows back.
    # ROUND 3 (2026-08-02): the LAST blocker, measured to a single boolean: KQ6's huntersLamp
    #   dies because `destroyed_is_permanent(19)` flips True->False. The lamp's acquisition
    #   entries come from `_entry_reach_walk_of(getLamp)`, and the walk threads machine-internal
    #   sequencing as CARRIED-LOCAL counters (`entry_locals`, CTR atoms in path guards, `c`
    #   writes). Lowering rm520's cross-object latches (locals 0-2 -- genuinely this gap's 2nd
    #   recorded instance) moves all three into register-land (Pred CMP atoms, `w` writes, no
    #   entry annotation), so the walk loses its internal resolution and the entry set weakens.
    # ROUND 4 (2026-08-02), WIRED: lowered OWN-SCRIPT registers now thread through the machine
    #   walks as counters keyed by the synthetic index (`Machine.local_regs`, `compile._lreg_test`,
    #   `_entry_reach_walk`), seeded from the declared reset (`ir._room_local_resets`) and
    #   overridden by the arming context's writes -- while the atoms and writes stay registers
    #   for every cross-scope consumer, which is the store's whole point. Pinned:
    #   `destroyed_is_permanent(huntersLamp)` True (test_kq6_ground_truth), the rm690 latch
    #   fixture in test_toll, and byte-identical LSL2/KQ4/Dagger surfaces.
    V.lower_room_locals(ir, V.derive_room_locals(ir, _X._room_numbers(ir)))
    _X.install_vocabulary(ir)
    V.lower_item_bit_flags(ir, V.derive_item_bit_flags(ir, _X._at_item), _X._at_item)
    # SIXTH container: a plain global used as a BIT-MASK WORD -- written `(|= gN $mask)`, read
    # by equality/bit-test -- with no accessor to key on. Same per-bit lowering as every flag
    # store. Measured corpus-wide: exactly one instance, KQ6's g161 (the Make-Rain readiness
    # word, the register half of the mists cage sorter); LSL2/KQ4/Dagger have zero mask-written
    # globals, so this is inert there by construction. LAST of the lowerings, deliberately:
    # ALLOCATION ORDER IS REGISTER IDENTITY (see lower_prop_flags), and a new store that
    # allocates mid-sequence renumbers every store after it -- measured: it took the skull's
    # item-bit registers (489/490) and test_scopes' pinned callback-scope check tripped on the
    # wrong store's writes.
    # SEVENTH container, a PRE-PASS to the sixth: the same mask word reached through an
    # ACCESSOR whose call sites carry the literal masks (LB2's global124, the per-act
    # story-beat word -- writes ride `((ScriptID 22 0) doit: <tick>)`, reads ride
    # `proc0_10`). The pre-pass inlines the accessor at every resolvable call site so the
    # sixth store below derives and lowers the store as if the game had spelled it
    # directly; it allocates nothing itself, so register identity elsewhere is untouched.
    # Corpus-measured single instance (see derive_mask_accessors' docstring).
    _macc = V.derive_mask_accessors(ir)
    if _macc:
        import sys as _sys
        _mw, _mr, _mskips = V.lower_mask_accessors(ir, _macc)
        # STDERR, like every other build diagnostic. On stdout this line lands inside the JSON
        # `snapshot.py GAME > before.json` writes -- the project's own documented regression
        # command -- and only on a COLD cache, so the file it corrupts is exactly the one taken
        # before a change to the code that invalidated the cache.
        print("  [lowered] mask accessor store(s) %s: %d write site(s), %d read call(s)"
              "%s" % (sorted(_macc), _mw, _mr,
                      "" if not _mskips else ", skipped %s" % _mskips), file=_sys.stderr)
    V.lower_mask_globals(ir, V.derive_mask_globals(ir))
    # A `switch` case label that is a PROPERTY is a literal the model was throwing away -- see
    # vocab.lower_property_case_labels. Runs LAST, after every store, deliberately: it allocates
    # no register, but it DOES change path conditions, and the derivations above key their
    # allocation order off what they see (see lower_mask_globals' note -- allocation order is
    # register identity). Placing it here leaves every store's numbering exactly as it was.
    _pcl = V.lower_property_case_labels(ir)
    if _pcl:
        import sys as _sys
        _heads = sorted({h for *_x, h in _pcl})
        print("  [lowered] %d property case label(s) in %d object(s), heads=%s"
              % (len(_pcl), len({(s, o) for s, o, *_r in _pcl}), _heads), file=_sys.stderr)
    d_gi, d_val = sig[0], (sig[1] if len(sig) > 1 else None)
    is_death = DeathSignal(d_gi, d_val)
    em = E.OpEmitter(ir, cfg, is_death)
    if not cfg.start_room or not cfg.goal_rooms:
        # Derive the reachability anchors from the game rather than declaring them. See anchors.py:
        # start = first room the player can act in, widest forward reach; goal = terminal,
        # reachable, never fatal. On LSL2 the derived pair reproduces the hand-tuned one exactly.
        import dataclasses, anchors
        st, gl = anchors.discover(em)
        cfg = dataclasses.replace(cfg, start_room=cfg.start_room or st,
                                  goal_rooms=cfg.goal_rooms or gl)
        em.cfg = cfg
    # AN UNANCHORED GOAL IS A FAILURE, NOT A CLEAN BILL OF HEALTH. Every "is X still
    # required?" question is answered against goal reachability, so an empty goal set makes
    # `goal_reaching` false everywhere: every guarded item lands in `hopeless`, `required`
    # collapses, and the pipeline prints "softlocks: 0 items" for a game it never anchored.
    # The death signal already refuses to be silent about this (see the SystemExit above);
    # the goal is the other half of the same pair and was not symmetric.
    if not cfg.goal_rooms:
        raise SystemExit(
            "could not derive a goal room for %s, and config.goal_rooms is unset. Every "
            "requirement question is answered against goal reachability, so continuing "
            "would report zero softlocks for a game that was never anchored. See anchors.py: "
            "a goal is terminal, reachable and never fatal; where the ending shares its flag "
            "with death, the ending that TESTS WHAT YOU ACHIEVED is the win." % cfg.name)
    return IrSccReach(em)


if __name__ == "__main__":
    s = load()
    print(f"rooms={len(s.rooms)}  SCCs={len(s.comps)}  goal_comps={sorted(s.goal_comps)}")
    cands = s.analyze()
    flagged = sorted({c["item"] for c in cands})
    print(f"softlock candidates ({len(flagged)} items):",
          [s.g.item_name(i) for i in flagged])
    for row in s.resource_exhaustion():
        where = (f"the roaming region {sorted(row['at_rooms'])}" if "at_rooms" in row
                 else f"rm{row['at_room']}")
        print(f"  + resource exhaustion: {row['item_name']} ({row['property']}) becomes unusable "
              f"at {where}, still needed at {row['still_needed_at']}")
    for row in s.group_strandings():
        print(f"  + disjunctive group {row['item_names']} needed at rm{row['need_room']}, "
              f"all sources {row['source_rooms']} unreachable from there")
    base = {c["item"] for c in cands}
    for row in s.joint_strandings():
        if row["item"] in base:
            continue                    # already an edge/register stranding -- the joint just re-sees it
        print(f"  + joint-window softlock: {row['item_name']} (source {row['source_rooms']}) is "
              f"unreachable once flags {row['flags']} advance -- still needed at {row['stranded_at']}")
