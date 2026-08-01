"""Tests for toll_strandings() -- the consumed-gate one-visit-pocket softlock (class 4).

A synthetic unit test pins the LOGIC (pocket = graph-dominated by the toll, loot sourced only
inside, one-way filter, leavability) with no game load. End-to-end assertions pin the ground
truth: KQ5's temple strands the Brass_Bottle + Gold_Coin behind the Staff, while LSL2 and KQ4 --
whose every toll candidate is re-obtainable -- must stay empty (the regression guard)."""
import os, sys, types, dataclasses
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import missability as M
from guard_ast import Pred
from scc_core import reachable

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"\n      {detail}" if detail and not cond else ""))


def _fake(edges, emeta, drops, placed, sources, required, reob, start=0, machines=()):
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
    for name in ("_pocket_leavable", "edge_demands", "_reg_readers", "_uses_in", "_use_escapes"):
        setattr(f, name, (lambda _n: lambda *a, _f=f: getattr(M.IrSccReach, _n)(_f, *a))(name))
    f.em = types.SimpleNamespace(
        cfg=types.SimpleNamespace(start_room=start),
        ts=types.SimpleNamespace(placed=placed, acqs=(), edges=(), cs_edges=()),
        machines=list(machines), global_machines=[],
        handler_writes=(), handler_gets=(), handler_drops=())
    f.g = types.SimpleNamespace(item_name=lambda i: f"item{i}")
    return f


def _own(n):
    return Pred("OWN", n)


def _cmp(reg):
    return Pred("CMP", reg, "==", 1)


def _machine(room, entry_guard, writes=(), exits=None, drops=()):
    """The minimum a machine info needs for `_uses_in` and `_reg_readers` to read it."""
    return {"room": room, "inst": f"m{room}", "entries": [(0, entry_guard)],
            "init_entries": [], "drops": tuple(drops),
            "states": {0: [(None, tuple(writes), None, (),
                            ("EXIT", exits) if exits is not None else None)]}}


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

    # A TOLL YOU NEVER PICKED UP IS NOT A TOLL. An item with no source anywhere is a capture gap,
    # not a one-way spend, and reading one as a paid toll invents a sealed pocket out of nothing.
    b = dict(BASE); b["sources"] = {6: {2}}                # the gate item has no source at all
    check("a gate item with no source is a capture gap, not a toll", _run(_fake(**b)) == [])


def _carry_in(**over):
    """BASE plus a carry-IN candidate: item 8, sourced OUTSIDE the pocket and used INSIDE."""
    b = dict(BASE)
    b["sources"] = dict(BASE["sources"]); b["sources"][8] = {0}
    b["required"] = dict(BASE["required"]); b["required"][8] = {2}
    # its use in the pocket sets reg99, and room 3 -- outside -- reads reg99
    b["machines"] = [_machine(2, _own(8), writes=[(99, 1)]), _machine(3, _cmp(99))]
    b.update(over)
    return b


def test_carry_in_logic():
    """The MIRROR direction: obtained outside, needed inside, and the pocket admits you once."""
    print("\n-- toll_strandings() carry-IN --")
    rows = [r for r in _run(_fake(**_carry_in())) if r["pattern"] == "one-visit-pocket-carry-in"]
    check("an item used inside a one-visit pocket must be carried in",
          {(r["item"], tuple(r["toll_edge"])) for r in rows} == {(8, (1, 2))})

    b = _carry_in(); b["sources"] = dict(b["sources"]); b["sources"][8] = {0, 2}
    check("...unless it is obtainable INSIDE -- then fetch it there",
          not [r for r in _run(_fake(**b)) if r["pattern"] == "one-visit-pocket-carry-in"])

    b = _carry_in(); b["required"] = dict(b["required"]); b["required"][8] = {3}
    check("...or is never used inside at all",
          not [r for r in _run(_fake(**b)) if r["pattern"] == "one-visit-pocket-carry-in"])

    # the mirror of `_pocket_leavable`: if the crossing itself demands it, you cannot arrive without
    # it, so it is forced rather than missable.
    b = _carry_in(); b["emeta"] = dict(b["emeta"])
    b["emeta"][(1, 2)] = [({}, {}, (frozenset({7, 8}),))]
    check("...or the crossing itself demands it -> forced, not missable",
          not [r for r in _run(_fake(**b)) if r["pattern"] == "one-visit-pocket-carry-in"])

    # THE CLAUSE THAT SEPARATES A CARRY-IN FROM A SOUVENIR, in its two failing shapes.
    b = _carry_in(machines=[_machine(2, _own(8))])         # the use writes nothing, goes nowhere
    check("a use that does nothing the pocket keeps is not a requirement",
          not [r for r in _run(_fake(**b)) if r["pattern"] == "one-visit-pocket-carry-in"])

    # ...but a register write COUNTS wherever it is read. This used to demand a reader OUTSIDE the
    # pocket, and that qualifier was fitted to a wrong answer -- see the RED assertion below.
    b = _carry_in(machines=[_machine(2, _own(8), writes=[(99, 1)]), _machine(2, _cmp(99))])
    check("a register write counts even where only the pocket reads it",
          [r["item"] for r in _run(_fake(**b))
           if r["pattern"] == "one-visit-pocket-carry-in"] == [8])

    # ...and the two other ways an effect gets out.
    b = _carry_in(machines=[_machine(2, _own(8), exits=3)])
    check("a crossing you cannot make later escapes the pocket",
          [r["item"] for r in _run(_fake(**b))
           if r["pattern"] == "one-visit-pocket-carry-in"] == [8])

    b = _carry_in(machines=[_machine(2, _own(8), drops=[6])])
    check("so does moving an item that is needed outside",
          [r["item"] for r in _run(_fake(**b))
           if r["pattern"] == "one-visit-pocket-carry-in"] == [8])


