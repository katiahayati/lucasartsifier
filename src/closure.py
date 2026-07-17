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
from collections import defaultdict, deque, namedtuple

sys.path.insert(0, os.path.dirname(__file__))
from model import load_game, Game, GOr, GAnd                         # noqa: E402
from analyze import (movement_graph, edge_requirements, region_maps,  # noqa: E402
                     is_room, _instance_of, _state_of, set_trigger_guards)
from machine import machines_of, compile_exits as machine_compile   # noqa: E402
from config import ACTIVE as CFG                                      # noqa: E402

Reach = namedtuple("Reach", "rooms items flags")

ANY = object()      # a global written with a non-literal -> any value is possible

# Cap on the worst-case promoted state multiplier (product of register domains).
# Promotion is a product over independent registers; this bounds it. LSL2's full set
# is 35x9x8x3x3 ~ 22.7k and blows past a minute; a ~1k budget keeps the endgame-local
# registers and drops the promiscuous gCurrentStatus. Tunable; a per-game
# config.promote_registers overrides selection entirely.
MAX_PROMOTED_PRODUCT = 1200


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
        # A SET inside a machine state keeps only its LOCAL path condition; the guard
        # that actually gates it is on the trigger that STARTED the machine. Dropping
        # it made rm64's `(= gCurrentStatus 10)` -- the parachute survival write, in
        # state 2 behind `gWearingParachute==1` -- look UNCONDITIONAL, so the model
        # survived the plane jump without the chute. Fold the trigger guard in, exactly
        # as edge_requirements already does for GOTOs.
        trig = set_trigger_guards(game)
        for num, s in game.scripts.items():
            for t in s.transitions:
                inst, st = _instance_of(t.context), _state_of(t.context)
                for e in t.effects:
                    if e.kind == "ACQUIRE":
                        for r in self._rooms_of(num):
                            self.acq[e.arg].append((r, t.guard_tree))
                    elif e.kind == "SET":
                        if e.receiver in ("++", "--", "+=", "-="):
                            continue
                        if e.arg in CFG.debug_globals:
                            continue          # QA scaffolding stays 0; see config
                        tg = trig.get((num, inst, st))
                        guard = (t.guard_tree if tg is None
                                 else GAnd([g for g in (t.guard_tree, tg) if g is not None]))
                        for r in self._rooms_of(num):
                            self.sets[e.arg].append((r, _lit(e.value), guard))

        # Intra-room state machines (machine.py). A room is not one node: its exit
        # may sit deep inside a Script's changeState switch, behind a gauntlet the
        # room graph cannot see. Where a machine owns a GOTO we let the machine
        # decide whether you can reach it, instead of trusting the flat edge.
        # A machine is an EXTRACTOR, not a runtime component: what it takes to get from
        # rm138 to rm42 does not depend on when you ask. So COMPILE each machine to one
        # guard per exit, once, here (machine.compile_exits) -- and hand the fixpoint a
        # formula. Running machines inside the closure is what produced Machine.project,
        # the _mcache, and the cache key that deleted KQ4's rm84 outright.
        #
        # It also buys the thing the monotone fixpoint cannot say. `_atom3` must answer
        # UNKNOWN for `(not (ego has: X))` to stay monotone in items, so it can never
        # express "you must NOT carry this". Enumeration has no such assumption: of the
        # 18 assignments that get you off the raft, the Spinach_Dip is held in ZERO, so
        # the compiled guard contains `¬own(13)`. That is the trap that made the shipped
        # patch unwinnable.
        self.machine_guards = {}              # (a,b) -> compiled guard tree (None=free)
        self.machine_edges = set()
        self.machine_untrusted = set()        # exits our machine model can't reproduce
        _local = lambda p, locs: _atom3(p, frozenset(), {}, False, locs)   # noqa: E731
        for num in game.scripts:
            if not is_room(game, num):
                continue
            ms = machines_of(game, num)
            if not ms:
                continue
            # Several machines in a room may deliver the same exit: they are
            # ALTERNATIVES, so OR their guards.
            deliverable = {}
            for mach in ms.values():
                for e, gt in machine_compile(mach, _local).items():
                    if e in deliverable and not (deliverable[e] is None or gt is None):
                        deliverable[e] = GOr([deliverable[e], gt])
                    else:
                        deliverable[e] = None if (e in deliverable and
                                                  deliverable[e] is None) else gt
            for t in game.scripts[num].transitions:
                inst, st = _instance_of(t.context), _state_of(t.context)
                if st is None or inst not in ms:
                    continue                  # doit/handleEvent GOTO: a direct action
                for e in t.effects:
                    if e.kind != "GOTO" or not isinstance(e.arg, int) or e.arg == num:
                        continue
                    if e.arg in deliverable:
                        self.machine_edges.add((num, e.arg))
                        self.machine_guards[(num, e.arg)] = deliverable[e.arg]
                    else:
                        # No assignment of its own atoms reaches this exit -- our model
                        # of SCI's cue idioms has a hole, not the game. Fall back to the
                        # flat edge rather than invent a dead end. (Same contract
                        # `control_exits` had; the compile subsumes it.)
                        self.machine_untrusted.add((num, e.arg))

        # No pruning, no cache, no per-closure re-interpretation: the machines are gone
        # from the runtime entirely, replaced by `machine_guards`.

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

        # --- MODE REGISTERS (phase 4) -----------------------------------------
        # A global tracked as "the set of values it can EVER take" answers `== 12`
        # with "is 12 in the set?" -- always yes for a register, so its gate never
        # binds. gCurrentStatus (splat vs chute), gIslandStatus (the endgame chain),
        # and the Cupid bow's arrow count all die this way. Fix: PROMOTE such a
        # register into the location, so reachability is over (room, value) and
        # `== 12` means "is it 12 HERE", not "could it ever be".
        #
        # Chosen mechanically -- a register is a global compared `==` against >=3
        # distinct literals and assigned only literals (no `++`, already excluded
        # above). PREDICATE-ABSTRACTED to the values actually tested: a room that
        # never reads R does not split on it, and gCurrentStatus's 35 values touch
        # ~99 (room,value) nodes, not 85x35. That is the difference between a 2x
        # state space and a 300x one.
        self.reg_tested = defaultdict(set)      # reg -> {int literals it is compared to}
        assigned = defaultdict(set)             # reg -> {int literals assigned to it}
        for s in game.scripts.values():
            for t in s.transitions:
                _collect_cmp(t.guard_tree, self.reg_tested)
        for gt in self.machine_guards.values():
            _collect_cmp(gt, self.reg_tested)
        for gn, sites in self.sets.items():
            for _r, v, _g in sites:
                if isinstance(v, int):
                    assigned[gn].add(v)
        candidates = [
            gn for gn, lits in self.reg_tested.items()
            if gn in game.globals and gn not in CFG.debug_globals
            and gn not in CFG.timer_globals             # a clock is not a mode register
            and len({v for v in lits if isinstance(v, int)}) >= 3
            and assigned.get(gn) and all(isinstance(v, int) for v in assigned[gn])]

        def _dom(gn):
            return ({v for v in self.reg_tested[gn] if isinstance(v, int)}
                    | assigned.get(gn, set())
                    | {_lit(next(iter(self.init_flags.get(gn, {0}))))})

        # Promotion multiplies the location space, and the registers are (largely)
        # INDEPENDENT, so promoting all of them is a product -- LSL2's
        # 35x9x8x3x3 blows past a minute. Promote a bounded subset instead: smallest
        # domains first, while the worst-case product stays under budget. This is a
        # conservative proxy (the *reachable* product is smaller), deterministic, and
        # generalises -- KQ4's registers fit comfortably; LSL2 keeps the cheap,
        # endgame-local ones and drops gCurrentStatus, which is written in 62 rooms and
        # gates nothing cleanly anyway. Per-game override via config.promote_registers.
        # OFF BY DEFAULT, and this is a MEASURED decision, not caution. Promotion is
        # correct (it fixes the mode-register gates), but it makes a single closure
        # ~200x slower, and `requirements()` runs ~373 closures -- so promotion-on takes
        # `requirements()` from 3s to ~12 MINUTES. That is Phase 5's job (make the query
        # incremental); until then, turning promotion on is not affordable for the
        # frontier scan. And on LSL2 it buys no finding anyway: the two gates it would
        # help (bomb, parachute) are gated OUTSIDE the register logic.
        #
        # So: `promoted` is empty unless a game's config opts in via
        # `promote_registers` (a set of names, or "auto" for the budget heuristic).
        # `candidate_registers`/`reg_dom_all` stay populated for reporting and for the
        # targeted rm79 test, which exercises the mechanism with one register in one
        # cheap closure.
        self.candidate_registers = frozenset(candidates)
        self.reg_dom_all = {gn: frozenset(_dom(gn)) for gn in candidates}
        override = getattr(CFG, "promote_registers", frozenset())
        if override == "auto":
            chosen, product = [], 1
            for gn in sorted(candidates, key=lambda g: len(_dom(g))):
                if product * len(_dom(gn)) <= MAX_PROMOTED_PRODUCT:
                    chosen.append(gn)
                    product *= len(_dom(gn))
        else:
            chosen = [gn for gn in candidates if gn in override]
        self.promoted = frozenset(chosen)
        self.reg_dom = {gn: frozenset(_dom(gn)) for gn in self.promoted}
        self._build_reg_writes()

    def promote(self, regs):
        """Turn promotion on for a chosen register set (for investigation / tests).

        Rebuilds `promoted`, `reg_dom`, and the room register-writes. Kept off the
        default path because promotion makes `requirements()` ~200x slower per closure
        -- see the note by the selection above."""
        self.promoted = frozenset(r for r in regs if r in self.candidate_registers)
        self.reg_dom = {r: self.reg_dom_all[r] for r in self.promoted}
        self._build_reg_writes()
        return self

    def _build_reg_writes(self):
        # ROOM REGISTER WRITES: room -> [(reg, abs-value, guard)] for promoted
        # registers, in source order. The closure applies these when you LEAVE a room,
        # each gated on its own guard against the SOURCE state -- which is the only
        # correct place for them, and it took two bugs to see why:
        #
        #  * A register write is NOT an add-only self-transition. Modelled that way, the
        #    stale PRE-write value survives in parallel: rm64 sets gCurrentStatus:=12 on
        #    entry, but (rm64, 0) stayed reachable too and leaked value 0 into rm65,
        #    which survives on `!= 12`. Applying the writes ON THE WAY OUT overwrites the
        #    stale value, so every exit from rm64 delivers 12 (or 10 with the chute).
        #  * The gating register and the WRITTEN register can differ. rm64's
        #    gCurrentStatus:=10 is gated on `gWearingParachute==1` -- a DIFFERENT
        #    register. So there is no "edge implies same-register write" shortcut; a
        #    write just carries its own guard, evaluated against the live state.
        #
        # rm79 still works: leaving rm77 at gIslandStatus=1, the edge (77,76) guard
        # `==1` holds on the source, and rm77's `:=2` write (guard `==1`, also true on
        # the source) is applied -> arrive rm76 at 2.
        # Split by WHEN the write takes effect, which is what the two bugs were really
        # about:
        #   ENTRY writes -- UNCONDITIONAL resets, e.g. NormalEgo's `gCurrentStatus:=0`
        #     (68 call sites) and rm64's `gCurrentStatus:=12`. These run when you ENTER
        #     the room and must be visible to the room's OWN out-edge guards: rm55->rm56
        #     needs `gCurrentStatus==0`, and applying the reset on exit left rm55 holding
        #     the stale incoming value -> the whole back half of LSL2 unreachable.
        #   EXIT writes -- GUARDED, co-triggered with a specific move, e.g. rm64's
        #     `:=10` behind `gWearingParachute==1` and rm77's `:=2` behind
        #     `gIslandStatus==1`. These are the SURVIVE/advance branch and belong on the
        #     edge, guard checked on the source value.
        self.room_entry_writes = defaultdict(list)   # room -> [(reg, abs-value)]
        self.room_exit_writes = defaultdict(list)    # room -> [(reg, abs-value, guard)]
        for reg in self.promoted:
            for room, val, guard in self.sets.get(reg, ()):
                if _has_atom(guard):
                    self.room_exit_writes[room].append((reg, _abs_val(val), guard))
                else:
                    self.room_entry_writes[room].append((reg, _abs_val(val)))

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


