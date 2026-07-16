"""M2/M3 core: derived maps, timed edges, irreversibility, movement reachability,
and a first pass of softlock candidates (missing-prereq-before-gate + sealed-area).

Method (conservative, per PLAN.md "no false alarms"):
  * Movement graph over-approximates: an inter-room GOTO edge is assumed
    traversable regardless of its guard. Over-approximating reachability means we
    only flag a softlock when even this *generous* graph cannot recover the
    resource -- biasing toward false negatives, which engine verification (M4)
    can then shore up, rather than false positives.
  * "Item X needed at room R" = an OWN(X) guard occurs in R. Candidate softlock:
    R is reachable but NO source of X is reachable from R (you can't go back for
    it). The one-way edge that cut R off from X's sources is the frontier.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict, deque

from model import load_game, Game
from config import ACTIVE as CFG

REPORTS = os.path.join(os.path.dirname(__file__), "..", "reports")

# game clocks / timers, for timed-gate detection; region labels for readability.
# NOTE: these were bound at import time, so swapping config.ACTIVE afterwards left
# them pointing at the old game. Read through to the live config instead.
class _LiveCfg:
    def __init__(self, attr):
        self._attr = attr

    def _v(self):
        import config
        return getattr(config.ACTIVE, self._attr)

    def __contains__(self, x):
        return x in self._v()

    def __iter__(self):
        return iter(self._v())

    def __len__(self):
        return len(self._v())

    def get(self, k, d=None):
        return self._v().get(k, d)

    def __getitem__(self, k):
        return self._v()[k]

    def items(self):
        return self._v().items()

    def __repr__(self):
        return repr(self._v())


TIMER_GLOBALS = _LiveCfg("timer_globals")
REGION_LABELS = _LiveCfg("region_labels")


def is_room(game: Game, num: int) -> bool:
    nm = game.scripts[num].name if num in game.scripts else ""
    return nm.startswith("rm") or (isinstance(num, int) and 0 < num < 1000 and nm.startswith("rm"))


def region_maps(game: Game):
    """region controller script # -> set of member rooms that attach it, and the
    reverse room -> regions. Region controllers (rm200/300/...) are not walkable
    rooms; requirements evaluated 'in region N' hold while in any member room."""
    members = defaultdict(set)   # region# -> {rooms}
    room_region = defaultdict(set)
    for num, s in game.scripts.items():
        for rg in s.regions:
            members[rg].add(num)
            room_region[num].add(rg)
    controllers = set(members)   # region numbers that are attached by some room
    return members, room_region, controllers


def where_needed(R, members, controllers):
    """Location set from which a requirement at script R is actually faced."""
    if R in controllers:
        return set(members[R]) or {R}
    return {R}


# --------------------------------------------------------------------------
def derived_maps(game: Game):
    sources = defaultdict(set)     # item -> {room where ACQUIRE}
    drops = defaultdict(set)       # item -> {room where DROP}
    required = defaultdict(set)    # item -> {room where OWN(item, want=True) guards something}
    global_sets = defaultdict(list)   # global -> [(room, value)]
    for num, s in game.scripts.items():
        for t in s.transitions:
            for e in t.effects:
                if e.kind == "ACQUIRE":
                    sources[e.arg].add(num)
                elif e.kind == "DROP":
                    drops[e.arg].add(num)
                elif e.kind == "SET":
                    global_sets[e.arg].append((num, e.value))
            for p in t.guards:
                if p.kind == "OWN" and p.want:
                    required[p.var].add(num)
    return sources, drops, required, global_sets


def movement_graph(game: Game):
    """directed room->room edges from three SCI0 movement mechanisms:
    (1) literal (newRoom: N) GOTO effects, (2) Rm edge properties
    north/south/east/west, (3) Door `entranceTo:` targets."""
    edges = defaultdict(set)       # from_room -> {to_room}
    edge_kind = defaultdict(set)   # (from,to) -> {'goto','edge','door'}
    for num, s in game.scripts.items():
        if not is_room(game, num):
            continue
        for t in s.transitions:
            for e in t.effects:
                if e.kind == "GOTO" and isinstance(e.arg, int) and e.arg != num:
                    edges[num].add(e.arg)
                    edge_kind[(num, e.arg)].add("goto")
        for _dir, dest in s.exits.items():
            if dest != num:
                edges[num].add(dest)
                edge_kind[(num, dest)].add("edge")
        for dest in s.doors:
            if dest != num:
                edges[num].add(dest)
                edge_kind[(num, dest)].add("door")
    return edges, edge_kind


def edge_requirements(game: Game):
    """Guards that must hold to TRAVERSE each movement edge a->b -> `[Pred]`.

    Movement edges are NOT free. That single omission is the bug behind the
    parachute, the sand/ashes argument, the rm55->56 false positive and the whale:
    the room graph dropped edge guards and we re-approximated them with `_sealed`
    ever since.

    The guard is rarely on the `newRoom` itself. Inside the whale (rm44) the
    `newRoom: 31` sits in `tickle:changeState` with NO guard at all, while the
    feather check that lets you start the tickle is over in `Room44:handleEvent`.
    So an edge's precondition is its GOTO transition's own guards PLUS those of
    whatever ACTIVATES the instance owning that GOTO -- either `(tickle
    changeState: 1)` from another instance, or `(self changeState: K)` issued from
    a handleEvent/doit, which is the controllable trigger of its own machine.

    Preconditions can be FLAGS as well as items: the parachute jump rm63->64 is
    traversable without the chute (you just die at rm64) -- what actually gates the
    survival edge rm64->65 is `wearingParachute`. So keep every evaluable Pred
    (OWN/FLAG/CMP) and let the fixpoint decide, rather than only collecting items.

    Multiple activators are ALTERNATIVE ways to trigger the same sequence, so their
    guards form a disjunction. We intersect them (what EVERY route requires), which
    under-approximates the precondition -- conservative: it can only ever miss a
    requirement, never invent one.
    """
    def _evaluable(preds):
        return [p for p in preds if p.kind in ("OWN", "FLAG", "CMP")]

    def _key(p):
        return (p.kind, p.var, p.op, str(p.value), p.want)

    reqs = {}
    for num, s in game.scripts.items():
        acts = defaultdict(list)                # instance -> [(target_state, transition)]
        for t in s.transitions:
            ctx = t.context or ""
            inst, meth = _instance_of(ctx), _method_of(ctx)
            for e in t.effects:
                if e.kind != "STATE" or not isinstance(e.arg, int):
                    continue
                if e.receiver and e.receiver != "self":
                    acts[e.receiver].append((e.arg, t))   # started from another instance
                elif meth != "changeState":
                    # `(self changeState: K)` from handleEvent/doit is the controllable
                    # trigger that STARTS this machine (vs. a state advancing itself).
                    acts[inst].append((e.arg, t))
        for t in s.transitions:
            ctx = t.context or ""
            inst, st = _instance_of(ctx), _state_of(ctx)
            for e in t.effects:
                if e.kind != "GOTO" or not isinstance(e.arg, int):
                    continue
                ps = {_key(p): p for p in _evaluable(t.guards)}
                # Which trigger leads HERE? A machine has many entry points (rm57Script
                # is entered at 1, 4, ...); the one that reaches state `st` is the
                # nearest with target K <= st. Same heuristic trigger.py already proves.
                cands = [(k, at) for (k, at) in acts.get(inst, ())
                         if st is None or k <= st]
                if cands:
                    kmax = max(k for k, _ in cands)
                    sets = [{_key(p): p for p in _evaluable(at.guards)}
                            for k, at in cands if k == kmax]
                    common = set(sets[0])
                    for d in sets[1:]:
                        common &= set(d)        # several routes to K -> intersect
                    for key in common:
                        ps.setdefault(key, sets[0][key])
                if ps:
                    reqs.setdefault((num, e.arg), {}).update(ps)
    return {k: list(v.values()) for k, v in reqs.items()}


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


def irreversible_globals(game: Game, global_sets):
    """A global is a set-once *story flag* latch if every assignment is an integer
    literal, at least one is non-zero, and it is never reset to 0 (nothing undoes
    it). We require int literals to exclude engine-init aliases (gEgo:=ego, ...)."""
    latches = {}
    for gname, assigns in global_sets.items():
        ints, all_int, has_reset = set(), True, False
        for _, val in assigns:
            try:
                iv = int(val)
                ints.add(iv)
                if iv == 0:
                    has_reset = True
            except (TypeError, ValueError):
                all_int = False
                break
        if all_int and ints and not has_reset and all(v != 0 for v in ints):
            latches[gname] = sorted(str(v) for v in ints)
    return latches


# Deaths. `terminals()` used to live here: it looked for rooms with no outgoing
# edge whose text mentioned the restart modal. It could never work -- in BOTH games
# death is raised from Main's doit via a global write, not from a terminal room, so
# it returned zero death rooms for LSL2. The model now emits Effect("DEATH")
# directly (see config.death_signal), with the path condition attached, so we
# classify those instead of guessing from room text.

TRIGGER_SAID = "SAID"            # a player verb reached it
TRIGGER_TIMED = "TIMED"          # a clock/counter guard reached it
TRIGGER_RANDOM = "RANDOM"        # a Random() decides whether the hazard fires
TRIGGER_POSITIONAL = "POSITIONAL"  # proximity / onControl geometry
TRIGGER_SCRIPTED = "SCRIPTED"    # a changeState sequence with no other tell

PROT_ITEM = "ITEM"               # `ego has: X` avoids it
PROT_GLOBAL = "GLOBAL"           # a flag avoids it (LSL2 gWearingSunscreen)
PROT_POSITIONAL = "POSITIONAL"   # only geometry avoids it ("don't walk on green")
PROT_NONE = "NONE"               # unavoidable / narrative


# Context is `instance:method[:state]`, e.g. `deadTimer:changeState:22`.
def _instance_of(context):
    """`deadTimer:changeState:22` -> `deadTimer`. The Script instance that owns it."""
    return (context or "").split(":")[0]


def _method_of(context):
    """`deadTimer:changeState:22` -> `changeState`."""
    parts = (context or "").split(":")
    return parts[1] if len(parts) > 1 else ""


def _state_of(context):
    """`deadTimer:changeState:22` -> 22; None if not inside a switch case."""
    parts = (context or "").split(":")
    if len(parts) > 2:
        try:
            return int(parts[2])
        except ValueError:
            return None
    return None


def death_sites(game: Game):
    """Every DEATH effect, classified.

    Crucially the protective condition is almost never on the death transition
    itself: the item check SELECTS WHICH STATE you enter, and the death sits in a
    later state with no guard at all (rm34 sunscreen in state 13, death in 14;
    rm44 feather in state 0, death in 22 -- 86 source lines apart; rm16 scarab in
    state 3, death in 13). So we aggregate evidence across the whole owning Script
    INSTANCE, not just the death's own path condition.

    We classify trigger/protection only. Fairness is deliberately NOT decided here
    -- it is not syntactically separable (protective conditions are often globals
    in another state, sometimes inverted, while genuinely reckless deaths do carry
    `has:` guards). A death is 'actionable' iff its protection turns out to be
    STRANDED, which the stranding analysis decides.
    """
    out = []
    for num, s in game.scripts.items():
        for t in s.transitions:
            if not any(e.kind == "DEATH" for e in t.effects):
                continue
            ctx = t.context or ""
            inst = _instance_of(ctx)
            # Scope = the whole ROOM SCRIPT, not just the owning instance. The whale
            # forced this: rm44's death is in `deadTimer`, but the feather check that
            # saves you is in `Room44:handleEvent` -- a different instance entirely.
            # (Guards also only survive if they gate a MODELED effect, so we rely on
            # a nearby SCORE/STATE/SET in the same branch carrying them.)
            sib_guards = [p for st in s.transitions for p in st.guards]
            sib_kinds = {p.kind for p in sib_guards}

            # --- protection: what, anywhere in this state machine, avoids it? ---
            # Either polarity counts: `(ego has: iScarab) -> survive` and
            # `(not (ego has: iAirsickBag)) -> die` both mark the item protective.
            prot_items = sorted({p.var for p in sib_guards if p.kind == "OWN"})
            # FLAG is a bare truthiness test; CMP is `(== gWearingSunscreen 1)` --
            # LSL2's protective conditions are mostly the latter, so both count.
            prot_flags = sorted({p.var for p in sib_guards
                                 if p.kind in ("FLAG", "CMP") and p.var not in TIMER_GLOBALS})
            if prot_items:
                prot = PROT_ITEM
            elif prot_flags:
                prot = PROT_GLOBAL
            elif "POS" in sib_kinds:
                prot = PROT_POSITIONAL
            else:
                prot = PROT_NONE

            # --- trigger: what reached this death (instance-wide evidence) ---
            if any(p.kind == "CMP" and p.var in TIMER_GLOBALS for p in sib_guards):
                trig = TRIGGER_TIMED
            elif "SAID" in sib_kinds:
                trig = TRIGGER_SAID
            elif "POS" in sib_kinds or ":doit" in ctx:
                trig = TRIGGER_POSITIONAL
            else:
                trig = TRIGGER_SCRIPTED

            out.append({
                "script": num, "name": s.name, "context": ctx, "instance": inst,
                "trigger": trig, "protection": prot,
                "protective_items": [game.item_name(i) for i in prot_items],
                "protective_flags": prot_flags,
                "own_guards": [str(p) for p in t.guards][:4],
            })
    return out


def timed_edges(game: Game):
    """Transitions whose guard compares a timer global, or that live in a room
    that increments a timer global -- candidate automatic/timed gates."""
    out = []
    for num, s in game.scripts.items():
        room_ticks = any(
            e.kind == "SET" and e.arg in TIMER_GLOBALS and e.receiver in ("++", "+=")
            for t in s.transitions for e in t.effects
        )
        for t in s.transitions:
            timer_guard = [p for p in t.guards if p.kind == "CMP" and p.var in TIMER_GLOBALS]
            gotos = [e for e in t.effects if e.kind == "GOTO"]
            sets_latch = [e for e in t.effects if e.kind == "SET"]
            if timer_guard and (gotos or sets_latch):
                out.append({
                    "room": num, "context": t.context,
                    "timer_guard": [repr(p) for p in timer_guard],
                    "effects": [repr(e) for e in t.effects],
                })
        if room_ticks:
            out.append({"room": num, "context": "<room doit ticks a timer>",
                        "timer_guard": ["increments " +
                                        ",".join(sorted({e.arg for t in s.transitions
                                                         for e in t.effects
                                                         if e.kind == "SET" and e.arg in TIMER_GLOBALS}))],
                        "effects": []})
    return out


def can_reach_source(game, edges, srcs):
    """Set of rooms from which at least one source is still reachable."""
    out = set()
    for r in [n for n in game.scripts if is_room(game, n)]:
        if reachable(edges, {r}) & srcs:
            out.add(r)
    return out


def frontier_edges(game, edges, canreach):
    """Point-of-no-return edges: (a->b) with a able to reach a source, b not.
    Crossing one strands the resource permanently."""
    fr = []
    for a, bs in edges.items():
        if a not in canreach:
            continue
        for b in bs:
            if b not in canreach:
                fr.append((a, b))
    return fr


def reg_label(regs):
    return [f"{r}={REGION_LABELS[r]}" if r in REGION_LABELS else str(r) for r in regs]


def prereq_before_gate(game: Game, sources, required, edges):
    """Candidate softlocks: item needed at location L but, once you're at L, no
    source of it is reachable (you crossed a point of no return without it).

    Region-controller requirements expand to member rooms; requirements in
    non-room scripts (Main / class libraries) are not location-gated and skipped.
    """
    members, room_region, controllers = region_maps(game)
    cands = []
    for item, need_scripts in required.items():
        srcs = sources.get(item, set())
        if not srcs:
            continue  # required but never obtainable -> coverage issue, not a softlock
        canreach = can_reach_source(game, edges, srcs)
        fr = frontier_edges(game, edges, canreach)
        seen_locsets = set()
        for R in sorted(need_scripts):
            # only location-gated requirements: rooms or region controllers
            if R not in game.scripts or not (is_room(game, R) or R in controllers):
                continue
            locset = where_needed(R, members, controllers)
            key = frozenset(locset)
            if key in seen_locsets:
                continue
            seen_locsets.add(key)
            reach = set()
            for L in locset:
                reach |= reachable(edges, {L})
            if srcs & reach:
                continue  # you can still go get it -> not a softlock
            regs = sorted({r for L in locset for r in room_region.get(L, set())})
            src_regs = sorted({r for s in srcs for r in room_region.get(s, set())})
            # is this need across a *region* boundary (structural PONR)? -> higher confidence
            cross_region = bool(regs) and bool(src_regs) and not (set(regs) & set(src_regs))
            cands.append({
                "pattern": "missing-prereq-before-gate",
                "item": item, "item_name": game.item_name(item),
                "needed_at_script": R, "needed_where": game.scripts[R].name,
                "need_region": reg_label(regs),
                "source_rooms": sorted(game.scripts[s].name for s in srcs if s in game.scripts),
                "source_region": reg_label(src_regs),
                "frontier_edges": [f"rm{a}->rm{b}" for a, b in sorted(fr)][:8],
                "confidence": "high" if cross_region else "medium",
                "note": "no source reachable once the need-location is reached (point of no return)",
            })
    cands.sort(key=lambda c: (c["confidence"] != "high", c["item_name"]))
    return cands


def main(src_dir=None):
    game = load_game(src_dir) if src_dir else load_game()
    from model import SRC_DEFAULT
    sources, drops, required, global_sets = derived_maps(game)
    edges, edge_info = movement_graph(game)
    latches = irreversible_globals(game, global_sets)
    timers = timed_edges(game)
    cands = prereq_before_gate(game, sources, required, edges)
    deaths = death_sites(game)

    os.makedirs(REPORTS, exist_ok=True)
    report = {
        "death_sites": deaths,
        "items": {str(k): v for k, v in game.items.items()},
        "n_globals": len(game.globals),
        "item_sources": {game.item_name(i): sorted(r) for i, r in sorted(sources.items())},
        "item_required_at": {game.item_name(i): sorted(r) for i, r in sorted(required.items())},
        "item_reversible_drop": {game.item_name(i): sorted(r) for i, r in sorted(drops.items())},
        "irreversible_global_latches": latches,
        "timed_edges": timers,
        "softlock_candidates": cands,
        "movement_rooms": len([n for n in game.scripts if is_room(game, n)]),
        "movement_edges": sum(len(v) for v in edges.values()),
    }
    with open(os.path.join(REPORTS, "lsl2_phaseA.json"), "w") as f:
        json.dump(report, f, indent=1)

    print(f"rooms={report['movement_rooms']} edges={report['movement_edges']} "
          f"latches={len(latches)} timed={len(timers)} candidates={len(cands)}")
    from collections import Counter as _C
    print(f"death sites: {len(deaths)}  by trigger={dict(_C(d['trigger'] for d in deaths))}  "
          f"by protection={dict(_C(d['protection'] for d in deaths))}")
    print("\n=== irreversible global latches (set-once, never reset) — top 12 ===")
    for k, v in list(latches.items())[:12]:
        print(f"  {k} := {v}")
    print("\n=== timed-gate candidates (timer-compared transitions) — top 8 ===")
    for t in timers[:8]:
        print(f"  rm{t['room']} {t['context']}: {t['timer_guard']} -> {t['effects'][:3]}")
    print("\n=== softlock candidates (missing-prereq-before-gate) ===")
    for c in cands:
        rg = f"region {c['need_region']}" if c['need_region'] else c['needed_where']
        print(f"  need '{c['item_name']}' in {rg}; obtainable only in "
              f"{c['source_rooms']} — unreachable once there")
    return report


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    main()
