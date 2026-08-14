"""The four DELETION-SIDE soundness holes the contextless v1.0-lb2 review found
(docs/reviews/review-v1.0-lb2.md §4.1-§4.4), each as a synthetic unit test.

WHY THIS FILE EXISTS, given every one of these is latent on today's corpus. Each hole is a
filter that DELETES -- a coverage claim, a modelled read, a death finding, a requirement -- on
a proof that does not check what its comment says it checks. None of them can be caught by a
golden or a watched surface, because on our four games the missing conjunct happens to be
satisfied: the review's own word for it is "fails silent and green". A hole nothing can
observe is a hole nobody will notice being exercised by the next game, so the observation is
built here instead, out of the smallest input that distinguishes the rule as written from the
rule as described.

Synthetic by necessity and by preference: a fixture states the failure mode in ten lines,
where a game states it only if the game happens to have one. Each test carries BOTH directions
-- the case the rule must refuse AND the case it must still accept -- because three of the four
have an obvious "fix" that simply deletes the filter, and deleting the filter loses the
measured behaviour it was built for (the LB2 forwarding, the LB2 seventh store, the LB2
pre-emption that closed the skeletonKey false positive, the LB2 rm300 notebook).

  1. `guards.defer_to_entry`  -- forwarding's SOLE-PRODUCER proof ignores flip edges whose
     source is not the pocket, so the player can stand at the stage without ever crossing the
     hold, and the surface still reports the demand as covered.
  2. `vocab.lower_mask_accessors` -- reader bodies are husked to a literal even when a call
     site could not be resolved, which turns "unmodelled" into "modelled FALSE" at that site.
  3. `missability._survivable`'s pre-emption -- a same-slot competitor is taken as an escape
     without asking whether the player can ARM it.
  4. `missability.build_maps`' entry intersection -- an entry that can never fire still
     dissolves the requirement its siblings carry.
"""
import copy
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guards as G                                                       # noqa: E402
import ir as I                                                           # noqa: E402
import missability as M                                                  # noqa: E402
import vocab as V                                                        # noqa: E402
from guard_ast import GAnd, Pred                                         # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"\n      {detail}" if detail and not cond else ""))


def _own(i):
    return Pred("OWN", i, None, None)


def _reg(r, v):
    return Pred("CMP", r, "==", v)


# --- 1. the forwarding proof's sole producer ---------------------------------------------------
#
# The shape is LB2's, abstracted. The pocket (520) is the room whose exit commits the act flip
# 4 -> 5; the crossing 520 -> 530 is demanded only at act 5; the hold that the demand rides is
# the sibling exit 520 -> 540, which is where the flip is written. Forwarding is sound exactly
# when that write is the ONLY way to stand at act 5 -- otherwise a player who reaches act 5
# some other way walks the crossing having never met the demand.
_EDGES = {0: {300}, 300: {310}, 310: {510}, 510: {520}, 520: {530, 540},
          530: set(), 540: set()}
_PST = {123: {(0, 4), (300, 4), (310, 5), (510, 5), (520, 4), (520, 5), (530, 5), (540, 5)}}
_SPEC = {"from_room": 520, "to_room": 530, "items": set(), "groups": []}


def _defer_fixture(emeta, inroom):
    """A duck-typed IrSccReach carrying only what `defer_to_entry` reads."""
    f = types.SimpleNamespace()
    f.edges, f._emeta, f._inroom, f._pstates = _EDGES, emeta, inroom, _PST
    f.regs, f.sources = {123}, {}
    f.em = types.SimpleNamespace(cfg=types.SimpleNamespace(start_room=0), ir=None)
    f.g = types.SimpleNamespace(item_name=lambda i: "item%d" % i)
    return f