OTHER = object()      # a promoted register holds a value we do not distinguish


def _abs_val(v):
    return v if isinstance(v, int) else OTHER


def _has_atom(guard):
    """True if a guard has any evaluable OWN/FLAG/CMP atom -- i.e. it can be false.
    A guard with none (None, or only empty conjunctions / opaque atoms) is an
    UNCONDITIONAL reset that runs on room entry."""
    from model import GAnd, GOr, GNot, Pred
    if guard is None:
        return False
    if isinstance(guard, (GAnd, GOr)):
        return any(_has_atom(k) for k in guard.kids)
    if isinstance(guard, GNot):
        return _has_atom(guard.kid)
    return isinstance(guard, Pred) and guard.kind in ("OWN", "FLAG", "CMP")


def _edge_implies_write(eguard, wguard, reg, dom):
    """Does taking this edge GUARANTEE the co-located register write also fired?

    True iff, over every value `reg` could hold, wherever the edge guard can be true
    the write guard is also true -- i.e. the edge and the write share the trigger.
    Evaluated with only `reg` bound (all other atoms UNKNOWN), so this is a statement
    about the register condition alone, which is what couples them. Requires the edge
    to actually CONSTRAIN reg (else every edge would inherit every same-room write).
    """
    if eguard is None:
        return False
    constrains = any(eval3(eguard, frozenset(), {reg: {k}}) is F for k in dom)
    if not constrains:
        return False
    for k in dom:
        if eval3(eguard, frozenset(), {reg: {k}}) is not F \
                and eval3(wguard, frozenset(), {reg: {k}}) is F:
            return False
    return True


