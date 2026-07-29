"""Unit tests for START/GOAL discovery (anchors.py), on synthetic graphs.

These were the last hand-declared game-specific values in the pipeline, so the rules that replace
them need to be pinned independently of LSL2 -- an LSL2-only check would just be re-measuring the
game we tuned against. End-to-end confirmation (derived anchors reproduce the hand-tuned sweep
exactly) lives in `python -m missability`.
"""
import sys

import anchors as A

PASS, FAIL = [], []
def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


class _Em:
    """Minimal emitter stand-in: a room graph and death rooms."""
    def __init__(self, edges, deaths=(), rooms=None):
        self._edges = {a: set(b) for a, b in edges.items()}
        self._deaths = set(deaths)
        self.rooms = list(rooms if rooms is not None else
                          set(self._edges) | {b for bs in self._edges.values() for b in bs})
        self.ts = type("ts", (), {"edges": [], "cs_edges": []})()
        self.machines = []
        self.handler_writes = []

    def is_death(self, gi, v):
        return False


def _edges(em):
    return em._edges


def test_engine_entry():
    print("\n-- engine_entry(): graph roots --")
    em = _Em({1: {2}, 2: {3}, 9: {2}})
    check("rooms with no in-edges are the entries", A.engine_entry(em, _edges(em)) == {1, 9})
    em2 = _Em({1: {2}, 2: {1}})
    check("a fully cyclic graph has no root", A.engine_entry(em2, _edges(em2)) == set())


def test_discover_start():
    print("\n-- discover_start(): the free-roam world the engine entries funnel into --")
    # Two pass-through roots (copy-protection screen, intro) both lead into room 3. Room 3 and its
    # downstream are reached by BOTH entries; each root only by itself -- so the roots drop out and
    # the convergent free-roam room wins. (LSL2: rm10 copy-protection + rm99 intro both -> the LA
    # cluster; without this the wider-reaching copy-protection root would win and drag the intro in.)
    em = _Em({1: {3}, 2: {3}, 3: {4}, 4: {5}})
    check("drops the pass-through roots for the room every entry funnels into",
          A.discover_start(em, _edges(em)) == 3)

    # When the real start simply IS a single root -- no second entry converging elsewhere -- keep
    # it; this degrades to widest-reach (KQ4's rm99).
    em2 = _Em({1: {2}, 2: {3}})
    check("a lone entry that is itself the start is kept",
          A.discover_start(em2, _edges(em2)) == 1)

    # Among the convergent rooms, the tie is broken by WIDEST forward reach, not a dead-end pocket.
    em3 = _Em({1: {3}, 2: {3}, 3: {4, 9}, 4: {5}, 9: {}})
    check("ties broken by widest forward reach",
          A.discover_start(em3, _edges(em3)) == 3)


def test_discover_goal():
    print("\n-- discover_goal(): terminal, reachable, never fatal --")
    class EmD(_Em):
        def is_death(self, gi, v):
            return True
    # 1 -> 2 -> {3 terminal-good, 4 terminal-DEATH}; 5 terminal but unreachable
    em = _Em({1: {2}, 2: {3, 4}}, rooms=[1, 2, 3, 4, 5])
    em._deaths = {4}
    # death_rooms() reads machines/handler_writes; inject directly for the test
    A_death = A.death_rooms
    try:
        A.death_rooms = lambda e: e._deaths
        g = A.discover_goal(em, _edges(em), start=1)
        check("the surviving terminal room is the goal", g == frozenset({3}))
        check("a terminal DEATH room is excluded", 4 not in g)
        check("an unreachable terminal room is excluded", 5 not in g)

        # nothing terminal -> no goal, rather than a wrong guess
        em2 = _Em({1: {2}, 2: {1}}, rooms=[1, 2])
        em2._deaths = set()
        check("a graph with no terminal room yields no goal",
              A.discover_goal(em2, _edges(em2), start=1) == frozenset())

        # script 0 is Main, not a location
        em3 = _Em({1: {0}}, rooms=[0, 1])
        em3._deaths = set()
        check("script 0 is never a goal", A.discover_goal(em3, _edges(em3), start=1) == frozenset())
    finally:
        A.death_rooms = A_death


