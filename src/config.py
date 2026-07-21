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
    src_dir: str                    # directory of decompiled .sc scripts (OURS -- see ir_path)
    resource_dir: str               # dir with RESOURCE.MAP + RESOURCE.00x (PIC/VIEW control-map oracle)
    # Both anchors are DISCOVERABLE -- leave start_room 0 / goal_rooms empty and
    # anchors.discover() derives them from the game (see anchors.py). The values below are
    # kept because they are hand-verified; the derived pair reproduces them exactly.
    start_room: int                 # free-roam entry point for reachability
    goal_rooms: frozenset           # winning-terminal rooms (victory)
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
    # QA scaffolding to pin off, by global INDEX. Also not universal: LSL2 gates its debug
    # item hand-outs on globals 100/111, whereas KQ4 has no debug global at all -- it calls the
    # SetDebug kernel. An empty set is therefore a legitimate answer, not a missing value.
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
    # Free-roam begins in the Los Angeles act. rm10 (copy-protection) and rm90-93
    # (intro cutscenes, reused as island cutscenes) are tangled into the island SCC,
    # so we anchor at a core LA room whose component reaches every act.
    start_room=21,
    # Victory = the ENDING (rm178), reached only via the rm78 wedding ceremony (which needs
    # gIslandStatus==105 <- 104 <- 103 <- rm92 <- the volcano <- the bomb). The approach rooms
    # rm75/76/77 and rm78-the-room are walk-reachable BEFORE the wedding (rm74->75 is a free
    # positional exit; rm77 has `east 78`), so counting them as victory lets the endgame be
    # bypassed. Tightened 2026-07-20 to require the wedding. NOTE: the volcano is still
    # bypassable via the rm90-93 intro-cutscene tangle (rm92 <- rm91 <- rm90) -- see
    # docs/NOTES / the endgame-cluster memory; that untangling is separate open work.
    goal_rooms=frozenset({178}),
    death_signal=(101, 1001),
    debug_globals=frozenset({100, 111}),          # gDebugging, gForceAtest
)

KQ4 = GameConfig(
    name="King's Quest IV: The Perils of Rosella (v1.006.004, SCI0, DOS/English)",
    src_dir=os.path.join(_ROOT, "build", "kq4", "src"),
    ir_path=os.path.join(_ROOT, "build", "kq4", "kq4.ir.json"),
    resource_dir="/mnt/i/sierra/kq4",
    # discover.py proposed start=23; goal confirmed as the Daventry ending where
    # Rosella cures King Graham (rm694, grahamFace; reached rm693->694, after
    # gamePhase=endGame(99) is set in rm92 when Lolotte dies).
    start_room=0,                       # discovered, fine
    # ========================= PROTOTYPE -- DO NOT KEEP =========================
    # goal_rooms is DECLARED here only to unblock the KQ4 analysis. It is NOT the
    # answer, and it must be removed once we know the real one.
    #
    # Why discovery cannot find it: KQ4's `global127` does not mean "you died", it
    # means "the game is over". It is set in 33 death rooms AND in both ending rooms
    # (Room694.sc:169, Room692.sc:344). anchors.discover_goal excludes death rooms --
    # correctly, since deaths are terminal too -- so it excludes victory along with
    # them and returns nothing. One flag, two meanings.
    #
    # The real fix is to separate win from lose. Leads, in order of promise:
    #   1. Main.sc ~795-860 branches inside the global127 handler (`proc0_12 800`
    #      near 816, a global182 test near 858) -- one may be the discriminator.
    #   2. A victory-only marker: a score award, or the endGame phase rm92 sets when
    #      Lolotte dies.
    #   3. If neither exists, the honest conclusion is that this genuinely cannot be
    #      derived for KQ4, and the config field is the right home -- but that is a
    #      finding to establish, not to assume, which is why this is marked.
    #
    # Everything derived from this value is provisional. Do not report KQ4 results
    # as validated while this comment is here.
    # ============================================================================
    goal_rooms=frozenset({694}),        # PROTOTYPE (see above)
    death_signal=(127, None),
    # Main.sc:55 `debugOn ;generic debug flag -- set from debug menu`
    debug_globals=frozenset(),                     # KQ4 uses the SetDebug kernel, not a global
)

# The config the pipeline runs against. Swap this (or set it from run.py) to target
# a different game.
ACTIVE = LSL2