def _collect_cmp(node, out):
    """reg -> set of literals it is `==`/`!=`/... compared against, over a guard tree."""
    from model import GAnd, GOr, GNot, Pred
    if isinstance(node, (GAnd, GOr)):
        for k in node.kids:
            _collect_cmp(k, out)
    elif isinstance(node, GNot):
        _collect_cmp(node.kid, out)
    elif isinstance(node, Pred) and node.kind == "CMP":
        out[node.var].add(_lit(node.value))


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


# The comparison operators we can actually decide. `norm_tree` also mints `u<`/`u>`
# (unsigned), which are NOT here -- callers must treat a missing op as UNDECIDABLE,
# not as true. Keeping the table separate from the permissive fallback is the point:
# "cannot evaluate" and "evaluates true" must not be the same value.
_CMP = {"==": lambda v, w: v == w, "!=": lambda v, w: v != w,
        "<": lambda v, w: v < w, ">": lambda v, w: v > w,
        "<=": lambda v, w: v <= w, ">=": lambda v, w: v >= w}


def _cmp_ok(v, op, want):
    """Satisfiability of a comparison against a SET member -- permissive by design.

    Returns True for "cannot evaluate", so it is only safe where True means "do not
    block". Never read its result as a definite truth; see _atom3's LOCAL branch,
    which did exactly that.
    """
    if v is ANY:
        return True
    w = _lit(want)
    if w is ANY or not isinstance(v, int) or not isinstance(w, int):
        return True                     # can't evaluate -> permissive
    fn = _CMP.get(op)
    return True if fn is None else fn(v, w)


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
        v, w = locs[p.var], _lit(p.value)
        if not isinstance(v, int) or not isinstance(w, int) or p.op not in _CMP:
            return U            # cannot decide -> UNKNOWN, never a verdict
        # ^ this called `_cmp_ok`, whose `{...}.get(op, True)` returns True to mean
        #   "cannot evaluate, be permissive" -- and then read that sentinel as a
        #   DEFINITE truth, so an unimplemented operator became provably-true, and
        #   provably-FALSE under negation, pruning a branch the game really takes.
        #   `norm_tree` mints LOCAL preds for `u<`/`u>` too, which `_cmp_ok` does not
        #   implement; both games ship them. A "be permissive" answer and a "this is
        #   true" answer must never be the same value.
        r = _CMP[p.op](v, w)
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


