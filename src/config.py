"""Game configuration: the per-game knobs kept out of the engine-general code.

Everything else in src/ is generic SCI0 machinery (S-expr reader, IR extraction,
name resolution, Rm/Door/region navigation, COI slice, SCC reachability). The
handful of things that are *specific to a title* live here so the same pipeline
can point at another SCI0 game by swapping the config.

Which of these could be auto-discovered instead of configured is discussed in the
README ("Auto-discovering the config"). Today they are set once per game; the
winning terminal in particular is the plan's one intended human-confirmation step.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


@dataclass(frozen=True)
class GameConfig:
    name: str
    src_dir: str                    # directory of decompiled .sc scripts
    start_room: int                 # free-roam entry point for reachability
    goal_rooms: frozenset           # winning-terminal rooms (victory)
    goal_scripts: tuple             # scripts whose guards seed the COI goal cone
    timer_globals: frozenset        # per-cycle game-clock globals (timed gates)
    region_labels: dict = field(default_factory=dict)   # region# -> label (report only)
    # (global, value) whose assignment IS death. Both games raise death from Main's
    # doit via a plain global write, so the IR already carries these as SET effects
    # with their path condition -- we only need to recognize them.
    #   LSL2: Main.sc:973 (if (== gCurrentStatus 1001) (gCurRoom setScript: dyingScript))
    #   KQ4 : Main.sc:722 (if dead ...restart modal...)
    death_signal: tuple = ()
    # QA / debug scaffolding, pinned to 0. A shipped game's debug menu is not part of
    # its winnability, and leaving these live is a LANDMINE: LSL2's rm82 (the volcano
    # crater) contains `(if gDebugging (gEgo get: 27 get: 21 get: 19))` -- the
    # Airsick_Bag, Hair_Rejuvenator and Matches, i.e. the entire bomb, handed to you in
    # the very room you need it. rm75 has `(if gForceAtest (= gIslandStatus 105))`,
    # which jumps straight to the end state and would make the whole endgame chain
    # vacuous. Today they stay 0 only BY ACCIDENT, on two coincidences: the only
    # `(= gDebugging 1)` lives in rm10 (the copy-protection screen, unreachable from
    # start_room), and Main.sc's `(^= gDebugging $0001)` toggle uses an operator
    # model.py does not parse. Either could change under a perfectly reasonable
    # edit -- a different start anchor, or adding `^=` for completeness -- and the
    # analysis would silently degrade with no test failing. Declare them instead.
    debug_globals: frozenset = frozenset()
    # Phase 4 mode-register promotion (closure.py). Empty = OFF (the default): a set
    # of register names to promote into the location state, or "auto" for the
    # product-budget heuristic. OFF because promotion makes requirements() ~200x
    # slower until Phase 5 makes the query incremental. See closure.FixModel.
    promote_registers: object = frozenset()


LSL2 = GameConfig(
    name="Leisure Suit Larry 2: Goes Looking for Love (v1.002.000, SCI0, DOS/English)",
    src_dir=os.path.join(_ROOT, "vendor", "sci-scripts", "lsl2-dos-1.002.000", "src"),
    # Free-roam begins in the Los Angeles act. rm10 (copy-protection) and rm90-93
    # (intro cutscenes, reused as island cutscenes) are tangled into the island SCC,
    # so we anchor at a core LA room whose component reaches every act.
    start_room=21,
    # Victory = the Nontoonyt Island wedding endgame (rm78 ceremony -> rm178 ending).
    goal_rooms=frozenset({75, 76, 77, 78, 178}),
    goal_scripts=(75, 76, 77, 78, 178),
    timer_globals=frozenset({
        "gRgTimer", "gGameSeconds", "gCurrentTimer", "gSeconds", "gMinutes", "gHours",
    }),
    region_labels={
        200: "Los Angeles", 300: "cruise ship / voyage", 400: "Nontoonyt Island",
        401: "island", 500: "island interior", 600: "airport/plane",
        700: "volcano/jungle", 7: "interior/overlay", 8: "interior/overlay",
    },
    death_signal=("gCurrentStatus", 1001),
    debug_globals=frozenset({"gDebugging", "gForceAtest"}),
)

KQ4 = GameConfig(
    name="King's Quest IV: The Perils of Rosella (v1.006.004, SCI0, DOS/English)",
    src_dir=os.path.join(_ROOT, "vendor", "sci-decomp-archive", "kq4", "SRC"),
    # discover.py proposed start=23; goal confirmed as the Daventry ending where
    # Rosella cures King Graham (rm694, grahamFace; reached rm693->694, after
    # gamePhase=endGame(99) is set in rm92 when Lolotte dies).
    start_room=23,
    goal_rooms=frozenset({693, 694}),
    goal_scripts=(693, 694),
    timer_globals=frozenset({"gameHours", "gameMinutes"}),   # the day/night deadline clock
    region_labels={},
    death_signal=("dead", "TRUE"),
    # Main.sc:55 `debugOn ;generic debug flag -- set from debug menu`
    debug_globals=frozenset({"debugOn", "debugMenu", "debugging"}),
)

# The config the pipeline runs against. Swap this (or set it from run.py) to target
# a different game.
ACTIVE = LSL2
