"""Tests for toll_strandings() -- the consumed-gate one-visit-pocket softlock (class 4).

A synthetic unit test pins the LOGIC (pocket = graph-dominated by the toll, loot sourced only
inside, one-way filter, leavability) with no game load. End-to-end assertions pin the ground
truth: KQ5's temple strands the Brass_Bottle + Gold_Coin behind the Staff, while LSL2 and KQ4 --
whose every toll candidate is re-obtainable -- must stay empty (the regression guard)."""
import os, sys, types, dataclasses
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import missability as M
from scc_core import reachable

PASS, FAIL = [], []
def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def _fake(edges, emeta, drops, placed, sources, required, reob, start=0):
    """A duck-typed IrSccReach carrying only what toll_strandings() reads."""
    f = types.SimpleNamespace()
    f.edges = edges
    f._emeta = emeta
    f.drops = drops
    f.sources = sources
    f.required = required
    f.reach_rooms = reachable(edges, {start})
    f._reob = reob
    f.reobtainable_rooms = lambda X, _f=f: _f._reob.get(X, set())
    f._pocket_leavable = lambda pocket, Y, _f=f: M.IrSccReach._pocket_leavable(_f, pocket, Y)
    f.em = types.SimpleNamespace(cfg=types.SimpleNamespace(start_room=start),
                                 ts=types.SimpleNamespace(placed=placed))
    f.g = types.SimpleNamespace(item_name=lambda i: f"item{i}")
    return f


def _run(f):
    return M.IrSccReach.toll_strandings(f)


# The temple abstracted: 0->1 hub, 1->2 is the toll (own(7) staff, spent at 1), 2->1 walks back,
# loot item 6 sits only in room 2 and is needed at room 3 (reachable free from the hub).
BASE = dict(
    edges={0: {1}, 1: {2, 3}, 2: {1}, 3: set()},
    emeta={(0, 1): [({}, {}, (frozenset(),))],
           (1, 2): [({}, {}, (frozenset({7}),))],       # toll: own(7)
           (2, 1): [({}, {}, (frozenset(),))],          # free walk out
           (1, 3): [({}, {}, (frozenset(),))]},
    drops={7: {1}},                                     # staff spent at room 1
    placed={},
    sources={7: {5}, 6: {2}},                           # loot 6 only in the pocket
    required={6: {3}, 7: {1}},                          # loot needed outside the pocket
    reob={7: set()},                                    # staff NOT re-gettable -> one-way toll
)


def test_toll_logic():
    print("\n-- toll_strandings() logic --")
    rows = _run(_fake(**BASE))
    got = {(r["item"], tuple(r["toll_edge"]), tuple(r["pocket"])) for r in rows}
    check("loot only inside a one-way toll pocket is stranded",
          got == {(6, (1, 2), (2,))})

    b = dict(BASE); b["reob"] = {7: {1}}                # staff re-gettable from room 1
    check("re-obtainable toll item -> benign, no stranding", _run(_fake(**b)) == [])

    b = dict(BASE); b["sources"] = {7: {5}, 6: {2, 9}}  # loot also gettable outside the pocket
    check("loot sourced outside the pocket too -> not stranded", _run(_fake(**b)) == [])

    b = dict(BASE); b["drops"] = {}                     # gate item not spent at the source
    check("gate item not spent crossing -> not a toll", _run(_fake(**b)) == [])

    b = dict(BASE); b["required"] = {6: {2}, 7: {1}}    # loot needed ONLY inside the pocket
    check("loot needed only inside the pocket -> taking it there suffices", _run(_fake(**b)) == [])

    # every exit of the pocket demands the loot -> you cannot leave without it -> not missable
    b = dict(BASE)
    b["edges"] = {0: {1}, 1: {2, 3}, 2: {3}, 3: set()}  # pocket 2 exits only via 2->3
    b["emeta"] = dict(BASE["emeta"]); b["emeta"][(2, 3)] = [({}, {}, (frozenset({6}),))]
    del b["emeta"][(2, 1)]
    check("pocket exit forces the loot item -> not missable", _run(_fake(**b)) == [])

    # b reachable by a second path -> the toll doesn't dominate it -> no pocket
    b = dict(BASE)
    b["edges"] = {0: {1, 2}, 1: {2, 3}, 2: {1}, 3: set()}  # 0->2 bypasses the toll
    check("target reachable another way -> not a sealed pocket", _run(_fake(**b)) == [])


def _kq5_cfg():
    import config
    ird = "/home/hayati/coding/sierra_softlock/build/kq5/ir"
    if not os.path.isdir(ird):
        return None
    irs = [f for f in os.listdir(ird) if f.endswith(".ir.json")]
    if not irs:
        return None
    return dataclasses.replace(
        config.LSL2, name="King's Quest V",
        src_dir=os.path.join(ird, "src"), ir_path=os.path.join(ird, irs[0]),
        resource_dir="/home/hayati/sierra/Games/Kings Quest 5",
        start_room=0, goal_rooms=frozenset(), death_signal=(), debug_globals=frozenset())


def test_ground_truth():
    print("\n-- ground truth (end-to-end) --")
    import config
    lsl2 = M.load(cfg=config.LSL2)
    check("LSL2 has no toll strandings (regression guard)", lsl2.toll_strandings() == [])
    kq4 = M.load(cfg=config.KQ4)
    check("KQ4 has no toll strandings (regression guard)", kq4.toll_strandings() == [])
    cfg = _kq5_cfg()
    if cfg is None:
        print("  [SKIP] KQ5 IR not built -- run pipeline decompile to enable")
        return
    kq5 = M.load(cfg=cfg)
    rows = kq5.toll_strandings()
    names = {kq5.g.item_name(r["item"]) for r in rows}
    check("KQ5 temple strands Brass_Bottle + Gold_Coin",
          names == {"Brass_Bottle", "Gold_Coin"})
    check("KQ5 toll item is the Staff via rm214->rm18",
          all(r["toll_item_name"] == "Staff" and r["toll_edge"] == [214, 18] for r in rows))


if __name__ == "__main__":
    test_toll_logic()
    test_ground_truth()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f"  FAILURES: {FAIL}" if FAIL else ""))
    sys.exit(1 if FAIL else 0)
