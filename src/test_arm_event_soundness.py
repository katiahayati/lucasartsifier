"""The silent arm-hold's soundness premise, annotated -- and the chain climb that cures it.

Play-found 2026-08-18 (the USER, at the hermit): the mermaid departure's arm-event guard held
`(self setScript: cartoon2)` in a room whose init had already gone hands-off, and the game HUNG
on a static beach -- no refusal, no exits, nothing left to run. The arm-event kind's own comment
states its premise: the gated script is an ADVERSARY the room merely offers (KQ4's whale), so
withholding it leaves the player in open play. Two context shapes break that premise, and both
are structural facts of the file, not hermit facts:

  * OUTSIDE-EXIT LIVENESS -- the sole-exit check counted any `newRoom:` outside the gated
    script as "the room still has a way out". cdHermitRoom's `goGetBoatScript` (newRoom 44) is
    outside the gated `cartoon2` textually, but it is armed ONLY from within cartoon2: withhold
    cartoon2 and no path arms the way out. An exit whose every arming lives inside the gated
    script is inside the gate for reachability purposes.
  * THE changeState HANDOFF -- an arming inside a Script's changeState is the machine handing
    FORWARD its own continuation, not an adversary arming next to open play (the free-running
    methods: init, doit, newRoom, cue). Withholding a continuation parks the machine in the
    client's script slot, and a room whose doit dispatches on `script` never reaches its edge
    exits again (rm046's bringCedric; same class as the 2026-08-04 finding #11 hang).

find_trigger ANNOTATES the unsound hold (kind stays arm-event -- the deferral triage's
contract) and, when a handoff machine is itself armed from a controllable handler up the
chain, names that arming (`chain_arm`): the refusal belongs at the last controllable moment
before the whole committed chain (USER ruling 2026-08-19, the shell give). A "decline-fork"
cure -- conjoining the demand into the gated cutscene's own decline arm -- was built and then
REMOVED BY USER RULING the same day: its one real site (goGetBoatScript) raised flag 105 on
the way out, a commitment deferral wearing a decline's clothes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trigger import find_trigger                 # noqa: E402
from sexpr import read_all as read_string                                # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"\n      {detail}" if detail and not cond else ""))


# The hermit shape, reduced: the room's init arms the departure cutscene; the cutscene's own
# state 18 forks between the stock decline (goHome, whose chain exits to 44) and the frontier
# continuation (newRoom 663). goHome's ONLY arming is inside the gated cutscene.
HERMIT = """(instance rm660 of Rm
\t(method (init)
\t\t(super init:)
\t\t(proc0_2)
\t\t(self setScript: cartoon2)
\t)
)

(instance cartoon2 of Script
\t(method (changeState param1)
\t\t(switch (= state param1)
\t\t\t(18
\t\t\t\t(if (and (proc0_12 55) (!= global361 46))
\t\t\t\t\t(self dispose:)
\t\t\t\t\t(global2 setScript: goHome)
\t\t\t\telse
\t\t\t\t\t(= cycles 1)
\t\t\t\t)
\t\t\t)
\t\t\t(28
\t\t\t\t(global2 newRoom: 663)
\t\t\t)
\t\t)
\t)
)

(instance goHome of Script
\t(method (changeState param1)
\t\t(switch (= state param1)
\t\t\t(0
\t\t\t\t(global2 newRoom: 44)
\t\t\t)
\t\t)
\t)
)
"""

# The handoff shape, reduced: the room's doit arms bringC, whose LAST state hands the client
# forward to the transit cutscene. The room has live edge exits of its own -- but a wrap that
# withholds the handoff parks bringC in the script slot and the doit dispatch never reaches
# them. There is no decline arm inside `transit`, so the placement must fall to sole-exit
# (the deferral/coverage machinery), never to the silent arm-event.
HANDOFF = """(instance rm46 of Rm
\t(method (doit)
\t\t(cond
\t\t\t(script
\t\t\t\t(script doit:)
\t\t\t)
\t\t\t(local2
\t\t\t\t(self setScript: bringC)
\t\t\t)
\t\t\t((== (global0 edgeHit:) 2)
\t\t\t\t(global2 newRoom: 45)
\t\t\t)
\t\t)
\t)
)

(instance bringC of Script
\t(method (changeState param1)
\t\t(switch (= state param1)
\t\t\t(0
\t\t\t\t(= cycles 1)
\t\t\t)
\t\t\t(1
\t\t\t\t(client setScript: transit)
\t\t\t)
\t\t)
\t)
)

(instance transit of Script
\t(method (changeState param1)
\t\t(switch (= state param1)
\t\t\t(0
\t\t\t\t(global2 newRoom: 661)
\t\t\t)
\t\t)
\t)
)
"""

# KQ4's whale, reduced: the room's own init arms the adversary next to a live room exit.
# The silent arm-event is CORRECT here and must not move -- this fixture is the frozen games'
# proxy (KQ4 Room31, KQ6 rm320's cue, LB2 rm300's cue, KQ5's henchman all share it).
WHALE = """(instance Room31 of Rm
\t(method (init)
\t\t(super init:)
\t\t(if (< (Random 1 100) 40)
\t\t\t(global0 setScript: whaleActions)
\t\t)
\t)
\t(method (doit)
\t\t(if (== (global0 edgeHit:) 2)
\t\t\t(global2 newRoom: 30)
\t\t)
\t)
)

