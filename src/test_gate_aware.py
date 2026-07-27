"""Unit tests for the GATE-AWARE movement model in missability.py, in ISOLATION:
  - entry_alts   (machine entry guards -> DNF alternatives per state)
  - blocked      (an edge is impassable only if EVERY alternative needs a banned item)
  - gating_registers / required_values (DISCOVERING which registers gate movement)
  - disjunctive_groups (sets that alternatively open one gate)

These replaced two rules the user flagged as overfit: the `_sealed` one-way-edge heuristic and
the cutscene splice. The point of pinning them here is that the OLD rules were fitted to LSL2
outcomes, whereas these are derived -- so they need input/output tests that do not mention LSL2.
Ground-truth scoring stays end-to-end (`python -m missability`).
"""
import sys

import missability as M
from guard_ast import GAnd, GOr, GNot, Pred

PASS, FAIL = [], []
def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def _own(i):
    return Pred("OWN", i, None, None)


def _machine(states, entries=(), init_entries=()):
    """A minimal machine info dict: states maps K -> [(guard, writes, gets, counters, trans)]."""
    return {"room": 1, "states": states, "entries": list(entries),
            "init_entries": list(init_entries)}


def test_blocked():
    print("\n-- blocked() --")
    A, B = frozenset({30}), frozenset({31})
    check("no alternatives -> never blocked (ungated)", not M.blocked((), frozenset({30})))
    check("free alternative -> never blocked",
          not M.blocked((frozenset(),), frozenset({30, 31})))
    check("single alternative, its item banned -> blocked",
          M.blocked((A,), frozenset({30})))
    check("single alternative, other item banned -> open",
          not M.blocked((A,), frozenset({31})))
    check("DISJUNCTION: banning one of two alternatives leaves the gate open",
          not M.blocked((A, B), frozenset({31})))
    check("DISJUNCTION: banning both alternatives blocks the gate",
          M.blocked((A, B), frozenset({30, 31})))
    check("CONJUNCTION: one alternative needing both, either ban blocks",
          M.blocked((frozenset({30, 31}),), frozenset({31})))


def test_entry_alts():
    print("\n-- entry_alts() --")
    # s8 armed by two rival handlers (own 30 / own 31); chain 8 -> 9 -> EXIT at 10.
    states = {8: [([], [], [], [], ("ADVANCE",))],
              9: [([], [], [], [], ("ADVANCE",))],
              10: [([], [], [], [], ("EXIT", 99))]}
    m = _machine(states, entries=[(8, [_own(30)]), (8, [_own(31)])])
    alts = M.entry_alts(m)
    check("rival entries become two alternatives at the armed state",
          set(alts[8]) == {frozenset({30}), frozenset({31})})
    check("alternatives PROPAGATE along the chain to the EXIT state",
          set(alts[10]) == {frozenset({30}), frozenset({31})})
    check("propagated disjunction does not collapse to 'needs both'",
          frozenset({30, 31}) not in set(alts[10]))
    check("propagated disjunction does not collapse to 'free'",
          frozenset() not in set(alts[10]))

    # an UNGUARDED entry that also reaches the exit makes the gate free
    m2 = _machine(states, entries=[(8, [_own(30)]), (9, [])])
    check("a free entry reaching the exit makes it ungated",
          frozenset() in set(M.entry_alts(m2)[10]))
    check("...and blocked() agrees it is open",
          not M.blocked(M.entry_alts(m2)[10], frozenset({30})))

    # a state no entry reaches -> no alternatives -> treated as ungated, never over-blocked
    m3 = _machine({**states, 20: [([], [], [], [], ("EXIT", 98))]},
                  entries=[(8, [_own(30)])])
    check("unreachable-from-any-entry state stays ungated (never over-block)",
          M.entry_alts(m3)[20] == () and not M.blocked(M.entry_alts(m3)[20], frozenset({30})))


class _Stub:
    """Minimal OpEmitter stand-in for gating_registers()."""
    class _TS:
        def __init__(self, edges, cs_edges):
            self.edges, self.cs_edges = edges, cs_edges
    class _E:
        def __init__(self, src, dst, guard):
            self.src, self.dst, self.guard = src, dst, guard

    def __init__(self, edges=(), machines=(), handler_writes=()):
        self.ts = self._TS(list(edges), [])
        self.machines = list(machines)
        self.handler_writes = list(handler_writes)
        self.machine_delivered = set()