def _closure_flat(m, start_room, items, fl, exhausted):
    """No-promotion fixpoint. Re-sweep, not worklist: I built the semi-naive worklist
    version (PLAN-v2 phase 5's 'Datalog-shaped' idea), diff-tested it identical on 1280
    configs across both games -- and it measured SLOWER (5.9M eval3 vs 4.0M). Flag values
    are added one at a time, so a promiscuous flag like gCurrentStatus emits ~35 events,
    and every watcher re-evaluates its whole guard per event; the batched sweep beats
    that. Kept the simple version; the closure count in requirements() is the real
    lever."""
    rooms = {start_room}
    changed = True
    while changed:
        changed = False
        for a in list(rooms):
            for b in m.edges.get(a, ()):
                if b in rooms:
                    continue
                guard = (m.machine_guards.get((a, b)) if (a, b) in m.machine_edges
                         else m.edge_reqs.get((a, b)))
                if holds_tree(guard, items, fl):
                    rooms.add(b)
                    changed = True
        for it, sites in m.acq.items():
            if it in items or it in exhausted:
                continue
            for room, guards in sites:
                if (room is None or room in rooms) and holds_tree(guards, items, fl):
                    items.add(it)
                    changed = True
                    break
        for g, sites in m.sets.items():
            for room, val, guards in sites:
                if (room is None or room in rooms) and val not in fl.get(g, ()) \
                        and holds_tree(guards, items, fl):
                    fl.setdefault(g, set()).add(val)
                    changed = True
    return Reach(rooms, items, fl)