(instance whaleActions of Script
\t(method (changeState param1)
\t\t(switch (= state param1)
\t\t\t(0
\t\t\t\t(global2 newRoom: 32)
\t\t\t)
\t\t)
\t)
)
"""

# The act-break card, reduced (LB2's script 26): ONE newRoom in the whole file, inside the
# gated script. Still sole-exit, exactly as before this change.
CARD = """(instance rm250 of Rm
\t(method (init)
\t\t(super init:)
\t\t(self setScript: actBreak)
\t)
)

(instance actBreak of Script
\t(method (changeState param1)
\t\t(switch (= state param1)
\t\t\t(0
\t\t\t\t(global2 newRoom: 26)
\t\t\t)
\t\t)
\t)
)
"""

# The chain shape (the USER's hermit ruling): the transit's armings are all changeState
# handoffs, but one of the handoff machines (giveC) is itself armed from a controllable
# handler -- the give click. The refusal belongs THERE: the last controllable moment before
# the whole committed chain. bringC's chain dead-ends in doit and is reported, not wrapped.
CHAIN = HANDOFF + """
(instance giveC of Script
\t(method (changeState param1)
\t\t(switch (= state param1)
\t\t\t(0
\t\t\t\t(= cycles 1)
\t\t\t)
\t\t\t(1
\t\t\t\t(global2 setScript: transit)
\t\t\t)
\t\t)
\t)
)

(instance hermitA of Actor
\t(method (handleEvent param1)
\t\t(switch (param1 message:)
\t\t\t(4
\t\t\t\t(global2 setScript: giveC)
\t\t\t\t(param1 claimed: 1)
\t\t\t)
\t\t)
\t)
)
"""

COND = "(and (global0 has: 30) (global0 has: 31))"
REFUSE = "(proc255_0 {Not yet!})"


def test_dead_outside_exit_declines_the_silent_hold():
    print("\n-- find_trigger: an outside exit armed only from within the gate is not live --")
    trig = find_trigger(read_string(HERMIT), 663)
    check("the hermit shape's hold is annotated unsound (kind stays arm-event: the "
          "deferral triage's contract)",
          trig["kind"] == "arm-event" and trig.get("unsound_hold")
          and trig.get("target_script") == "cartoon2",
          detail="got %r" % (trig,))
    check("no decline is offered (the machinery was removed by USER ruling 2026-08-19)",
          "decline_script" not in trig, detail="got %r" % (trig,))


def test_changestate_handoff_declines_the_silent_hold():
    print("\n-- find_trigger: a changeState arming is a continuation handoff, never held --")
    trig = find_trigger(read_string(HANDOFF), 661)
    check("the handoff shape's hold is annotated unsound",
          trig["kind"] == "arm-event" and trig.get("unsound_hold"),
          detail="got %r" % (trig,))
    check("with no decline arm the annotation carries no decline_script "
          "(the main loop then takes the sole-exit flow)",
          trig.get("decline_script") is None, detail="got %r" % (trig,))


def test_adversary_arming_keeps_the_silent_hold():
    print("\n-- find_trigger: the whale shape (frozen games' proxy) still arm-events --")
    trig = find_trigger(read_string(WHALE), 32)
    check("an init arming next to a live room exit stays arm-event, unannotated",
          trig["kind"] == "arm-event" and trig["trigger_method"] == "init"
          and not trig.get("unsound_hold"),
          detail="got %r" % (trig,))


def test_chain_climb_to_the_controllable_arming():
    print("\n-- find_trigger: the climb to the last controllable moment (the give click) --")
    trig = find_trigger(read_string(CHAIN), 661)
    check("the handoff chain climbs to the controllable arming",
          trig.get("chain_arm") == {"trigger_instance": "hermitA",
                                    "trigger_method": "handleEvent",
                                    "target_script": "giveC"},
          detail="got %r" % (trig,))
    check("the unclimbable sibling door is reported, not silently skipped",
          trig.get("chain_unwrapped") == ["bringC"],
          detail="got %r" % (trig,))


def test_true_sole_exit_is_unchanged():
    print("\n-- find_trigger: the act-break card still reports sole-exit --")
    trig = find_trigger(read_string(CARD), 26)
    check("one newRoom in the file, inside the gate: sole-exit",
          trig["kind"] == "sole-exit", detail="got %r" % (trig,))


def run():
    test_dead_outside_exit_declines_the_silent_hold()
    test_changestate_handoff_declines_the_silent_hold()
    test_chain_climb_to_the_controllable_arming()
    test_adversary_arming_keeps_the_silent_hold()
    test_true_sole_exit_is_unchanged()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    run()
