"""The two derivations that give a script-armed scene its way BACK -- unit level.

QFG-VGA's ten combat arenas are real rooms entered by `(global2 newRoom: global279)` and left by
`(global2 newRoom: global12)` -- an exit to the PREVIOUS-ROOM register, written not in the arena
scripts but in the `Arena` CLASS (script 211) they all inherit. The model dropped both halves of
that return, so the arenas read terminal and `anchors.discover` promoted all ten to GOALS --
docs/QFG-STATE-EXPLOSION.md §8.5, and the reason `softlock_items: []` said nothing about the game.

Two general facts, neither of which names QFG:

  1  prevRoom is a RESOLVABLE destination. `newRoom: <prevRoom>` means "return to whichever room
     you came from": one edge back along every in-edge, each guarded `prev == p`. The register is
     already derived (`extract.prev_room_global`) and already guards edges (KQ5 has 53 of them);
     only the DESTINATION reading was missing. `var_room_values` answers with a sentinel
     (`extract.PREV_DEST`) because the in-edge set does not exist until the whole graph does;
     `opmodel.OpEmitter._resolve_prev_returns` expands it once flat edges and machine exits are
     both final. Corpus census 2026-08-25b: 8 sites -- QFG-VGA (Arena::doit ×2, killGoblin,
     killBrigand), KQ5 (OpenBottle), LB2 (bigRosetta, sMeanWhile, sEmbraceStop); zero in
     LSL2/KQ4/KQ6.

  2  A room RUNS the methods it INHERITS. An un-overridden method of an ancestor room-class is
     the room's own code executing from another script -- the same scope fact regions and
     ScriptID-loaded scripts already have. Excluded: an ancestor EVERY room inherits (the game's
     uniform plumbing -- KQ6Room, KQ5Room, the Rm root), which is the `Game::newRoom` precedent
     ("runs on every room change" is an engine fact, not a per-room one), and ancestors outside
     the room-species closure (they are not room behaviour). Universality is judged over the
     rooms RECOGNISED BY the closure -- a name-fallback room with no derived chain votes on
     nothing. Census with those two rules: QFG-VGA walks Arena::doit into 9 arenas; LB2 walks
     LBRoom::{doit,doVerb,setInset} into 76 rooms; KQ6's CastleRoom/CliffRoom/LabRoom are
     region-covered (already walked); LSL2 and KQ4 walk NOTHING new.

Run: python3 test_prev_return.py
"""
import sys
sys.path.insert(0, ".")

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))


# ---- synthetic AST builders (ir.py node shapes; same dialect as test_scopes) ----
def V(vtype, index): return {"t": "Variable", "vtype": vtype, "index": index}
def N(value):        return {"t": "Number", "value": value}
def SEL(name):       return {"t": "Selector", "name": name}
def MSG(sel, *ps):   return {"t": "SendMessage", "kids": [SEL(sel), *ps]}
def SEND(recv, *msgs): return {"t": "Send", "kids": [recv, *msgs]}
def OBJ(name):       return {"t": "Object", "name": name}
def ASSIGN(dst, src): return {"t": "Assignment", "kids": [dst, src]}

def _meth(name, stmts):
    return {"sel": 0, "name": name, "ast": {"t": "List", "kids": list(stmts)}}

def _obj(name, methods, is_class=False, species=0, super_=0):
    return {"name": name, "isClass": is_class, "species": species, "super": super_,
            "properties": [], "methods": [_meth(mn, body) for mn, body in methods.items()]}

def _script(num, objects):
    return {"number": num, "locals": [], "procedures": [], "exports": [], "objects": objects}

