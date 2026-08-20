"""The 2026-08-19d contextless review's DERIVABILITY and SOUNDNESS findings, as unit tests.

docs/REVIEW-2026-08-19d-FIXES.md. Every one of these is LATENT on today's five games: the fuse
classification, the escape pricing and the two arming remedies emit rows only on KQ5, and on
KQ5 the missing conjunct happens to be satisfied. That is the same "fails silent and green"
shape `test_deletion_soundness.py` exists for, and it gets the same answer: a synthetic fixture
states the failure mode in fifteen lines, where a game states it only if the game happens to
have one.

Each test carries BOTH directions -- the case the rule must refuse AND the case it must still
accept -- because most of these have an obvious "fix" that simply deletes the rule, and deleting
it loses the measured KQ5 behaviour the rule was built for.

  F4  `_death_fuses`' countdown was "any register compared nonzero on the write's spine", not
      "a register this handler counts DOWN". That is the root cause of the self-re-arm
      exclusion, a clause whose only job was to keep a known answer still
      ([[clause-that-protects-a-known-answer]]).
  F9  a machine that can only TOP UP a countdown was condemned as one that lights it, and a
      condemned machine can never be an ESCAPE.
  F10 `price()`'s continuation admits escapes the chain's own writes have made unarmable.
  F11 discharge was applied to NEGATIVE flag demands, turning an unsatisfiable alternative
      into a free one.
  F7  neither arming remedy asks whether its demand can be PAID -- the anti-wall gate its
      sibling `fold_carryins` has had since it was written.
  F12 `if (a for a in ...) and not alts:` -- a generator is always truthy.
  F13 the fuse row named one spawning procedure out of however many there are, and two
      per-room demands could both be conjoined onto one site.
  F15 the capture row read arming rooms polarity-blind.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guards as G                                                       # noqa: E402
import missability as M                                                  # noqa: E402
from guard_ast import GAnd, GNot, GOr, Pred                                 # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"\n      {detail}" if detail and not cond else ""))


def _cmp(r, op, v):
    return Pred("CMP", r, op, v)


def _own(i):
    return Pred("OWN", i, None, None)


CTR = ("CTR", ("L", 5), "!=", 0)          # `(if local5 ...)` -- the tick latch, as extracted
FBASE = 1000


def _machine(inst, room, entries, states, recv=(("G", 2),), armers=None):
    return {"inst": inst, "room": room, "entries": list(entries), "init_entries": [],
            "entry_armers": list(armers) if armers else [None] * len(entries),
            "entry_locals": [{}] * len(entries), "entry_recv": list(recv),
            "restores_control": set(), "states": states, "drops": (), "script": 10}


def _model(machines, handler_writes, decs, regs, sources=None, reach=(1,)):
    """A duck-typed `IrSccReach` carrying only what `_death_fuses` and `_Escapes` read."""
    ir = types.SimpleNamespace(flag_synth_base=FBASE, flag_indices=frozenset(range(200)),
                               scripts={})
    f = types.SimpleNamespace()
    f.em = types.SimpleNamespace(machines=list(machines), dropped_entries=(),
                                 handler_writes=list(handler_writes),
                                 handler_decs=frozenset(decs), ir=ir,
                                 ts=types.SimpleNamespace(placed={}))
    f.reach_rooms, f.sources, f.regs = set(reach), dict(sources or {}), set(regs)
    f.NOWHERE = set()
    f.g = types.SimpleNamespace(item_name=lambda i: "item%d" % i)
    return f


# --- F4: the countdown is the register the handler COUNTS DOWN ----------------------------------
#
# The clock's shape, abstracted from castle::doit: a per-cycle handler writes a death phase when
# a countdown runs out, and the countdown's own `(-- global352)` is right there in the same
# handler. `global333`, the henchman's MODE register, sits on the same spine and is not a clock
# at all -- and "any register compared nonzero" cannot tell the two apart, which is why an
# exclusion had to be invented to keep it out.
def _clock_model(extra_spine=(), extra_writes=(), decs=((1, 10, 900),)):
    doom = _machine("sDoom", 1, [(0, GAnd([_cmp(800, "==", 3)]))],
                    {0: [([], (), (), (), ("DEATH", 0))]})
    writes = [(1, 10, 800, 3, GAnd([CTR, _cmp(900, ">", 0)] + list(extra_spine)))]
    return _model([doom], writes + list(extra_writes), decs, {12, 800, 900, 901})


def test_the_countdown_is_the_register_the_handler_decrements():
    print("\n-- missability._death_fuses: a fuse is a register that COUNTS DOWN --")
    fuses, phases, deaths, _pr = M.IrSccReach._death_fuses(_clock_model())
    check("the plain clock still classifies (the case the rule exists for)",
          fuses == {900} and phases == [(800, 3)] and deaths == ["sDoom"],
          detail="fuses=%r phases=%r deaths=%r" % (fuses, phases, deaths))

    # ...and the same clock with a MODE register conjoined onto its spine. Nothing about
    # `global333` is a countdown: no handler decrements it, it is the scene state the fuse
    # write happens to be scoped by.
    got, _p, _d, _pr = M.IrSccReach._death_fuses(
        _clock_model(extra_spine=[_cmp(901, "!=", 0)]))
    check("a mode register on the same spine is NOT dragged in as a second fuse",
          got == {900},
          detail="fuses=%r -- 901 is compared nonzero and never decremented, so it is scene "
                 "state, not a clock. Promoting it is what forced the self-re-arm exclusion "
                 "(`S not in cds`), a clause written to keep a known answer still." % (got,))

    # ...and the SELF-RE-ARM write that exclusion was invented for: the cycle continuing
    # (`global353 := 5` while 353 runs), which must grow the fuse set by nothing at all --
    # with no special case naming it.
    got2, _p, _d, _pr = M.IrSccReach._death_fuses(_clock_model(
        extra_spine=[_cmp(901, "!=", 0)],
        extra_writes=[(1, 10, 900, 5, GAnd([CTR, _cmp(900, "!=", 0), _cmp(901, "!=", 0)]))]))
    check("a countdown re-arming ITSELF grows the fuse set by nothing, with no special case",
          got2 == {900}, detail="fuses=%r" % (got2,))

    # ...and CHAINING still closes: 900's expiry lighting 901 makes 901 a fuse too, but only
    # because a handler counts 901 down as well.
    got3, _p, _d, _pr = M.IrSccReach._death_fuses(_clock_model(
        extra_writes=[(1, 10, 900, 3, GAnd([CTR, _cmp(901, "!=", 0)]))],
        decs=((1, 10, 900), (1, 10, 901))))
    check("the fuse set still closes under CHAINING (KQ5's 353 -> 352 -> phase)",
          got3 == {900, 901}, detail="fuses=%r" % (got3,))


def test_a_region_clock_does_not_promote_prevroom():
    print("\n-- missability._death_fuses: `== <nonzero>` on prevRoom is not a countdown --")
    # `_demands_nonzero` accepts `(== reg N)` for any nonzero N, and the previous-room register
    # is in `regs`. A game whose region clock writes a phase under `(== gPrevRoom 85)` -- or
    # under `(== gAct 2)` -- would promote the realm seal, or the act, to a FUSE, and every
    # machine that writes it to a committed death. Catastrophic on LB2; inert today only for
    # want of a seed. The decrement is what tells a countdown from a scoping equality.
    fuses, _p, _d, _pr = M.IrSccReach._death_fuses(
        _clock_model(extra_spine=[_cmp(12, "==", 85)]))
    check("a `prev == 85` scoping conjunct is not promoted to a fuse",
          fuses == {900},
          detail="fuses=%r -- nothing decrements the previous-room register; it scopes the "
                 "write, it does not time it." % (fuses,))


# --- F9: lighting a fuse is not the same as topping one up --------------------------------------
def test_a_bounded_topup_is_not_a_lighting():
    print("\n-- missability._fuse_machines: a write that can only RAISE is not a commitment --")
    # rm067's `(if (< global353 120) (= global353 120))`: the guard bounds the register BELOW
    # the value written, so the write cannot hasten anything -- it is the game handing the
    # player time. Condemning it makes `henchCaught` and `zzzScript` fuse-lighters, and a
    # fuse-lighter is barred from ever being an ESCAPE.
    topup = _machine("sTopUp", 1, [(0, GAnd([]))],
                     {6: [(GAnd([_cmp(900, "<", 120)]), ((900, 120),), (), (), ("ADVANCE",))]})
    light = _machine("sLight", 1, [(0, GAnd([]))],
                     {3: [(GAnd([_cmp(900, "!=", 0)]), ((900, 3),), (), (), ("ADVANCE",))]})
    fm = getattr(M, "_fuse_machines", None)
    if fm is None:
        check("the fuse-lighting classification is a named, testable rule",
              False,
              detail="`missability._fuse_machines` does not exist -- the rule is written twice "
                     "inline, in `fuse_death_armings` and in `capture_fold_armings` "
                     "([[same-rule-two-places]]), and neither copy can be exercised.")
        return
    got = fm([topup, light], {900})
    check("a write bounded below the value it writes is not a lighting",
          got == {"sLight"},
          detail="fuse machines=%r -- `(< 900 120) -> 900 := 120` can only raise the "
                 "countdown, so running it commits to nothing." % (sorted(got),))
    check("...and a write that can SHORTEN one still is (KQ5's cat: 353 := 3 while running)",
          "sLight" in got, detail="fuse machines=%r" % (sorted(got),))


# --- F11: discharge must not make an unsatisfiable alternative free -----------------------------
def test_discharge_does_not_erase_a_negative_demand():
    print("\n-- missability._Escapes.tokens: a chain write can FALSIFY, not only discharge --")
    E = M._Escapes(_model([], [], (), {800}), [], {}, set())
    pos = GAnd([_cmp(FBASE + 62, "!=", 0)])                  # demands flag 62
    neg = GAnd([GNot(_cmp(FBASE + 62, "!=", 0))])            # demands NOT flag 62

    def _tok(g, discharged):
        """(tokens, eqs, unsatisfiable). The third element is the whole finding: today
        `tokens` returns only two, because a contradiction has nowhere to be reported."""
        r = E.tokens(g, discharged)
        return r if len(r) == 3 else (r[0], r[1], None)

    toks, _eqs, bad = _tok(pos, frozenset({(FBASE + 62, 1)}))
    check("a POSITIVE demand the chain already wrote is discharged (the rule's own job)",
          not bad and not toks, detail="tokens=%r bad=%r" % (toks, bad))
    toks2, _eqs2, bad2 = _tok(neg, frozenset({(FBASE + 62, 1)}))
    check("a NEGATIVE demand the chain contradicts makes the alternative UNSATISFIABLE",
          bad2,
          detail="tokens=%r bad=%r -- the chain sets flag 62, so a `¬62` arm can never fire. "
                 "Dropping the token instead reports that arm as FREE, and a free arm is the "
                 "cheapest alternative, so it wins `_minimal` and the demand collapses to "
                 "nothing." % (toks2, bad2))
    toks3, _eqs3, bad3 = _tok(neg, frozenset())
    check("...and with nothing discharged the same demand is an ordinary negative token",
          not bad3 and toks3 == {("nflag", 62)}, detail="tokens=%r bad=%r" % (toks3, bad3))


# --- F10: a continuation escape its own chain has DISARMED is not an answer ---------------------
def test_the_continuation_drops_escapes_the_chain_disarms():
    print("\n-- missability._Escapes.price: a chain write can DISARM the continuation --")
    # KQ5's shape, abstracted. `sHalf` answers the encounter and then re-arms it (hands off
    # into the lethal set), so it is only half an answer: its price conjoins the price of the
    # escapes of the encounter it re-arms. Those escapes are priced DISCHARGED of what the
    # chain wrote -- but discharge only ever makes an alternative CHEAPER, and the same writes
    # can make it IMPOSSIBLE. `sFull` arms only at scene state 901 == 5; `sHalf` writes 901 := 7
    # on its way out, so the encounter it re-arms has no answer left and `sHalf` is not one
    # either. This is the mechanism docs/KQ5-ORACLE.md §23 claimed and the code never had.
    death = _machine("sDeath", 1, [(0, GAnd([]))], {0: [([], (), (), (), ("DEATH", 0))]})
    full = _machine("sFull", 1, [(0, GAnd([_cmp(901, "==", 5), _own(24)]))],
                    {0: [([], (), (), (), ("ADVANCE",))]})
    # ...the machine that establishes that scene state, in a slot of its own so it is not
    # itself a competitor for the encounter's.
    setter = _machine("sSetStage", 1, [(0, GAnd([]))],
                      {0: [(GAnd([]), ((901, 5),), (), (), ("ADVANCE",))]}, recv=(("G", 3),))
    lit = _machine("sHalf", 1, [(0, GAnd([_own(37)]))],
                   {0: [(GAnd([]), ((901, 7),), (), (), ("ADVANCE",))]})
    unlit = _machine("sHalf", 1, [(0, GAnd([_own(37)]))],
                     {0: [(GAnd([]), (), (), (), ("ADVANCE",))]})
    for (half, want, name) in (
            (lit, [], "an escape whose continuation its own chain disarms prices as NO answer"),
            (unlit, [frozenset({("own", 24), ("own", 37)})],
             "...and a continuation the chain leaves armable still prices as the fixpoint")):
        infos = [death, half, full, setter]
        s = _model(infos, [], (), {901}, sources={24: {1}, 37: {1}})
        E = M._Escapes(s, infos, {("sHalf", 0): {"sDeath"}}, {"sDeath"})
        got = E.price("sHalf")
        check(name, got == want,
              detail="price=%r want=%r -- `sHalf` writes 901 := 7 and `sFull` arms only at "
                     "901 == 5, so there is no next encounter to answer. Admitting `sFull` "
                     "anyway reports `own(24) ∧ own(37)` as a way through the game does not "
                     "offer -- an UNDER-demand wherever the continuation genuinely matters."
                     % (got, want))


# --- F15: an arming room named under a NEGATION is not an arming room ---------------------------
def test_entry_rooms_reads_polarity():
    print("\n-- missability._entry_rooms: `(not (== gCurRoom 67))` names no arming room --")
    import extract as X
    cur = getattr(X, "_CURROOM", None)
    if cur is None:
        check("the current-room register is derivable", False, "no extract._CURROOM")
        return
    s = _model([], [], (), {cur}, reach=(54, 58, 59, 67))
    info = {"entries": [(0, GAnd([_cmp(cur, "==", 54)])),
                        (0, GAnd([_cmp(cur, "==", 59), GNot(_cmp(cur, "==", 67))]))],
            "init_entries": []}
    got = M.IrSccReach._entry_rooms(s, info)
    check("only the rooms an entry POSITIVELY names are reported",
          got == [54, 59],
          detail="arm_rooms=%r -- rm67 appears only under a negation, so the machine cannot "
                 "arm there and a guard's effect is not felt there either." % (got,))

    # ...and the shape a REGION machine actually has, which is why the read cannot stop at the
    # AND spine: one disjunction of per-room arms, each still carrying the cond-ordering
    # negations of the arms above it. Every room named positively in one of those arms is a
    # room this machine arms in.
    region = {"entries": [(0, GAnd([GOr([
        GAnd([_cmp(cur, "==", 54)]),
        GAnd([GNot(_cmp(cur, "==", 54)), _cmp(cur, "==", 58)]),
        GAnd([GNot(_cmp(cur, "==", 54)), GNot(_cmp(cur, "==", 58)),
              _cmp(cur, "==", 67)])])]))], "init_entries": []}
    got2 = M.IrSccReach._entry_rooms(s, region)
    check("a region machine's per-room disjunction reports every arm it has",
          got2 == [54, 58, 67],
          detail="arm_rooms=%r -- stopping at the AND spine reports none of them, which is a "
                 "coverage claim shrinking in silence." % (got2,))


# --- F7 / F12 / F13: the remedies' gates --------------------------------------------------------
def _fuse_row(items, flags, procs=("proc550_16",), machine="theCatScript"):
    return {"pattern": "fuse-death-arming", "item": items[0] if items else None,
            "item_name": "x", "machine": machine, "hosts": ["theCat"], "arm_rooms": [60],
            "arm_procs": [{"script": 550, "name": p} for p in procs],
            "fuse": [352], "phases": [(331, 3)], "death": ["theWizardScript"],
            "flags": sorted(flags), "escapes": ["catInBag"],
            "demand_alts": [{"items": sorted(items), "flags": sorted(flags)}]}


def _cap_row(**kw):
    row = {"pattern": "capture-fold-arming", "machine": "theHenchManScript", "need_room": 67,
           "fold_machine": "henchCaught", "fold_state": 8, "escapes": ["theThrowPeasScript"],
           "answerless": False, "arm_rooms": [54], "host": ["theHenchMan"], "script": 550,
           "context_unrendered": [], "demand_alts": [{"owners": [], "items": [24], "flags": [],
                                                      "not_flags": [], "iprops": [],
                                                      "not_iprops": []}]}
    row.update(kw)
    return row


def _stub(sources, rows=(), cap_rows=()):
    return types.SimpleNamespace(
        em=types.SimpleNamespace(ir=types.SimpleNamespace(flag_test_proc="proc0_12")),
        sources=dict(sources), reach_rooms={54, 60},
        fuse_death_armings=lambda: list(rows),
        capture_fold_armings=lambda: list(cap_rows))


def test_an_arming_hold_refuses_a_demand_that_cannot_be_paid():
    print("\n-- guards: the ANTI-WALL gate both new remedies were shipped without --")
    payable = G.fuse_arming_remedies(_stub({24: {60}}, [_fuse_row([24], [63])]))
    check("a demand the player can pay ships (KQ5's own case)",
          len(payable) == 1 and not payable[0]["refused"], detail="specs=%r" % (payable,))

    walled = G.fuse_arming_remedies(_stub({}, [_fuse_row([24], [63])]))
    check("a demand naming an item with NO reachable source is REFUSED, not shipped",
          len(walled) == 1 and walled[0]["refused"],
          detail="specs=%r -- item 24 has no source anywhere reachable, so holding the "
                 "encounter on it holds it forever. `fold_carryins` has had this gate since it "
                 "was written ('demanding it here would wall the crossing'); neither new "
                 "remedy had one." % (walled,))

    cwalled = G.capture_fold_remedies(_stub({}, cap_rows=[_cap_row()]))
    check("...and the capture hold refuses an unpayable demand the same way",
          len(cwalled) == 1 and cwalled[0]["refused"],
          detail="specs=%r" % (cwalled,))
    cpay = G.capture_fold_remedies(_stub({24: {54}}, cap_rows=[_cap_row()]))
    check("...while a payable one still ships", len(cpay) == 1 and not cpay[0]["refused"],
          detail="specs=%r" % (cpay,))


def test_a_capture_hold_refuses_context_it_cannot_render():
    print("\n-- guards.capture_fold_remedies: a dropped context atom is a dropped scope --")
    # The fold's context is what SCOPES the demand: rm86's row carries `prev == 85`, "the losing
    # arm arms exactly on the kidnap". The row rendered only the FLAG entries and dropped
    # everything else in silence, so a scoped demand shipped as an unscoped one.
    row = _cap_row(context_unrendered=[[12, 85]])
    got = G.capture_fold_remedies(_stub({24: {54}}, cap_rows=[row]))
    check("a context atom the condition cannot spell refuses the spec",
          len(got) == 1 and got[0]["refused"],
          detail="specs=%r -- an unrendered `prev == 85` widens the hold from one crossing to "
                 "every arming, which is the wall-shaped failure." % (got,))


def test_a_second_spawning_procedure_is_not_dropped():
    print("\n-- guards.fuse_arming_remedies: every spawning procedure is held --")
    two = G.fuse_arming_remedies(
        _stub({24: {60}}, [_fuse_row([24], [63], procs=("proc550_16", "proc550_20"))]))
    check("a machine spawned from TWO procedures gets a hold on each",
          sorted(sp["proc"] for sp in two) == ["proc550_16", "proc550_20"]
          and not any(sp["refused"] for sp in two),
          detail="specs=%r -- `procs[0]` silently under-guarded the rest, and the surface "
                 "reported applied=True sites=1 either way." % (two,))

    # ...and two DIFFERENT demands arriving at one site must not be silently conjoined into a
    # strictly stronger one: the row key is (machine, item) across rooms while the demand is
    # derived per room, so two alternative sets can both reach the same `(if`.
    clash = G.fuse_arming_remedies(_stub(
        {24: {60}, 37: {60}}, [_fuse_row([24], [63]), _fuse_row([37], [64])]))
    check("two DIFFERENT demands at one site refuse rather than conjoin into a wall",
          all(sp["refused"] for sp in clash) and len(clash) == 2,
          detail="specs=%r -- conjoining them makes a demand neither row derived, and a "
                 "stronger demand at an arming is a wall risk." % (clash,))


def test_an_empty_rendered_demand_refuses():
    print("\n-- guards.capture_fold_remedies: `(a for a in ...)` is always truthy --")
    # The generator in the emptiness test made the condition unconditional. It happened to be
    # accidentally correct; pinned here so the correction cannot change behaviour unnoticed.
    empty = G.capture_fold_remedies(_stub({}, cap_rows=[_cap_row(demand_alts=[])]))
    check("a row with no demand at all is refused", len(empty) == 1 and empty[0]["refused"],
          detail="specs=%r" % (empty,))
    unrend = G.capture_fold_remedies(_stub({}, cap_rows=[_cap_row(
        demand_alts=[{"owners": [], "items": [], "flags": [], "not_flags": [],
                      "iprops": [], "not_iprops": []}])]))
    check("...and so is a row whose alternatives all render to nothing",
          len(unrend) == 1 and unrend[0]["refused"], detail="specs=%r" % (unrend,))


# === THE 2026-08-20 REVIEW: what the first round of cures still got wrong ======================

def test_falsifies_reads_a_set_of_writes_not_a_state():
    print("\n-- missability._falsifies: a chain's WRITES are not a register STATE (R4) --")
    # `chain_writes` unions every write of every state of a machine AND of the machine that
    # armed it. Discharge can read that union safely, because the flag store is monotone: a
    # flag once set stays set. A REGISTER is not monotone -- KQ5's global332 is written 2, 3
    # and 4 by one chain -- so "the chain wrote (332, 3), therefore `332 == 2` is false" is not
    # a deduction. Measured on KQ5: `_falsifies` fires 26 times and EVERY firing rests on a
    # register the chain writes three different values to.
    #
    # The error direction is the dangerous one. A falsified entry is dropped, so the escape it
    # was is deleted: the demand rises (a wall) or the row vanishes (a shipped softlock).
    fal = getattr(M, "_falsifies", None)
    if fal is None:
        check("the falsification rule is a named, testable function", False)
        return
    check("a write that CONTRADICTS the only value of that register still falsifies",
          fal(GAnd([_cmp(901, "==", 5)]), frozenset({(901, 7)})),
          detail="the rule's own job: `sHalf` wrote 901 := 7, so a `901 == 5` arm cannot fire")
    check("...and a write that SATISFIES it does not",
          not fal(GAnd([_cmp(901, "==", 5)]), frozenset({(901, 5)})))
    check("a chain that writes the register SEVERAL values falsifies nothing",
          not fal(GAnd([_cmp(901, "==", 5)]), frozenset({(901, 5), (901, 7)})),
          detail="the chain writes 901 twice and one of the writes IS 5, so the entry can "
                 "still fire; dropping it deletes a real escape. `chain_writes` is an "
                 "unordered union over every state -- it says what the run TOUCHES, never "
                 "what the register HOLDS at the end.")
    check("...and the same is true whichever order the pair is read in",
          not fal(GAnd([_cmp(901, "==", 7)]), frozenset({(901, 5), (901, 7)})))
    check("a NEGATED conjunct is falsified only when EVERY write contradicts it",
          fal(GAnd([GNot(_cmp(901, "==", 5))]), frozenset({(901, 5)}))
          and not fal(GAnd([GNot(_cmp(901, "==", 5))]), frozenset({(901, 5), (901, 7)})),
          detail="`¬(901 == 5)` is impossible only if the register can hold nothing but 5")


def test_a_second_room_deriving_a_stronger_demand_is_not_dropped():
    print("\n-- missability.fuse_death_armings: the row key must carry its room (R5) --")
    # `emitted` lives outside the per-room loop and is keyed `(machine, item)`, while the
    # demand is derived PER ROOM off that room's escapes. Two rooms that arm the same encounter
    # with different escapes available derive different demands, and only the first is ever
    # emitted -- so the guard ships the weaker hold and the second room's softlock ships open.
    # The clash gate added to `fuse_arming_remedies` cannot see this: it only sees rows that
    # survived `emitted`.
    import inspect
    src = inspect.getsource(M.IrSccReach.fuse_death_armings)
    body = src[src.index("out, emitted"):]
    key = [ln for ln in body.splitlines() if "key = (" in ln]
    check("the dedupe key distinguishes two rooms' demands for one (machine, item)",
          bool(key) and ("room" in key[0] or "alt" in key[0] or "demand" in key[0]),
          detail="key line is %r -- keyed on (machine, item) alone, across every room, while "
                 "`demand_alts` is derived per room. The first room to emit wins and the "
                 "second room's stronger demand is silently dropped." % (key[0] if key else None))


def run():
    print("=== test_fuse_classification ===")
    test_the_countdown_is_the_register_the_handler_decrements()
    test_a_region_clock_does_not_promote_prevroom()
    test_a_bounded_topup_is_not_a_lighting()
    test_discharge_does_not_erase_a_negative_demand()
    test_the_continuation_drops_escapes_the_chain_disarms()
    test_entry_rooms_reads_polarity()
    test_an_arming_hold_refuses_a_demand_that_cannot_be_paid()
    test_a_capture_hold_refuses_context_it_cannot_render()
    test_a_second_spawning_procedure_is_not_dropped()
    test_an_empty_rendered_demand_refuses()
    test_falsifies_reads_a_set_of_writes_not_a_state()
    test_a_second_room_deriving_a_stronger_demand_is_not_dropped()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