def test_required_values():
    print("\n-- required_values() --")
    eq7 = Pred("CMP", 101, "==", 7)
    check("positive == extracts the required value", M.required_values(eq7, 101) == {7})
    check("no constraint -> None", M.required_values([], 101) is None)
    check("AND keeps the constraint", M.required_values(GAnd([eq7, _own(3)]), 101) == {7})
    check("negated == is not a requirement", M.required_values(GNot(eq7), 101) is None)
    check("a different register is ignored", M.required_values(eq7, 102) is None)
    check("own() alone constrains no register", M.required_values(_own(3), 101) is None)
    check("two values for one register are both allowed",
          M.required_values(GOr([eq7, Pred("CMP", 101, "==", 9)]), 101) == {7, 9})

    # "this flag is SET" -- `(!= flag 0)`, positive -- carries only for a global WE minted from a
    # flag store (domain exactly {0,1}) and only along the must-hold spine. It used to be known to
    # required_values and NOT to edge_meta, so the same gate constrained a machine entry and not a
    # room edge; both now go through guard_reqs. KQ6's realm entry needs flags 14 and 4 SET.
    import vocab
    setf = Pred("CMP", 900, "!=", 0)
    saved = vocab.BOOL_GLOBALS
    try:
        vocab.BOOL_GLOBALS = frozenset({900})
        check("a flag-SET gate on a minted bool global requires 1",
              M.required_values(setf, 900) == {1})
        check("...and edge_meta's scan agrees, over all registers at once",
              M.guard_reqs(GAnd([setf, eq7]), {900, 101}) == {900: {1}, 101: {7}})
        check("...but not under an OR, where the flag need not hold",
              M.required_values(GOr([setf, _own(3)]), 900) is None)
        vocab.BOOL_GLOBALS = frozenset()
        check("a real global's `!= 0` stays unconstraining (domain unknown)",
              M.required_values(setf, 900) is None)
    finally:
        vocab.BOOL_GLOBALS = saved

    # The same rule with a domain supplied instead of minted: `!= v` is exact when the register's
    # complete value set is known, which is true of the previous-room register by construction.
    # KQ6 leaves the realm of the dead through one door, guarded `(!= prev 670)`.
    dom = {12: {0, 155, 340, 670, 690}}
    ne670 = Pred("CMP", 12, "!=", 670)
    check("`!= v` over a complete domain means every OTHER value",
          M.guard_reqs(ne670, {12}, dom) == {12: {0, 155, 340, 690}})
    check("...and `(not (== v))` is the same assertion, the other spelling",
          M.guard_reqs(GNot(Pred("CMP", 12, "==", 670)), {12}, dom) == {12: {0, 155, 340, 690}})
    check("...with no domain it still constrains nothing",
          M.guard_reqs(ne670, {12}) == {})
    check("...and inside an OR it constrains nothing either",
          M.guard_reqs(GOr([ne670, _own(3)]), {12}, dom) == {})

    # structural_reqs: the composing reader. An OR of two armings must not read as a conjunction
    # of both -- KQ4's whale is `(or (prev == 44) (g109 == 1 and ...))` and reading it flat
    # demanded you may only be swallowed if you have just been spat out.
    armA = GAnd([GNot(Pred("CMP", 12, "==", 43)), Pred("CMP", 12, "==", 44)])
    armB = GAnd([Pred("CMP", 109, "==", 1), Pred("CMP", 183, "==", 0)])
    check("flat reading of an OR-of-armings demands both (why edge_meta cannot compose it)",
          M.guard_reqs(GOr([armA, armB]), {12, 109, 183}) == {12: {44}, 109: {1}, 183: {0}})
    check("structural reading demands neither",
          M.structural_reqs(GOr([armA, armB]), {12, 109, 183}) == {})
    check("...but keeps what a single arming requires",
          M.structural_reqs(armA, {12, 109, 183}) == {12: {44}})
    check("...and unions the values when both branches constrain one register",
          M.structural_reqs(GOr([Pred("CMP", 5, "==", 1), Pred("CMP", 5, "==", 2)]), {5})
          == {5: {1, 2}})