def test_forwarding_sole_producer():
    print("\n-- guards.defer_to_entry: the forwarded demand's sole-producer proof --")
    base = {(520, 530): [({123: {5}}, {}, None)],          # the crossing: demanded at act 5
            (520, 540): [({123: {4}}, {123: 5}, None)],    # the hold: the flip 4 -> 5
            (510, 520): [({}, {}, None)]}
    inroom = {123: {520: {5}}}                             # the pocket's own in-room write

    got = G.defer_to_entry(_defer_fixture(dict(base), inroom), dict(_SPEC))
    check("the flip's own exit hosts the forwarded demand (the LB2 shape, unchanged)",
          got is not None and (got.get("fwd") or {}).get("host") == (520, 540),
          detail="fwd=%r" % (got and got.get("fwd")))

    # ...and now a SECOND way to reach act 5, on an edge that leaves some other room. Nothing
    # about it is exotic -- it is the same kind of row as the host, one `sets` entry on a
    # movement edge -- and the proof never looks at it, because it only ever scanned edges out
    # of the pocket and in-ROOM writes elsewhere.
    other = dict(base)
    other[(300, 310)] = [({123: {4}}, {123: 5}, None)]
    got2 = G.defer_to_entry(_defer_fixture(other, inroom), dict(_SPEC))
    check("a flip edge with a NON-POCKET source refuses the forwarding",
          got2 is not None and got2.get("fwd") is None,
          detail="the crossing is demanded at act 5, the 300->310 edge writes act 5, so the "
                 "player can stand at the crossing without ever crossing the hold: "
                 "fwd=%r" % (got2 and got2.get("fwd")))


# --- 2. husking a reader whose call site did not resolve ---------------------------------------
def _n(v):
    return {"t": "Number", "value": v}


def _gv(i):
    return {"t": "Variable", "vtype": "Global", "index": i}


def _pv(i):
    return {"t": "Variable", "vtype": "Parameter", "index": i}


# The owner accumulates a byte-masked parameter; the reader bit-tests the word against its own
# parameter. Both are LB2's shapes, copied node for node out of `The Dagger of Amon Ra.ir.json`
# (script 22 `triggerAndClock::doit`, script 0 `proc0_10`) with the arithmetic reduced to the
# one idiom the store is derived from.
_OWNER_BODY = {"t": "List", "kids": [
    {"t": "AssignmentBinAnd", "kids": [_pv(1), _n(255)]},
    {"t": "AssignmentAdd", "kids": [_gv(124), _pv(1)]}]}
_READER_BODY = {"t": "List", "kids": [
    {"t": "AssignmentBinAnd", "kids": [_pv(1), _n(255)]},
    {"t": "Return", "kids": [{"t": "BinAnd", "kids": [_gv(124), _pv(1)]}]}]}


def _mask_ir(second_read_arg):
    """An IR with one owner, one reader proc, one literal write site and two read sites."""
    def wsite(arg):
        return {"t": "Send", "kids": [
            {"t": "KernelCall", "name": "ScriptID", "func": 2, "kids": [_n(22), _n(0)]},
            {"t": "SendMessage", "kids": [{"t": "Selector", "name": "doit", "value": 57},
                                          arg]}]}

    def rsite(arg):
        return {"t": "PublicCall", "name": "proc0_10", "script": 0, "export": 10,
                "kids": [arg]}

    return I.IR({"game": "synthetic", "selectors": [], "scripts": [
        {"number": 0, "locals": [], "objects": [], "exports": [None] * 11,
         "procedures": [{"name": "proc0_10", "ast": copy.deepcopy(_READER_BODY)}]},
        {"number": 22, "locals": [], "exports": ["triggerAndClock"], "procedures": [],
         "objects": [{"name": "triggerAndClock", "isClass": False, "species": 1, "super": 0,
                      "properties": [],
                      "methods": [{"name": "doit", "sel": 57,
                                   "ast": copy.deepcopy(_OWNER_BODY)}]}]},
        {"number": 250, "locals": [], "exports": ["rm250"], "procedures": [],
         "objects": [{"name": "rm250", "isClass": False, "species": 2, "super": 0,
                      "properties": [],
                      "methods": [{"name": "init", "sel": 10, "ast": {"t": "List", "kids": [
                          wsite(_n(8)), rsite(_n(16)), rsite(second_read_arg)]}}]}]}]})