def _game_loop_main():
    """Main whose Game loop derives pending=13, current=11, prev=12 -- the three shapes
    `pending_room_global` / `current_room_global` / `prev_room_global` read."""
    loop = {"t": "If", "kids": [
        {"t": "Ne", "kids": [V("Global", 13), V("Global", 11)]},
        SEND(OBJ("self"), MSG("newRoom", V("Global", 13)))]}
    switch = [ASSIGN(V("Global", 12), V("Global", 11)),          # save where we were
              ASSIGN(V("Global", 11), V("Parameter", 1)),        # and go
              ASSIGN(V("Global", 13), V("Parameter", 1))]
    return _script(0, [_obj("Fake", {"doit": [loop], "newRoom": switch},
                            is_class=True, species=1, super_=0)])


def test_prev_dest_sentinel():
    print("Part 1: var_room_values reads `newRoom: <prevRoom>` as the return sentinel")
    import ir as I
    import extract as X
    ROOM_SP = 5
    ir = I.IR({"game": "fake", "selectors": [], "scripts": [
        _game_loop_main(),
        _script(994, [_obj("Rm", {}, is_class=True, species=ROOM_SP, super_=0)]),
        # rm30 sends `newRoom: g12` itself; g12 is also ASSIGNED a literal room in this script,
        # which must NOT shadow the return reading -- the register's value is the engine's.
        _script(30, [_obj("rm30", {"doit": [
            ASSIGN(V("Global", 12), N(31)),
            SEND(OBJ("self"), MSG("newRoom", V("Global", 12)))]}, species=0, super_=ROOM_SP)]),
        _script(31, [_obj("rm31", {}, species=0, super_=ROOM_SP)]),
    ]})
    check("prev_room_global derives from the synthetic loop", X.prev_room_global(ir) == 12)
    got = X.var_room_values(ir, 30, V("Global", 12))
    check("the prevRoom destination answers with PREV_DEST",
          getattr(X, "PREV_DEST", None) is not None
          and got == {X.PREV_DEST: None}, repr(got))
    other = X.var_room_values(ir, 30, V("Global", 40))
    check("any other global still resolves by assignment scan (empty here)",
          other == {}, repr(other))


def test_inherited_room_methods():
    print("Part 2: inherited_room_methods -- un-overridden ancestor methods, universality excluded")
    import ir as I
    import extract as X
    ROOM_SP, MID_SP, OUT_SP = 5, 6, 9
    doit_body = [SEND(OBJ("self"), MSG("newRoom", V("Global", 12)))]
    ir = I.IR({"game": "fake", "selectors": [], "scripts": [
        _game_loop_main(),
        _script(994, [_obj("Rm", {"doit": [N(0)], "newRoom": [N(0)]},
                           is_class=True, species=ROOM_SP, super_=0)]),
        _script(211, [_obj("MidArena", {"doit": doit_body},
                           is_class=True, species=MID_SP, super_=ROOM_SP)]),
        _script(300, [_obj("Elsewhere", {"doit": [N(1)]},
                           is_class=True, species=OUT_SP, super_=0)]),
        # rm425 inherits MidArena::doit (no override) -> walked
        _script(425, [_obj("rm425", {"init": []}, species=0, super_=MID_SP)]),
        # rm430 OVERRIDES doit -> nothing inherited
        _script(430, [_obj("rm430", {"doit": [N(2)]}, species=0, super_=MID_SP)]),
        # rm11 inherits only the root -> nothing walked (Rm is universal by construction)
        _script(11, [_obj("rm11", {"init": []}, species=0, super_=ROOM_SP)]),
        # rm50 is a NAME-FALLBACK room outside the closure: it votes on no universality and
        # inherits nothing walkable
        _script(50, [_obj("rm50", {"init": []}, species=0, super_=OUT_SP)]),
    ]})
    fn = getattr(X, "inherited_room_methods", None)
    check("extract.inherited_room_methods exists", fn is not None)
    if fn is None:
        return
    got = fn(ir)
    check("the arena room inherits the mid-class doit",
          [(sn, cn, mn) for (sn, cn, mn, _ast) in got.get(425, ())]
          == [(211, "MidArena", "doit")], repr(got.get(425)))
    check("an override shadows its ancestor", got.get(430, []) == [], repr(got.get(430)))
    check("the universal root is walked nowhere", got.get(11, []) == [], repr(got.get(11)))
    check("a room outside the closure inherits nothing here", got.get(50, []) == [],
          repr(got.get(50)))


