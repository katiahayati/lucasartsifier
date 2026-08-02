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
    for name in ("_pocket_leavable", "edge_demands", "_uses_in", "_use_escapes"):
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
    """The minimum a machine info needs for `_uses_in` to read it."""
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

    ⚠️ THIS IS A MARKER, NOT A TEST OF THE THING IT NAMES, and saying so is the point. Its
    fixture is IDENTICAL to the passing `a use that does nothing the pocket keeps is not a
    requirement` above -- a machine that writes no register, moves nothing and goes nowhere --
    because our machine model has no way to express "writes a room local" at all. So the two
    assert opposite verdicts on the same input, and this one is the half that must fail.

    That also means it CANNOT flip when the gap closes: there is nothing here to start passing.
    Closing the gap means giving the machine model a room-local representation FIRST; at that
    point this fixture gets rebuilt around a real local and the marker becomes a test. Until
    then it exists so the gap is impossible to forget, and so no passing test claims we handle
    it. Do not delete it, and do not make it green by weakening the assertion.

    STATUS 2026-08-01: the REPRESENTATION exists -- `vocab.derive_room_locals` (cross-scope,
    constant-write, taint-on-computed) + `lower_room_locals` (synthetic registers, entry-reset
    via init_writes), and rm690's local0 derives exactly. It is NOT WIRED, because measured
    wired-in it regresses KQ4 (whale items lost through `death_traps` + `_reg_cost`'s "0 is
    free") and KQ6 (huntersLamp lost; `render_register` spells the new block as phantom flags).
    The three consumers need reset-aware semantics first -- see the note at the call site in
    `missability.load`."""
    print("\n-- 🔴 RED: a room-local latch gating the pocket's exit --")
    b = _carry_in(machines=[_machine(2, _own(8))])       # writes no REGISTER, only (notionally) a
    #   local; our machine model has no way to say that, so this stands in for it: the effect the
    #   game cares about is invisible, and the item is dropped.
    got = [r["item"] for r in _run(_fake(**b)) if r["pattern"] == "one-visit-pocket-carry-in"]
    check("🔴 KNOWN GAP: a use that only sets a room local is not seen as a requirement",
          got == [8])


def _kq5_cfg():
    """KQ5 has no entry in `config`, so build one -- repo-relative, like `config` itself does.
    Returns None when the KQ5 build is absent, and the caller skips."""
    import config
    ird = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "build", "kq5", "ir")
    if not os.path.isdir(ird):
        return None
    irs = [f for f in os.listdir(ird) if f.endswith(".ir.json")]
    if not irs:
        return None
    return dataclasses.replace(
        config.LSL2, name="King's Quest V",
        src_dir=os.path.join(ird, "src"), ir_path=os.path.join(ird, irs[0]),
        resource_dir=os.path.expanduser("~/sierra/Games/Kings Quest 5"),
        start_room=0, goal_rooms=frozenset(), death_signal=(), debug_globals=frozenset())


def test_exit_guard_placement():
    """The register-valued EXIT guard: derived, PLACED, and pinned per clause.

    USER RULING 2026-07-31: "it should be both; if you go in without the teacup you can't win; if
    you go out without the water in the teacup you can't win; the exit guard doesn't really subsume
    the entrance guard." The entrance half ships (`pocket_frontier`); the exit half ships since
    2026-08-01 (commitment in the placement walk -- see below)."""
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

    # PLACED, and pinned per clause -- promoted 2026-08-01 from a 🔴 KNOWN GAP. What closed it is
    # two commitments in the placement walk (`_settable_frontier`), each a true fact of the game
    # rather than a relaxation of the rule:
    #   * an UNCONDITIONAL entry write commits (`_psucc(commit=...)` reads `em.init_writes`, a
    #     class that is unconditional by construction) -- entering the sealing room forces the
    #     seal, so "re-enter with it clear and comply on a second visit" stops being credited;
    #   * an ITEM toll commits in the other store: the row itself proved the crossing consumes
    #     its payment unrecoverably, so compliance may not be proved THROUGH a second crossing.
    # Detection walks stay permissive; only this placement proof changed direction.
    exits = {(sp["from_room"], sp["to_room"], R, tuple(vs))
             for sp in specs if sp.get("req") and not sp["refused"]
             for R, vs in sp["req"].items()}
    check("the water is demanded at the Realm exit -- the oracle's own site (rm680->rm155)",
          water is not None and (680, 155, water, (1,)) in exits)
    # The mirror-shown flag places TWICE, at nested boundaries, and the guard oracle blesses
    # exactly that shape ("the later one is the tighter and the redundancy is harmless"): once at
    # the Charon pocket's own boundary, once at the Realm's.
    shown = {(a, b) for (a, b, R, vs) in exits if (R, vs) != (water, (1,))}
    check("the mirror-shown flag is demanded at rm670->rm660 and rm680->rm155",
          shown == {(670, 660), (680, 155)})
    # ...and what stays refused, stays refused for a stated reason at a real edge: the two
    # `flag == 0` half-questions pair with no entrance guard (demanding a flag CLEAR on the way
    # out closes no softlock), and a refusal must be LOUD -- a guard that vanishes silently is
    # how a half-closed softlock ships.
    refused = [sp for sp in specs if sp.get("req") and sp["refused"]]
    check("every refusal says why, at a real edge",
          bool(refused) and all(sp["condition"] and sp["refused"] for sp in refused))
    check("no refusal claims permissive modelling any more",
          all("PERMISSIVELY" not in w for sp in refused for w in sp["refused"]))

    # THE CATACOMBS CAPTURE GUARD -- the guard oracle's row 1. All four carry-ins (brick 2,
    # holeInTheWall 18, scarf 41, tinderBox 48) on every rm340 exit guard, whose placement wraps
    # the capture arming `(and (not (proc913_0 1)) (proc913_0 2))` in rm340::init. The brick
    # joined 2026-08-01 when `_maze_reach` stopped flooding THROUGH other rooms' cells: in the
    # maze's own door lists cell 20 (rm420, the crushing ceiling) is a CUT VERTEX between the
    # entrance (117) and the trapdoor (7), so with the phantom rm405->rm435 corridor gone the
    # brick's last obtainable edge is the capture crossing itself.
    four = {2, 18, 41, 48}
    cap = [sp for sp in specs if sp["site"] == "edge" and sp["from_room"] == 340
           and sp["to_room"] in (370, 405, 440)]
    check("the three capture guards demand all four catacombs carry-ins",
          len(cap) == 3 and all(four <= set(sp["items"]) for sp in cap),
          f"{[(sp['to_room'], sorted(sp['items'])) for sp in cap]}")
    # ...and the eight rm*->rm420 wall-guards they replaced stay gone: a guard there stops a
    # CAPTIVE who cannot go back for the brick, which is a wall, not a fix.
    check("no wall-guard into rm420 remains",
          not any(sp.get("to_room") == 420 for sp in specs if sp["site"] == "edge"))


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


def test_register_strandings_is_degenerate_on_sci11():
    """`register_strandings` is CAUSAL since 2026-08-02 -- promoted from a 🔴 KNOWN GAP.

    The cure was the docstring's own missing conjunct, derived rather than named: A FLIP STRANDS
    ONLY WHAT THE PRE-FLIP STATE COULD STILL REACH. The same walk is run from the pre-flip states
    at the seed rooms; a source unreachable from there too was stranded by the REGION (the edge
    and toll detectors own that), not by the flip -- and a room only ever seen at the new value
    has no pre-flip player, so its "flip" is an arrival, i.e. an edge crossing wearing a
    register. No register is named anywhere.

    MEASURED: KQ6 323 rows -> 1 (zero on prevRoom), and the survivor is a real lead -- flag 166
    strands the `letter` (what the skeleton key unlocks), needed at rm730/rm870. NOT promoted to
    the oracle: an addition is a suspicion until the user rules (see the KQ6 oracle's contract).
    LSL2 and KQ4 drop to ZERO rows -- diagnosed row by row, every LSL2 row was the same junk
    shape (prevRoom values and timer registers condemning items analyze() already carries, all
    failing the causality test), so the old non-empty output was duplication, not detection.
    test_scopes Part 7 pins the LSL2 side."""
    print("\n-- register_strandings on SCI1.1: causal, not degenerate --")
    import os
    import config
    if not (config.KQ6.ir_path and os.path.exists(config.KQ6.ir_path)):
        print("  [SKIP] no KQ6 IR")
        return
    s = M.load(cfg=config.KQ6)
    rows = s.register_strandings()
    regs = {r["register"] for r in rows}
    prev = M.prev_room_reg(s.em)
    check("no prevRoom flip is reported as a point of no return, and the output is small",
          prev not in regs and len(rows) <= 5,
          f"{len(rows)} rows over {len(regs)} registers; prevRoom is reg{prev} and it is "
          f"{'IN' if prev in regs else 'not in'} the reported set. See the detector's docstring.")
    # ...and the survivor is pinned by SHAPE: the letter row is a lead under user review, and a
    # different row appearing here is a new claim about KQ6 that needs the same review.
    check("the only KQ6 row is the flag-166 letter lead",
          len(rows) == 1 and rows[0]["item_name"] == "letter" and rows[0]["register"] == 338,
          repr([(r["register"], r["value"], r["item_name"]) for r in rows]))


if __name__ == "__main__":
    test_toll_logic()
    test_carry_in_logic()
    test_local_latch_is_not_modelled()
    test_exit_guard_placement()
    test_register_strandings_is_degenerate_on_sci11()
    test_ground_truth()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f"  FAILURES: {FAIL}" if FAIL else ""))
    sys.exit(1 if FAIL else 0)