class _Overlay:
    """`fl` with a promoted register's ONE current value spliced over its set.

    `_atom3`'s CMP branch already decides a SINGLETON flag set precisely:
    `flags[reg] == {12}` makes `== 12` true and `!= 12` false. So promotion needs no
    change to the evaluator -- carry each register as one value per state and hand
    that value through as a singleton. OTHER -> ANY (undecidable), the safe direction.
    """
    __slots__ = ("base", "over")

    def __init__(self, base, over):
        self.base, self.over = base, over

    def get(self, k, d=None):
        v = self.over.get(k)
        return v if v is not None else self.base.get(k, d)


def closure(m: FixModel, start_room, held=(), flags=None, exhausted=()):
    """Least fixpoint from a state: everything you could EVER reach/obtain.

    Reachability is over (room, register-valuation) for the PROMOTED registers
    (phase 4) -- items and non-promoted globals stay monotone. So `gCurrentStatus
    == 12` is decided against the value you actually hold HERE, not against the set
    of values it could ever take, and a mode-register gate finally binds.
    """
    items = set(held)
    fl = {k: set(v) for k, v in (flags if flags is not None else m.init_flags).items()}
    exhausted = set(exhausted)

    order = sorted(m.promoted)
    if not order:
        return _closure_flat(m, start_room, items, fl, exhausted)   # no promotion: fast path

    def _abs(v):
        return v if isinstance(v, int) else OTHER

    def _overlay(rv):
        if not order:
            return fl
        return _Overlay(fl, {order[i]: ({rv[i]} if rv[i] is not OTHER else {ANY})
                             for i in range(len(order))})

    idx = {reg: i for i, reg in enumerate(order)}

    def enter(room, rv):
        # apply a room's UNCONDITIONAL entry writes (resets) to the arriving valuation
        ew = m.room_entry_writes.get(room, []) + m.room_entry_writes.get(None, [])
        if not ew:
            return rv
        lst = list(rv)
        for reg, av in ew:
            lst[idx[reg]] = av
        return tuple(lst)

    init_rv = enter(start_room, tuple(_abs(next(iter(fl.get(r) or {0}))) for r in order))
    reach = {(start_room, init_rv)}                # (room, register-valuation)

    changed = True
    while changed:
        changed = False
        by_room = defaultdict(set)
        for (a, rv) in reach:
            by_room[a].add(rv)

        # 1. movement. Edge guard on the SOURCE valuation; then a's GUARDED exit writes
        #    (co-triggered, guard on source) produce the valuation carried out; then b's
        #    UNCONDITIONAL entry writes (resets) apply as you arrive. Entry-vs-exit is
        #    the difference between rm55's `gCurrentStatus:=0` reset (must be visible to
        #    rm55's own out-edge) and rm64's `:=10` survive branch (delivered to rm65).
        for (a, rv) in list(reach):
            ov = _overlay(rv)
            drv = list(rv)
            for reg, av, wguard in (m.room_exit_writes.get(a, []) + m.room_exit_writes.get(None, [])):
                if holds_tree(wguard, items, _overlay(tuple(drv))):
                    drv[idx[reg]] = av
            drv = tuple(drv)
            for b in m.edges.get(a, ()):
                guard = (m.machine_guards.get((a, b)) if (a, b) in m.machine_edges
                         else m.edge_reqs.get((a, b)))
                if not holds_tree(guard, items, ov):
                    continue
                nrv = enter(b, drv)
                if (b, nrv) not in reach:
                    reach.add((b, nrv))
                    changed = True

        # 2. pick up anything acquirable at SOME reachable (room, rv)
        for it, sites in m.acq.items():
            if it in items or it in exhausted:
                continue
            if any((room is None or room in by_room)
                   and _reachable_guard(guards, items, room, by_room, reach, fl, _overlay)
                   for room, guards in sites):
                items.add(it)
                changed = True
        # 3. set any NON-promoted flag whose setter is reachable
        for g, sites in m.sets.items():
            if g in m.promoted:
                continue
            for room, val, guards in sites:
                if val in fl.get(g, ()):
                    continue
                if _reachable_guard(guards, items, room, by_room, reach, fl, _overlay):
                    fl.setdefault(g, set()).add(val)
                    changed = True

    rooms = {a for (a, _rv) in reach}
    # mirror each promoted register's REACHABLE values back into fl, so .flags stays a
    # meaningful "achievable set" for callers (reports, _check_core) that read it.
    for i, reg in enumerate(order):
        fl[reg] = {rv[i] for (_a, rv) in reach}
    return Reach(rooms, items, fl)


