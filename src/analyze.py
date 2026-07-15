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

# game clocks / timers, for timed-gate detection; region labels for readability
TIMER_GLOBALS = CFG.timer_globals
REGION_LABELS = CFG.region_labels


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


def terminals(game: Game, edges):
    """Rooms with no outgoing movement edge: candidate death/ending terminals.
    Death is signalled by the Main restart modal; ending rooms show congrats text."""
    death_rooms, ending_rooms, other = [], [], []
    import glob as _glob
    import os as _os
    srcdir = SRC_DIR_HINT[0]
    for num, s in game.scripts.items():
        outdeg = len(edges.get(num, ()))
        if not is_room(game, num) or outdeg > 0:
            continue
        path = _os.path.join(srcdir, f"{s.name}.sc") if srcdir else None
        txt = ""
        if path and _os.path.exists(path):
            txt = open(path, encoding="latin-1").read()
        if "restart:" in txt or "you've screwed up" in txt.lower():
            death_rooms.append(num)
        elif "ongratulat" in txt or "you win" in txt.lower() or "married" in txt.lower():
            ending_rooms.append(num)
        else:
            other.append(num)
    return {"death_terminal_rooms": sorted(death_rooms),
            "ending_terminal_rooms": sorted(ending_rooms),
            "other_terminal_rooms": sorted(other)}


SRC_DIR_HINT = [None]  # set in main() so terminals() can read raw source for text cues


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
    SRC_DIR_HINT[0] = src_dir or SRC_DEFAULT
    sources, drops, required, global_sets = derived_maps(game)
    edges, edge_info = movement_graph(game)
    latches = irreversible_globals(game, global_sets)
    timers = timed_edges(game)
    cands = prereq_before_gate(game, sources, required, edges)
    term = terminals(game, edges)

    os.makedirs(REPORTS, exist_ok=True)
    report = {
        "goal_death": term,
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
    print(f"terminals: death={term['death_terminal_rooms']} ending={term['ending_terminal_rooms']} "
          f"other={term['other_terminal_rooms']}")
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
