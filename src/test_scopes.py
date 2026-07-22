"""Unit tests for the two EXTRACTION SCOPES that were silently empty, using synthetic AST
fragments so each part is checked without an end-to-end run. Run: python3 test_scopes.py

Parts under test:
  1. item_transfer  -- the item-LOCATION store has two spellings and we read only one.
                       `gEgo get:/put:` (LSL2) and `(Inv at: N) moveTo: D` (KQ4) are ONE
                       operation. KQ4 contains no `get: 24` at all, so the Dead_Fish did not
                       exist in our model; LSL2 destroys the Soap with `moveTo: -1` twice.
  2. region scope   -- SCI dispatches at three scopes (Main / Rgn / room) and we had the
                       middle one keyed off the `rm<N>` decompiler naming convention, so KQ4
                       mapped 0 of its 26 regions. Region MACHINES were dropped too.

Part 2 needs a real IR and skips cleanly without one; part 1 is pure.
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


def run():
    test_item_transfer()
    test_ownedby_spelling()
    test_region_scope()
    test_main_scope()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