def _reads_the_word(body):
    """Does this body still TEST the word -- i.e. was it left readable rather than husked?"""
    return any(isinstance(n, dict) and n.get("t") == "BinAnd"
               and any(I.is_global(k, 124) for k in (n.get("kids") or [])
                       if isinstance(k, dict))
               for n in I.walk(body))


def test_mask_accessor_refuses_unresolvable_reads():
    print("\n-- vocab.lower_mask_accessors: an unresolvable read is not a FALSE read --")
    ir1 = _mask_ir(_n(32))
    accs1 = V.derive_mask_accessors(ir1)
    w1, r1, sk1 = V.lower_mask_accessors(ir1, accs1)
    check("every call site literal -> the store lowers and the reader is husked (LB2's g124)",
          list(accs1) == [124] and (w1, r1) == (1, 2) and not sk1
          and not _reads_the_word(ir1.scripts[0].procs["proc0_10"]),
          detail="accs=%r w=%d r=%d skips=%r" % (list(accs1), w1, r1, sk1))

    # The same store, with ONE read call whose argument we cannot evaluate. That call is
    # "skipped" -- correctly, we do not know which bits it asks about -- but the reader's body
    # is husked all the same, so the call now returns a literal 0: a gate the game passes reads
    # in our model as a gate that is shut, and the edges and requirements behind it vanish.
    ir2 = _mask_ir(_gv(125))
    accs2 = V.derive_mask_accessors(ir2)
    w2, r2, sk2 = V.lower_mask_accessors(ir2, accs2)
    check("an unresolvable READ refuses the whole store (nothing lowered, nothing husked)",
          (w2, r2) == (0, 0) and _reads_the_word(ir2.scripts[0].procs["proc0_10"]),
          detail="lowered w=%d r=%d, skips=%r, reader husked=%r -- a skipped call site left "
                 "pointing at a husked body reads constant-FALSE"
                 % (w2, r2, sk2, not _reads_the_word(ir2.scripts[0].procs["proc0_10"])))

    # WHERE A REFUSED STORE LEAVES THE GLOBAL, which is the half of the refusal that makes it
    # the safe direction rather than merely a different one: unlowered, the word keeps its own
    # non-literal shapes, the sixth store refuses it in turn, and its tests read as UNMODELLED
    # -- opaque, permissive, exactly where they were before the seventh store existed. A
    # lowered store, by contrast, hands back the word's bits.
    check("a refused store leaves the word unmodelled, not modelled-false",
          V.derive_mask_globals(ir2) == {} and 124 in V.derive_mask_globals(ir1),
          detail="refused=%r lowered=%r" % (V.derive_mask_globals(ir2),
                                            V.derive_mask_globals(ir1)))


# --- 3. the pre-emption rule's unarmable competitor ---------------------------------------------
def _machine(inst, room, entries, states, recv, restores=()):
    return {"inst": inst, "room": room, "entries": list(entries), "init_entries": [],
            "entry_armers": [None] * len(entries), "entry_locals": [{}] * len(entries),
            "entry_recv": list(recv), "restores_control": set(restores),
            "states": states, "drops": ()}


def _trap_model(escape_item, sources):
    """A room whose trap machine hands control back and waits, plus one same-slot competitor.

    `sTrap` is `sUnlockTrunk` abstracted: using item 5 arms it, state 0 restores control and
    waits, and the wait ends in death. `sEscape` is `sInsertMeat`: the same script slot, armed
    by using item `escape_item`, and arming it disposes the trap."""
    trap = _machine("sTrap", 1, [(0, GAnd([_own(5)]))],
                    {0: [([], (), (), (), ("ADVANCE",))],
                     1: [([], (), (), (), ("DEATH", 0))]},
                    recv=[("G", 2)], restores=(0,))
    esc = _machine("sEscape", 1, [(0, GAnd([_own(escape_item)]))],
                   {0: [([], (), (), (), ("EXIT", 2))]}, recv=[("G", 2)])
    f = types.SimpleNamespace(em=types.SimpleNamespace(machines=[trap, esc],
                                                       dropped_entries=()),
                              reach_rooms={1}, sources=dict(sources), NOWHERE=set())
    return f


