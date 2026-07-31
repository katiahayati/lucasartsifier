"""Unit tests for the extraction gaps that were silently EMPTY rather than wrong, using synthetic AST
fragments where possible so each part is checked without an end-to-end run. Run: python3 test_scopes.py

Every part here fixes something that was silently EMPTY rather than wrong -- the failure mode
this project keeps hitting, where an LSL2 spelling is the only one implemented and a second game
produces a confident wrong answer instead of an error.

  1  item_transfer  -- the item-LOCATION store has two spellings and we read one. `gEgo get:/put:`
                       (LSL2) and `(Inv at: N) moveTo: D` (KQ4) are ONE operation. KQ4 contains no
                       `get: 24` at all, so the Dead_Fish did not exist in our model; LSL2 destroys
                       the Soap with `moveTo: -1` twice and we never saw that either.
  1b ownedBy         -- "is it still lying there": `ownedBy: gCurRoomNum` vs `ownedBy: 78`.
  2  region scope   -- SCI dispatches at three scopes (Main / Rgn / room); the middle one was keyed
                       off the `rm<N>` naming convention, so KQ4 mapped 0 of its 26 regions.
  3  Main scope     -- script 0 is a scope, not a room, and only LSL2's happened to be walked.
 3b icon-bar scope -- SCI1 added a FOURTH always-live scope: nothing arms the script the inventory
                       items live in, because the icon bar dispatches their `doVerb`. It is lifted
                       for its REGISTER effects and their costs, and for nothing else -- KQ6's
                       magic paint is mixed there and is written nowhere else in the game.
 3c handle alias   -- `(= temp0 (gInv at: 11))` then `(temp0 state: ...)`: half a bit-store is
                       worse than none, because the half we had could only ever block.
  4  asserts_eq     -- `(if (not gX) ...)` IS an equality test, in both copies of the rule.
  5  cue arming     -- an edge fired from a Prop's `cue` inherits the guard that armed it.
  6  pending room   -- `(= global13 N)` IS `newRoom: N`, one layer down. KQ4 uses it 20 times.
  7  register flips -- the SECOND softlock class: a flag advances and shuts a region.
  8  goal discovery -- victory when the game ends wins and losses through one flag.
  9  derived constants -- death and debug read out of the game, not declared.
 10  resource exhaustion -- a finite item degraded one-way by ordinary use.
 11  item names    -- the number -> name map derives from the game's own class table, not one
                       hardcoded LSL2 dict applied to every game (KQ4's Shovel was "Bikini_Top").
 12  grid + joint  -- a room that is a virtual map (KQ4's ocean) summarises to an edge gate on the
                       previous-room global, and the JOINT of that gate with the one-time whale flag
                       strands the Golden Bridle -- a softlock no single-register projection sees.

Parts 2-7 need a real IR and skip cleanly without one; 1, 1b and 4 are pure.
"""
import sys
sys.path.insert(0, ".")

# ---- synthetic AST builders (match ir.py node shapes) --------------------
def V(vtype, index): return {"t": "Variable", "vtype": vtype, "index": index}
def N(value):        return {"t": "Number", "value": value}
def SEL(name):       return {"t": "Selector", "name": name}
def MSG(sel, *ps):   return {"t": "SendMessage", "kids": [SEL(sel), *ps]}
def SEND(recv, *msgs): return {"t": "Send", "kids": [recv, *msgs]}
def OBJ(name):       return {"t": "Object", "name": name}

EGO_VAR = V("Global", 0)                      # gEgo
def INV_AT(n):                                 # `(Inv at: N)`
    return SEND(OBJ("Inv"), MSG("at", N(n)))

def _fake_ir(scripts):
    """A minimal IR from {script number: {object name: {method name: [statements]}}}.

    Enough for the derivations that read the Game loop's shape. Every object also carries the
    `(if (!= g13 g11) (self newRoom: g13))` test the pending/current pair derives from, so a
    synthetic Game loop is one method, not a fixture."""
    import ir as I
    def meth(name, stmts):
        return {"sel": 0, "name": name, "ast": {"t": "List", "kids": list(stmts)}}
    loop = {"t": "If", "kids": [
        {"t": "Ne", "kids": [V("Global", 13), V("Global", 11)]},
        SEND(OBJ("self"), MSG("newRoom", V("Global", 13)))]}
    return I.IR({"game": "fake", "selectors": [], "scripts": [
        {"number": num, "locals": [], "procedures": [], "exports": [],
         "objects": [{"name": obj, "isClass": False, "species": 0, "super": 0, "properties": [],
                      "methods": [meth(mn, list(body) + [loop]) for mn, body in ms.items()]}
                     for obj, ms in objs.items()]}
        for num, objs in scripts.items()]})


PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))


def _transfer(node):
    """Run item_transfer over the one message in a synthetic Send."""
    import ir as I
    from extract import item_transfer
    recv, msgs = I.send_pairs(node)
    for sel, params in msgs:
        r = item_transfer(recv, sel, params)
        if r is not None:
            return r
    return None


def test_item_transfer():
    print("Part 1: item_transfer -- both spellings of the item-location store")
    import os, config, ir as I, extract as X
    from extract import EGO
    # The selector table is DERIVED from the game's class table now, not hardcoded, so a
    # vocabulary has to be installed before any of this means anything. Synthetic CALL SITES
    # against a real derived vocabulary -- which is a better test than synthetic both ends.
    if not os.path.exists(config.LSL2.ir_path):
        print("  (skip: no LSL2 IR to derive a vocabulary from)")
        return
    v = X.install_vocabulary(I.load_ir(config.LSL2.ir_path))
    check("a vocabulary is derived at all", v is not None, repr(v))
    if v is None:
        return
    check("...naming the store and its accessors", v.prop == "owner"
          and "moveTo" in v.writes and "ownedBy" in v.reads, v.describe())
    check("...and the game's own wrappers over them", {"get", "put"} <= set(v.writes),
          sorted(v.writes))

    # -- LSL2's spelling: the EGO is the receiver -------------------------
    check("gEgo get: 9 -> (9, EGO)",
          _transfer(SEND(EGO_VAR, MSG("get", N(9)))) == (9, EGO))
    check("gEgo put: 9 -1 -> (9, -1)",
          _transfer(SEND(EGO_VAR, MSG("put", N(9), N(-1)))) == (9, -1))
    # LSL2 also writes `put:` with the destination omitted -- SCI defaults it to NOWHERE.
    check("gEgo put: 9 (no dest) -> (9, -1)",
          _transfer(SEND(EGO_VAR, MSG("put", N(9)))) == (9, -1))
    # KQ4 disposes with `put: 25 999` -- a pseudo-room, NOT -1. The destination used to be
    # discarded entirely, which is why `put:`'s two dialects looked identical.
    check("gEgo put: 25 999 -> (25, 999), destination kept",
          _transfer(SEND(EGO_VAR, MSG("put", N(25), N(999)))) == (25, 999))

    # -- KQ4's spelling: the ITEM is the receiver --------------------------
    check("(Inv at: 24) moveTo: gEgo -> (24, EGO)   [the Dead_Fish's only acquisition]",
          _transfer(SEND(INV_AT(24), MSG("moveTo", EGO_VAR))) == (24, EGO))
    check("(Inv at: 19) moveTo: 206 -> (19, 206)    [the worm's window closing]",
          _transfer(SEND(INV_AT(19), MSG("moveTo", N(206)))) == (19, 206))
    check("(Inv at: 18) moveTo: -1 -> (18, -1)      [LSL2 rm48/rm71 destroy the Soap]",
          _transfer(SEND(INV_AT(18), MSG("moveTo", N(-1)))) == (18, -1))

    # -- what must NOT be read as a transfer ------------------------------
    # `moveTo: x y` is the Window/View SCREEN-POSITION selector, unrelated and used ~30 times
    # in LSL2's dialog code. Arity is what separates them, plus the `(X at: N)` receiver.
    check("window moveTo: 4 4 (two args) is NOT a transfer",
          _transfer(SEND(OBJ("SysWindow"), MSG("moveTo", N(4), N(4)))) is None)
    check("moveTo: on a non-(at: N) receiver is NOT a transfer",
          _transfer(SEND(OBJ("SysWindow"), MSG("moveTo", N(4)))) is None)
    check("get: on a non-ego receiver is NOT a transfer",
          _transfer(SEND(V("Global", 5), MSG("get", N(9)))) is None)
    # a non-constant item number cannot be resolved -- must be dropped, not guessed
    check("(Inv at: <local>) moveTo: gEgo is NOT a transfer (item not a constant)",
          _transfer(SEND(SEND(OBJ("Inv"), MSG("at", V("Local", 3))),
                         MSG("moveTo", EGO_VAR))) is None)


