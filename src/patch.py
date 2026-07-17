"""B1: LucasArts-invariant remedy synthesis (engine-agnostic).

!! DISABLED -- THIS SYNTHESIS PATH EMITS A GAME-BREAKING PATCH. See DISABLED_WHY
!! below and `main()`. It is kept only as the reference for the semantic
!! replacement; it must not be run against a real game.

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
from search import SccReach                              # noqa: E402


DISABLED_WHY = """\
patch.py is DISABLED: its guards are synthesized from the SYNTACTIC core
(search.SccReach), which is UNSOUND for synthesis. It cannot tell an item that
SAVES you from one that KILLS you -- it only sees that some `OWN(x)` guard is
mentioned in a room. It therefore emitted, and we shipped:

    rm38 -> rm131 : (and (gEgo has: 11) (gEgo has: 12) (gEgo has: 13) (gEgo has: 14))
                                                  ^^^^^^^^^^^^^^^^ Spinach_Dip

The Spinach_Dip is FATAL. LSL2 rm138 (the raft) state 6, day 6 tests it FIRST and
jumps to state 15 -> ... -> 26 -> `(= gCurrentStatus 1001)`:
"Unfortunately for you, the mayonnaise has spoiled in the hot, tropical sun!"
Day 6 actually needs Sewing_Kit OR Fruit, and holding the dip kills you even if
you also hold them. So this guard FORCES the fatal item and makes LSL2
unwinnable; it is wrong on 3 of its 4 items (two are OR-alternatives ANDed
together, one is a death sentence).

validate_patch.py did not catch it because it imports the SAME SccReach core --
the detector, the synthesizer and the "proof" all share one blind spot: none of
them models a room's Script state machine, where the whole raft gauntlet lives.

Re-enable only when guards come from the semantic core (closure.py) with state
machines lifted, so that "needed past this edge" is DERIVED from winnability
rather than from an item being mentioned. Until then, running this would
regenerate a patch that breaks the game.
"""


class Synth:
    def __init__(self, game: Game):
        self.g = game
        self.s = SccReach(game)

    def patch_specs(self, force=False):
        # The refusal lives HERE, not in main(): patch_trigger.py and
        # patch_ericoakford.py import Synth and call this directly, so a check in
        # main() would not stop them regenerating the broken guard.
        if not force:
            raise RuntimeError(DISABLED_WHY)

        # Detection and synthesis are the SAME object: guards come straight from the
        # shared gate-aware stranding core (SccReach.edge_strandings), the same
        # primitive the report (search.analyze) reads. One library, no drift.
        #
        # ^ That was the claim. It is exactly the defect: the ONE library is the
        #   syntactic core, which cannot distinguish a protective item from a fatal
        #   one, and the validator shares its blind spot. See DISABLED_WHY.
        out = []
        for es in self.s.edge_strandings():
            ra, rb = es["from_room"], es["to_room"]
            items = [{"id": i, "name": self.g.item_name(i)} for i in es["items"]]
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


def main(force=False):
    if not force:
        print(DISABLED_WHY)
        print("Refusing to synthesize. (src/patch.py --force to run it anyway; the "
              "output is known-wrong and must not be compiled into a game.)")
        return 1

    game = load_game()
    synth = Synth(game)
    specs = synth.patch_specs(force=True)
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
        # The DO-NOT-SHIP banner must be REPRODUCIBLE, not hand-added to the artifact.
        # This used to `json.dump(specs, ...)` -- a bare list -- while the committed
        # file was a dict wrapping the specs in `_DISABLED`/`_why`. So the one
        # documented way to regenerate it (`patch.py --force`) silently stripped the
        # warning and left the fatal rm38->rm131 guard behind, reading exactly like the
        # version that was believed shippable. The whole safety story for this file is
        # "retained only as a record of what went wrong"; a story that lives only in an
        # artifact nothing can reproduce is not a safety story.
        json.dump({
            "_DISABLED": "KNOWN-WRONG OUTPUT -- DO NOT COMPILE OR SHIP.",
            "_why": DISABLED_WHY.strip(),
            "_superseded_by": ("closure.requirements() -- CNF from minimal blocking "
                               "sets, which excludes the fatal Spinach_Dip by "
                               "construction and gets Fruit-OR-Sewing_Kit right"),
            "specs": specs,
        }, f, indent=1)
    print(f"\nwrote {os.path.normpath(path)} (with the DO-NOT-SHIP banner)")
    return specs


if __name__ == "__main__":
    raise SystemExit(main(force="--force" in sys.argv) or 0)
