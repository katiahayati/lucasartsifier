"""The fixpoint core: what can you reach and obtain from a given state?

Adventure state is MOSTLY monotonic -- you gain items and set flags, you rarely
un-gain. So we do not enumerate the product state space (21 items => 2^21
subsets, the explosion that made the old code project down to a bare room graph
and throw the guards away). We compute a least fixpoint instead: exact,
guard-respecting, and cheap.

  ! MONOTONICITY IS AN APPROXIMATION, NOT A LAW, AND LSL2 BREAKS IT. Carrying the
  ! Spinach_Dip onto the lifeboat KILLS you: rm138 state 6 day 6 tests it FIRST and
  ! jumps to the death chain, so ACQUIRING an item can lose you the game. Two
  ! consequences worth remembering before trusting a result here:
  !   * `strandings` asks W(room, x) with `imax` = "hold everything". If holding
  !     everything is itself fatal, that baseline is a false premise.
  !   * `_atom3` answers UNKNOWN for `(not (ego has: X))` because it cannot model
  !     "you must not hold X" -- which is exactly why the dip's trap is invisible
  !     to us today. It is a MISS, which is the direction we accept, but it is not
  !     a soundness proof.

    closure(m, start, held, flags, exhausted) -> Reach(rooms, items, flagvals)
    winnable(...)  ==  a goal room is in reach.rooms

That turns softlock detection into a QUERY rather than a feature:

    for each irreversible action, recompute the closure from its POST-state;
    if the goal no longer closes, that action is the cut.

Cases that fall out of this one algorithm, with no special-casing: the whale (in
rm44 without iFeather, `(ego setScript: tickle)` is gated on the feather so the
machine never starts and there is no exit), the magic fruit (consumed, its
one-shot source exhausted, so rm694's ending is unreachable), and -- since the
state-machine lift (machine.py) -- the LSL2 lifeboat gauntlet: board the cruise
without the Sunscreen or the Grotesque_Gulp and the raft's day loop can never
reach its exit.

Deaths need no special handling here: the fixpoint does not care WHY you cannot
proceed. "Stuck" and "dead" are the same to it -- both are simply "the goal no
longer closes". The death catalogue (analyze.death_sites) is for LABELLING a
finding, which is a reporting concern. (That was only ever true of deaths that
block a MOVEMENT edge; deaths inside a room's own state machine were invisible
until machine.py made the machine part of the transition system.)

KNOWN MISS -- the parachute. Jumping without it is fatal, but rm64 reaches rm65
either way: the chute only decides `gCurrentStatus` (10 = descending vs 12 =
plummeting), and rm65's entries branch on it into an exit or a death. We model a
global as THE SET OF VALUES IT CAN EVER TAKE, so `(== gCurrentStatus 12)` asks
"can it be 12?" -- yes -- and `(!= gCurrentStatus 12)` asks "can it be something
else?" -- also yes. Both entries open, so the death never binds. Catching it needs
per-instant tracking of a mode register, not this abstraction. It USED to be
reported, but only via a bug: edge_requirements ANDs the guards of two ALTERNATIVE
routes to the same room, which manufactured a parachute requirement on an
unguarded edge. Right answer, wrong reason; the lift removed it.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict, namedtuple

sys.path.insert(0, os.path.dirname(__file__))
from model import load_game, Game                                    # noqa: E402
from analyze import (movement_graph, edge_requirements, region_maps,  # noqa: E402
                     is_room, _instance_of, _state_of)
from machine import (machines_of, run as machine_run,                    # noqa: E402
                     control_exits as machine_control_exits)
from config import ACTIVE as CFG                                      # noqa: E402

Reach = namedtuple("Reach", "rooms items flags")

ANY = object()      # a global written with a non-literal -> any value is possible


class FixModel:
    """Everything the fixpoint needs, extracted from the IR once.

    Note we take ACQUIRE/SET with their GUARDS, unlike analyze.derived_maps which
    flattens them and loses the condition -- the whole point here is to honour the
    conditions.
    """

    def __init__(self, game: Game):
        self.g = game
        self.edges, _kind = movement_graph(game)
        self.edge_reqs = edge_requirements(game)
        members, _room_region, controllers = region_maps(game)
        self.members, self.controllers = members, controllers

        # item -> [(room, guards)]   ; room may be a REGION script (iFeather's
        # source is script 505, a region) -- expand those to their member rooms,
        # exactly as the old _need_rooms did for `required`.
        self.acq = defaultdict(list)
        # global -> [(room, value, guards)]
        self.sets = defaultdict(list)
        for num, s in game.scripts.items():
            for t in s.transitions:
                for e in t.effects:
                    if e.kind == "ACQUIRE":
                        for r in self._rooms_of(num):
                            self.acq[e.arg].append((r, t.guard_tree))
                    elif e.kind == "SET":
                        if e.receiver in ("++", "--", "+=", "-="):
                            continue
                        if e.arg in CFG.debug_globals:
                            continue          # QA scaffolding stays 0; see config
                        for r in self._rooms_of(num):
                            self.sets[e.arg].append((r, _lit(e.value), t.guard_tree))

        # Intra-room state machines (machine.py). A room is not one node: its exit
        # may sit deep inside a Script's changeState switch, behind a gauntlet the
        # room graph cannot see. Where a machine owns a GOTO we let the machine
        # decide whether you can reach it, instead of trusting the flat edge.
        self.machines = {}
        self.machine_edges = set()
        self.machine_untrusted = set()        # exits our machine model can't reproduce
        _ev = lambda t, i, f, l: eval3(t, i, f, locs=l)          # noqa: E731
        for num in game.scripts:
            if not is_room(game, num):
                continue
            ms = machines_of(game, num)
            if not ms:
                continue
            self.machines[num] = ms
            # What can each machine deliver when nothing is denied to it? An exit it
            # cannot reach even then is a hole in OUR model of SCI's cue idioms, not
            # a gate in the game -- so leave those edges to the flat movement graph.
            deliverable = set()
            for mach in ms.values():
                deliverable |= machine_control_exits(mach, _ev)
            for t in game.scripts[num].transitions:
                inst, st = _instance_of(t.context), _state_of(t.context)
                if st is None or inst not in ms:
                    continue                  # doit/handleEvent GOTO: a direct action
                for e in t.effects:
                    if e.kind != "GOTO" or not isinstance(e.arg, int) or e.arg == num:
                        continue
                    if e.arg in deliverable:
                        self.machine_edges.add((num, e.arg))
                    else:
                        self.machine_untrusted.add((num, e.arg))

        # Only machines that actually OWN a trusted exit can change an answer; the
        # rest are pure cost (80 machines -> the handful that gate movement). Prune
        # so the fixpoint doesn't re-run cutscene machinery on every sweep.
        owned = {a for (a, _b) in self.machine_edges}
        self.machines = {a: {i: mm for i, mm in ms.items()
                             if any((a, b) in self.machine_edges
                                    for b in machine_control_exits(mm, _ev))}
                         for a, ms in self.machines.items() if a in owned}
        self.machines = {a: ms for a, ms in self.machines.items() if ms}
        self._mcache = {}                 # (inst id, projected world) -> exits

        # SCI0 ZERO-INITIALIZES script 0's locals, so a global nobody assigns is 0 --
        # not "unknown". Seeding every global (not just the ones with an explicit `=`
        # initializer) is what lets a guard on an UNSETTABLE global come out FALSE
        # instead of UNKNOWN-and-therefore-permissive. That is the Wig: day 4 of the
        # raft asks `(if gWearingWig ...)`, and without the Wig item nothing can ever
        # set it, so the honest answer is "you die" rather than "maybe you're fine".
        #
        # This costs precision-for-completeness: every setter we FAIL to extract now
        # reads as "this global can only be 0", which can manufacture a false dead end.
        # It was blocked for exactly that reason until the state-machine lift landed --
        # with globals zeroed, `gBombStatus` used to strand LSL2 at 50/100 rooms via a
        # bootstrap cycle (rm52->rm53 wants gBombStatus==3; rm52 sets 3 only if it is
        # already 2; rm152 sets 2 only if 1; rm54 sets 1 but sits behind rm53). The
        # cycle was an artifact: rm54's real entrance is a machine exit the old flat
        # edge was blocking. Both games now reach the same rooms zeroed as not, so this
        # is pure gain -- but keep _check_core.py's sanity checks honest, because they
        # are the only thing standing between this and a confident false positive.
        self.init_flags = {gn: ({_lit(game.global_inits[gn])} if gn in game.global_inits
                                else {0})
                           for gn in game.globals}
        # QA scaffolding is pinned OFF, by declaration rather than by luck. A debug
        # branch that hands you the bomb in the room you need it is not a walkthrough.
        for gn in CFG.debug_globals:
            self.init_flags[gn] = {0}

        # Items that GATE something -- the only ones that can strand you. An item
        # nothing ever tests can't make the goal unreachable.
        self.gating_items = {p.var for s in game.scripts.values()
                             for t in s.transitions for p in t.guards
                             if p.kind == "OWN" and p.want}

    def _rooms_of(self, num):
        """Where do this script's effects happen?

        - a REGION script isn't a walkable room; its effects happen in its members
          (iFeather's source is script 505, a region -- room reachability can never
          reach 505 itself).
        - non-room scripts (Main's procedures, the class library) are GLOBAL code
          called from anywhere -> None, meaning "available wherever you are".
          Without this, `(= gCurrentTimer name)` inside Main's SetRgTimer procedure
          never fires, and every timer-gated edge is wrongly blocked.
        """
        if num in self.controllers and self.members.get(num):
            return sorted(self.members[num])
        if not is_room(self.g, num):
            return [None]
        return [num]


def _lit(v):
    """Literal value of a SET, or ANY when it isn't a constant (`++`, an expr...)."""
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    if s in ("TRUE", "true"):
        return 1
    if s in ("FALSE", "false", "NULL"):
        return 0
    return ANY


def _truthy(vals):
    return any(v is ANY or (isinstance(v, int) and v != 0) for v in vals)


def _cmp_ok(v, op, want):
    if v is ANY:
        return True
    w = _lit(want)
    if w is ANY or not isinstance(v, int) or not isinstance(w, int):
        return True                     # can't evaluate -> permissive
    return {"==": v == w, "!=": v != w, "<": v < w, ">": v > w,
            "<=": v <= w, ">=": v >= w}.get(op, True)


T, F, U = True, False, None          # 3-valued: true / false / unknown


_INV = {"==": "!=", "!=": "==", "<": ">=", ">": "<=", "<=": ">", ">=": "<"}


def _and3(vals):
    if any(v is F for v in vals):
        return F
    return U if any(v is U for v in vals) else T


def _or3(vals):
    if any(v is T for v in vals):
        return T
    return U if any(v is U for v in vals) else F


def _atom3(p, items, flags, neg, locs=None):
    """SATISFIABILITY of an atom: can the player arrange for it to hold?

    Note this is NOT truth at a fixed instant. `flags` holds the SET of values a
    global can ever take, so `(== gCurrentStatus 0)` asks "can it be 0?", not "is
    it 0 now?". That is why negation must be pushed into the leaf (== -> !=)
    rather than applied to the answer: negating "0 is achievable" would give
    "cannot be non-zero", which is nonsense for a mode register that takes 37
    values -- and it blocked half of LSL2 when I tried it.
    """
    if p.kind == "LOCAL":
        # A machine's own bounded counter (machine.py). Unlike `flags`, this is a
        # CONCRETE value at a concrete node of the state machine, not a set of
        # ever-achievable values -- so it is ordinary two-valued arithmetic, and
        # negation may be applied to the answer. This is what makes the LSL2 raft's
        # `(== day 3)` select exactly the sunscreen branch instead of leaving every
        # day's hazard simultaneously dodgeable via the cond's `else`.
        if locs is None or p.var not in locs:
            return U
        r = _cmp_ok(locs[p.var], p.op, p.value)
        return (F if r else T) if neg else (T if r else F)
    if p.kind == "OWN":
        want = p.want != neg
        if not want:
            return U              # "must NOT hold x": monotonic items can't model dropping
        return T if p.var in items else F
    if p.kind == "FLAG":
        want = p.want != neg
        vals = flags.get(p.var)
        if not vals:
            return U
        t = _truthy(vals)
        if want:
            return T if t else F
        return T if any(v == 0 for v in vals) or any(v is ANY for v in vals) else F
    if p.kind == "CMP":
        vals = flags.get(p.var)
        if not vals:
            return U
        if any(v is ANY for v in vals):
            return U
        op = _INV.get(p.op, p.op) if neg else p.op
        return T if any(_cmp_ok(v, op, p.value) for v in vals) else F
    return U                      # SAID / POS / OPAQUE -> unknown


def eval3(node, items, flags, neg=False, locs=None):
    """3-valued (Kleene) evaluation of a guard TREE, with negation pushed to the
    leaves via De Morgan. UNKNOWN is load-bearing: anything we cannot interpret
    stays U rather than becoming T, so we only ever refuse an edge on a PROVABLY
    false guard -- miss a stranding rather than invent one.

    `locs` binds a state machine's bounded counters when evaluating inside one
    (machine.py); it is None everywhere else.
    """
    from model import GAnd, GOr, GNot, Pred
    if isinstance(node, GAnd):
        vals = [eval3(k, items, flags, neg, locs) for k in node.kids]
        return _or3(vals) if neg else _and3(vals)       # ¬(a∧b) = ¬a ∨ ¬b
    if isinstance(node, GOr):
        vals = [eval3(k, items, flags, neg, locs) for k in node.kids]
        return _and3(vals) if neg else _or3(vals)       # ¬(a∨b) = ¬a ∧ ¬b
    if isinstance(node, GNot):
        return eval3(node.kid, items, flags, not neg, locs)
    if isinstance(node, Pred):
        return _atom3(node, items, flags, neg, locs)
    return U


def holds_tree(tree, items, flags, locs=None):
    """Block only on a provably-false guard. A missing tree = unguarded = free."""
    if tree is None:
        return True
    return eval3(tree, items, flags, locs=locs) is not F


def own_atoms(node, out=None, neg=False):
    """OWN items a guard tree mentions at POSITIVE polarity.

    This used to recurse through `GNot` without flipping, so `(not (ego has: X))`
    reported X as mentioned-positively -- i.e. as the exact opposite of what the
    guard says. Its own docstring warned that "a mention is not a requirement, since
    it may sit under an `or` or a `not`", and then `requirements()` used it as a
    semantic filter anyway. Polarity is now tracked; for "does this guard actually
    REQUIRE x", use `guard_requires()`, which asks rather than scans.
    """
    from model import GAnd, GOr, GNot, Pred
    out = set() if out is None else out
    if isinstance(node, (GAnd, GOr)):
        for k in node.kids:
            own_atoms(k, out, neg)
    elif isinstance(node, GNot):
        own_atoms(node.kid, out, not neg)
    elif isinstance(node, Pred) and node.kind == "OWN" and (node.want != neg):
        out.add(node.var)
    return out


class _AllBut:
    """Everything except the named items -- a maximal world with one hole."""

    def __init__(self, missing):
        self.missing = missing

    def __contains__(self, x):
        return x not in self.missing


def guard_requires(tree, cands):
    """Which of `cands` does this guard PROVABLY refuse to be crossed without?

    Asks instead of scanning: hold everything but x, be maximally permissive about
    every flag, and see whether the guard goes provably false. That is the only
    reading of "the game already blocks you without x" that survives `or` and `not`
    -- a syntactic atom scan gets `(or (has: A) (has: B))` wrong (neither is
    required) and `(not (has: X))` exactly backwards (X is FORBIDDEN, not required).
    """
    if tree is None:
        return set()
    from machine import _AnyFlags
    anyf = _AnyFlags()
    return {x for x in cands if eval3(tree, _AllBut({x}), anyf) is F}


def holds(preds, items, flags):
    """Do these guards hold under (items, flags)? Deliberately PERMISSIVE about
    anything we cannot evaluate -- an unknown guard is assumed satisfiable. That
    biases us to MISS strandings rather than invent them, which is the direction
    we want: a false 'you're stuck' would be far worse than a quiet omission.

    Negative ownership (`(not (ego has: X))`) is also treated as satisfiable: the
    fixpoint is monotonic in items, so it cannot model 'you must not hold X'.
    """
    for p in preds:
        if p.kind == "OWN":
            if p.want and p.var not in items:
                return False            # must hold it, and we can't get it
        elif p.kind == "FLAG":
            vals = flags.get(p.var)
            if vals and p.want and not _truthy(vals):
                return False
        elif p.kind == "CMP":
            vals = flags.get(p.var)
            if vals and not any(_cmp_ok(v, p.op, p.value) for v in vals):
                return False
    return True


def closure(m: FixModel, start_room, held=(), flags=None, exhausted=()):
    """Least fixpoint from a state: everything you could EVER reach/obtain."""
    rooms = {start_room}
    items = set(held)
    fl = {k: set(v) for k, v in (flags if flags is not None else m.init_flags).items()}
    exhausted = set(exhausted)

    cache = m._mcache          # lives on the model: shared across every closure,
                               # which is what makes strandings' ~1400 re-closures
                               # affordable (they mostly perturb items no machine
                               # looks at, so they collapse onto the same key).

    def _exits(inst, mach):
        # Key on the MACHINE, not its instance NAME. Script instance names are only
        # unique within a script, and rooms reuse them: KQ4 has `doDoor` in both rm80
        # and rm87, `doorOpen` in rm49/51, `egoActions` in rm690/693, `henchChase` in
        # rm86/87/91. rm80's doDoor exits to 92 and rm87's to 84; they projected to the
        # identical key, rm80 was closed first, and rm87 read back rm80's answer -- so
        # rm84 was DELETED from the game. A fabricated dead end, the one error this
        # tool must never make, from a cache key.
        key = (mach.script, mach.inst, mach.project(items, fl))
        ex = cache.get(key)
        if ex is None:
            ex, _deaths = machine_run(mach, items, fl,
                                      lambda t, i, f, l: eval3(t, i, f, locs=l))
            cache[key] = ex
        return ex

    changed = True
    while changed:
        changed = False
        # 1. walk anywhere whose edge preconditions hold
        for a in list(rooms):
            for b in m.edges.get(a, ()):
                if (a, b) in m.machine_edges:
                    # Owned by a state machine -> step 1b decides, and the flat edge
                    # stays out of it.
                    #
                    # REVIEW REJECTED A CHANGE HERE, with evidence. The proposal was:
                    # when a trusted machine declines an exit, fall back to
                    # `holds_tree(edge_reqs)` rather than treat machine silence as
                    # proof of a gate. Sound-looking, and it deletes FOUR of six
                    # findings -- Sunscreen, Grotesque_Gulp, Wig, Fruit-OR-Sewing_Kit
                    # all vanish. The reason is the raft itself: `edge_reqs[(138,42)]`
                    # is `opaque((>= day 9))`, which is UNKNOWN, which is permissive.
                    # The flat guard has NOTHING to say about any edge a machine owns
                    # -- that is precisely why the machine had to own it. Falling back
                    # to it is falling back to "no gate".
                    #
                    # The live bug the reviewer traced (KQ4 rm84 deleted) was the cache
                    # key above, now fixed. The residual concern is real and stands
                    # unfixed: `control_exits` runs once with everything granted and
                    # only asks "does this exit exist at all", so it cannot catch
                    # mis-modelling that is item/flag-DEPENDENT rather than total (an
                    # exit reachable permissively via an item-guarded branch, while the
                    # genuinely free branch stalls on a cue idiom we misread). There is
                    # no cheap detector for that, and the offered cure costs the
                    # feature. Documented rather than papered over.
                    continue
                if b not in rooms and holds_tree(m.edge_reqs.get((a, b)), items, fl):
                    rooms.add(b)
                    changed = True
        # 1b. a room's own state machines: an exit buried in a changeState switch is
        #     reachable only along a path THROUGH the machine, and that path may run
        #     a gauntlet (LSL2's raft: survive days 3-6 or the exit never comes).
        for a in list(rooms):
            for inst, mach in m.machines.get(a, {}).items():
                for b in _exits(inst, mach):
                    if b != a and b not in rooms and (a, b) in m.machine_edges:
                        rooms.add(b)
                        changed = True
        # 2. pick up anything acquirable in reach (and not consumed away)
        for it, sites in m.acq.items():
            if it in items or it in exhausted:
                continue
            for room, guards in sites:
                if (room is None or room in rooms) and holds_tree(guards, items, fl):
                    items.add(it)
                    changed = True
                    break
        # 3. set any flag we can reach the setter of (room None == global code)
        for g, sites in m.sets.items():
            for room, val, guards in sites:
                if (room is None or room in rooms) and val not in fl.get(g, ()) \
                        and holds_tree(guards, items, fl):
                    fl.setdefault(g, set()).add(val)
                    changed = True
    return Reach(rooms, items, fl)


def winnable(m: FixModel, start_room, held=(), flags=None, exhausted=(), goals=None):
    goals = set(goals if goals is not None else CFG.goal_rooms)
    return bool(closure(m, start_room, held, flags, exhausted).rooms & goals)


MAX_CLAUSES_PER_EDGE = 6      # see the `truncated` flag -- never a silent cap


def requirements(m: FixModel, start=None, goals=None, log=None):
    """What must you be carrying to cross each irreversible edge? -- as CNF.

    Not a feature, a query. `W(room, S)` asks: standing in `room` holding
    everything EXCEPT the set S, can you still win? (The closure re-acquires
    anything in S whose source is still reachable, so a "no" means genuinely
    unrecoverable.)

    A MINIMAL BLOCKING SET for edge a->b is a minimal S with `not W(b, S)`:
    lacking all of S loses, and dropping any one member makes it winnable again.
    Read it as a clause -- **you must hold at least one of S** -- and the answer for
    an edge is the AND of its clauses. That single shape covers both cases:

        |S| == 1   "you must hold the Sunscreen"      (an ordinary stranding)
        |S| >  1   "you must hold Fruit OR Sewing_Kit" (raft day 6 -- either feeds you)

    THIS IS WHY THE SINGLE-ITEM QUERY WAS NOT ENOUGH. Asking W(b, {x}) one item at a
    time can never see a disjunction: drop only the Fruit and the Sewing_Kit still
    feeds you, so neither is ever "the" stranded item, and a real dead-end (carrying
    neither) goes unreported. The old syntactic core "found" these by ANDing the
    alternatives, which is the same rule that demanded the fatal Spinach_Dip -- right
    row, wrong logic. Minimality is what separates them: the Spinach_Dip is in no
    blocking set at all (lacking it does not lose -- holding it does), while
    {Fruit, Sewing_Kit} is a blocking set and neither singleton is.

    Method: per edge, take the items you can never get back past b, then peel off one
    minimal blocking set at a time (deletion-based: try dropping each member; if it
    still blocks, that member was not needed). Cost is O(|C|) closures per clause,
    not the 2^|C| of trying every subset.
    """
    start = CFG.start_room if start is None else start
    goals = set(CFG.goal_rooms if goals is None else goals)
    base = closure(m, start)
    imax = frozenset(base.items)
    # only items that actually gate something can strand you
    cand_all = frozenset(x for x in m.gating_items if x in imax)

    wmemo, lmemo = {}, {}

    # Flags RESET to init here, and that is deliberate -- `closure` re-derives them
    # from the items you actually hold. It is the same premise as `imax`: "standing
    # here with this inventory, what can you still achieve?"
    #
    # A review finding proposed passing `base.flags` instead, on the grounds that the
    # reset forgets flags the player provably set on the way. Tried it: it DELETES the
    # Sunscreen and the Wig. Those are exactly the item -> flag -> survival chains the
    # core exists to find -- `gWearingSunscreen` is only settable while HOLDING the
    # Sunscreen, so handing in "{1,2,3} is achievable" while removing the item asserts
    # the conclusion the query is asking about. Flags must stay coupled to items or the
    # question is meaningless.
    #
    # The finding's real observation stands and is handled below: the sink test drops
    # edges silently, and its comment claimed they were death rooms. They are not; they
    # are rooms you genuinely cannot win from with the inventory re-derived, which for
    # rm138 (the raft) is simply TRUE -- board it without having worn sunscreen on the
    # ship and you are dead, and no cargo changes that. So the skip is right; the
    # silence was not.
    def W(room, lacking):
        k = (room, frozenset(lacking))
        if k not in wmemo:
            wmemo[k] = bool(closure(m, room, imax - k[1]).rooms & goals)
        return wmemo[k]

    def lost(b):
        """Candidates you can NEVER re-acquire once you are at b. One closure, not
        one per item: drop them all and see which the fixpoint hands back (it
        re-acquires transitively, so a chain of sources resolves itself)."""
        if b not in lmemo:
            lmemo[b] = frozenset(cand_all - closure(m, b, imax - cand_all).items)
        return lmemo[b]

    out, sinks = [], []
    for a in sorted(base.rooms):
        for b in sorted(m.edges.get(a, ())):
            if b not in base.rooms:
                continue
            if not W(b, ()):
                # Unwinnable even holding EVERYTHING, so nothing about WHAT you carry
                # can change the outcome and there is no requirement to report.
                #
                # The comment here used to say "absorbing sink (a death room)", which
                # was a guess dressed as a fact: the test fires for any room the goal
                # cannot be re-closed from, and rm138 (the raft) and rm152 are not death
                # rooms. Most of that was the flag reset above, now fixed. Whatever is
                # left is a genuine "you cannot win from here at all" -- but say so out
                # loud, because a dropped edge is a finding we will never make.
                # MAX_CLAUSES_PER_EDGE gets a `truncated` flag precisely so a cap is
                # never silent; this drop is bigger and was completely silent.
                sinks.append((a, b))
                continue
            # Items the game ALREADY refuses to let you cross without -- no point
            # reporting a requirement the edge itself enforces.
            #
            # This used to be `own_atoms(...)`, a syntactic scan that collected OWN at
            # ANY polarity. So `(not (ego has: X))` -- an edge that forbids X -- exempted
            # X from ever being reported, and an `(or (has: A) (has: B))` exempted both
            # when neither is required. On LSL2 that silenced 14 item/edge pairs,
            # including every item on rm0->rm152. Ask the guard instead of reading it.
            pool = set(lost(b))
            pool -= guard_requires(m.edge_reqs.get((a, b)), pool)
            clauses, truncated = [], False
            while pool:
                if W(b, pool):
                    break         # lacking everything still in the pool is survivable
                if len(clauses) >= MAX_CLAUSES_PER_EDGE:
                    truncated = True
                    break
                S = _minimal_blocking(W, b, pool)
                # It must also be RECOVERABLE on the near side, or the loss happened
                # upstream and this edge is just where we noticed.
                if W(a, S):
                    clauses.append(sorted(S))
                pool -= S
            if clauses:
                out.append({
                    "from_room": a, "to_room": b,
                    "clauses": [{"items": c,
                                 "item_names": [m.g.item_name(i) for i in c]}
                                for c in clauses],
                    "guard_sexpr": _cnf_sexpr(clauses),
                    "truncated": truncated,
                })
                if truncated and log is not None:
                    log.append(f"rm{a}->rm{b}: stopped at {MAX_CLAUSES_PER_EDGE} "
                               f"clauses; more may exist")
    if sinks and log is not None:
        log.append(f"{len(sinks)} edge(s) skipped as unwinnable-even-holding-everything "
                   f"(no requirement can be reported for them): "
                   + ", ".join(f"rm{a}->rm{b}" for a, b in sinks[:8])
                   + (" ..." if len(sinks) > 8 else ""))
    return out


def _minimal_blocking(W, b, S):
    """Shrink S to a MINIMAL set whose absence still blocks the goal at b.

    Deletion-based: for each x, ask whether lacking S-{x} still loses. If it does,
    x was carrying no weight and drops out. What survives is a set where every
    member matters -- i.e. holding any ONE of them is enough. Precondition: `not
    W(b, S)`.
    """
    B = set(S)
    for x in sorted(S):
        if len(B) > 1 and not W(b, B - {x}):
            B.discard(x)
    return frozenset(B)


def _cnf_sexpr(clauses):
    """The LucasArts guard for an edge: AND of clauses, each an OR of `has:`.

    Note what this fixes. The old synthesizer emitted a flat conjunction of every
    item it thought was needed, which is how the glacier came out as
    `(and (gEgo has: 30) (gEgo has: 31))` -- Sand AND Ashes -- when either does.
    """
    def lit(i):
        return f"(gEgo has: {i})"
    parts = [lit(c[0]) if len(c) == 1 else "(or " + " ".join(lit(i) for i in c) + ")"
             for c in clauses]
    return parts[0] if len(parts) == 1 else "(and " + " ".join(parts) + ")"


def strandings(m: FixModel, start=None, goals=None):
    """The singleton view of `requirements`: edges that strand ONE named item.

    Kept because it is the readable form of the common case, and because a
    single-item answer is what the reports and _check_core.py speak. Disjunctive
    requirements (|clause| > 1) are invisible here BY CONSTRUCTION -- ask
    `requirements()` for those.
    """
    out = []
    for e in requirements(m, start, goals):
        for c in e["clauses"]:
            if len(c["items"]) == 1:
                out.append({"from_room": e["from_room"], "to_room": e["to_room"],
                            "item": c["items"][0], "item_name": c["item_names"][0]})
    return out


def consumable_strandings(m: FixModel, start=None, goals=None):
    """Items whose LOSS is unrecoverable and fatal to winning -- e.g. eating the
    magic fruit. Post-state = the item gone AND its sources exhausted (a one-shot
    pickup does not respawn just because you can walk back to the room)."""
    start = CFG.start_room if start is None else start
    goals = set(CFG.goal_rooms if goals is None else goals)
    base = closure(m, start)
    out = []
    for x in sorted(m.gating_items):
        if x not in base.items:
            continue
        r = closure(m, start, exhausted={x})
        if not (r.rooms & goals):
            out.append({"item": x, "item_name": m.g.item_name(x)})
    return out


def main():
    game = load_game()
    m = FixModel(game)
    r = closure(m, CFG.start_room)
    goals = set(CFG.goal_rooms)
    rooms_total = len([n for n in game.scripts if is_room(game, n)])
    print(f"{CFG.name}")
    print(f"  edges with preconditions : {len(m.edge_reqs)}")
    print(f"  closure from rm{CFG.start_room}: {len(r.rooms)}/{rooms_total} rooms, "
          f"{len(r.items)}/{len(game.items)} items, {len(r.flags)} globals")
    ok = bool(r.rooms & goals)
    print(f"  goal {sorted(goals)} reachable? {ok}")
    print(f"  SANITY: a shipped game must be winnable with nothing removed -> "
          f"{'PASS' if ok else 'FAIL (the model is wrong, not the game)'}")
    if not ok:
        missing = sorted(goals - r.rooms)
        print(f"    unreached goal rooms: {missing}")
    return m, r


if __name__ == "__main__":
    main()