def test_ownedby_spelling():
    print("\nPart 1b: ownedBy -- 'is the item still lying there', spelled two ways")
    from extract import atom
    from guard_ast import Pred
    # LSL2: `ownedBy: gCurRoomNum` -- says "here" without naming a room.
    g = atom(SEND(INV_AT(18), MSG("ownedBy", V("Global", 11))))
    check("ownedBy: gCurRoomNum -> LOC value 'room'",
          isinstance(g, Pred) and g.kind == "LOC" and g.var == 18 and g.value == "room", repr(g))
    # KQ4: `ownedBy: 78` inside Room78 -- the same claim, with the room named. The literal is
    # KEPT rather than collapsed, because only the caller knows which room it is standing in:
    # `ownedBy: 206` (the worm's limbo) is the same syntax and means the opposite.
    g = atom(SEND(INV_AT(25), MSG("ownedBy", N(78))))
    check("ownedBy: 78 -> LOC value 78 (literal kept, not flattened to 'other')",
          isinstance(g, Pred) and g.kind == "LOC" and g.var == 25 and g.value == 78, repr(g))
    g = atom(SEND(INV_AT(19), MSG("ownedBy", N(206))))
    check("ownedBy: 206 -> LOC value 206", isinstance(g, Pred) and g.value == 206, repr(g))

    # ...and the consumer resolves it against the room the guard was found in.
    import missability as M
    loc = M.IrSccReach._loc_required
    fruit_here = atom(SEND(INV_AT(25), MSG("ownedBy", N(78))))
    check("_loc_required(guard, 25, room=78) is True   (the fruit is on the tree here)",
          loc(None, fruit_here, 25, 78) is True)
    check("_loc_required(guard, 25, room=23) is False  (a different room's claim)",
          loc(None, fruit_here, 25, 23) is False)
    lsl2_here = atom(SEND(INV_AT(18), MSG("ownedBy", V("Global", 11))))
    check("_loc_required still True for the gCurRoomNum spelling with no room given",
          loc(None, lsl2_here, 18) is True)


_EM_CACHE = {}
def real_em(which):
    """Load a real model once; None if that game's IR is not present."""
    if which in _EM_CACHE:
        return _EM_CACHE[which]
    import os, config, missability as M
    cfg = getattr(config, which)
    em = None
    if os.path.exists(cfg.ir_path):
        try:
            em = M.load(cfg=cfg).em
        except Exception as e:                      # noqa: BLE001 -- a missing IR must SKIP
            print(f"  (skip {which}: {e})")
    else:
        print(f"  (skip {which}: no IR at {cfg.ir_path})")
    _EM_CACHE[which] = em
    return em


def test_region_scope():
    print("\nPart 2: region scope -- the middle of SCI's three dispatch scopes")
    for which in ("LSL2", "KQ4"):
        em = real_em(which)
        if em is None:
            continue
        rr = em.region_rooms
        rooms = set().union(*rr.values()) if rr else set()
        # The bug was silence, not an error: KQ4 mapped 0 regions because the lookup was
        # `by_name["rm<N>"]`, and KQ4 names its rooms `Room<N>`. Any game with `setRegions:`
        # in its sources must map SOME region.
        check(f"{which}: at least one region script is mapped to rooms",
              len(rr) > 0, f"region_rooms={len(rr)}")
        check(f"{which}: mapped regions cover more rooms than regions",
              len(rooms) >= len(rr), f"{len(rooms)} rooms over {len(rr)} regions")
        # A region's MACHINES must be lifted into the rooms that activate it, not skipped for
        # not being a room themselves -- regUnicorn's `uniActions` is the only place KQ4 ever
        # requires the Golden_Bridle.
        machine_rooms = {i["room"] for i in em.machines}
        region_members = {r for rs in rr.values() for r in rs}
        check(f"{which}: some machine is lifted into a region member room",
              bool(machine_rooms & region_members),
              f"{len(machine_rooms)} machine rooms, {len(region_members)} region members")


def test_main_scope():
    print("\nPart 3: Main scope -- script 0 is a scope, not a room")
    for which in ("LSL2", "KQ4"):
        em = real_em(which)
        if em is None:
            continue
        # LSL2's script 0 happened to land in ts.rooms and so was walked; KQ4's did not, so every
        # effect in its Main was dropped -- including the Magic Fruit being eaten. Whether a game
        # declares a room object in script 0 must not decide whether Main is analysed at all.
        n = sum(1 for x in em.handler_writes if x[1] == 0)
        n += sum(1 for x in em.handler_gets if x[1] == 0)
        n += sum(1 for x in em.handler_drops if x[1] == 0)
        check(f"{which}: Main (script 0) contributes handler effects", n > 0, f"{n} effects")


