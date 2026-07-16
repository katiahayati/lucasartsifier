# Finding: LSL2's "boat timers" are timed *deaths*, not softlocks (and a tool scope gap)

Status: documented; **fix deferred to a second pass** (user decision).

## What we found
LSL2's two "missed the boat" events are **timed deaths**, not walking-dead softlocks:

1. **LA departure timer.** Armed in **rm115** (`SetRgTimer 1 4:30`, the spy-shop mission
   scene) → phase `gCurrentTimer = 1`. The LA region controller **rm200** `doit` watches:
   ```lisp
   (if (and (== gCurrentTimer 1) (not gRgTimer) (< gCurRoomNum 26) …)
       (= gCurrentStatus 1001)
       (Print 200 0) ; "You have fooled around too long! … the departure of your cruise ship."
       (Print 200 1) ; "you have "missed the boat!""
   )
   ```
2. **Shipwreck escape timer.** Armed in **rm36** when you lower the lifeboats
   (`(= gLoweredLifeboats 1)`, `SetRgTimer 3 2:10`) → phase `gCurrentTimer = 3`. The ship
   region controller **rm300** `doit` sets `gCurrentStatus = 1001` if the clock expires
   while you're not in an escape room (31/38/131/138).

Both funnel into the **same doom** (Main.sc):
```lisp
(if (== gCurrentStatus 1001)
    (gCurRoom setScript: dyingScript))     ; -> HandsOff, deadSnd, the
                                           ;    "you've screwed up again!" Restore/Restart/Quit modal
```
So `gCurrentStatus == 1001` ⇒ `dyingScript` ⇒ **death**. The player perceives "the boat
left and I'm stuck," but mechanically it's a death screen + restart.

## Why the analyzer never reported it — two gaps
1. **Scope.** The detector hunts *walking-dead softlocks* (`reachable ∧ ¬CanWin ∧
   **¬death**`) and deliberately excludes deaths. A timed death is correctly *out of scope*
   — so it was never in the softlock catalog. The tool wasn't wrong; its scope is narrower
   than the "LucasArts" goal (which also bans unfair timed deaths).
2. **No timed-forcing model** (see task #9). The analysis sees `gRgTimer`/`gCurrentTimer`
   as variables but never *simulates* a clock reaching zero and forcing
   `gCurrentStatus := 1001`. So timed traps are invisible regardless of death-vs-softlock.

## Correction to an earlier overstatement
Phase A once listed "boat timer" among the *three documented dead-ends the tool caught*.
That was overstated: what actually happened was *detecting the timer globals* and labeling
them "the boat-timer class." The mechanic was never traced. It is a **death**, so it was
**never in the softlock catalog**. Honest score: 2 genuine softlocks caught cold
(sunscreen, lifeboat items) + a timer that was hand-waved.

## The fix (deferred — second pass)
Both boat timers are **uncontrollable forcing transitions** that push you out of the
winning region against your will. Per the neutralization formalization this is **case C**:
a supervisor can't govern a clock, so it deletes it. Concretely:
- remove the `gCurrentStatus := 1001` doom blocks in **rm200** (LA) and **rm300** (ship),
  and/or don't arm the countdown in rm115 / rm28 / rm36; or
- guard the *committing* action (lowering the lifeboats in rm36) on already holding the
  escape items, so you can never start a clock you can't beat.
This composes with the item-guards Phase B already adds: you still can't leave unequipped,
you're just never rushed.

To do this automatically the tool must **widen detection to treat timed/forced deaths as
first-class findings** (`timer-expiry → dyingScript/death`), then let the same Phase-B
pass delete both timers.

## Related second-pass goal: remove *all* unfair deaths (not just timed ones)
User intent (deferred): also neutralize non-timed forced deaths — e.g. *"board the plane
without the blue-plate special ⇒ you die."* That is the general **"you can't die"**
LucasArts property, one step beyond "you can't get stuck." Same machinery: detect
death-inducing transitions (reach `dyingScript`/the restart modal), and either guard the
committing action on the prerequisite or make the death non-fatal. This is a superset of
the timed-death work above and should be its own pass.