def test_inherited_scope_no_temp_bleed():
    print("Part 2b: an inherited method's computed exit resolves in the CLASS's script")
    # The KQ5 rm049 temp-bleed shape, one level up: `Mid::doit` sends `newRoom: temp0` and never
    # assigns it a literal; the HOST room's own unrelated `(= temp0 11)` (a counter, a view
    # number, anything) must not become that method's destination. Caught live on KQ6: walking
    # `KQ6Room::doit` into rm105/rm580 minted phantom edges ->100 from a Display count-down
    # temp, and the phantoms moved the derived START anchor. Resolution belongs to the script
    # whose TEXT is walked -- exactly the scope `machine._var_dests` and `_array_room_values`
    # already use.
    import ir as I
    import extract as X
    ROOM_SP, MID_SP = 5, 6
    ir = I.IR({"game": "fake", "selectors": [], "scripts": [
        _script(994, [_obj("Rm", {}, is_class=True, species=ROOM_SP, super_=0)]),
        _script(211, [_obj("Mid", {"doit": [SEND(OBJ("self"), MSG("newRoom", V("Temp", 0)))]},
                           is_class=True, species=MID_SP, super_=ROOM_SP)]),
        _script(425, [_obj("rm425", {"init": [ASSIGN(V("Temp", 0), N(11))]},
                           species=0, super_=MID_SP)]),
        _script(11, [_obj("rm11", {"init": []}, species=0, super_=ROOM_SP)]),
    ]})
    ts = X.extract(ir)
    got = sorted((e.src, e.dst) for e in ts.edges)
    check("the host room's unrelated temp does not become a destination",
          (425, 11) not in got, repr(got))


def test_resolve_prev_returns():
    print("Part 3: _resolve_prev_returns -- the sentinel expands over the FULL graph, fixpoint")
    import extract as X
    import opmodel
    from guard_ast import Pred, GAnd
    sent = getattr(X, "PREV_DEST", "PREV")
    em = object.__new__(opmodel.OpEmitter)

    class _IR:  # only prev_room_global reads it, via the resolver's own derivation cache
        pass
    import ir as I
    em.ir = I.IR({"game": "fake", "selectors": [], "scripts": [_game_loop_main()]})
    ts = type("ts", (), {})()
    # 10 -> 20 flat; 11 -> 20 by machine EXIT; 20 returns to sender BOTH ways
    ts.edges = [X.Edge(10, 20, None, ""), X.Edge(20, sent, None, "")]
    ts.cs_edges = []
    ts.rooms = {10, 11, 20}
    em.ts = ts
    em.machines = [
        {"room": 11, "inst": "goPlay", "script": 11, "delivered": {20},
         "states": {0: [([], [], [], [], ("EXIT", 20))]}},
        {"room": 20, "inst": "goBack", "script": 20, "delivered": {sent},
         "states": {0: [([], [], [], [], ("EXIT", sent))]}},
    ]
    em.machine_delivered = {(11, 20), (20, sent)}
    em.reg_vals = {}
    fn = getattr(em, "_resolve_prev_returns", None)
    check("OpEmitter._resolve_prev_returns exists", fn is not None)
    if fn is None:
        return
    fn()
    flat = {(e.src, e.dst) for e in ts.edges}
    check("no sentinel survives in the flat edges", sent not in {e.dst for e in ts.edges},
          repr(flat))
    check("the flat return reaches the flat sender", (20, 10) in flat, repr(flat))
    check("...and the machine sender", (20, 11) in flat, repr(flat))
    g = next((e.guard for e in ts.edges if (e.src, e.dst) == (20, 10)), None)
    def _atoms(t):
        if t is None: return []
        if isinstance(t, GAnd):
            return [a for k in t.kids for a in _atoms(k)]
        return [t]
    check("the return edge is guarded `prev == p`",
          any(isinstance(a, Pred) and a.kind == "CMP" and a.var == 12
              and a.op == "==" and str(a.value) == "10" for a in _atoms(g)), repr(g))
    mpaths = em.machines[1]["states"][0]
    mdsts = {tr[1] for (_g, _w, _gg, _c, tr) in mpaths if tr and tr[0] == "EXIT"}
    check("no sentinel survives in the machine paths", sent not in mdsts, repr(mdsts))
    check("the machine return fans per predecessor", mdsts == {10, 11}, repr(mdsts))
    check("delivered follows", em.machines[1]["delivered"] == {10, 11},
          repr(em.machines[1]["delivered"]))
    check("machine_delivered follows",
          (20, 10) in em.machine_delivered and (20, 11) in em.machine_delivered
          and (20, sent) not in em.machine_delivered, repr(em.machine_delivered))
    check("the prev register's domain learns the return values",
          em.reg_vals.get(12, set()) >= {10, 11}, repr(em.reg_vals))