def test_iconbar_scope():
    print("\nPart 3b: the ICON BAR is a scope too -- and it contributes registers, nothing else")
    import ir as I, vocab as V, config, os
    # 3b.1 -- WHICH script, derived from the item class table and never named.
    #   The whole reason the rule is safe on the goldens is that SCO0 titles declare their items
    #   in script 0, which is ALREADY the Main scope, so nothing new is homed there.
    want = {"LSL2": {0}, "KQ4": {0}, "KQ6": {907}}
    for which, exp in want.items():
        cfg = getattr(config, which)
        if not (cfg.ir_path and os.path.exists(cfg.ir_path)):
            print(f"  (skip {which}: no IR)")
            continue
        got = set(V.inventory_scripts(I.load_ir(cfg.ir_path)))
        check(f"{which}: inventory script derives as {sorted(exp)}", got == exp, repr(sorted(got)))

    em = real_em("KQ6")
    if em is None:
        return
    # 3b.2 -- ...and only a script NOTHING ELSE ARMS is taken. `global_homed` closes over the
    #   scripts the inventory arms and that live nowhere else -- KQ6's `mixPaintScr` (915) is
    #   armed by `KqInv doVerb 30` and by nothing at all otherwise.
    check("KQ6: the inventory script and what it arms are homed globally",
          {907, 915} <= set(em.global_homed), repr(sorted(em.global_homed)))
    check("...and a script that already had a home is NOT taken (241 is armed by rm240)",
          241 not in em.global_homed and em.armed_rooms.get(241) == {240},
          repr(em.armed_rooms.get(241)))

    # 3b.3 -- THE POINT OF THE SCOPE: a register written nowhere else gets a writer. Flag 22 is
    #   "the magic paint is mixed" and `KqInv doVerb 30` is its only writer in the whole game;
    #   without this scope it has an EMPTY domain and the castle's long door reads as free.
    import missability as M
    s = M.load(cfg=config.KQ6)
    check("KQ6: flag 22 (reg 194, the mixed paint) has a writer at last",
          194 in s.regs and len(s._rstep.get(194, {})) > 0,
          f"promoted={194 in s.regs} rstep_rooms={len(s._rstep.get(194, {}))}")

    # 3b.4 -- AND NOTHING ELSE. Every other thing `machines` feeds is a claim about a PLACE, and
    #   the icon bar has no place; the separate list is how that is said once instead of at each
    #   consumer. Each of these broke a real verdict when the machine was left in `machines`:
    #   `required` (five softlocks lost), `sources`/`drops`, EXIT (fabricated ways out of the dark
    #   room), `death_traps` (an inventory action read as an ESCAPE from a trap).
    check("KQ6: global-scope machines are kept OUT of em.machines",
          em.global_machines and not any(i.get("global_scope") for i in em.machines),
          f"{len(em.global_machines)} global, "
          f"{sum(1 for i in em.machines if i.get('global_scope'))} leaked")
    check("...so an always-available action is not a per-room requirement",
          sorted(s.required.get(46, ())) == [230, 340, 470, 660],
          f"required[teaCup]={sorted(s.required.get(46, ()))} -- if this is ~86 rooms the scope "
          f"is being read as evidence about every room, which collapses every frontier.")

    # 3b.5 -- the scope's EXTENT: `doVerb` is what the icon bar dispatches. `cue` is a callback,
    #   and where it fires is the caller's business. Pinned on what the clause ASSERTS rather than
    #   on an item list, because it is measured inert on today's corpus -- KQ6's `skull::cue`
    #   clears the ember bit, and lifted whole it would say the skull can be emptied in any room.
    check("KQ6: a callback in the inventory script is not lifted as a player action",
          not [1 for (_r, sc, gi, _v, _g) in em.handler_writes
               if sc in em.global_homed and gi in (489, 490)],
          "skull::cue's bit-clear is being attributed to every room")


def test_handle_aliases():
    print("\nPart 3c: `(= temp0 (gInv at: 11))` -- the cached-handle alias")
    import vocab as V
    at = lambda n: (n.get("kids", [None])[0] or {}).get("_item") if isinstance(n, dict) else None

    def item_expr(k):                               # a stand-in for `(gInv at: k)`
        return {"t": "Send", "kids": [{"_item": k}]}
    T0, T1 = V_("Temp", 0), V_("Temp", 1)
    body = {"t": "List", "kids": [
        {"t": "Assignment", "kids": [T0, item_expr(11)]},
        {"t": "Assignment", "kids": [T1, item_expr(7)]},
        {"t": "Assignment", "kids": [T1, {"t": "Number", "value": 3}]},   # reassigned: not an alias
    ]}
    al = V._handle_aliases(body, at)
    check("a single-assignment handle resolves to its item", al.get(("T", 0)) == 11, repr(al))
    check("a variable assigned anything else is NOT an alias", ("T", 1) not in al, repr(al))
    r = V._alias_resolver(body, at)
    check("the resolver still prefers a direct receiver", r(item_expr(4)) == 4)
    check("...and falls back to the alias", r(T0) == 11)
    check("...and refuses an unknown variable", r(T1) is None)


