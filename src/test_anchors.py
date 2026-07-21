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
    """Minimal emitter stand-in: a room graph, a cutscene set, and death rooms."""
    def __init__(self, edges, cutscenes=(), deaths=(), rooms=None):
        self._edges = {a: set(b) for a, b in edges.items()}
        self._cut = set(cutscenes)
        self._deaths = set(deaths)
        self.rooms = list(rooms if rooms is not None else
                          set(self._edges) | {b for bs in self._edges.values() for b in bs})
        self.ts = type("ts", (), {"edges": [], "cs_edges": []})()
        self.machines = []
        self.handler_writes = []

    def _cutscene_room_set(self):
        return self._cut

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
    print("\n-- discover_start(): first room the player can ACT in --")
    # 1 (cutscene) -> 2 (cutscene) -> 3 (playable)
    em = _Em({1: {2}, 2: {3}, 3: {4}, 4: {5}}, cutscenes={1, 2})
    check("walks THROUGH the intro cutscenes to the first playable room",
          A.discover_start(em, _edges(em)) == 3)

    # two candidates: 3 sees the whole map, 9 is a dead-end pocket
    em2 = _Em({1: {2}, 2: {3, 9}, 3: {4}, 4: {5}, 9: {10}}, cutscenes={1, 2})
    check("prefers the candidate with the WIDEST forward reach (not a pocket)",
          A.discover_start(em2, _edges(em2)) == 3)

    # an interactive entry is itself a candidate
    em3 = _Em({1: {2}, 2: {3}}, cutscenes=set())
    check("an entry that is already playable is eligible",
          A.discover_start(em3, _edges(em3)) == 1)


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


def run():
    print("=== test_anchors ===")
    test_engine_entry()
    test_discover_start()
    test_discover_goal()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