def _reachable_guard(guards, items, room, by_room, reach, fl, overlay):
    """Does `guards` hold at some reachable state in `room` (None = anywhere)?"""
    states = reach if room is None else ((room, rv) for rv in by_room.get(room, ()))
    return any(holds_tree(guards, items, overlay(rv)) for (_a, rv) in states)


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
                # Deterministic order: singletons (must-hold) before disjunctions,
                # then lexicographic. The clauses are peeled off in whatever order the
                # minimiser happens to hit them -- QuickXplain and linear deletion find
                # the same SET but not the same sequence -- so sort for a stable
                # guard_sexpr that does not depend on the search algorithm.
                clauses.sort(key=lambda c: (len(c), c))
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
    """A MINIMAL subset of S whose absence still blocks the goal at b -- via
    QuickXplain (Junker 2004), not linear deletion. Precondition: `not W(b, S)`.

    The blocking set is almost always tiny (1-2 items: the Sunscreen, or the
    Fruit/Sewing_Kit pair), while S -- the items unrecoverable past b -- can be ~20.
    Deletion asks W() once per member of S (~20 closures); QuickXplain asks
    O(|result| * log(|S|/|result|)) (~4-6). Across requirements() that is the
    difference between 1129 W() calls and a few hundred, and it compounds on bigger
    games. `W(b, X)` True == "lacking X you can still win" == consistent.
    """
    def qx(bg, delta, cand):
        # minimal subset of `cand` that, added to lacking-set `bg`, still blocks.
        # Invariant: `bg | cand` blocks. `not W(b, X)` == "lacking X blocks".
        if delta and not W(b, bg):
            return frozenset()          # bg alone already blocks -> no candidate needed
        cand = sorted(cand)
        if len(cand) == 1:
            return frozenset(cand)      # this one is load-bearing
        mid = len(cand) // 2
        c1, c2 = frozenset(cand[:mid]), frozenset(cand[mid:])
        d2 = qx(bg | c1, c1, c2)
        d1 = qx(bg | d2, d2, c1)
        return d1 | d2

    return qx(frozenset(), frozenset(), frozenset(S))


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