def V_(vtype, index):
    return {"t": "Variable", "vtype": vtype, "index": index}


def test_asserts_eq():
    print("\nPart 4: asserts_eq -- `(if (not gX) ...)` is an equality test")
    import missability as M
    check("x == v  asserts equality", M.asserts_eq("==", True) is True)
    check("not (x != v)  asserts equality (SCI's `(if (not gX) ...)`)",
          M.asserts_eq("!=", False) is True)
    check("x != v  does not", M.asserts_eq("!=", True) is False)
    check("not (x == v)  does not (a negative requirement; deliberately permissive)",
          M.asserts_eq("==", False) is False)


def test_cue_arming():
    print("\nPart 5: cue-armed edges inherit their arming guard")
    em = real_em("KQ4")
    if em is None:
        return
    import missability as M
    # KQ4's dwarves' house: `(Said 'open/door')` opens it only `(if (not global100)` -- daytime --
    # while the `newRoom: 54` itself lives in the door Prop's `cue`, an object away. Without the
    # inheritance the edge is guarded by the opaque cel test alone, i.e. free.
    door = [e for e in em.ts.edges if e.src == 22 and e.dst == 54]
    check("rm22 -> rm54 (the dwarves' door) exists", len(door) == 1, f"{len(door)} edges")
    if door:
        check("...and requires global100 == 0, i.e. daytime",
              M.required_values(door[0].guard, 100) == {0},
              repr(M.required_values(door[0].guard, 100)))
    # and the gate must survive into the movement model, not just the guard tree -- these were
    # two separate copies of the same equality test, and only one of them got fixed at first.
    s = M.load(cfg=__import__("config").KQ4)
    reqs = [req.get(100) for (req, sets, alts) in s._emeta.get((22, 54), [])]
    check("...and edge_meta agrees (no second copy of the rule)", reqs == [{0}], repr(reqs))


def test_pending_room():
    print("\nPart 6: the pending-room global -- newRoom: written one layer down")
    import ir as I, config, extract as X
    import os
    for which, cfg in (("LSL2", config.LSL2), ("KQ4", config.KQ4)):
        if not os.path.exists(cfg.ir_path):
            print(f"  (skip {which}: no IR)")
            continue
        # DISCOVERED from `(if (!= <pending> <current>) (self newRoom: <pending>))` in the Game
        # loop, not declared. Both games land on 13 -- by derivation, not by assuming it.
        g = X.pending_room_global(I.load_ir(cfg.ir_path))
        check(f"{which}: pending-room global is discovered", g is not None, repr(g))
    em = real_em("KQ4")
    if em is None:
        return
    # KQ4 enters the witches' cave with `(= global13 57)` on a control-colour test. Without this
    # rm57 had NO in-edges, which made it look sealed by nightfall AND let start discovery anchor
    # on a room nothing can reach.
    ins = {e.src for e in em.ts.edges if e.dst == 57}
    check("KQ4: rm57 (witches' cave) has an in-edge", bool(ins), f"in-edges from {sorted(ins)}")


def test_register_strandings():
    print("\nPart 7: register-flip strandings agree with the edge detector")
    import os, config, missability as M
    if not os.path.exists(config.LSL2.ir_path):
        print("  (skip: no LSL2 IR)")
        return
    s = M.load(cfg=config.LSL2)
    found = {r["item_name"] for r in s.register_strandings()}
    known = {c["item_name"] for c in s.analyze()} | {"Ashes", "Sand"}
    # The two detectors see different CLASSES (crossing a one-way edge vs a flag advancing), so
    # they need not agree -- but on the one game with hand-verified ground truth, everything the
    # register detector finds is already known. A new name here is a claim about LSL2 and needs
    # the user, not a passing test.
    check("LSL2: register-flip findings introduce no new items",
          not (found - known), f"new: {sorted(found - known)}")
    check("LSL2: the register detector finds something at all", bool(found), f"{len(found)} items")
    for r in s.register_strandings():
        if r["source_rooms"] and set(r["source_rooms"]) & set(r["still_needed_at"]):
            check("a finding must not have a source inside its own post-flip region", False,
                  repr(r))
            return
    check("no finding has a source inside its own post-flip region", True)