def test_return_to_sender_pricing():
    """Part 4: what a RETURN-TO-SENDER edge costs -- `missability._return_to_sender`.

    Part 3 builds the return; this prices it. An edge `a -> b` guarded `prev == b` is takeable
    only by someone who came to `a` straight from `b`, so it may assert whatever every OTHER
    arrival at `b` necessarily demanded -- of the registers neither room can have changed since.
    Unit level, over a synthetic `meta`: no game, no model build, no register named."""
    print("Part 4: _return_to_sender -- a return may assert its destination's entry condition")
    import missability as M

    def _em(start=0, writes=()):
        """`_return_to_sender` reads only these five things off the model."""
        em = type("em", (), {})()
        em.cfg = type("cfg", (), {"start_room": start})()
        em.handler_writes = [(room, 0, gi, 1, None) for (room, gi) in writes]
        em.init_writes, em.init_seq, em.machines = {}, {}, []
        return em
    P = 12                                     # the previous-room register
    dom = {P: {0, 10, 20, 30}, 5: {0, 1, 2, 3}, 6: {0, 1}, 7: {0, 1}}
    regset = {P, 5, 6, 7}

    def _meta(extra=None):
        # 30 -> 20 is the return (`prev == 20`); 10 -> 20 is the real way in.
        m = {(10, 20): [({5: {0, 1}}, {P: 10}, (frozenset(),))],
             (20, 30): [({}, {P: 20}, (frozenset(),))],
             (30, 20): [({P: {20}}, {P: 30}, (frozenset(),))]}
        m.update(extra or {})
        return m
    meta = _meta()
    M._return_to_sender(meta, _em(), regset, dom, P)
    check("the return inherits the destination's entry requirement",
          meta[(30, 20)][0][0].get(5) == {0, 1}, repr(meta[(30, 20)][0][0]))
    check("...and the real way in is untouched", meta[(10, 20)][0][0] == {5: {0, 1}},
          repr(meta[(10, 20)][0][0]))

    meta = _meta()
    M._return_to_sender(meta, _em(writes=[(30, 5)]), regset, dom, P)   # the SCENE writes it
    check("a register the intermediate room writes is withdrawn", 5 not in meta[(30, 20)][0][0],
          repr(meta[(30, 20)][0][0]))

    meta = _meta()
    M._return_to_sender(meta, _em(writes=[(20, 5)]), regset, dom, P)   # the DESTINATION writes it
    check("a register the DESTINATION writes is withdrawn too (the window opens at the entry, "
          "not at the departure)", 5 not in meta[(30, 20)][0][0], repr(meta[(30, 20)][0][0]))

    meta = _meta()
    del meta[(10, 20)]                                                 # no other way in
    M._return_to_sender(meta, _em(), regset, dom, P)
    check("a destination with no non-return arrival asserts nothing",
          meta[(30, 20)][0][0] == {P: {20}}, repr(meta[(30, 20)][0][0]))

    meta = _meta()
    M._return_to_sender(meta, _em(start=20), regset, dom, P)
    check("the START room asserts nothing about itself",
          meta[(30, 20)][0][0] == {P: {20}}, repr(meta[(30, 20)][0][0]))

    meta = _meta({(10, 20): [({6: {0, 1}}, {P: 10}, (frozenset(),))]})
    M._return_to_sender(meta, _em(), regset, dom, P)
    check("a requirement covering the whole domain constrains nothing",
          6 not in meta[(30, 20)][0][0], repr(meta[(30, 20)][0][0]))

    # TWO real arrivals: the NECESSARY reading -- only what both name, and then the union.
    meta = _meta({(11, 20): [({5: {2}, 7: {1}}, {P: 11}, (frozenset(),))]})
    M._return_to_sender(meta, _em(), regset, dom, P)
    got = meta[(30, 20)][0][0]
    check("two arrivals: the shared register keeps the UNION of their values",
          got.get(5) == {0, 1, 2}, repr(got))
    check("...and a register only one arrival names is dropped", 7 not in got, repr(got))


