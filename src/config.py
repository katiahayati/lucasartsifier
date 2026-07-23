"""Game configuration: the per-game knobs kept out of the engine-general code.

Everything else in src/ is generic SCI0 machinery (S-expr reader, IR extraction,
name resolution, Rm/Door/region navigation, COI slice, SCC reachability). The
handful of things that are *specific to a title* live here so the same pipeline
can point at another SCI0 game by swapping the config.

Which of these could be auto-discovered instead of configured is discussed in the
README ("Auto-discovering the config"). Start, goal, death and debug are now ALL
DERIVED (this config leaves them empty and the pipeline discovers them); what remains
here is paths, the game's display name, and the promote_registers knob -- no game logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


@dataclass(frozen=True)
class GameConfig:
    name: str
    src_dir: str                    # directory of decompiled .sc scripts (OURS -- see ir_path)
    resource_dir: str               # dir with RESOURCE.MAP + RESOURCE.00x (PIC/VIEW control-map oracle)
    # Both anchors are DISCOVERED -- leave start_room 0 / goal_rooms empty; anchors.discover()
    # derives them from the game (see anchors.py). The derived rooms may DIFFER from a human's
    # hand-pick (LSL2 discovers start rm11 / goal rm86, not the old rm21 / rm178) while yielding
    # the SAME findings, so we derive rather than hand-pick. Both games leave these empty.
    start_room: int                 # free-roam entry point for reachability (0 = discover)
    goal_rooms: frozenset           # winning-terminal rooms (victory; empty = discover)
    ir_path: str = ""               # JSON IR our sci-tools fork emits alongside src_dir
    # (global, value) whose assignment IS death. Both games raise death from Main's
    # doit via a plain global write, so the IR already carries these as SET effects
    # with their path condition -- we only need to recognize them.
    #   LSL2: Main.sc:973 (if (== gCurrentStatus 1001) (gCurRoom setScript: dyingScript))
    #   KQ4 : Main.sc:722 (if dead ...restart modal...)
    # (global INDEX, value) whose assignment IS death; value None means "any non-zero".
    # By INDEX, not name: the JSON IR identifies globals positionally and carries no symbol
    # table, so a name here could never be resolved -- which is exactly how the previous
    # by-name version came to be dead code with the real value hardcoded in missability.py.
    # NOT derivable from one shape: LSL2 raises death as `gCurrentStatus == 1001` (a magic
    # constant) while KQ4 uses `global127` as a plain boolean set in 37 different death rooms.
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
    # QA scaffolding to pin off, by global INDEX. Not universal in VALUE but so far universal in
    # KIND: LSL2 gates its debug item hand-outs on globals 100/111, KQ4 on global215. We once
    # recorded that KQ4 "has no debug global at all"; that was only true while Main went unwalked.
    debug_globals: frozenset = frozenset()
    # Phase 4 mode-register promotion (closure.py). Empty = OFF (the default): a set
    # of register names to promote into the location state, or "auto" for the
    # product-budget heuristic. OFF because promotion makes requirements() ~200x
    # slower until Phase 5 makes the query incremental. See closure.FixModel.
    promote_registers: object = frozenset()


LSL2 = GameConfig(
    name="Leisure Suit Larry 2: Goes Looking for Love (v1.002.000, SCI0, DOS/English)",
    # OUR OWN decompilation, reproducible from the pristine game in ~1s:
    #   tools/sci-tools-fork/build.sh /mnt/i/sierra/lsl2 build/ir
    # Deliberately NOT a downloaded pre-made .sc tree: one of those exists only for LSL2,
    # so depending on it would make the pipeline unable to open any other game.
    src_dir=os.path.join(_ROOT, "build", "ir", "src"),
    ir_path=os.path.join(_ROOT, "build", "ir", "lsl2.ir.json"),
    resource_dir="/mnt/i/sierra/lsl2",   # PRISTINE game. Never point this at a patched
    #   build: `out/lsl2_playable` used to live here and was the previous (broken) patcher
    #   output, so the control-map oracle was reading resources of our own making.
    # DISCOVERED (anchors.discover) -- left empty so the derivation runs. It lands on a room in the
    # free-roam LA cluster (rm11) and goal rm86 (the terminal entered from the rm178 wedding
    # cutscene). discover_start drops the copy-protection/intro ROOTS (rm10/rm99) by preferring the
    # room every engine entry funnels into. Those ROOMS differ from the old hand-set rm21 / rm178 --
    # a human would name rm21 and rm178 -- but the derived pair yields the SAME 15 stranded items +
    # the Ashes/Sand group (verified 2026-07-22 by emptying these fields), so we derive.
    start_room=0,
    goal_rooms=frozenset(),
    # BOTH DERIVED (vocab.derive_death / derive_debug); left empty so the derivation runs.
    # Kept as override fields only. Derivation reproduces the hand-declared (101, 1001) exactly,
    # and derives debug {14, 100} where {100, 111} was declared -- behaviourally identical
    # (global111 is never written, so the model already pins it at 0).
    death_signal=(),
    debug_globals=frozenset(),
)

KQ4 = GameConfig(
    name="King's Quest IV: The Perils of Rosella (v1.006.004, SCI0, DOS/English)",
    src_dir=os.path.join(_ROOT, "build", "kq4", "src"),
    ir_path=os.path.join(_ROOT, "build", "kq4", "kq4.ir.json"),
    resource_dir="/mnt/i/sierra/kq4",
    start_room=0,                       # DISCOVERED -> rm99, the room Main.sc:779 starts in
    # DISCOVERED (anchors.discover_goal), not declared -- the prototype that used to sit here
    # is gone. It took a second rule to get there: KQ4's global127 means "the game is over", not
    # "you died", so it fires in 33 death rooms AND in both endings and the primary rule threw
    # victory out with the losses. Among those excluded terminals, the ending that TESTS WHAT YOU
    # ACHIEVED is the win -- rm694 is `(if (gEgo has: 25) <cure your father> else <watch him die>)`
    # while rm692, the marry-Edgar ending, asks nothing. Discovery reproduces rm694 exactly.
    goal_rooms=frozenset(),
    death_signal=(),          # DERIVED -> (127, None), any non-zero
    # DERIVED -> {215}, found as the global a debug menu TOGGLES with `^=`. An earlier note
    # here claimed KQ4 had no debug global at all; `copyProtect.sc:687` uses it to warp to any
    # room you type, so leaving it unpinned would have emptied the analysis.
    debug_globals=frozenset(),
)

# The config the pipeline runs against. Swap this (or set it from run.py) to target
# a different game.
ACTIVE = LSL2