def test_goal_discovery():
    print("\nPart 8: victory is discovered, including when it shares death's flag")
    import os, dataclasses, config, missability as M, anchors as A
    for which, cfg, want in (("LSL2", config.LSL2, 86), ("KQ4", config.KQ4, 694)):
        if not os.path.exists(cfg.ir_path):
            print(f"  (skip {which}: no IR)")
            continue
        em = M.load(cfg=dataclasses.replace(cfg, start_room=0, goal_rooms=frozenset())).em
        got = sorted(em.cfg.goal_rooms)
        # KQ4's global127 means "the game is over", not "you died" -- it fires in 33 death rooms
        # AND in both endings, so the primary rule throws victory out with the losses. The
        # fallback picks the excluded terminal whose ending TESTS WHAT YOU ACHIEVED.
        check(f"{which}: goal discovered as rm{want}", got == [want], repr(got))
    em = real_em("KQ4")
    if em is None:
        return
    # the discriminator itself: the win asks what you are carrying, the loss does not
    win = A._tests_achievement(em, {692, 694})
    check("KQ4: rm694 (cure your father) tests achievement", 694 in win, repr(win))
    check("KQ4: rm692 (marry Edgar) does not", 692 not in win, repr(win))


def test_derived_constants():
    print("\nPart 9: death and debug are DERIVED, not declared")
    import os, dataclasses, config, ir as I, vocab as V, missability as M
    for which, cfg, want_death in (("LSL2", config.LSL2, (101, 1001)),
                                   ("KQ4", config.KQ4, (127, None))):
        if not os.path.exists(cfg.ir_path):
            print(f"  (skip {which}: no IR)")
            continue
        ir = I.load_ir(cfg.ir_path)
        # DEATH: the global the Game subclass tests on the way to Restore/Restart/Quit. LSL2 hands
        # off through `dyingScript` and KQ4 offers the dialog inline -- one `setScript:` hop apart,
        # same anchor. Must reproduce the hand-declared value exactly.
        got = [shape for shape, _o, _m in V.derive_death(ir)]
        check(f"{which}: death signal derives as {want_death}", want_death in got, repr(got))
        # DEBUG: a flag that is TOGGLED (`^=`), which is what a menu checkbox compiles to.
        dbg = set(V.derive_debug(ir))
        check(f"{which}: a debug flag is derived", bool(dbg), repr(sorted(dbg)))
        check(f"{which}: ...covering everything declared that is ever written",
              cfg.debug_globals <= dbg or not cfg.debug_globals, repr(sorted(dbg)))
    # and the whole analysis must be unchanged with NOTHING declared
    if os.path.exists(config.LSL2.ir_path):
        blank = dataclasses.replace(config.LSL2, death_signal=(), debug_globals=frozenset())
        s = M.load(cfg=blank)
        items = sorted({x["item_name"] for x in s.analyze()})
        check("LSL2 fully derived still finds 15 items + 1 group",
              len(items) == 15 and len(s.group_strandings()) == 1, f"{len(items)} items")


def test_resource_exhaustion():
    print("\nPart 10: resource exhaustion -- items you use UP, not throw away")
    import os, config, missability as M
    for which, cfg, want in (("LSL2", config.LSL2, False), ("KQ4", config.KQ4, True)):
        if not os.path.exists(cfg.ir_path):
            print(f"  (skip {which}: no IR)")
            continue
        s = M.load(cfg=cfg)
        rows = s.resource_exhaustion()
        # LSL2 has no item-property writes at all, so this class cannot fire there -- which is
        # also why the whole fourth store went unnoticed until a second game.
        check(f"{which}: resource-exhaustion findings {'exist' if want else 'are empty'}",
              bool(rows) == want, repr([(r["item_name"], r["at_room"]) for r in rows]))
        if which == "LSL2":
            # dangerous_sinks must NOT flag a consumption that KILLS you (drink the Grotesque_Gulp
            # or the Fruit -> die -> reload with the item). Matches the v1.0-lsl2 tag exactly; the
            # regression was folding guard_required into real_uses (guard_required feeds
            # resource_exhaustion instead). See real_uses.
            ds = {s.g.item_name(x["item"]) for x in s.dangerous_sinks()}
            check("LSL2: dangerous_sinks = the tag's four (no death-consumed Grotesque_Gulp/Fruit)",
                  ds == {"Matches", "Hair_Rejuvenator", "Parachute", "Airsick_Bag"}, repr(sorted(ds)))
        if which == "KQ4":
            # item 15 is the Shovel: it snaps after five wrong digs (Room16:589) and global113 is a
            # GLOBAL, so holes dug in the graveyard count against the crypt -- needed in both. Names
            # now DERIVE per game (vocab.item_names), so the NAME is checked too (was "Bikini_Top").
            shovel = [r for r in rows if r["item"] == 15]
            check("KQ4: the Shovel is flagged in both digging rooms",
                  {r["at_room"] for r in shovel} == {16, 18}, repr(shovel))
            check("KQ4: the Shovel is NOT collapsed (its rooms are a fixed region, not roaming)",
                  len(shovel) == 2 and not any("at_rooms" in r for r in shovel), repr(shovel))
            check("KQ4: item 15 is named the Shovel, not LSL2's table",
                  all(r["item_name"] == "Shovel" for r in shovel),
                  repr([r["item_name"] for r in shovel]))
            # A0n(2): the unicorn ROAMS (regUnicorn writes global124 to 20/26/27), so the bow's
            # arrow-spend there is ONE encounter, not three -- collapsed to a single roaming row.
            bow_roam = [r for r in rows if r["item"] == 14 and "at_rooms" in r]
            # `still_needed_at` also carries rm3 -- the bow's OWN SOURCE room. Room3 tests
            # `(global0 has: 14)` to choose a LOOK MESSAGE (`proc255_0 3 14` / `3 17`); the branch
            # arms no state, takes no item and writes no register, so it is evidence of nothing.
            # ACCEPTED (user, 2026-07-25) rather than fixed: it changes no output -- KQ4's full
            # snapshot surface is byte-identical and test_kq4_ground_truth is green -- and the
            # claim under test here is the COLLAPSE (one row over the roaming rooms), which holds.
            # The real cure is to require a PRODUCTIVE clause for requirement evidence, the rule
            # `_armed_wrote`/`_clause_productive` already applies elsewhere; tracked, not urgent.
            check("KQ4: the roaming unicorn collapses to one Cupid's Bow row",
                  len(bow_roam) == 1 and bow_roam[0]["at_rooms"] == [20, 26, 27]
                  and bow_roam[0]["still_needed_at"] == [3, 82], repr(bow_roam))


