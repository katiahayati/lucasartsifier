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
)

# The config the pipeline runs against. Swap this (or set it from run.py) to target
# a different game.
ACTIVE = LSL2
