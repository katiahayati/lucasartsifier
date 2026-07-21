"""Unit tests for the GATE-AWARE movement model in missability.py, in ISOLATION:
  - entry_alts   (machine entry guards -> DNF alternatives per state)
  - blocked      (an edge is impassable only if EVERY alternative needs a banned item)
  - _status_required / edge composition (register-gated movement)
  - disjunctive_groups (sets that alternatively open one gate)

These replaced two rules the user flagged as overfit: the `_sealed` one-way-edge heuristic and
the cutscene splice. The point of pinning them here is that the OLD rules were fitted to LSL2
outcomes, whereas these are derived -- so they need input/output tests that do not mention LSL2.
Ground-truth scoring stays end-to-end (`python -m missability`); see docs/ROADMAP.md.
"""
import sys

import missability as M
from model import GAnd, GOr, GNot, Pred

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


def test_status_required():
    print("\n-- _status_required() --")
    R = M._STATUS_REG
    eq7 = Pred("CMP", R, "==", 7)
    check("positive == extracts the required value", M._status_required(eq7) == {7})
    check("no constraint -> None", M._status_required([]) is None)
    check("AND keeps the constraint", M._status_required(GAnd([eq7, _own(3)])) == {7})
    check("negated == is not a requirement", M._status_required(GNot(eq7)) is None)
    check("a different register is ignored",
          M._status_required(Pred("CMP", R + 1, "==", 7)) is None)
    check("own() alone constrains no status", M._status_required(_own(3)) is None)


def run():
    print("=== test_gate_aware ===")
    test_blocked()
    test_entry_alts()
    test_status_required()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