def test_preempt_requires_an_armable_competitor():
    print("\n-- missability.fatal_uses: a competitor you cannot arm is not an escape --")
    no_escape = types.SimpleNamespace(
        em=types.SimpleNamespace(machines=[_machine(
            "sTrap", 1, [(0, GAnd([_own(5)]))],
            {0: [([], (), (), (), ("ADVANCE",))], 1: [([], (), (), (), ("DEATH", 0))]},
            recv=[("G", 2)], restores=(0,))], dropped_entries=()),
        reach_rooms={1}, sources={}, NOWHERE=set())
    check("with no competitor at all, the fatal use is reported",
          [r["item"] for r in M.IrSccReach.fatal_uses(no_escape)] == [5])

    # The pre-emption this rule was built for: the escape costs an item, and the item is there
    # to be had. This is LB2's meat, and it is why using the skeleton key is not a fatal use.
    check("an escape whose price the player can pay still pre-empts the death",
          M.IrSccReach.fatal_uses(_trap_model(7, {7: {1}})) == [])

    # ...and the same competitor when its price cannot be paid. Nothing in the room changed;
    # what changed is that arming the escape is not something the player can do, so the wait
    # still ends in death and the use that armed it is still fatal.
    got = M.IrSccReach.fatal_uses(_trap_model(7, {}))
    check("an escape the player can never arm does NOT pre-empt the death",
          [r["item"] for r in got] == [5],
          detail="item 7 has no source anywhere, so `sEscape` can never take the slot; "
                 "rows=%r" % got)


# --- 4. an entry that cannot fire dissolving its siblings' requirement ---------------------------
def _entry_model(latch_raised):
    """One room, one machine, two ways in: one costs item 3, one is gated on a room-local latch.

    The latch is the fifth store's own shape (a lowered room local, homed to this room), and
    `latch_raised` decides whether any machine in the room ever writes it -- which is exactly
    the difference between a second way in and a way in that does not exist."""
    mach = {"inst": "sAskEnterBar", "room": 1,
            "entries": [(0, GAnd([_own(3)])), (0, GAnd([_reg(900, 1)]))],
            "init_entries": [], "entry_armers": [None, None], "entry_locals": [{}, {}],
            "entry_recv": [("G", 2), ("G", 2)], "restores_control": set(),
            "states": {0: [([], (), (), (), ("EXIT", 2))]}, "drops": ()}
    raiser = {"inst": "sRaiseLatch", "room": 1, "entries": [(0, [])], "init_entries": [],
              "entry_armers": [None], "entry_locals": [{}], "entry_recv": [("G", 2)],
              "restores_control": set(),
              "states": {0: [([], ((900, 1),), (), (), ("EXIT", 2))]}, "drops": ()}
    ir = types.SimpleNamespace(_room_local_index={900: (1, 5)}, scripts={})
    em = types.SimpleNamespace(
        machines=[mach] + ([raiser] if latch_raised else []), global_machines=[],
        machine_delivered=set(), machine_gets=set(), handler_gets=(), handler_drops=(),
        handler_writes=(), dropped_entries=(), global_homed=(), ir=ir,
        reg_vals={900: {0, 1}},
        ts=types.SimpleNamespace(edges=(), cs_edges=(), acqs=(), items=(), bulk_moves=(),
                                 item_prop_writes=(), dispatchers=set(), maze_reach={},
                                 placed={}),
        cfg=types.SimpleNamespace(start_room=0, goal_rooms=frozenset({2}),
                                  debug_globals=frozenset()))
    return M.build_maps(em)[4]                       # required: item -> rooms


def test_entry_intersection_ignores_unfirable_entries():
    print("\n-- missability.build_maps: an unfirable entry vouches for nothing --")
    # The rule as designed, and the case that forced it (LB2's rm300 bar door, where a synonym
    # verb armed the same machine without the notebook): a second, REAL way in means the item
    # is not faced here.
    check("a genuine second way in dissolves the requirement (LB2's rm300 notebook)",
          not _entry_model(latch_raised=True).get(3),
          detail="required[3]=%r" % (_entry_model(latch_raised=True).get(3),))

    # ...and the same shape where the second way in cannot happen: nothing in the room ever
    # raises the latch it is gated on, so the only way to arm this machine is still to hold
    # item 3. `_reg_entry_demands._via_latch` already refuses to be vouched for by an entry
    # like this ("an unfirable entry vouches for nothing"); the requirement side does not.
    got = _entry_model(latch_raised=False)
    check("an entry gated on a latch nothing raises does NOT dissolve the requirement",
          got.get(3) == {1},
          detail="no machine and no handler in room 1 writes the latch, so the own(3) entry is "
                 "the only way in: required[3]=%r" % (got.get(3),))