def test_gating_registers():
    """Discovery: a register earns promotion iff it is BOTH compared in a movement guard AND
    written. Neither half alone can create an impossible composition."""
    print("\n-- gating_registers() --")
    E = _Stub._E
    cmp5 = Pred("CMP", 5, "==", 1)      # compared AND written -> promote
    cmp6 = Pred("CMP", 6, "==", 1)      # compared, never written -> cannot gate a composition
    m = {"room": 1, "states": {0: [([], [(5, 1)], [], [], ("PARK",))]},
         "entries": [], "init_entries": []}
    em = _Stub(edges=[E(1, 2, GAnd([cmp5, cmp6]))], machines=[m])
    regs = M.gating_registers(em)
    check("compared AND written -> discovered", 5 in regs)
    check("compared but never written -> skipped", 6 not in regs)

    # written but never compared cannot block anything either
    m2 = {"room": 1, "states": {0: [([], [(7, 3)], [], [], ("PARK",))]},
          "entries": [], "init_entries": []}
    em2 = _Stub(edges=[E(1, 2, cmp5)], machines=[m, m2])
    check("written but never compared -> skipped", 7 not in M.gating_registers(em2))

    # a register compared only in a machine ENTRY guard still gates movement
    m3 = {"room": 1, "states": {0: [([], [(9, 1)], [], [], ("EXIT", 2))]},
          "entries": [(0, Pred("CMP", 9, "==", 1))], "init_entries": []}
    check("compared in a machine ENTRY guard counts", 9 in M.gating_registers(_Stub(machines=[m3])))
    check("discovery is deterministic/sorted", M.gating_registers(em) == sorted(M.gating_registers(em)))


def test_goal_reachability_traps():
    """The TRAP rule, re-derived: a use you cannot still WIN from is not evidence of a
    requirement. Death is only the commonest way to fail that -- these pin the general rule."""
    print("\n-- goal-reachability trap rule --")
    GOAL = {50}                      # rooms from which the goal is still reachable

    # rm138-shaped: one own()-guarded path dies, a sibling exits somewhere winnable.
    m = _machine({0: [([_own(13)], [], [], [], ("DEATH",)),
                      ([_own(12)], [], [], [], ("EXIT", 50))]})
    gr = M.goal_reaching(m, GOAL)
    check("a DEATH path is hopeless",
          not M.hopeful(m, 0, ("DEATH",), gr, GOAL))
    check("an EXIT to a goal-reaching room is hopeful",
          M.hopeful(m, 0, ("EXIT", 50), gr, GOAL))

    # THE GENERALIZATION: no death at all -- the use just strands you where the goal is gone.
    check("an EXIT to a room with NO route to the goal is hopeless (no death involved)",
          not M.hopeful(m, 0, ("EXIT", 99), gr, GOAL))

    # PARK hands control back to the player, so it inherits THIS room's prospects
    m_ok = _machine({0: [([], [], [], [], ("PARK",))]})
    m_ok["room"] = 50
    check("PARK in a goal-reaching room is hopeful",
          M.hopeful(m_ok, 0, ("PARK",), M.goal_reaching(m_ok, GOAL), GOAL))
    m_bad = _machine({0: [([], [], [], [], ("PARK",))]})
    m_bad["room"] = 99
    check("PARK in a room with no route to the goal is hopeless",
          not M.hopeful(m_bad, 0, ("PARK",), M.goal_reaching(m_bad, GOAL), GOAL))

    # propagation: a chain ending in death is hopeless all the way back
    chain = _machine({0: [([], [], [], [], ("ADVANCE",))],
                      1: [([], [], [], [], ("ADVANCE",))],
                      2: [([], [], [], [], ("DEATH",))]})
    grc = M.goal_reaching(chain, GOAL)
    check("hopelessness propagates backward along a chain",
          grc[0] is False and grc[1] is False and grc[2] is False)
    # ...but one winnable branch anywhere makes the state hopeful
    fork = _machine({0: [([], [], [], [], ("ADVANCE",))],
                     1: [([], [], [], [], ("DEATH",)),
                         ([], [], [], [], ("EXIT", 50))]})
    check("a single winnable branch makes the state hopeful",
          M.goal_reaching(fork, GOAL)[0] is True)

    # goal_reaching_rooms: backward walk over the room graph
    edges = {1: {2}, 2: {50}, 7: {8}, 8: {7}}
    ok = M.goal_reaching_rooms(edges, {50})
    check("rooms feeding the goal are goal-reaching", {1, 2, 50} <= ok)
    check("a disconnected pocket is not", not ({7, 8} & ok))


def run():
    print("=== test_gate_aware ===")
    test_blocked()
    test_entry_alts()
    test_required_values()
    test_gating_registers()
    test_goal_reachability_traps()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
