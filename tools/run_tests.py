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
KNOWN_RED = {
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
        "🔴 KNOWN GAP (KQ6): every non-refused spec places":
            "PHASE 4. The arrival-commit re-site LANDED 2026-08-04: the capture demand sits on "
            "the isle's entry frontier (rm320's cue arm-gate + rm300's shortcut nav-assign "
            "re-route -- finding #8's bypass -- stage-conditioned with the game's own "
            "capture-arm test, sites from guards.commit_entry_frontier -- model knowledge, "
            "not text search), so the rm340 rows all place. Remaining skips, both "
            "deliberate: rm420->rm435 (the shared-dispatcher seam; its demand is covered by "
            "the capture guards) and the huntersLamp sink (a TRADE; its remedy is the mists "
            "carry-in). Goes green only when those two either place or become refusals.",
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
        "🔴 KNOWN GAP (KQ5): the bees' flag-36 window closure is caught":
            "flag 36's only writer is bearScript (runs only while `has: 5` spawns the bear); "
            "the hive arms deathByBees under not-flag36, so the honeycomb -> beeswax -> boat "
            "chain dies with the wasted fish. Phase 3 (window closure): a demanded value "
            "whose every producer is guarded on a flag the producers' own trigger sets.",
        "🔴 KNOWN GAP (KQ5): the cat window's closure on arming is caught":
            "The rm86 demand rows are green, but flag 83 is set the moment the chase STARTS "
            "(rm006::doit) -- every producer of `owner == 6` sits inside a window that "
            "closes on arming, win or lose, and no row states the window. Phase 3; the same "
            "fact is patch A's hold site.",
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
        "🔴 KNOWN GAP (KQ5): the fortune teller's needle substitution is caught":
            "rm13's amulet slot takes Gold_Coin(11) OR Golden_Needle(3); the needle's real "
            "consumer is the tailor (-> cloak). Exchange-slot class ([[exchange-slots-one-"
            "statement-one-item]]) -- the detector for 'a slot consumed by an item another "
            "slot demands' does not exist yet.",
        "🔴 KNOWN GAP (KQ5): the witch-region worn-amulet death fold is caught":
            "witchRegion.sc's fireball is survived only under `(and (has: 27) flag84)` -- worn "
            "IS modelled (flag 84, the ordinary bit store), but the fold lives in a REGION "
            "script and the death-fold scope stops at rooms. Extending it to setRegions "
            "scripts is the build.",
        "🔴 KNOWN FP (KQ5): fatal_uses does not condemn the tambourine":
            "hugScript (Dink's hug, proc0_26 death) arms under own(34) because Dink only "
            "EXISTS while you hold the tambourine, and giving it (giveTamboScript, the "
            "hairpin's source) is the escape from that very machine. Savior-condemned family, "
            "sixth member, NEW POLARITY: the item rides the arming guard, not a branch. The "
            "cure belongs in fatal_uses' survivability reading, not in the oracle.",
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
        for f, red in KNOWN_RED.items():
            if f in names:
                for name in red:
                    print(f"  \033[2mknown-red\033[0m  {f}: {name}")
        print("\n\033[32mThe suite agrees with KNOWN_RED.\033[0m"
              + ("" if not skipped else
                 f"  \033[33m({len(skipped)} section(s) skipped -- those gates did not run; "
                 f"`--strict` fails on them)\033[0m"))
        return 0
    if strict and skipped and not (unexpected or crashed or promoted or silent):
        print("\n\033[31m--strict: the run is red because gates were SKIPPED, not because "
              "anything failed. A regression net that can go green by being absent is not a "
              "net.\033[0m")
    return 1


if __name__ == "__main__":
    sys.exit(main())
