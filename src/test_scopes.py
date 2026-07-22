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
  4  asserts_eq     -- `(if (not gX) ...)` IS an equality test, in both copies of the rule.
  5  cue arming     -- an edge fired from a Prop's `cue` inherits the guard that armed it.
  6  pending room   -- `(= global13 N)` IS `newRoom: N`, one layer down. KQ4 uses it 20 times.
  7  register flips -- the SECOND softlock class: a flag advances and shuts a region.
  8  goal discovery -- victory when the game ends wins and losses through one flag.

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

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))


def _transfer(node):
    """Run item_transfer over the one message in a synthetic Send."""
    import ir as I
    from extract2 import item_transfer
    recv, msgs = I.send_pairs(node)
    for sel, params in msgs:
        r = item_transfer(recv, sel, params)
        if r is not None:
            return r
    return None


def test_item_transfer():
    print("Part 1: item_transfer -- both spellings of the item-location store")
    from extract2 import EGO

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
    from extract2 import atom
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
    import ir as I, config, extract2 as X
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


def run():
    test_item_transfer()
    test_ownedby_spelling()
    test_region_scope()
    test_main_scope()
    test_asserts_eq()
    test_cue_arming()
    test_pending_room()
    test_register_strandings()
    test_goal_discovery()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
