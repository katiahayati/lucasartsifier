"""Auto-discover the per-game config knobs from the decompiled scripts.

The knobs in config.py (timers, start room, goal rooms, region labels) were set by
hand while prototyping on LSL2 -- but each is really the codification of a manual
step. This module performs those steps automatically and emits a *proposed*
GameConfig. Everything is derived except the winning terminal, which is proposed
as ranked candidates for a single human confirmation (the plan's one manual step).

Run:  python3 src/discover.py
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from model import load_game, Game                        # noqa: E402
from analyze import movement_graph, region_maps, is_room, derived_maps  # noqa: E402
import config                                            # noqa: E402


def reachable(edges, start):
    seen = set(start)
    stack = list(start)
    while stack:
        u = stack.pop()
        for v in edges.get(u, ()):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def _room_text(src_dir):
    """raw text per room script number (message strings + decompiler comments)."""
    out = {}
    for path in glob.glob(os.path.join(src_dir, "rm*.sc")):
        m = re.search(r"rm(\d+)\.sc$", path)
        if m:
            out[int(m.group(1))] = open(path, encoding="latin-1").read()
    return out


# --------------------------------------------------------------------------
def discover_timers(game: Game):
    """A timer/counter is a global COMPARED in a guard that is also DRIVEN like a
    clock: written per-cycle in a `doit`, or stepped (++/--/+=/-=). Catching both
    directions matters -- e.g. gRgTimer counts *down*, gCurrentTimer is a status
    counter, gGameSeconds counts up."""
    compared, in_doit, stepped = set(), set(), set()
    for s in game.scripts.values():
        for t in s.transitions:
            doit = ":doit" in t.context
            for p in t.guards:
                if p.kind == "CMP":
                    compared.add(p.var)
            for e in t.effects:
                if e.kind != "SET":
                    continue
                if doit:
                    in_doit.add(e.arg)
                stepping = e.receiver in ("++", "--", "+=", "-=") or (
                    isinstance(e.value, str)
                    and (e.value.startswith(f"(+ {e.arg}") or e.value.startswith(f"(- {e.arg}")))
                if stepping:
                    stepped.add(e.arg)
    timers = compared & (in_doit | stepped)
    return {"timers": sorted(timers),
            "per_cycle_timers": sorted(compared & in_doit),
            "stepped_timers": sorted(compared & stepped),
            "evidence": "compared-in-guard AND (written per-cycle in a doit OR stepped ++/--)"}


def discover_start(game: Game, edges):
    """Start = a player-controlled room whose forward reach covers ~everything
    (the source act of the progression)."""
    rooms = [n for n in game.scripts if is_room(game, n)]
    fwd = {r: len(reachable(edges, {r})) for r in rooms}
    mx = max(fwd.values()) if fwd else 0
    # player-controlled rooms: init hands control to the player
    txt = _room_text(config.ACTIVE.src_dir)
    controlled = {r for r in rooms if re.search(r"HandsOn|NormalEgo", txt.get(r, ""))}
    act = sorted(r for r in rooms if fwd[r] >= 0.95 * mx)          # the start act
    cands = sorted((r for r in act if r in controlled), key=lambda r: (-fwd[r], r)) or act
    return {"proposed": cands[0] if cands else None,
            "start_act_rooms": act,
            "max_forward_reach": mx,
            "evidence": "player-controlled room with ~maximal forward reachability"}


VICTORY = ["congratulat", "happily ever", "married", "the wedding", "you win",
           "you have won", "the end", "\\05"]  # \05 = SCI end-of-game marker
DEATH = ["screwed up", "restart:", "gGame restart"]


def discover_goal(game: Game, edges):
    """Rank rooms as winning-terminal candidates from victory text + structure,
    excluding the death modal. Returns candidates for HUMAN CONFIRMATION."""
    txt = _room_text(config.ACTIVE.src_dir)
    rooms = [n for n in game.scripts if is_room(game, n)]
    outdeg = {r: len(edges.get(r, ())) for r in rooms}
    death_rooms = sorted(r for r in rooms
                         if any(w in txt.get(r, "").lower() for w in DEATH))
    scored = []
    for r in rooms:
        low = txt.get(r, "").lower()
        vscore = sum(low.count(w) for w in VICTORY)
        if vscore == 0:
            continue
        is_death = any(w in low for w in DEATH)
        late = r >= 70                       # heuristic: endgame rooms are late-numbered
        sink = outdeg.get(r, 0) == 0
        rank = vscore + (2 if late else 0) + (1 if sink else 0) - (5 if is_death else 0)
        scored.append({"room": r, "victory_hits": vscore, "late": late,
                       "sink": sink, "is_death": is_death, "rank": rank})
    scored.sort(key=lambda d: -d["rank"])
    return {"candidates_for_confirmation": scored[:8],
            "death_rooms_detected": death_rooms,
            "evidence": "victory text + late/sink structure, minus death modal"}


PLACE_WORDS = {"los angeles": "Los Angeles", "nontoonyt": "Nontoonyt Island",
               "island": "island", "ship": "cruise ship", "lifeboat": "lifeboat",
               "airplane": "airplane", "airport": "airport", "volcano": "volcano",
               "jungle": "jungle"}


def discover_region_labels(game: Game):
    """Cosmetic: best-effort place name per region from its rooms' text."""
    txt = _room_text(config.ACTIVE.src_dir)
    members, _, _ = region_maps(game)
    labels = {}
    for rg, rooms in members.items():
        counts = defaultdict(int)
        for r in rooms:
            low = txt.get(r, "").lower()
            for kw, label in PLACE_WORDS.items():
                counts[label] += low.count(kw)
        if counts:
            best = max(counts, key=counts.get)
            if counts[best] > 0:
                labels[rg] = best
    return labels