def test_item_names():
    print("\nPart 11: item names DERIVE per game (vocab.item_names), not one LSL2 table for all")
    import os, config, vocab, ir as I
    # LSL2: the derivation must reproduce the old hand-written _NAMES table on every real item;
    # item 0 is the NoInv placeholder, which was never in _NAMES and is never a real softlock.
    if os.path.exists(config.LSL2.ir_path):
        m = vocab.item_names(I.load_ir(config.LSL2.ir_path))
        want = {0: "NoInv", 1: "Dollar_Bill", 5: "Swimsuit", 6: "Wad_O_Dough",
                15: "Bikini_Top", 17: "Knife", 24: "Parachute", 30: "Ashes", 31: "Sand"}
        check("LSL2: derived names reproduce the curated table",
              all(m.get(i) == n for i, n in want.items()), repr({i: m.get(i) for i in want}))
    # KQ4: the names every report used to hand-resolve from Main.sc, now derived. The Shovel (15)
    # used to print as LSL2's "Bikini_Top" -- the reporting hazard A0h closes.
    if os.path.exists(config.KQ4.ir_path):
        m = vocab.item_names(I.load_ir(config.KQ4.ir_path))
        want = {0: "Silver_Flute", 7: "Obsidian_Scarab", 14: "Cupid_s_Bow", 15: "Shovel",
                17: "Fishing_Pole", 19: "Worm", 25: "Magic_Fruit", 33: "Magic_Hen"}
        check("KQ4: names derived from its own class table",
              all(m.get(i) == n for i, n in want.items()), repr({i: m.get(i) for i in want}))


