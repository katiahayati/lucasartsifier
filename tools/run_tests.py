"""Run every `src/test_*.py` and say something meaningful about the result.

    python3 tools/run_tests.py              # the whole suite
    python3 tools/run_tests.py toll scopes  # only files whose name contains one of these

WHY THIS EXISTS. Every test file here is a plain script with its own `run()` and its own
`sys.exit`, and one of them (`test_toll`) exits 1 BY DESIGN -- it carries assertions that are
deliberately RED, because no passing test may assert known-wrong behaviour. So "did the suite
pass" had no answer: a green run and a run with a fresh regression looked identical from the
outside, and the only way to tell was to read twelve files of output by eye.

THE CONTRACT. Failure is not the interesting axis; AGREEMENT WITH `KNOWN_RED` is. This exits 0
only when the set of failing checks is EXACTLY the declared set. That makes two things loud
that were previously silent:

  * an UNDECLARED failure is a regression, named with the file it came from;
  * a declared RED that has gone GREEN is ALSO a failure -- "a gap was closed, promote it".
    Without that half, closing a modelling gap looks like nothing happening, which is how a
    real fix gets landed, forgotten, and later undone by someone who never knew it was there.

Every file prints `  [PASS] name` / `  [FAIL] name`, so the parsing below is the whole protocol;
a new test file needs no registration unless it is deliberately red.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(_ROOT, "src")

# --- THE DELIBERATELY RED CHECKS -------------------------------------------------------------
#
# `file -> {check name: why it is red}`. A check listed here MUST fail; one that starts passing
# is reported as a promotion, not quietly accepted. Keep the reason short and name the gap, so
# the next reader can tell a known limitation from a broken test without opening the file.
#
# ✅ PROMOTED 2026-08-20 -- NINE of the ten 2026-08-20 review defects are GREEN and no longer
# listed. They were declared (commit 58aedb0) as OPEN DEFECTS with their cures known rather than
# as limitations, so that closing them would read as the promotion it is; this is that reading.
#
#   R1 `_enclosing_if_test`'s candidate scan is `_code_finditer` now, not a raw one, so an `(if`
#      inside a `{...}` message can never be picked as the arming (`_place_capture_arm`'s
#      `setScript:` scan and `_init_send_positions` went through the same filter).
#   R2 an `(if` carrying a depth-1 `else` is disqualified WHOLE -- conjoining onto its test
#      diverts control into the else -- and the search no longer climbs outward past it: the
#      caller wraps the arming STATEMENT instead (`_wrap_statement`), which holds exactly the
#      arming and leaves the game's other outcome free. `NESTED_ELSE_ARM` was re-derived, not
#      patched around, and `BARE_SPAWNER` with it.
#   R3 `_place_fuse_arm` enumerates `setScript: <machine>` alongside the host's `init:` sends,
#      so a procedure arming one machine both ways holds both sites or refuses whole.
#   R4 `_falsifies` asks "can this conjunct still hold?" -- falsified only when the register IS
#      written and NO write satisfies it -- instead of "does SOME write contradict it?".
#   R5 the `fuse_death_armings` row key carries the room's DEMAND, so a second room deriving a
#      stronger hold reaches `fuse_arming_remedies`' clash gate instead of vanishing.
#
# All five games' emitted patch source trees are byte-identical across the change
# (`tools/measure_emitted_bytes.py` against a worktree at cc3b897), which is the check that
# matters for a patcher edit: the snapshot surface freezes whether a guard landed, never its
# text. R6 is not here because it never had a test -- it needs a design decision from the USER.
KNOWN_RED = {
    "test_patch_text.py": {
        "🔴 KNOWN GAP: the hold covers `(super init:)`, or refuses by disposing the host":
            # The 2026-08-19d review's F6. Every arming hold placed inside a host's OWN `init`
            # -- the rm54 fish discriminator and the capture hold both -- sits AFTER
            # `(super init:)`, so a refused arming leaves the actor in the cast with
            # `script == 0`. rm054.sc:447-449 then reads
            # `(>= (((ScriptID 550 3) script:) state:) 1)`, a send to 0, behind a
            # `(global5 contains: ...)` test that a scriptless cast member satisfies.
            #
            # DECLARED RATHER THAN CURED because both cures -- wrapping the `init:` CALL SITES
            # the way `fuse-arm` does, or adding `else (self dispose:)` -- change emitted bytes
            # in a patch the USER has already play-tested end to end (v17, tag v3.0-kq5). The
            # right order is the USER's call plus a play test, not a silent rewrite of a
            # verified emission.
            #
            # ⛔ NOT A KQ5 SHIPPING HAZARD -- KQ5 HAS NO PATH TO IT [USER, play, 2026-08-20].
            # Play-confirmed: prop the grate, tug it, nothing happens and nothing crashes. The
            # structure agrees -- the ambush needs an unequipped arrival at rm54, and our own
            # boat guard demands the Iron_Bar (30) and the Fishhook (31) at all three of
            # `boatRegion`'s `leave` armings, so `theHenchMan::init` never runs there. What
            # stays red is the APPLIER, for the next game: a hold placed inside a host's own
            # `init` after `(super init:)` is the wrong shape wherever the refusal is reachable.
            "the applier places a hold inside its host's `init` AFTER `(super init:)`, so a "
            "refused arming leaves the host cast-resident with script 0 -- unreachable on KQ5 "
            "(play-confirmed), open for the next game; both cures move a play-confirmed "
            "emission, so this waits on the USER",
    },
    "test_toll.py": {
        # ✅ PROMOTED 2026-08-16 -- "KQ5 temple strands Brass_Bottle + Gold_Coin" and "KQ5 toll
        # item is the Staff via rm214->rm18" are GREEN and no longer listed. Both demanded that
        # KQ5's WHOLE toll set be the temple and nothing else, and both were held red by the two
        # rm57->rm683 carry-in rows the cutscene FP produced. `extract.room_valued_globals` now
        # reads `(== global338 gCurRoom)` -- the bagged cat is in the room where you bagged it --
        # so `theCat` is in the cast in seven castle rooms rather than all sixteen, and the toll
        # set is the temple's two items on the edge rm214->rm18, exactly as declared. This is the
        # promotion contract working: the red was declared 2026-08-15 with the cure named, and
        # curing it turned both green in the same commit. LSL2, KQ4, KQ6 and LB2 byte-identical
        # on the full snapshot surface, placements included.
        # ✅ PROMOTED 2026-08-06 -- both mists REDs ("the carry-in demands rain-readiness
        # (global161==15), not just the lamp" and "the isle landing is guarded when the
        # shore-carry revisit is armed") are GREEN and no longer listed. Three derivations
        # closed finding #17: the SIXTH store (vocab.derive_mask_globals/lower_mask_globals
        # lowers plain-global literal-mask arithmetic per-bit -- measured corpus-wide it
        # matches exactly KQ6's g161, zero on LSL2/KQ4/Dagger), the register half of
        # sink_survival_carryins (structural reqs of the positive arming, presentability-
        # checked, spelled `(== global161 15)`, WAIVED under the surviving arm's own one-way
        # latch flag 74 because makeRain resets the word on success -- an unconditional
        # demand would wall every winner), and the stage-conditioned landing propagation
        # (the shore ambush's `captured`, its 25&!14 stage inherited through the new
        # machine-method armer link, demands compliance at every crossing into rm550 under
        # `(or (not <stage>) <demand>)`). Rebuilt GREEN as
        # test_mists_survival_demand_carries_the_register_half's four pins.
        # ✅ CORRECTED, NOT PROMOTED, 2026-08-05 -- "the long route's treasure-corral letter
        # seal is detected" demanded a row with `register != 338`, and that row should never
        # exist: remeasured against the source, flag 166 (reg338, rFlag1 $0002) IS the long
        # route's seal. The wedding fuse (`weddingRemind`, rgCastle::doit, per-real-second)
        # writes it region-homed in every castle room; the hidden-passage arm refuses under it
        # (rm720.sc:429); 850->781 closes by cond order. `register_strandings`' one row
        # (338, 1, letter, flip_rooms = the 15 rooms outside the walls, 770 and 710 included)
        # carries BOTH routes -- the "covers the SHORT route only" reading was the
        # misdiagnosis that also drove the refuted forced-escort design (guard-actor patrol
        # was the drama, not the seal; KQ4's day/night is the same class -- adversarial-clock
        # phase change). The check is rebuilt GREEN as "the letter row covers the long route"
        # (flip_rooms/still_needed_at pinned), and the remedy now reaches the region-homed
        # writer: `guard_prop_flag_owner_write` freezes the fuse's countdown clause until the
        # letter is in hand (v22, 80.SCR joins the set). See test_toll's docstring and
        # docs/KQ6-CASTLE-CAPTURE-MAP.md §2b for the measurement.
        # ✅ PROMOTED 2026-08-02 -- "a use that only sets a room local is not seen as a
        # requirement" is retired: the FIFTH store is WIRED (round 4). Room-script latch locals
        # lower to synthetic registers (vocab.lower_room_locals) and the machine walks thread the
        # own-script ones as counters (Machine.local_regs, compile._lreg_test), so the latch write
        # is an ordinary register write every consumer sees. The marker was rebuilt as
        # test_local_latch_is_modelled, which pins rm690's local0 chain on KQ6 itself.
        # ✅ PROMOTED 2026-08-01 -- "no exit guard is placed, so the water is demanded nowhere" is
        # GREEN and no longer listed. The placement walk now COMMITS what is genuinely committed:
        # unconditional entry writes (`_psucc(commit=...)` from `em.init_writes`) and consumed item
        # tolls (`_settable_frontier`'s compliance fixpoint loses the spent toll edge). The water
        # is demanded at rm680->rm155 -- the guard oracle's own site -- and the mirror-shown flag
        # at rm670->rm660 and rm680->rm155. Detection walks stay permissive.
        # ✅ PROMOTED 2026-08-02 -- "register_strandings reports prevRoom flips as points of no
        # return" is GREEN and no longer listed. The causality conjunct landed: a flip strands
        # only what the pre-flip state could still reach, judged by the same walk from the
        # pre-flip states (no register named). KQ6 323 rows -> 1 (the flag-166 `letter` lead,
        # held for user review); LSL2/KQ4 -> 0, every old row diagnosed as region-junk.
    },
    # THE ROAD TO A PATCHED KQ6. Each of these turns green when its phase lands, and that is the
    # only mechanism that will notice -- a plan document goes stale in silence. Phases are in
    # the approved plan; derivations in docs/SCI11-PATCHING-PLAN.md.
    "test_sci11_patch.py": {
        # ✅ PHASE 2 LANDED 2026-08-01 -- "the refusal primitive is derived per game" is GREEN and
        # is therefore no longer listed. `patcher.refusal_form` reads the game's own text-display
        # procedure out of its scripts (LSL2/KQ4 `proc255_0`, KQ6 and the Dagger `proc921_0`), and
        # a game with no derivable form emits no refusal-bearing guard at all.
        # ✅ PHASE 5's fatal-use half LANDED 2026-08-01 -- "a fatal use produces a remedy spec" is
        # GREEN. `guard_specs` emits an `action` spec per `fatal_uses` row and the patcher places
        # it on the arming of the fatal machine (KQ6: rm420's `setScript: throwSkull`). Inert on
        # LSL2, KQ4 and the Dagger, which have no fatal uses.
        # ✅ RETIRED BY RULING 2026-08-17b -- "🔴 KNOWN GAP (KQ6): every non-refused spec
        # places" is gone because the USER ruled the state it complained about is the INTENDED
        # output, not a gap: *"whatever we have there is working as intended and should not be
        # a red."* The two skips it was held open by are both deliberate and both already
        # carry their remedy or their coverage: the huntersLamp sink is a TRADE (deleting the
        # disposal would refuse the magic lamp with it; trading the lamp commits you to the
        # short ending -- the shipped remedy is the mists carry-in, the 2026-08-03 "refuse the
        # trip, keep the trade" doctrine), and rm420->rm435 is the shared-dispatcher seam
        # whose demand the capture guards on the isle's entry frontier already carry. Rebuilt
        # GREEN as a PIN of exactly that two-skip set -- a new skip is a regression, a
        # declared one moving is a mechanism change, and neither is a standing red. No model,
        # patcher or surface change; the Shoe/Stick shape -- a red retired by DISAGREEING
        # with it, this time about what the red's own state meant.
        # ✅ PROMOTED 2026-08-05 (same day as the play find) -- "the Realm-entry demand wraps
        # catchNiteMare's arming, not blowinIt's" is GREEN. The cross-file block now READS the
        # helper's arming graph (trigger.reaching_owners/reaching_procs) instead of assuming any
        # export is the way in; a helper-internal arming whose call sites all sit outside `init`
        # is wrapped in place (kind `proc-arm`: nightMare.sc's `(nightMare setScript:
        # catchNiteMare)` inside proc344_1), and init call sites still route to the
        # entry-frontier re-site. test_realm_entry_guard_sits_on_the_spell_delivery pins it.
        # ✅ TWO OF LB2's THREE CAUSES CLOSED 2026-08-06, and the count is no longer the story.
        # The old note here said "2 of 4 place, and the two that DO are 24-item guards ... events
        # that would never fire". Both halves are now false: the 24-item conjunctions collapsed to
        # `(gEgo has: 6)` when the act break got its ordering (docs/LB2-ORACLE.md §7g), and the
        # press-pass sink places -- it had been re-found by a pattern hardcoded to `(globalN put:
        # I D)`, while LB2's Main spells the receiver `(ego put: ...)` and carries nine trailing
        # arguments the engine ignores (`patcher.ego_spellings` derives the names from the game's
        # own `(= global0 ego)`).
        # ✅ PROMOTED 2026-08-11 (the user's word, same session as the fix) -- "every
        # non-refused dagger spec places" is GREEN again, this time on real coverage. Its
        # 2026-08-10 promotion had been REVERSED next day (the sole-exit wraps sat inside
        # commits -- the user's play test caught rm250's; §7al). What closed it honestly:
        # the NIGHT-GUARD SHAPE (§7an, guard_flip_interceptor) placed the act-4->5 demand
        # inside rm520::newRoom's own exit-interceptor arm -- the flip's commit clause,
        # re-tested every exit, held = the stock else exit -- and DEMAND FORWARDING
        # (guards.defer_to_entry "fwd" + patcher._forward_demand_to_hold) carried the
        # act-5->end demand's uncovered remainder (bifocals + redHair, sourceable through
        # act 4, zero loss sites) into the same arm, its own crossing having no survivable
        # site (the commit is rm480's mid-chase capture). The user chose the forwarding over
        # narrowing the red: "i vote 2. i think it's the practical right answer too".
        # ✅ PHASE 5 LANDED 2026-08-02 -- "every KQ6 finding is closed by a guard" is GREEN and no
        # longer listed. The last three: handkerchief + skeletonKey placed at the Realm's exit
        # frontier (pocket_carryout_frontier, rm640->rm650), and the wrong-door stranding rows
        # died to edge_strandings applying two of its own siblings' rules to its output (forced-
        # not-missable, unholdable-cannot-strand; SINGLETON-only -- the group form deletes LSL2's
        # play-validated raft guard and is ruled out). `pipeline --report` exits 0 on KQ6.
    },
    # ✅ ALL FIVE PROMOTED 2026-08-14, the day they were declared -- the review's §3.1 and §3.2.
    # `guard_flip_interceptor` now wraps EVERY arm that pins the stage and routes into the pocket
    # (a commitment reached through N doors and guarded at one of them is not guarded -- findings
    # #4 and #8), returns that count so the frozen `sites=N` says what was really covered, and
    # decides "pins the stage" STRUCTURALLY: the stage must be a conjunct of the arm's head,
    # walking THROUGH nested `and`s and never through `or`/`not`.
    #
    # The `and`-recursion is not a nicety. Without it the second demand FORWARDED onto an
    # already-wrapped hold stopped matching its own host -- LB2's rm26->rm750 went
    # applied=True -> REFUSED, a real coverage loss that the surface diff caught and no test
    # would have. `test_patch_text` now pins that spelling too ("an arm THIS function already
    # wrapped is still pinned"), and LB2 is back to 5 of 5 placements.
    # ✅ ALL FOUR PROMOTED 2026-08-14, the same day they were declared. The v1.0-lb2 review's
    # deletion-side holes (docs/reviews/review-v1.0-lb2.md §4.1-§4.4) are closed, and
    # `test_deletion_soundness.py` is now ten green checks -- four cures plus the six companions
    # that keep each cure from being "delete the filter":
    #   §4.1 the forwarding proof's second half. "Sole producer" was proved over in-ROOM writes
    #        elsewhere plus edges OUT OF the pocket, which never asks whether some OTHER room's
    #        edge commits the same value; it does now, and a register written in two spellings
    #        being checked in one is this codebase's oldest bug shape ([[same-rule-two-places]]).
    #   §4.2 `lower_mask_accessors` refuses the whole store when a READ call site cannot be
    #        evaluated, because husking the reader body under it turns "unmodelled" into
    #        "modelled false" -- the one place in the codebase where ignorance argued for a wall.
    #        Asymmetric with writes on purpose (an unmodelled write is invisible everywhere
    #        else); LB2's g124 keeps its store, its one skip being a write.
    #   §4.3 the pre-emption rule asks whether the player can ARM the competitor (`entry_musts`
    #        priced against reachable sources), the weakest test that is still a proof: LB2's
    #        trunk keeps every escape it had, including the meat.
    #   §4.4 `build_maps` no longer lets an entry that cannot fire dissolve its siblings'
    #        requirement, off the same evidence `_reg_entry_demands._via_latch` already uses --
    #        now one `latch_evidence` shared by both, rather than the rule in two places.
    # MEASURED: all four games' FULL snapshot surfaces byte-identical before and after (LSL2 and
    # KQ4 goldens, KQ6 and LB2 watched, placements included -- LB2 still ships all five, the
    # forwarded rm26->rm750 demand among them). Every cure is latent on today's corpus by
    # construction; the tests are the only thing that will see the next game exercise one.

    # ✅ PROMOTED 2026-08-10 -- "test_lb2_ground_truth.py: the act-boundary carries are caught" is
    # no longer red. The five rows were THREE causes plus one misclassification: §7s (the act
    # register could run backwards) closed smellingSalts; §7y (register_strandings walks the
    # JOINT projections) closed cheese, snakeOil and snakeLasso; and eveningGown was RULED by the
    # user -- "act 2 gate, not a softlock" -- once the model derived the whole mechanism (the
    # ACT 1 -> ACT 2 break itself demands `wearingGown`, whose only act-1 writer costs the gown;
    # docs/LB2-ORACLE.md §7ab). The four real carries now sit in EXPECTED_CAUGHT, where a drop is
    # a loud regression; the gown sits in NEVER_STRANDABLE, where flagging it is an FP. (The
    # `skeletonKey` FP that was tripping the suspicion check -- kept out of this list on purpose,
    # as a defect rather than a limitation -- was closed the same day: a hands-on wait with the
    # Script clock running is pre-emptable, docs/LB2-ORACLE.md §7ad.)
    # ✅ PROMOTED 2026-08-10, the same day it was declared -- "test_lb2_ground_truth.py: the
    # street block is sealed from act 2 on (POSITIONAL taxi seal)" went green and is deleted.
    # The "positional, control-map class, unmodellable" diagnosis was only the LAST link of the
    # chain: the arrival taxi's init is consumed by its own departing handsOff cutscene
    # (extract._object_departures -- no click window ever opens), the `south 250` nav prop is a
    # polygon-proven dead letter (polygons.dead_nav_exits -- north deliberately never claimed,
    # the ego's rect height is unmodelled), and the surviving act gate `(< global123 2)` lowers
    # exactly over the register's own value universe (guard_reqs relational + edge_meta domains).
    # All three measured byte-identical on LSL2/KQ4/KQ6; the street collapsed to acts [1] and
    # the check is a permanent green pin. docs/LB2-ORACLE.md §7ag.

    "test_kq5_ground_truth.py": {
        # ✅ PROMOTED 2026-08-19d, SAME SESSION AS DECLARED -- "the henchman's arming demands a
        # survivable capture or the pea answer" is GREEN, with the remedy pinned beside it.
        # `missability.capture_fold_armings` carries a fold's demand back to the arming of any
        # machine whose OWN transition EXITs into the fold's room (theHenchManScript st12 =
        # EXIT 67), which is the discriminator against the chase exclusion: KQ4's dog and KQ5's
        # yeti end where they start, this one CARRIES you, and leaving is how you lose it.
        # Escapes gained DISPOSERS (`setScript: 0` from outside the slot -- the pea throw is
        # armed into the room's slot), and the pricing fixpoint moved to a shared `_Escapes`
        # ([[same-rule-two-places]]) so the cat and the henchman cannot drift; the cat's rows
        # are byte-identical across that refactor. Two filters keep it honest and were each
        # paid for by a real row: the FOLD-DISARMED test (rm67 dispatches maze arrivals to
        # `enterHole`, so the maze's own carrier was a false positive) and the CONTINUATION
        # test (rm59's `caughtScript` runs on `global333 == 5`, which the root writes -- gating
        # the root covers it). Answerless rows are REFUSED rather than shipped: rm41's roc and
        # rm85's kidnap already carry their fold demand at their crossing, verified against the
        # shipped specs. LSL2/KQ4/KQ6/LB2 emit zero rows from both detectors.
        # ✅ PROMOTED 2026-08-19c, SAME SESSION AS DECLARED -- "the castle cat's arming demands
        # the whale kit (remote fuse = death)" is GREEN. `missability.fuse_death_armings`
        # landed with the three classifications the red named: DEATH PHASES ((331,3) arms
        # theWizardScript in nine castle rooms, (331,6) arms wakeUpScript in rm63 -- an
        # unavoidable machine's entry pinning a register value off an unpriced spine); the
        # CLOCK (a CTR-gated handler write with a running-countdown atom and no item on the
        # spine -- castle::doit's per-game-minute expiry), with the fuse set closing under
        # chaining (353's expiry writes 352 := 3) but NOT under self-re-arm (353 := 5 is the
        # cycle continuing, and without that exclusion the henchman's global333 classified as
        # a fuse); and FUSE-ARMING MACHINES (theCatRunScript st3 writes 353 := 3). The demand
        # derives as the saving-writer FIXPOINT over the root's slot escapes -- catInBag priced
        # own(24) ∧ 63 ∧ 62 off its chain-composed entry, catGetFish priced own(37) plus the
        # re-armed encounter's price DISCHARGED of flag 62 (theThrowFishScript writes it) --
        # yielding `63 ∧ own(24) ∧ (62 ∨ own(37))`, the USER's ruling verbatim, and rows once
        # per (root, item) at the proc's real call sites {60, 61, 63}. LSL2, KQ4, KQ6 and LB2
        # all return [] (KQ6's wedding fuse has no death phase -- it stays an item seal).
        # ✅ PROMOTED 2026-08-19b, same session as declared -- "no confirmed softlock has
        # DROPPED", "mechanism pinned: Fishhook" and "mechanism pinned: Shell" are GREEN and no
        # longer listed. Declared on the USER's play-found harpy-island ruling (the departure
        # cutscene writes flag 54; every flag-54 return arms a 50%-roll positional kill on
        # control mask $0002 with no counter, so the island is ONE SAFE VISIT and the true
        # frontier for the Shell and the Fishhook is the boat click). The cure differed from
        # the reds' named guess in ONE respect ([[re-derive-a-reds-premise]]): analyze's
        # value-blind frontier does not move -- the catch is register_strandings' reg456=1
        # rows, the (room, register-value) trapped state. Five derivations, each measured:
        # the SCI1 PIC extended-op dialect (sci_gfx renders KQ5 pics), the onControl-mask
        # positional-hazard spelling + Script-host liveness via arming_conditions, staged
        # control-return seeds with prevRoom tags (the boat landing; the per-edge tag
        # exclusion), per-layout obstacle alternatives, and hazard-priced PICKUPS (the
        # shell's spot) conjoined into source_guards -- read by register_strandings' walks
        # through the new liveness-aware source test (_live_srcs/_source_live, the same
        # standard reobtainable_rooms already applied). Snake gate byte-identical; the
        # hazard-gates pin now freezes all three rows.
        # ✅ PROMOTED 2026-08-17 -- "no UNEXPECTED item flagged (suspicion)" is GREEN and no
        # longer listed. It was declared red the day before with the cure named ("goes green the
        # day positional gates land"), and this is that day: the Tambourine's
        # `need@rm55 sources=[13] frontier=rm40->rm41` row is gone because the model now knows
        # you cannot leave town without charming the snake.
        #
        # THE CURE, and it is the ranked #1 census gap in its cleanest form. A `doit` runs every
        # cycle whether the player likes it or not, so `((< (gEgo distanceTo: snake) 30)
        # (setScript: strike))` is the script saying "come within 30 pixels and you die". That
        # makes the disc around a STATIONARY killer ground the player may not cross, i.e. an
        # obstacle -- and an obstacle is a thing `polygons.py` already reasons about. So the
        # geometry answers the question `control_oracle.crossing_forces_rect` asks of the SCI0
        # control plane, over the polygons an SCI1 room hands its pathfinder instead: rm2's east
        # handoff is walkable only through the y in (48,81) slit poly1 and poly4 leave, and every
        # cell of it is inside the disc. The edge inherits the NEGATION OF THE SNAKE'S CAST
        # CONDITION (flag 47), whose price `_reg_cost` independently derives as item 34.
        #
        # It needed `polygons.instance_polygons` first: KQ5 declares obstacles as named
        # `Polygon` instances filled from local arrays, and reading only the inline spelling
        # meant 84 `addObstacle:` sites across 67 rooms produced NO polygons -- every KQ5 room
        # read as open floor. LSL2/KQ4 have no obstacles at all and KQ6/QFG/LB2 pass expressions
        # rather than named instances, so all five frozen surfaces are untouched by it.
        #
        # MEASURED, as a funnel: 27 `doit` arms corpus-wide bound the ego's distance (KQ5 8,
        # KQ6 6, QFG-VGA 8, LB2 5); 17 of them ARM something (6/5/4/2); and exactly ONE of the
        # 17 says "inside the radius, full stop" rather than "inside the radius, AND some local
        # is clear". That one is the snake. Every other hazard in the corpus is conditional --
        # KQ6's zombie wants `(not local73)`, LB2's rat3 wants `(== (gEgo view:) 732)` -- and
        # four of KQ6's five also move, so their `(x,y)` is not a place either. The rule is
        # general and the corpus is simply thin in unconditional killers.
        # KQ5's full surface (placements included) moved by exactly two lines, both this FP
        # leaving. Three green pins replace this entry, one per conjunct. docs/KQ5-ORACLE.md §15.

        # KQ5's oracle landed 2026-08-14 (docs/KQ5-ORACLE.md: game source + three independent
        # walkthroughs) with five caught softlocks pinned green and these five declared red the
        # same day. The first two share one root -- the (room, register-value) trapped state --
        # and the design for closing them is the oracle doc's §1/§2 three-phase plan.
        # ✅ PHASE 2 LANDED 2026-08-14 -- "the inn-cellar corral demands the Hammer" is GREEN
        # and no longer listed. register_strandings' fetch walks (post-flip and the pre-flip
        # causality walk) now BAN the item they fetch -- the permissive walk was crossing the
        # own(Hammer)-priced cellar exit while judging whether the Hammer was still
        # obtainable, i.e. assuming the hammer to fetch the hammer, the exact assumption
        # `_psucc`'s ban parameter documents as the parachute lesson. The `priced` precheck
        # (items named by some edge alternative or in-room write cost) keeps every other
        # item's walks bit-for-bit permissive. Row: reg12=85, flip room 86, needed at 86.
        # ✅ PHASE 1 LANDED 2026-08-14 -- "the cat-scene window reaches the kidnap read", "the
        # roc's-nest lamb fold is caught" and "the eagle's pie swallow strands the yeti's
        # counter-item" are GREEN and no longer listed. `missability.ownedby_death_folds`:
        # an arrival that forks on an OWNER VALUE, whose losing arm cannot be survived
        # (`_room_unavoidable`, the classifier fatal_uses answers to), demands the value at
        # the room's entry -- rm86's yourStuck (all four pool items, prev==85), rm42's hatch
        # state-6 fork (the lamb; its death chain sits behind a `(++ state)` skip the
        # transition model now reads -- compile._interp), and rm35's killEgo (the pie,
        # prev==36; the rm36 chase itself makes no claim because a `Chase` state is a race
        # the player can decline by leaving, which keeps KQ4's rm49 dog out). LSL2/KQ4
        # surfaces byte-identical plus the new empty key; KQ5 moved by pure addition.
        # The fish flipped with the same rows (its rm86 demand); the BEES half is the
        # narrower red below.
        # ✅ RULED AND RE-PINNED 2026-08-16b -- "mechanism pinned: Shoe" / "Stick" were
        # declared red earlier the same day pending this ruling, and are GREEN. They pinned the
        # `dangerous_sinks Shoe@rm12 / Stick@rm12` rows ("spending it at the dog leaves it needed
        # at the cat"), which f623aa2 retired. USER: *"you can't skip the bear... use your shoe on
        # the dog, that's okay, finish the bear, get the stick, and use that on the cat. it's not
        # a softlock."* The source agrees and says why the pool cannot be starved at all:
        # `rm006.sc:112` inits the cat and the rat only under `(or (has: 8) (has: 16))`, and
        # flag 83 -- the window -- is set by `rm006::doit` only once the rat is on screen, so
        # walking in empty-handed neither spends anything nor closes anything. The rows were
        # FALSE POSITIVES; both items are now pinned to the rm86 pool demand alone and sit in
        # EXPECTED_CAUGHT. docs/KQ5-ORACLE.md §1.
        # ✅ PROMOTED 2026-08-17 -- "🔴 KNOWN GAP (KQ5): the bees' flag-36 window closure is
        # caught" is GREEN and no longer listed. It was never a register-flip window at all (the
        # 2026-08-16b note here already corrected that): flag 36's only writer is `bearScript`,
        # the bear exists only while `has: 5`, and the bear takes item 5 alone -- so what shuts
        # the window is an ITEM SPENT SOMEWHERE ELSE, and the shape is a sink, not a closure.
        # Three derivations, none of which moves anything alone (docs/KQ5-ORACLE.md §16):
        #
        # (a) A TRADE TO A ROOM IS A DESTRUCTION WHEN THE ITEM CANNOT COME BACK. `destroying_
        # sinks` admitted only `put:` with NO destination, on the ground that owner -1 is not a
        # room so no `ownedBy: gCurRoomNum` acquisition can be met again -- but that argument is
        # about the DESTINATION, not about -1, and `(gEgo put: 5 6)` hands the fish to the cat's
        # room just as finally. ⛔ The one-step version of that test ("does any acquisition demand
        # owner == dest") is WRONG and KQ4 proved it: `Room3::newRoom` parks Cupid's bow at 202
        # whenever you leave it lying, and `doCupid` -- armed one visit in three under
        # `ownedBy: 202` -- brings it back, so 202 is where the bow is SUPPOSED to rest and the
        # naive rule condemned it. The reading is a graph: `_owner_graph` makes each owner value a
        # node and each transfer an edge (source = what its guard demands about the item's
        # location, wildcard when it demands nothing), and `drop_is_permanent` asks whether EGO is
        # reachable. `destroyed_is_permanent` is now that same function called with NOWHERE -- one
        # rule, one implementation. It needed `opmodel.machine_moves`: `Step.moves` has always
        # carried `(item, dest)` and `_machine_info` reduced it to a bare set of item numbers, so
        # a cutscene handing an item back to the world was invisible in every reading.
        #
        # (b) `disjunctive_groups` GROUPED BY STATE AND READ BY REQUIREMENT. Entries are
        # alternatives only when they arm the same thing, and the cat's one item-free entry at
        # state 0 was discarding the seven throw entries as "one alternative is free"; and a throw
        # entry's guard carries the scene's arming disjunction alongside the act, so
        # `_own_positive` returned {8,16} for every entry and the shared intersection killed the
        # group. By state, with `_own_required`, the derivation is rm6 -> {Fish, Shoe, Stick,
        # Leg_of_Lamb} and rm12 -> {Shoe, Stick, Leg_of_Lamb} -- the asymmetric pool the USER
        # PLAY-CONFIRMED on 2026-08-16 ("that wouldn't divert the dog's attention"), derived
        # rather than recorded.
        #
        # (c) THE DISJUNCTIVE RESCUE READ AT THE CONSUMER. An alternative is only an alternative
        # for the gate it opens. Asked at the spend site, "the cat takes a Shoe too" excuses
        # spending the Fish there -- while the room that still needs the Fish is rm11, where the
        # bear takes nothing else. Read at the room where the item is STILL NEEDED, the Shoe and
        # the Stick keep their rescue (the user's own 2026-08-16b ruling, pinned green) and the
        # Fish loses it. Same rule as [[an-item-some-armings-demand-is-not-a-gate]].
        #
        # MEASURED across the corpus: LSL2's golden sink set is the v1.0-lsl2 tag exactly
        # (Matches / Hair_Rejuvenator x3 / Parachute / Airsick_Bag x3) and its one group is
        # unchanged; KQ4 keeps its single Magic_Fruit row and gains no group (the Cupid FP the
        # one-step test created is gone); KQ6 holds at four rows and two groups; LB2 stays at zero
        # sinks and gains one group that moves no finding. KQ5 gains the Fish row, and the Pie's
        # pinned sink moves rm38 -> rm1 (a strengthening -- see the pin) plus a second row at
        # rm34. Rebuilt as two green pins, one per direction of (c).
        # ✅ PROMOTED 2026-08-16b -- "🔴 KNOWN GAP (KQ5): the cat window's closure on arming is
        # caught" is GREEN and no longer listed. `missability.window_closures` is phase 3: the
        # fold rows state that the kidnap DEMANDS a banked throw, and these state that the only
        # way to bank one shuts by itself. The conjunct a room-reachability test cannot supply is
        # PRODUCER LIVENESS -- rm6 stays walkable forever, what stops being possible is the throw
        # -- so each producer is read through `guard_reqs` against the register being flipped and
        # a row needs every one of them dead at that value. Two closers, both real: flag 83 goes
        # up as the chase ARMS (rm006::doit, win or lose) and rm6's `local0` when you LOSE the
        # race. It landed with `extract.feature_adders`, without which three of the seven
        # `put: <item> 6` sites -- `catStrip`, which joins the cast only via
        # `(gGame setFeatures: catStrip)` -- carry none of the scene's arming and the closure is
        # invisible. Four rows, one per pool member, mechanism-pinned.
        # ✅ PROMOTED 2026-08-16 -- "🔴 KNOWN FP (KQ5): no carry-in demand rides the rm57->rm683
        # cutscene" is GREEN and no longer listed, and it took `test_toll.py`'s two KQ5
        # assertions green with it, as the red said it would. rm683 is `cdCassimaToon`, a CD
        # cutscene that tests no item at all; the own(Cat_Fish)/own(Bag_of_Peas) demands were
        # broadcast into it because `castle.sc` is the region live in all 16 castle rooms and
        # `theCat` had NO presence condition -- its bagged arm is
        # `(and (== global332 7) (== global338 gCurRoom))` and an unreadable disjunct frees the
        # whole OR. `extract.room_valued_globals` derives what such a global can hold (least
        # fixpoint based at false, because the machine that writes it is armed from the cat's own
        # handler) and lowers the compare to the room disjunction it means. Measured:
        # g338 -> {57,58,59,60,61,63,64}, the rm57->rm683 toll rows and their patch guard gone,
        # every other KQ5 row unmoved; LSL2, KQ4, KQ6 and LB2 byte-identical on the FULL surface
        # with placements (KQ4 and LB2 derive a room-valued global of their own and do not move).
        # ✅ PROMOTED 2026-08-15 -- "🔴 KNOWN FP (KQ5): no detector demands the Wand" is GREEN and
        # no longer listed. `missability._unrefusable_grants`: rm001.sc:78 hands Crispin's wand to
        # anyone entering room 1 without it, in `init`, under no other condition, so
        # `_reach_without(28)` stops at rm1 and the two analyze rows (plus the Wand's conjunct in
        # the rm40->rm41 spec) go with it. The full snapshot surface of LSL2, KQ4, KQ6 and LB2 is
        # byte-identical, placements included. Mechanism in docs/KQ5-ORACLE.md §10 -- including
        # the site that DOES take the wand (rm066's machine tray), which the old reason denied.
        # ✅ RETIRED 2026-08-17, USER-RULED IN THE GAME -- "🔴 KNOWN GAP (KQ5): the fortune
        # teller's needle substitution is caught" is gone because it DEMANDED THE WRONG ROW, not
        # because a build landed. It asserted that some detector flags the Golden_Needle, on the
        # tier-3 claim that paying the gypsy with it makes the game unwinnable "because the
        # needle's real consumer is the tailor". Both halves are false.
        #
        # The reason, refuted by the source: `tailorShop.sc:143-151` accepts Golden_Needle(3),
        # Gold_Coin(11) OR Heart(9). KQ5 runs a FIVE-TOKEN MARKET over four purchases --
        # gypsy{3,11}->Amulet, tailor{3,9,11}->Cloak, toyMaker{3,9,11,12}->Sled,
        # baker{3,4,9,11}->Pie, with tokens Needle(rm27), Coin(rm4), Heart(rm21), Gold_Coin(rm18)
        # and Marionette(rm10). Every token is reachable before the amulet is needed (the temple is
        # a short walk from town via rm14/15 -> rm212/213 -> rm214), so a perfect assignment
        # survives ANY single payment.
        #
        # The verdict, refuted by the USER in two steps: the gypsy takes the needle, and the tailor
        # then sells the cloak for the gold coin. So the model emitting nothing is CORRECT, and a
        # row would have been a false positive. Rebuilt as two green pins -- the market reads as
        # four alternative-sets (`disjunctive_groups` at rm13/rm5/rm206), and no detector strands a
        # token -- the same shape the witch amulet's red was rebuilt into on 2026-08-16b.
        #
        # ⚠️ WHAT SURVIVES IS A DIFFERENT MECHANISM, and it is recorded as OPEN rather than as a
        # missed catch (docs/KQ5-ORACLE.md §6): spending BOTH 3 and 11 away from the gypsy empties
        # a slot no other token fills, because the Heart is two screens into the forest the amulet
        # opens. That is a Hall deficiency over the market and needs TWO wrong payments, so no
        # single-spend detector can state it. Do not re-declare it as this row.
        #
        # ⛔ The scoring tell is NOT evidence and must not be used as any detector's conjunct:
        # `proc0_27 3` fires only for coin->gypsy and `proc0_27 4` only for needle->tailor, which
        # marks Sierra's intended pairing. We already knew that tell is not a softlock signal --
        # the Lamb and the Fish score nothing at the cat and still save the mouse.
        #
        # ✅ BOTH 2026-08-17 REDS PROMOTED 2026-08-17b -- "the shop market squeeze is caught" and
        # "spending the Heart at a shop is condemned by the Harp it costs" are GREEN and no longer
        # listed, closed by ONE detector because they were never two problems. The USER's framing,
        # verbatim: "the 3 vendors and the gypsy each accepting some payments that can starve
        # other merchants, when everything you get from the merchants is required."
        # `missability.market_squeezes` derives the market (who must be paid, out of which
        # one-copy tokens -- four requiredness readings, each corpus-witnessed, see its
        # docstring) and condemns a payment exactly when the residual has no perfect matching.
        # KQ5 9 rows: the heart at any shop (the princess starves -- the Harp's sole source),
        # the needle/gold coin at the toy maker or baker (the gypsy-tailor-princess triangle
        # drops to two tokens for three purchases), and the pie eaten or fed to the eagle (the
        # yeti's rm35 fold, restated from the matching side). MEASURED: LSL2 0, KQ4 0, KQ6 0,
        # LB2 0. Every user-ruled safe play is silent: needle->gypsy, coin->tailor, the pool.
        #
        # ⚠️ The squeeze's old "needs TWO payments" framing was SHARPENED by the user's cloak
        # ruling ("the cloak is needed", 2026-08-17b): with all five products required the
        # needle/coin rows are ONE-payment dead ends -- the old two-payment story rested on the
        # heart covering the tailor, which the Heart ruling itself removed.
        #
        # ⛔ The Heart red's DECLARED CURE was wrong, and it was measured twice and rejected
        # twice: widening `destroying_sinks` over `machine_moves` cost 19 FPs on 2026-08-17,
        # and after the region-broadcast and put-HERE causes were fixed it still cost 8 KQ6
        # rows (the pawn shop reading intended uses as competing with the rm280 counter) and
        # 2 LB2 pressPass rows CARRYING TWO SHIPPED PLACEMENTS -- and KQ6 is GOLDEN, exactly
        # like LSL2/KQ4 (user, "as I've said many times"). The market states the same Heart
        # facts with zero movement anywhere else. [[re-derive-a-reds-premise]], for a cure.
        #
        # ✅ PROMOTED 2026-08-17b -- "🔴 KNOWN GAP (KQ5): eating the lamb is condemned by the
        # eagle it starves" is GREEN and no longer listed, and its stated cure was REFUTED
        # rather than built ([[re-derive-a-reds-premise]], on a cure, twice in one day). It
        # prescribed owner-gating the cupboard acquisition; the true fact is that SCARCITY IS
        # CONSUMER-RELATIVE: the eagle's fold sits at rm42, past the roc, and
        # `reobtainable_rooms(19)` already excludes rm42 -- the same gate-aware fact the lamb's
        # analyze carry-across row rests on -- so to the one consumer that matters every lamb
        # is the last lamb, restockable cupboard or not. `_market` now waives pressure only for
        # a token re-suppliable FROM THE CONSUMER'S OWN ROOMS, and the loss/satisfaction reads
        # follow (a spend is a loss to a consumer that can never re-fetch; a spend TO the
        # fold's own destination is its satisfaction). THREE rows landed, not one: the EAT
        # verb, and the cat and dog throws -- oracle §1a's "throw the lamb at the cat or dog
        # -> rm42 death", a declared TRUE softlock never before caught. Corpus: LSL2 0, KQ4 0,
        # KQ6 0, LB2 0, KQ5 9 -> 12. Rebuilt as two green pins (the three rows; the lamb TO
        # the eagle stays silent).
        # ✅ RETIRED 2026-08-16b, USER-RULED -- "🔴 KNOWN GAP (KQ5): the witch-region worn-amulet
        # death fold is caught" is gone because it DEMANDED THE WRONG ROW, not because a build
        # landed. It asserted that some detector flags the Amulet, on the oracle's old verdict
        # that walking into the dark forest without it strands you. USER: "on rm19 you can get
        # back out. I don't think you can get more than 1 screen into the forest, but that's
        # fine. so you need the amulet but it's not a stranding." Measured agreement: from rm19,
        # 98 of the 100 reachable rooms are still reachable -- rm13, the fortune teller, among
        # them -- and rm680, the amulet handover, is entered only from rm13.
        #
        # ⛔ AND ITS STATED REASON WAS WRONG TOO: region scope was never the blocker; script
        # 200's machines are attributed to rm19-26 and always were. What hid the fork was an
        # unread `(+= state 4)` -- the relative setstate with a stride -- which sent BOTH arms of
        # the fireball fork into state 8's proc0_26. Fixed in compile._interp and
        # machine._op_leaf; `required[27]` went [0, 13] -> all seven forest rooms.
        #
        # Rebuilt GREEN as two pins: "the worn-amulet fireball fork demands the Amulet in every
        # forest room" (the demand, which is what the fix bought) and "no detector claims the
        # Amulet is STRANDED" (the FP guard, same shape as the Wand's). docs/KQ5-ORACLE.md §7.
        # ✅ PROMOTED 2026-08-16b -- "🔴 KNOWN FP (KQ5): fatal_uses does not condemn the
        # tambourine" is GREEN and no longer listed. The SIXTH savior-condemned correction, and
        # the first where the item was named by WHO WAS IN THE ROOM rather than by anything the
        # player did: Dink is init:ed only under `(has: 34)`, his script arms `hugScript`, and
        # hugScript's state 5 is a death -- so own(34) sat in the lethal entry as the monster's
        # existence condition. Giving the tambourine is the ESCAPE, so the row became
        # `action_specs: Tambourine@rm55: (not (has: 34))` -- a SHIPPED PATCH WITHHOLDING THE
        # ITEM THAT SAVES YOU, the Spinach_Dip shape. Cured by `Machine.entry_site`: the guard as
        # built at the arming site, before `_chain_entries` and `_inherit_local_continuations`
        # strengthen it. `entries[i]` is what must hold; `entry_site[i]` is what the player did,
        # and fatal_uses wanted the second. KQ6's skull survives (its own() comes from
        # `theGears doVerb 51`, at the site); LSL2/KQ4/KQ6/LB2 byte-identical.
    },
}

CHECK = re.compile(r"^\s*\[(PASS|FAIL)\]\s*(.*?)\s*$")
TALLY = re.compile(r"^(\d+) passed, (\d+) failed")
# A gate that cannot find its game says so and returns True. That is the right behaviour on a
# machine without the games -- and it is also how the whole regression net can report success
# having asserted nothing, because this runner only ever compared the FAILING set to KNOWN_RED.
# Skips are now counted and printed; `--strict` turns them into failures.
SKIPPED = re.compile(r"^\s*\(skip\b", re.I)


def run_one(path, echo=True):
    """Run one test file, streaming its output.

    Returns (passed, failed_names, exit_code, skips)."""
    proc = subprocess.Popen([sys.executable, "-u", path], cwd=SRC,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    passed, failed, skips = 0, [], []
    for line in proc.stdout:
        if echo:
            sys.stdout.write("    " + line)
            sys.stdout.flush()
        m = CHECK.match(line)
        if m:
            if m.group(1) == "PASS":
                passed += 1
            else:
                failed.append(m.group(2))
        elif SKIPPED.match(line):
            skips.append(line.strip())
    proc.wait()
    return passed, failed, proc.returncode, skips


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    strict = "--strict" in argv
    argv = [a for a in argv if a != "--strict"]
    names = sorted(f for f in os.listdir(SRC) if f.startswith("test_") and f.endswith(".py"))
    if argv:
        names = [f for f in names if any(a in f for a in argv)]
    if not names:
        raise SystemExit("no test files matched")

    t0 = time.time()
    total_pass, unexpected, promoted, crashed = 0, [], [], []
    skipped, silent = [], []
    for f in names:
        print(f"\n\033[1m=== {f}\033[0m", flush=True)
        t1 = time.time()
        passed, failed, code, skips = run_one(os.path.join(SRC, f))
        total_pass += passed
        red = KNOWN_RED.get(f, {})
        unexpected += [(f, n) for n in failed if n not in red]
        promoted += [(f, n) for n in red if n not in failed]
        skipped += [(f, s) for s in skips]
        # A file that asserts NOTHING is not a passing file. Under the old accounting it was
        # indistinguishable from a clean one, because only failures were ever compared to
        # KNOWN_RED -- so a machine without the games printed "agrees with KNOWN_RED" having
        # checked nothing at all.
        if passed == 0 and not failed:
            silent.append(f)
        # A file that dies before printing a tally (import error, traceback) fails silently
        # under a pure check-line count -- it has no FAIL lines to find. Catch it on the code.
        if code != 0 and not failed:
            crashed.append((f, code))
        print(f"  \033[2m-- {passed} passed, {len(failed)} failed"
              + (f", {len(skips)} skipped" if skips else "")
              + f" ({time.time() - t1:.0f}s)\033[0m", flush=True)

    n_red = sum(len(v) for k, v in KNOWN_RED.items() if k in names)
    print("\n" + "=" * 78)
    print(f"\033[1m{total_pass} passed, {n_red - len(promoted)} known-red, "
          f"{len(unexpected)} unexpected, {len(crashed)} crashed"
          + (f", {len(skipped)} skipped" if skipped else "")
          + f"\033[0m  ({time.time() - t0:.0f}s)")
    # SKIPS IN THE HEADLINE, so "green" cannot quietly mean "absent". Each one is a gate that
    # did not run because its game files were not there.
    for f, s in skipped:
        print(f"  \033[33mskipped\033[0m  {f}: {s}")
    for f in silent:
        print(f"  \033[31mASSERTED NOTHING\033[0m  {f}: no [PASS]/[FAIL] line -- the file ran "
              f"but checked nothing, which is not the same as passing")

    for f, name in unexpected:
        print(f"  \033[31mUNEXPECTED FAILURE\033[0m  {f}: {name}")
    for f, code in crashed:
        print(f"  \033[31mCRASHED\033[0m  {f}: exit {code} with no FAIL line -- import error or "
              f"traceback; run it directly")
    for f, name in promoted:
        print(f"  \033[33mRED WENT GREEN\033[0m  {f}: {name}\n"
              f"      {KNOWN_RED[f][name]}\n"
              f"      If the gap really is closed, say so with the user and remove it from "
              f"KNOWN_RED in this file. Until then this is a failure, because a limitation "
              f"that silently stops being one is a limitation nobody will remember to re-check.")
    # A file that asserted nothing is always a failure; a SKIPPED section is one only under
    # --strict, because skipping is correct on a machine that does not have the game.
    bad = bool(unexpected or crashed or promoted or silent or (strict and skipped))
    if not bad:
        # ⛔ "AGREES WITH KNOWN_RED" IS NOT "GREEN", AND SAYING SO IN GREEN WAS A LIE OF TONE.
        # USER 2026-08-16: "I don't like that we report a suite green when we're in the process of
        # building a game and there are still 6 reds." The contract this file exists to enforce is
        # about MOVEMENT -- no undeclared failure, no silent promotion -- and it is satisfied
        # whether the declared set holds one gap or twenty. That is worth an exit code, not a
        # colour. So the outstanding gaps are COUNTED and the closing line only turns green when
        # there are none left to count.
        outstanding = [(f, name) for f, red in KNOWN_RED.items() if f in names for name in red]
        for f, name in outstanding:
            print(f"  \033[2mknown-red\033[0m  {f}: {name}")
        skip_note = ("" if not skipped else
                     f"  \033[33m({len(skipped)} section(s) skipped -- those gates did not run; "
                     f"`--strict` fails on them)\033[0m")
        if outstanding:
            by_file = {}
            for f, _name in outstanding:
                by_file[f] = by_file.get(f, 0) + 1
            where = ", ".join(f"{f.removeprefix('test_').removesuffix('.py')} {n}"
                              for f, n in sorted(by_file.items()))
            print(f"\n\033[33mNo movement: the failing set is exactly the declared one. "
                  f"{len(outstanding)} declared gap(s) still open ({where}) -- this run is NOT "
                  f"a clean bill of health.\033[0m" + skip_note)
        else:
            print("\n\033[32mThe suite is green: nothing failed and nothing is "
                  "declared red.\033[0m" + skip_note)
        return 0
    if strict and skipped and not (unexpected or crashed or promoted or silent):
        print("\n\033[31m--strict: the run is red because gates were SKIPPED, not because "
              "anything failed. A regression net that can go green by being absent is not a "
              "net.\033[0m")
    return 1


if __name__ == "__main__":
    sys.exit(main())