def test_local_latch_is_not_modelled():
    """🔴 DELIBERATELY RED -- a use whose only effect is a room LOCAL that gates the pocket's exit.

    USER GROUND TRUTH (2026-07-31, tested in-game): *"you need the gauntlet. without it the game
    refuses to show Death the mirror."* KQ6 rm690:

        (method (doVerb param1) (switch param1
            (48  ... (global2 setScript: issueChallenge))      ; the gauntlet -- NOT gated
            (13  (if local0 (say <brush-off>) else ... (global2 setScript: holdUpMirror)))))
        introScript  state 2:  (= local0 1)  handsOn:  (= seconds 15)
        issueChallenge state 0: (= local0 0)

    so `local0` is raised before the player's ONLY arrival window and the challenge is the one
    thing that clears it with hands on. The gauntlet is therefore the precondition of
    `holdUpMirror`, which is the pocket's only non-death exit.

    WE DO NOT MODEL ROOM LOCALS, so that link is invisible: the model reads `holdUpMirror`'s entry
    as `own(mirror)` alone. KQ6's gauntlet is currently kept by an INCIDENTAL register write (it
    sets which death message you get), i.e. the right verdict for the wrong reason -- and an item
    whose use touched a local and nothing else would be dropped outright. This is the third
    recorded instance of the same gap (`liftTapestry`'s L1, `huntersLamp`'s rm520 `doit`).

    Turn this green by making a use that writes a local READ BY a guard on the pocket's exit
    escape, not by deleting the case."""
    print("\n-- 🔴 RED: a room-local latch gating the pocket's exit --")
    b = _carry_in(machines=[_machine(2, _own(8))])       # writes no REGISTER, only (notionally) a
    #   local; our machine model has no way to say that, so this stands in for it: the effect the
    #   game cares about is invisible, and the item is dropped.
    got = [r["item"] for r in _run(_fake(**b)) if r["pattern"] == "one-visit-pocket-carry-in"]
    check("🔴 KNOWN GAP: a use that only sets a room local is not seen as a requirement",
          got == [8])


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


def test_exit_guard_placement():
    """The register-valued EXIT guard: derived, correctly refusing, and one 🔴 for why.

    USER RULING 2026-07-31: "it should be both; if you go in without the teacup you can't win; if
    you go out without the water in the teacup you can't win; the exit guard doesn't really subsume
    the entrance guard." The entrance half ships (`pocket_frontier`). The exit half is built and
    currently emits NOTHING, which is the safe direction but not the finished one."""
    import config, guards as G
    print("\n-- the register-valued exit guard --")
    if not os.path.exists(config.KQ6.ir_path):
        print("  (skip: no KQ6 IR)")
        return
    s = M.load(cfg=config.KQ6)
    specs = G.guard_specs(s)

    # THE ENTRANCE GUARD, which is the half that works. The teacup joins the coin, the skull and
    # the mirror on a guard the game's own boundary already carries.
    door = next((sp for sp in specs if sp["site"] == "edge"
                 and (sp["from_room"], sp["to_room"]) == (340, 155)), None)
    cup = next((i for i in s.required if s.g.item_name(i) == "teaCup"), None)
    check("the Realm entrance demands the teacup", bool(door) and cup in door["items"]
          and not door["refused"])

    # A REGISTER can be written back in the game's own spelling. Lowering a flag into a synthetic
    # global is one-way for the analysis; a patch has to reverse it.
    water = next((R for R in s.regs if s._reg_cost(R, {1}) == frozenset({cup})), None)
    check("a lowered flag renders back as the game's own test",
          water is not None and G.render_register(s, water, 1) is not None)

    # 🔴 AND IT IS NOT PLACED, for a reason that is about the MODEL and not about KQ6. Register
    # writes are added to each projection UNGUARDED on purpose (`_build_product`: "each projection
    # stays permissive and can only remove movement the guards actually forbid"). That is right for
    # finding strandings and fatal here: the walk believes you can re-enter the one-visit pocket
    # with its own seal still clear, so no crossing ever commits and no placement can be proved
    # safe. We refuse rather than wall -- but refusing is not closing.
    #
    # Turn this green by making the pocket's SEAL non-permissive for this question (the seal is
    # already derived and carried on the row as `toll_reg`), not by relaxing the placement rule.
    exits = [sp for sp in specs if sp.get("req") and not sp["refused"]]
    check("🔴 KNOWN GAP: no exit guard is placed, so the water is demanded nowhere",
          bool(exits),
          f"every register-valued spec is refused: "
          f"{sorted({w for sp in specs if sp.get('req') for w in sp['refused']})}")
    # ...and the refusal must be LOUD. A guard that vanishes silently is how a half-closed
    # softlock ships; this is the assertion that keeps the reason in the report.
    refused = [sp for sp in specs if sp.get("req") and sp["refused"]]
    check("...and every refusal says why, at a real edge",
          bool(refused) and all(sp["condition"] and sp["refused"] for sp in refused))


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
    test_carry_in_logic()
    test_local_latch_is_not_modelled()
    test_exit_guard_placement()
    test_ground_truth()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f"  FAILURES: {FAIL}" if FAIL else ""))
    sys.exit(1 if FAIL else 0)
