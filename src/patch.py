"""B1: LucasArts-invariant remedy synthesis (engine-agnostic).

Neutralize softlocks by implementing the maximally-permissive supervisor of the
winnability reachability game: forbid the controllable moves that leave the
winning region (the frontier edges), and delete the uncontrollable timers that
can push you out of it.

Concretely, per irreversible act-boundary edge a->b (a one-way edge in the SCC
condensation, i.e. a point of no return that still leads to the goal):

    guard(a->b) = AND own(r)  for every resource r that is
                  obtainable on the near side (reachable from a) but NOT the far
                  side (not reachable from b), and needed on the far side.

That is exactly "you can't take the irreversible edge until you have everything
you'll need past it." The stranded set comes straight from the reachability
analysis -- detection and synthesis are the same object.

Emits abstract PatchSpecs (add_guard / delete_timer) consumed by patch_sci0.py.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from model import load_game, Game                        # noqa: E402
from analyze import region_maps                          # noqa: E402
from search import SccReach, GOAL_ROOMS                  # noqa: E402


class Synth:
    def __init__(self, game: Game):
        self.g = game
        self.s = SccReach(game)
        self.members, self.room_region, self.controllers = region_maps(game)
        self.goal_comps = {self.s.comp_of[r] for r in GOAL_ROOMS if r in self.s.comp_of}

    def _src_comps(self, item):
        return {self.s.comp_of[r] for r in self.s.sources.get(item, set()) if r in self.s.comp_of}

    def can_get_from(self, comp, item):
        """Is a source of `item` still reachable once you are at component `comp`?"""
        return bool(self.s.creach.get(comp, set()) & self._src_comps(item))

    def _need_comps(self, item):
        out = set()
        for R in self.s.required.get(item, set()):
            if R in self.controllers:                      # region controller -> members
                for m in self.members.get(R, ()):
                    if m in self.s.comp_of:
                        out.add(self.s.comp_of[m])
            elif R in self.s.comp_of:
                out.add(self.s.comp_of[R])
        return out

    def stranded_by(self, a, b):
        """Resources obtainable before crossing a->b, not after, and needed after."""
        out = []
        for item in sorted(self.s.required):
            if not self.s.sources.get(item):
                continue
            if (self.can_get_from(a, item) and not self.can_get_from(b, item)
                    and (self._need_comps(item) & self.s.creach.get(b, set()))):
                out.append(item)
        return out

    def gates(self):
        """Irreversible condensation edges worth guarding, with their stranded set."""
        specs = []
        for a, bs in self.s.cedges.items():
            for b in bs:
                # only guard crossings that still lead to victory (skip death sinks)
                if not (self.s.creach.get(b, set()) & self.goal_comps):
                    continue
                stranded = self.stranded_by(a, b)
                if not stranded:
                    continue
                # room-level newRoom edges realizing this act boundary (guardable in code)
                realizers = [(ra, rb) for ra in self.s.comps[a] for rb in self.s.comps[b]
                             if rb in self.s.edges.get(ra, set())
                             and "goto" in self.s.edge_kind.get((ra, rb), set())]
                if not realizers:
                    continue
                specs.append({"comp_from": a, "comp_to": b,
                              "realizers": realizers, "stranded": stranded})
        return specs

    def patch_specs(self):
        out = []
        for gate in self.gates():
            items = [{"id": i, "name": self.g.item_name(i)} for i in gate["stranded"]]
            for (ra, rb) in gate["realizers"]:
                out.append({
                    "op": "add_guard",
                    "pattern": "irreversible-edge / LucasArts invariant",
                    "room": ra, "newroom_target": rb,
                    "require_items": items,
                    "guard_sexpr": "(and " + " ".join(f"(gEgo has: {i['id']})" for i in items) + ")",
                    "rationale": (f"crossing rm{ra}->rm{rb} strands "
                                  + ", ".join(i["name"] for i in items)
                                  + " (obtainable before, needed after, not gettable after)"),
                })
        # forcing timers: uncontrollable transitions that set an irreversible latch
        for tspec in self._forcing_timers():
            out.append(tspec)
        return out

    def _forcing_timers(self):
        """Timers whose per-cycle firing sets a one-way latch -> delete candidates."""
        from analyze import timed_edges, derived_maps, irreversible_globals
        latches = irreversible_globals(self.g, derived_maps(self.g)[3])
        out = []
        for te in timed_edges(self.g):
            sets_latch = [e for e in te.get("effects", []) if e.startswith("set(") and
                          any(l in e for l in latches)]
            if sets_latch:
                out.append({"op": "delete_timer", "room": te["room"],
                            "context": te["context"], "timer_guard": te["timer_guard"],
                            "effects": te["effects"],
                            "rationale": "uncontrollable timer sets a one-way latch; "
                                         "cannot supervise a clock, so remove it"})
        return out


def main():
    game = load_game()
    synth = Synth(game)
    specs = synth.patch_specs()
    guards = [s for s in specs if s["op"] == "add_guard"]
    timers = [s for s in specs if s["op"] == "delete_timer"]

    print(f"PatchSpecs: {len(guards)} edge-guards, {len(timers)} timer-deletions\n")
    print("=== edge guards (LucasArts: can't cross until you hold these) ===")
    for g in guards:
        names = ", ".join(i["name"] for i in g["require_items"])
        print(f"  rm{g['room']} → rm{g['newroom_target']} : require [{names}]")
    print("\n=== forcing-timer deletions ===")
    for t in timers:
        print(f"  rm{t['room']} {t['context']}: {t['timer_guard']} -> {t['effects'][:2]}")

    path = os.path.join(os.path.dirname(__file__), "..", "reports", "patch_specs.json")
    with open(path, "w") as f:
        json.dump(specs, f, indent=1)
    print(f"\nwrote {os.path.normpath(path)}")
    return specs


if __name__ == "__main__":
    main()