def main():
    game = load_game()
    edges, _ = movement_graph(game)
    timers = discover_timers(game)
    start = discover_start(game, edges)
    goal = discover_goal(game, edges)
    labels = discover_region_labels(game)

    print("=" * 72)
    print("PROPOSED CONFIG (auto-discovered)   —  confirm the goal, the rest is derived")
    print("=" * 72)
    print(f"\ntimers        : {timers['timers']}")
    print(f"  per-cycle   : {timers['per_cycle_timers']}")
    print(f"\nstart_room    : {start['proposed']}  (start act = {start['start_act_rooms'][:12]}"
          f"{'…' if len(start['start_act_rooms']) > 12 else ''})")
    print(f"\ngoal_rooms    : NEEDS HUMAN CONFIRMATION — ranked candidates:")
    for c in goal["candidates_for_confirmation"]:
        tag = " [DEATH?]" if c["is_death"] else ""
        print(f"    rm{c['room']:<4} rank={c['rank']:<3} victory_hits={c['victory_hits']} "
              f"late={c['late']} sink={c['sink']}{tag}")
    print(f"  death modal rooms detected: {goal['death_rooms_detected']}")
    print(f"\nregion_labels : {labels}")

    # validate against the hand-set config
    cfg = config.LSL2
    print("\n" + "-" * 72)
    print("VALIDATION vs hand-set config.LSL2")
    print("-" * 72)
    disc_t = set(timers["timers"])
    real_handset = {g for g in cfg.timer_globals if g in game.globals}
    missing = real_handset - disc_t
    print(f"timers: hand-set {sorted(cfg.timer_globals)}")
    print(f"        (of those, actually exist as globals: {sorted(real_handset)}; "
          f"the rest were speculative)")
    print(f"        discovered {sorted(disc_t)}")
    print(f"        finds every REAL hand-set timer? {not missing}"
          f"{'' if not missing else '  MISSING: ' + str(sorted(missing))}")
    print(f"start:  hand-set rm{cfg.start_room}; in discovered start act? "
          f"{cfg.start_room in start['start_act_rooms']}")
    top_goal = {c['room'] for c in goal['candidates_for_confirmation']}
    print(f"goal:   hand-set {sorted(cfg.goal_rooms)}; surfaced in candidates: "
          f"{sorted(set(cfg.goal_rooms) & top_goal)}")

    # a paste-able proposal (goal left for the human to confirm from the ranked list)
    top = [c["room"] for c in goal["candidates_for_confirmation"][:4]]
    print("\n" + "-" * 72)
    print("PASTE INTO src/config.py after confirming goal_rooms from the ranked list:")
    print("-" * 72)
    print(f"""GameConfig(
    name="<title>",
    src_dir="<decompiled .sc dir>",
    start_room={start['proposed']},
    goal_rooms=frozenset({{ ...CONFIRM... }}),   # top candidates: {top}
    goal_scripts=( ...CONFIRM... ),
    timer_globals=frozenset({set(timers['per_cycle_timers'])}),
    region_labels={labels},
)""")

    out = {"timers": timers, "start": start, "goal": goal, "region_labels": labels}
    path = os.path.join(os.path.dirname(__file__), "..", "reports", "discovered_config.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote {os.path.normpath(path)}")
    return out


if __name__ == "__main__":
    main()