def test_branch_cost_chaining():
    """Part 5: `_chain_branch_costs` -- the fold's composition, asked of the per-branch table.

    Not a prev-room fact, but the same round's other half and the same kind of claim: a write
    branch guarded `S == v` cannot be taken by a player who lacks whatever making `S` equal `v`
    costs. `_own_fixpoint` said that of `_inroom_own` and never of `_wbranch`."""
    print("Part 5: _chain_branch_costs -- a branch pays for the registers its own guard names")
    import missability as M
    # own: making reg 8 == 1 costs item 40 (one way); reg 9 == 1 costs 41 or 42 depending on room
    own = {(8, 60, 1): frozenset({40}),
           (9, 61, 1): frozenset({41}), (9, 62, 1): frozenset({42}),
           (8, 60, 2): frozenset({43})}

    def _tbl():
        return {(7, 50, 1): [({8: {1}}, frozenset({99}), frozenset()),      # depends on reg 8
                             ({9: {1}}, frozenset(), frozenset()),          # ...and one on reg 9
                             ({7: {0}}, frozenset(), frozenset()),          # self-dep: skipped
                             ({8: {0}}, frozenset(), frozenset()),          # the START value
                             ({8: {1, 2}}, frozenset(), frozenset())]}      # either value will do
    tbl = _tbl()
    M._chain_branch_costs((tbl,), own)
    got = [sorted(c) for (_d, c, _co) in tbl[(7, 50, 1)]]
    check("a branch inherits what its dependency costs, keeping its own",
          got[0] == [40, 99], repr(got[0]))
    check("two writers of the demanded value: the CHEAPEST, i.e. their intersection",
          got[1] == [], repr(got[1]))
    check("a branch depending on its OWN register pays nothing (that is _rstep's business)",
          got[2] == [], repr(got[2]))
    check("the value a register STARTS at is free", got[3] == [], repr(got[3]))
    check("several allowed values: reaching any one suffices, so intersect over them",
          got[4] == [], repr(got[4]))

    tbl = _tbl()
    M._chain_branch_costs((tbl,), {})          # nothing writes anything -> every value is free
    check("with no writers at all the table is untouched",
          [sorted(c) for (_d, c, _co) in tbl[(7, 50, 1)]] == [[99], [], [], [], []],
          repr([sorted(c) for (_d, c, _co) in tbl[(7, 50, 1)]]))


def run():
    test_prev_dest_sentinel()
    test_inherited_room_methods()
    test_inherited_scope_no_temp_bleed()
    test_resolve_prev_returns()
    test_return_to_sender_pricing()
    test_branch_cost_chaining()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(run())