def test_grid_and_joint():
    print("\nPart 12: the ocean grid + the joint-window softlock (KQ4 Golden Bridle)")
    import os, config, missability as M, grid, extract as X, ir as I

    # (a) the room globals derive from the Game loop; ego from the store wrapper's holders. Both
    #     games -> previous 12, current 11, ego {0} -- no longer the old hardcoded G_EGO/G_CURROOM.
    for which, cfg in (("LSL2", config.LSL2), ("KQ4", config.KQ4)):
        if not os.path.exists(cfg.ir_path):
            continue
        ird = I.load_ir(cfg.ir_path)
        check(f"{which}: previous-room global derives as 12", X.prev_room_global(ird) == 12,
              repr(X.prev_room_global(ird)))
        check(f"{which}: current-room global derives as 11", X.current_room_global(ird) == 11,
              repr(X.current_room_global(ird)))
        X.install_vocabulary(ird)   # sets _EGO / _CURROOM from derivation, not the template default
        check(f"{which}: ego global derives as {{0}}, current-room as 11 (not hardcoded)",
              X._EGO == frozenset({0}) and X._CURROOM == 11, f"ego={sorted(X._EGO)} cur={X._CURROOM}")

    # (a2) and the previous-room global is the one the ROOM-SWITCH METHOD saves, not any global a
    #      game happens to copy the current room into. KQ5's boatRegion remembers which shore you
    #      sailed from with `(= global361 global11)`, won on script order, and made KQ5's 53
    #      prevRoom-guarded edges measure as 4. Synthetic so it holds without KQ5's IR.
    def _asn(dst, src): return {"t": "Assignment", "kids": [dst, src]}
    switcher = [_asn(V("Global", 12), V("Global", 11)),     # save   <- the answer
                _asn(V("Global", 11), V("Parameter", 1)),   # and go <- what marks the method
                _asn(V("Global", 13), V("Parameter", 1))]
    decoy = [_asn(V("Global", 361), V("Global", 11))]       # a room's own "where did I come from"
    fake = _fake_ir({99: {"decoy": {"init": decoy}},        # script order puts the decoy FIRST
                     0:  {"KQ6": {"newRoom": switcher}}})
    check("the decoy `(= X current)` outside the switch method does not win",
          X.prev_room_global(fake) == 12, repr(X.prev_room_global(fake)))
    check("...and with no switch method at all, nothing is derived",
          X.prev_room_global(_fake_ir({99: {"decoy": {"init": decoy}}})) is None)

    # (b) the ocean summarises to an edge gate: the island (rm43) is reachable ONLY from the whale
    #     (44) or the island itself (43). LSL2 has no virtual-map room and yields nothing.
    if os.path.exists(config.LSL2.ir_path):
        g = grid.analyze(M.load(cfg=config.LSL2).em, 12)
        check("LSL2: no grid rooms (latches are not grids)", g == {}, repr(g))
    if os.path.exists(config.KQ4.ir_path):
        g = grid.analyze(M.load(cfg=config.KQ4).em, 12)
        island = g.get(31, {}).get(43)
        check("KQ4: rm31->43 (island) gated on previous-room in {43,44}",
              island == frozenset({43, 44}), repr(island))

    # (c) the joint (previous-room x one-time whale flag) strands the Golden Bridle -- a softlock no
    #     single-register projection sees. LSL2 (no grid) reports nothing.
    if os.path.exists(config.LSL2.ir_path):
        js = M.load(cfg=config.LSL2).joint_strandings()
        check("LSL2: no joint-window softlocks", js == [], repr(js))
    if os.path.exists(config.KQ4.ir_path):
        s = M.load(cfg=config.KQ4)
        js = s.joint_strandings()
        bridle = [f for f in js if f["item"] == 21]
        check("KQ4: Golden Bridle (21) is a joint-window softlock",
              len(bridle) == 1 and bridle[0]["source_rooms"] == [43]
              and 183 in bridle[0]["flags"], repr(bridle))
        # the joint adds the Golden_Bridle (21) AND, since the deliverability generalisation
        # (2026-07-22), the Dead_Fish (24) -- both behind the one-time whale: the bridle's SOURCE is
        # on the island, the fish's NEED is, and a source only counts if a need is reachable after it.
        base = {c["item"] for c in s.analyze()}
        net = {f["item"] for f in js} - base
        check("KQ4: joint sweep adds the Golden Bridle and the Dead_Fish", net == {21, 24},
              repr(sorted(net)))


def test_patcher_layout():
    print("\nPart 13: the patcher derives the object-global layout (ego/game/room), not 0/1/2")
    import os, config, ir as I, patcher as P
    for which, cfg in (("LSL2", config.LSL2), ("KQ4", config.KQ4)):
        if not os.path.exists(cfg.ir_path):
            continue
        P.configure(I.load_ir(cfg.ir_path))
        # ego = store holder, game = changeScore receiver, room = newRoom receiver. Both games use
        # the SCI template 0/1/2, so emitted patches are unchanged -- but they are now DERIVED.
        check(f"{which}: patcher layout derives ego=0 game=1 room=2",
              (P._EGO, P._GAME, P._ROOM) == (0, 1, 2), f"{(P._EGO, P._GAME, P._ROOM)}")
    # setScript triggers: KQ4's rm45 amulet handover starts the endgame via `(self setScript: closer)`,
    # and `closer` does `newRoom: 690`. trigger.py must find THAT (not just the changeState idiom).
    import trigger as T
    from sexpr import read_file
    r45 = os.path.join(config.KQ4.src_dir, "Room45.sc")
    if os.path.exists(r45):
        pl = T.find_trigger(read_file(r45), 690)
        check("KQ4: rm45->690 endgame guard finds the setScript trigger",
              pl.get("kind") == "setscript" and pl.get("target_script") == "closer", repr(pl))


def run():
    test_item_transfer()
    test_ownedby_spelling()
    test_region_scope()
    test_main_scope()
    test_iconbar_scope()
    test_handle_aliases()
    test_asserts_eq()
    test_cue_arming()
    test_pending_room()
    test_register_strandings()
    test_goal_discovery()
    test_derived_constants()
    test_resource_exhaustion()
    test_item_names()
    test_grid_and_joint()
    test_patcher_layout()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