def _machine(room, inst, entry, own=False):
    """A machine stand-in: one entry condition, optionally testing what the player carries."""
    from guard_ast import Pred
    return {"room": room, "inst": inst, "script": 0,
            "entries": [(0, entry)], "init_entries": [],
            "states": {0: [([Pred("OWN", var=7)] if own else [], [], [], None, None)]}}


def test_resolve_pass_through():
    """A terminal that only REPORTS the outcome yields to the branch that DECIDES it.

    Synthetic, because pinning this against KQ6 alone would be re-measuring the game the rule was
    designed on. Each check corresponds to one clause of the rule, so a clause cannot be dropped or
    widened without a failure here. The real-game anchors are pinned by the LSL2 golden (which
    carries `goal_rooms`) and by the KQ4/KQ6 oracles."""
    print("\n-- _resolve_pass_through(): a credits screen is not an outcome --")
    from guard_ast import GAnd, GNot, Pred
    import extract as X
    prev = Pred("CMP", var=12, op="==", value="180")     # CMP values arrive as strings
    other = GAnd([GNot(prev), Pred("CMP", var=338, op="!=", value="0")])
    real = X.prev_room_global
    try:
        X.prev_room_global = lambda ir: 12
        # 1 -> 740 -> 94(terminal).  rm740 runs two rival endings; only one tests achievement.
        em = _Em({1: {740}, 740: {94}}, rooms=[1, 94, 180, 740])
        em.ir = object()
        em.machines = [_machine(740, "win", prev, own=True), _machine(740, "lose", other)]
        check("the winning ending's prevRoom entry becomes the goal",
              A._resolve_pass_through(em, _edges(em), frozenset({94})) == frozenset({180}))

        # KQ4's shape: the predecessor holds ONE machine, so there is no branch to read.
        em1 = _Em({1: {693}, 693: {694}}, rooms=[1, 180, 693, 694])
        em1.ir = object()
        em1.machines = [_machine(693, "egoActions", prev, own=True)]
        check("one machine is not a branch, so the terminal stands",
              A._resolve_pass_through(em1, _edges(em1), frozenset({694})) == frozenset({694}))

        # The signal has to SEPARATE the rivals: if they all test achievement it says nothing.
        em2 = _Em({1: {740}, 740: {94}}, rooms=[1, 94, 180, 740])
        em2.ir = object()
        em2.machines = [_machine(740, "a", prev, own=True), _machine(740, "b", other, own=True)]
        check("rivals that ALL test achievement leave the terminal alone",
              A._resolve_pass_through(em2, _edges(em2), frozenset({94})) == frozenset({94}))

        # A winner gated on a FLAG has no room-set equivalent -- that is TODO 6.1, not a goal.
        flag = Pred("FLAG", var=15)
        em3 = _Em({1: {740}, 740: {94}}, rooms=[1, 94, 180, 740])
        em3.ir = object()
        em3.machines = [_machine(740, "win", flag, own=True),
                        _machine(740, "lose", GNot(flag))]
        check("a winner not gated on prevRoom is left as-is rather than guessed",
              A._resolve_pass_through(em3, _edges(em3), frozenset({94})) == frozenset({94}))

        # Two ways in means the terminal is itself a choice, and carries its own information.
        em4 = _Em({1: {740, 94}, 740: {94}}, rooms=[1, 94, 180, 740])
        em4.ir = object()
        em4.machines = [_machine(740, "win", prev, own=True), _machine(740, "lose", other)]
        check("a terminal with more than one predecessor is untouched",
              A._resolve_pass_through(em4, _edges(em4), frozenset({94})) == frozenset({94}))

        check("contradiction is detected through a negated conjunct",
              A._mutually_exclusive(prev, other) and not A._mutually_exclusive(prev, prev))
    finally:
        X.prev_room_global = real


def run():
    print("=== test_anchors ===")
    test_engine_entry()
    test_discover_start()
    test_discover_goal()
    test_resolve_pass_through()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