# --- 5. a departure claimed from one arm of a branch ---------------------------------------------
#
# `extract._object_departures` says "this script parks that object off-pic, so its `init:`
# yields no interactive presence" -- the rule that sealed LB2's street, and the only rule in the
# codebase that DELETES a click window. Its docstring promises to be strict in the KEEPING
# direction; the walk that implements it reads every send in a case body, including the ones
# inside an `if`, so a departure that happens on one arm reads as a departure that always
# happens. Fabricating a seal is worse than missing one: it deletes a way through that the
# player really has.
def _departure_script(conditional):
    """LB2's `sTaxiLeave` (rm330), verbatim in shape, with the drive optionally under a branch."""
    def send(recv, sel, *params):
        return {"t": "Send", "kids": [recv, {"t": "SendMessage", "kids": [
            {"t": "Selector", "name": sel, "value": 0}] + list(params)}]}

    def moveto(x, y):
        return send({"t": "Object", "name": "taxi"}, "setMotion",
                    {"t": "Class", "name": "MoveTo", "number": 32},
                    {"t": "Number", "value": x}, {"t": "Number", "value": y}, {"t": "Self"})

    hands = lambda sel: send({"t": "Variable", "vtype": "Global", "index": 1}, sel)  # noqa: E731
    drive = (moveto(369, 125) if not conditional else
             # ON-pic if the branch is taken, off-pic otherwise: the object leaves on ONE arm.
             {"t": "If", "kids": [{"t": "Variable", "vtype": "Global", "index": 9},
                                  {"t": "List", "kids": [moveto(100, 100)]},
                                  {"t": "List", "kids": [moveto(369, 125)]}]})
    body = {"t": "List", "kids": [{"t": "Switch", "kids": [
        {"t": "Assignment", "kids": [{"t": "Property", "name": "state", "index": 20},
                                     {"t": "Variable", "vtype": "Parameter", "index": 1}]},
        {"t": "Case", "kids": [{"t": "Number", "value": 0},
                               {"t": "List", "kids": [hands("handsOff"), drive]}]},
        {"t": "Case", "kids": [{"t": "Number", "value": 1},
                               {"t": "List", "kids": [hands("handsOn")]}]}]}]}
    return I.Script({"number": 330, "locals": [], "exports": [], "procedures": [],
                     "objects": [{"name": "sTaxiLeave", "isClass": False, "species": 1,
                                  "super": 0, "properties": [],
                                  "methods": [{"name": "changeState", "sel": 1, "ast": body}]}]})


def test_departure_is_not_claimed_from_one_arm():
    print("\n-- extract._object_departures: a departure on ONE arm is not a departure --")
    import extract as X                                                  # noqa: E402
    check("the unconditional drive departs the taxi (LB2's rm330, the rule's own case)",
          X._object_departures(_departure_script(False)) == {"taxi": {"sTaxiLeave"}},
          detail="%r" % (X._object_departures(_departure_script(False)),))

    got = X._object_departures(_departure_script(True))
    check("a drive that only leaves the pic on ONE ARM departs nothing",
          got == {},
          detail="the taxi parks off-pic in the else branch and stays on-pic in the other, so "
                 "the player's click window survives on one route -- and a seal claimed here "
                 "deletes it: %r" % (got,))


def run():
    print("=== test_deletion_soundness ===")
    test_forwarding_sole_producer()
    test_mask_accessor_refuses_unresolvable_reads()
    test_preempt_requires_an_armable_competitor()
    test_entry_intersection_ignores_unfirable_entries()
    test_departure_is_not_claimed_from_one_arm()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
