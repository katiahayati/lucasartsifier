"""Independent unit tests for the 'everything means everything' capture parts, using
synthetic IR fragments so each part is verified WITHOUT the 700s end-to-end winnability
round-trip. Run: python3 test_everything.py

Parts under test:
  1. local-compare guards   -- atom() must model `(== <local> v)` (was OPAQUE)
  2. setScript capture       -- `(x setScript: S)` starts machine S (was dropped)
  3. fall-through hack gone   -- a machine with real entries gets NO free start fall-through
  4. item-property state      -- `(item prop:)` compares tracked (the third store)
"""
import sys
sys.path.insert(0, ".")
import config
import ir as I
from guard_ast import Pred, GAnd, GOr, GNot

# ---- synthetic AST builders (match ir.py node shapes) --------------------
def V(vtype, index): return {"t": "Variable", "vtype": vtype, "index": index}
def N(value):        return {"t": "Number", "value": value}
def CMP(op, a, b):   return {"t": op, "kids": [a, b]}
def NOT(x):          return {"t": "Not", "kids": [x]}
def AND(*xs):        return {"t": "And", "kids": list(xs)}
def SEL(name):       return {"t": "Selector", "name": name}
def MSG(sel, *ps):   return {"t": "SendMessage", "kids": [SEL(sel), *ps]}
def SEND(recv, *msgs): return {"t": "Send", "kids": [recv, *msgs]}
def OBJ(name):       return {"t": "Object", "name": name}

PASS = []; FAIL = []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

# ---- Part 1: local-compare guards ---------------------------------------
def test_local_compare():
    print("Part 1: local-compare guards")
    from extract import atom
    # `(== <Local#2> 5)` should NOT be opaque -- it should be a tracked-local guard
    g = atom(CMP("Eq", V("Local", 2), N(5)))
    is_ctr = isinstance(g, tuple) and g and g[0] == "CTR"
    check("atom(local == 5) is a CTR local guard, not OPAQUE", is_ctr, repr(g))
    if is_ctr:
        check("CTR carries (vtype_char, index)=(L,2)", g[1] == ("L", 2), repr(g))
        check("CTR carries op '==' and value 5", g[2] == "==" and g[3] == 5, repr(g))
    # negation wraps in GNot (polarity handled by the tree, like globals)
    gn = atom(NOT(CMP("Eq", V("Local", 2), N(5))))
    check("atom(not local==5) is GNot(CTR)", isinstance(gn, GNot)
          and isinstance(gn.kid, tuple) and gn.kid[0] == "CTR", repr(gn))
    # Temp variables too
    gt = atom(CMP("Gt", V("Temp", 0), N(3)))
    check("atom(temp > 3) is a CTR (T,0) '>' 3", isinstance(gt, tuple)
          and gt[0] == "CTR" and gt[1] == ("T", 0) and gt[2] == ">" and gt[3] == 3, repr(gt))
    # a GLOBAL compare must STILL be a CMP Pred (unchanged)
    gg = atom(CMP("Eq", V("Global", 101), N(0)))
    check("atom(global==0) still a CMP Pred (unchanged)",
          isinstance(gg, Pred) and gg.kind == "CMP" and gg.var == 101, repr(gg))

_EM = None
def real_em():
    """Load the real LSL2 model once (skips gracefully if the IR isn't present)."""
    global _EM
    if _EM is None:
        import os
        p = config.ACTIVE.ir_path
        if not os.path.exists(p):
            return None
        import opmodel as E
        ir = I.load_ir(p)
        _EM = E.OpEmitter(ir, config.LSL2, lambda gi, v: gi == 101 and v == 1001)
        _EM.emit()   # populate n_opaque etc.
    return _EM

def _has_ctr(g):
    if isinstance(g, tuple) and g and g[0] == "CTR": return True
    if isinstance(g, (GAnd, GOr)): return any(_has_ctr(k) for k in g.kids)
    if isinstance(g, GNot): return _has_ctr(g.kid)
    return False

def test_local_compare_real():
    print("Part 1b: local-compare guards on real LSL2 (disguise henchStatus)")
    em = real_em()
    if em is None:
        print("  [SKIP] LSL2 IR not present"); return
    # rm47's henchStatus (loc index 2) must be a TRACKED guard variable now
    check("rm47 henchStatus local is tracked (loc_dom)", (47, "L", 2) in em.loc_dom,
          str([k for k in em.loc_dom if k[0] == 47]))
    # its doit branches produce resolving CTR guards, not opaque
    ctr_locals = sum(1 for r, s, k, v, g in em.handler_locals if _has_ctr(g))
    check("handler-locals carry resolving CTR guards (>=10)", ctr_locals >= 10, f"{ctr_locals}")
    check("n_opaque dropped below the pre-fix 1780", em.n_opaque < 1780, f"n_opaque={em.n_opaque}")

# ---- Part 2: setScript capture ------------------------------------------
def test_setscript():
    print("Part 2: setScript capture")
    from machine import _setscript_target
    # Returns (script, name); a None script means "the script this reference appears in", which
    # is all an Object reference can mean. A `(ScriptID s n)` target carries its own script and
    # needs the IR's export table to resolve -- covered against the real game below.
    check("setScript target from Object ref",
          _setscript_target(OBJ("henchScript")) == (None, "henchScript"))
    check("setScript target from (X new:)",
          _setscript_target(SEND(OBJ("henchScript"), MSG("new"))) == (None, "henchScript"))
    check("setScript target None for non-script param", _setscript_target(N(5)) is None)
    em = real_em()
    if em is None:
        print("  [SKIP] LSL2 IR not present (real check)"); return
    # rm47's henchScript is started via setScript -> it must now have an entry (was empty)
    hs = [info for info in em.machines if info["room"] == 47 and info["inst"] == "henchScript"]
    check("rm47 henchScript machine exists", len(hs) == 1)
    if hs:
        check("rm47 henchScript now HAS entries (setScript captured)", len(hs[0]["entries"]) >= 1,
              f"entries={hs[0]['entries']}")
    # CROSS-SCRIPT arming, `setScript: (ScriptID s n)`. `n` indexes the EXPORT table, which does
    # not follow object order, so this is only resolvable on an IR carrying exports. KQ6's
    # nightMare is export 2 of script 344 but its objects[2] is `smoke` -- picking by position
    # would silently arm the wrong object, so assert the export path specifically.
    import os, glob, ir as I
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    kq6 = glob.glob(os.path.join(_root, "build", "sweep", "kq6", "*.ir.json"))
    if not kq6:
        print("  [SKIP] KQ6 IR not present (cross-script check)"); return
    kir = I.load_ir(kq6[0])
    if not (kir.scripts.get(344) and kir.scripts[344].exports):
        print("  [SKIP] KQ6 IR predates the export table"); return
    sid = lambda s, n: {"t": "KernelCall", "name": "ScriptID",
                        "kids": [N(s), N(n)]}
    check("ScriptID resolves through the EXPORT table, not object order",
          kir.script_id_target(sid(344, 2)) == (344, "nightMare")
          and kir.scripts[344].objects[2].name != "nightMare")
    check("cross-script setScript target resolves",
          _setscript_target(sid(344, 3), kir) == (344, "blowinIt"))
    check("unresolvable ScriptID stays None (code export / missing script)",
          _setscript_target(sid(344, 0), kir) is None
          and _setscript_target(sid(99999, 0), kir) is None)

    # A `cue`-method arming is a CONTINUATION, not a way in, and an unconditional one erases every
    # real precondition its machine's other armings carry (entries are alternatives). KQ6's rm407
    # kills you in the hole-in-the-wall room without the hole -- `(not (global0 has: 18))` -- and
    # `(method (cue) ... (setScript: emptyHandedDeath))` was making that vacuous.
    import extract as X, machine as MA
    X.install_vocabulary(kir)
    b = MA.MachineBuilder(kir, lambda *a: False)
    m = next((x for x in b.machines(kir.scripts[407]) if x.inst == "emptyHandedDeath"), None)
    if m is None:
        print("  [SKIP] KQ6 rm407 not in this IR"); return
    check("rm407's death machine keeps no unconditional `cue` entry",
          all(g is not None for _k, g in m.entries), repr(m.entry_sources))
    check("...and the hole-in-the-wall gate survives in its armings",
          any(18 in __import__("missability")._own_positive(g)
              for _k, g in m.entries if g is not None),
          repr([str(g)[:60] for _k, g in m.entries]))
    # ...while a machine armed ONLY from `cue` keeps its entry, since dropping it would strengthen
    # a guard with nothing to replace it -- the direction that invents softlocks.
    cue_only = [x for s in kir.scripts.values() for x in b.machines(s)
                if x.entry_sources and set(x.entry_sources) == {"cue"}]
    check("a cue-ONLY machine is left alone", all(x.entries for x in cue_only),
          f"{len(cue_only)} such machines")

    # Object-property state has TWO SPELLINGS and KQ6 mixes them on the SAME object: rm407 says
    # both `((ScriptID 30 0) seenByMino:)` and `(rLab seenSecretLatch: 1)`, rLab being script 30's
    # export 0 -- and declared a CLASS, which is how SCI1.1 writes a singleton region. Reading only
    # the ScriptID spelling left half that object's state invisible, `seenSecretLatch` included:
    # the hole-in-the-wall matters because putting it up lets you watch the minotaur and learn
    # where his lair is.
    import vocab as V2
    kir2 = I.load_ir(kq6[0])          # fresh: derive_* must run before any lowering rewrites it
    props = V2.derive_obj_props(kir2)
    r30 = {sel for scr, sel in props if scr == 30}
    check("both spellings resolve to the SAME object's register set",
          {"seenByMino", "seenSecretLatch"} <= r30, sorted(r30))
    check("...and a class receiver is eligible (SCI1.1 regions are classes)",
          "hiddenDoorOpen" in r30, sorted(r30))

    # An object the room inits only under a CONDITION can only be interacted with under that
    # condition, so a machine armed from its methods inherits it. KQ6's rm340 keeps the cave mouth
    # to the minotaur's lair out of the cast until the minotaur is dead --
    # `(if (proc913_0 1) (= local2 23) (minoOpening init:) else (= local2 20))` -- and
    # `minoOpening::doVerb` is what arms `goToLair`. Without this the lair has an unguarded
    # entrance and the catacombs can be beaten carrying nothing.
    cast = X.cast_conditions(kir.scripts[340])
    check("a conditionally-init'ed object reports its cast condition",
          X.cast_guard(cast, "minoOpening") is not None, repr(cast.get("minoOpening")))
    check("...an object init'ed in a bulk `add: ... eachElementDo: #init` is IN the cast",
          "labDoor" in cast and "theDoor" in cast, sorted(cast))
    check("...and unconditionally-init'ed objects contribute nothing",
          X.cast_guard(cast, "labDoor") is None and X.cast_guard(cast, "nosuchobject") is None)
    # On a flag-LOWERED IR the shared condition is visible as one synthetic global, so assert the
    # thing that matters: the `doit` arming (`(and (== onControl 512) (proc913_0 1))`) and the
    # `doVerb` arming (gated only by the conditional `init:`) demand the SAME flag. Before the cast
    # rule the doVerb entry was a bare `opaque()`, which made the disjunction vacuous.
    kir3 = I.load_ir(kq6[0])
    fl = V2.derive_flags(kir3)
    base = V2.lower_flags(kir3, fl[0], fl[1])[0] if fl else None
    X.install_vocabulary(kir3)
    lair = next((x for x in MA.MachineBuilder(kir3, lambda *a: False)
                 .machines(kir3.scripts[340]) if x.inst == "goToLair"), None)
    want = f"{base + 1}!=0"            # flag 1 = "the minotaur is dead"
    check("every arming of KQ6's goToLair carries the minotaur flag",
          base is not None and lair is not None and len(lair.entries) > 1
          and all(g is not None and want in str(g) for _k, g in lair.entries),
          repr([str(g)[:70] for _k, g in (lair.entries if lair else [])]))

    # THE MAZE GRID. `makeDoors` is the DISPATCHER's door table and is right about the cells the
    # dispatcher draws; a cell that is a real room is drawn by that room's own script, and may use
    # a screen edge for something else. KQ6's rm405 is the catacombs entrance: the table says its
    # south is open, but its own doit sends `edgeHit 3` to `walkOut -> newRoom 340`, i.e. OUT. With
    # the invented descent the lower level is walkable from the entrance and both rooms the player
    # must survive can be skipped; without it the trapdoor is the only way down.
    ex = X.Extractor.__new__(X.Extractor)
    ex.ir = kir
    key, tbl = ex._dir_table(kir.scripts[400])
    check("the maze's direction table is read out of its own re-entry switch",
          key == ("sel", "prevEdgeHit") and tbl == {1: -16, 3: 16, 2: 1, 4: -1}, f"{key} {tbl}")
    check("rm405 takes SOUTH back for its own exit; the other maze rooms take nothing",
          ex._repurposed_dirs(kir.scripts[400], 405) == {16}
          and all(not ex._repurposed_dirs(kir.scripts[400], r) for r in (406, 409, 420, 435)),
          repr(sorted(ex._repurposed_dirs(kir.scripts[400], 405))))
    check("...and a room whose walk-out can still reach the dispatcher keeps its direction",
          not ex._repurposed_dirs(kir.scripts[400], 409))
    # A pseudo-room named for a LIST of cells: `(if (proc999_5 temp1 65 103 ...) (return -411))`.
    # Without them rm411 has no coordinate, and _splice_dispatcher's fallback gives a cell-less
    # room every room in the table -- which is where the maze's free edge into the lair came from.
    listed = ex._listed_pseudo_rooms(kir.scripts[400], X._room_numbers(kir))
    check("a pseudo-room named for a LIST of coordinates recovers all of them",
          listed.get(411) == {65, 103, 112, 130, 165, 183, 230}, repr(listed))

    # A machine armed inside a PROCEDURE has no way in of its own -- the proc runs because someone
    # called it. KQ6 puts the hole-in-the-wall up through one: `proc404_0` arms `holeOnWall`, and
    # its call sites are `doVerb` cases on the hole itself. Scanned standalone the entry is
    # unconditional, and one vacuous alternative erases the item gate.
    b404 = MA.MachineBuilder(kir3, lambda *a: False)
    hw = next((x for x in b404.machines(kir3.scripts[404]) if x.inst == "holeOnWall"), None)
    check("a machine armed inside a procedure inherits its CALL SITES",
          hw is not None and hw.entries
          and all(g is not None and "own(18)" in str(g) for _k, g in hw.entries),
          repr([str(g)[:80] for _k, g in (hw.entries if hw else [])]))

    # AN `init:` INSIDE A `changeState` INHERITS THAT MACHINE'S ENTRY. The body has no path
    # condition of its own -- it runs because the machine was armed and got that far -- which is
    # the same rule the PROCEDURE case above applies, with a different supplier. KQ6's rm407 puts
    # the hole-in-the-wall on the wall in `putHoleOnWall` (armed from `doVerb 25`, i.e. from USING
    # the hole) and inits `theHole` at state 2, so looking through it -- how you learn where the
    # minotaur's lair is -- costs own(18). Read standalone that init is unconditional and free.
    import missability as MI
    bprime = MA.MachineBuilder(kir3, lambda *a: False).prime()
    cast407 = bprime._cast(kir3.scripts[407])
    check("an object init'ed inside a cutscene inherits the cutscene's entry",
          "own(18)" in str(X.cast_guard(cast407, "theHole")),
          repr(X.cast_guard(cast407, "theHole")))
    check("...and unprimed, the same init reads as unconditional (pass 0 is the old behaviour)",
          X.cast_guard(MA.MachineBuilder(kir3, lambda *a: False)._cast(kir3.scripts[407]),
                       "theHole") is None)
    look = next((x for x in bprime.machines(kir3.scripts[407]) if x.inst == "lookInHole"), None)
    check("...so the machine armed from that object's doVerb carries the item too",
          look is not None and look.entries
          and all(g is not None and "own(18)" in str(g) for _k, g in look.entries),
          repr([str(g)[:80] for _k, g in (look.entries if look else [])]))

    # `addToPic:` IS an init -- the game's own class table says so (`View::addToPic` is
    # `(if (global5 contains: self) ... else (self init:))`). Derived per CLASS, because
    # `Cursor::setLoop` and `Talker::say` also init self and unioning the names would make the
    # cast rule vacuous. Without it KQ6's rm480 -- which inits the gates when you arrive from
    # rm490 and `addToPic:`s them otherwise -- looked as though its gates were only clickable
    # once you had already been through them, stranding the red scarf behind its own door.
    isel = X.init_selectors(kir3)
    byname = {o.name: o for s in kir3.scripts.values() for o in s.objects if o.is_class}
    view, cursor = byname.get("View"), byname.get("Cursor")
    check("addToPic is derived as an init for the View family",
          view is not None and "addToPic" in isel.get(view.species, ()),
          repr(sorted(isel.get(view.species, ())) if view else None))
    check("...and a Cursor's own init-aliases stay on the Cursor",
          cursor is not None and "setLoop" in isel.get(cursor.species, ())
          and "setLoop" not in isel.get(view.species, ()),
          repr(sorted(isel.get(cursor.species, ())) if cursor else None))
    # rm480 spells it `(if (== global12 490) (gates ... init:) else (gates ... addToPic:))`, so
    # with `addToPic` counted the two branches are complementary and the disjunction constrains
    # nothing; without it only the `init:` arm is a cast site and the gates demand `prev == 490`
    # -- a requirement to have already been where they take you. Asserted through `structural_reqs`
    # because that is the reading a cast guard is COMPOSED with, and a tautology is only visible
    # there (`any_guard` cannot fold `A or not A`).
    mg = lambda on: bprime._entry_guard.get((480, on))
    pg = lambda pn: X.any_guard(bprime.proc_calls.get(pn))
    PREV, dom = 12, {12: {0, 480, 490}}
    prev_of = lambda g: MI.structural_reqs(g, {PREV}, dom).get(PREV)
    sites = lambda sels: [prev_of(g) for g in
                          X.cast_conditions(kir3.scripts[480], proc_guard=pg, machine_guard=mg,
                                            init_sels=sels).get("gates", ())]
    check("the `init:` branch is the one that demands you arrived from rm490",
          {490} in sites(isel) and {490} in sites(None), repr(sites(None)))
    check("...and counting addToPic recovers the `else` branch that covers it",
          any(p and 490 not in p for p in sites(isel))
          and not any(p and 490 not in p for p in sites(None)), repr(sites(isel)))

    # `state_musts` splits its dataflow node by the machine's LOCALS. A cutscene decides something
    # early, remembers it in a local, and acts on it much later -- KQ6's tapestry tests
    # `seenSecretLatch` at state 2, keeps it in local1, and only opens the secret door at state 18.
    # Keyed by state alone both branches reach 18 and the merge throws the fact away (correctly,
    # for "what holds on EVERY path") before the local can discriminate.
    import missability as MI
    from guard_ast import Pred
    LATCH = Pred("CMP", var=900, op="==", value="1")
    info = {
        "entries": [(0, None)], "init_entries": [], "entry_locals": [{}], "init_entry_locals": [],
        "states": {
            0: [([LATCH], [], [], [(("L", 1), "set", 1)], ("ADVANCE",)),   # saw it -> local1 := 1
                ([], [], [], [], ("ADVANCE",))],                            # else, local1 stays 0
            1: [([("CTR", ("L", 1), "!=", 0)], [(901, 1)], [], [], ("ADVANCE",))],
        },
    }
    sm = MI.state_musts(info, {900})
    check("merged musts lose the fact where the two branches rejoin",
          sm.get(1, {}) == {}, repr(sm.get(1, {})))
    check("...but the per-PATH view keeps it for the branch the local selects",
          sm.at(1, [("CTR", ("L", 1), "!=", 0)]) == {900: {1}},
          repr(sm.at(1, [("CTR", ("L", 1), "!=", 0)])))
    check("...and the other branch of the same local is unconstrained",
          sm.at(1, [("CTR", ("L", 1), "==", 0)]) == {},
          repr(sm.at(1, [("CTR", ("L", 1), "==", 0)])))

    # DEATH TRAPS. A Script object holds one `setScript:` slot, so machines armed into the same
    # slot are competitors and the player's action cancels the timer that was in it. But taking the
    # slot is not enough: KQ6's rm420 offers `throwSkull` (own 11), which ENDS by re-arming the
    # death, and `useBrick` (own 2), which does not. Only the second is an escape.
    from guard_ast import GNot
    def mach(inst, entries, recv, armers, trans, room=1):
        return {"room": room, "inst": inst, "entries": entries, "entry_recv": recv,
                "entry_armers": armers, "states": {0: [([], [], [], [], trans)]}}
    SLOT = ("G", 2)
    em = type("Em", (), {})()
    em.machines = [
        mach("timer", [(0, None), (0, None)], [SLOT, SLOT], [None, ("tryIt", 9)], ("DEATH",)),
        mach("useIt", [(0, Pred("OWN", var=2))], [SLOT], [None], ("ADVANCE",)),
        mach("tryIt", [(0, Pred("OWN", var=11))], [SLOT], [None], ("ADVANCE",)),
        mach("elsewhere", [(0, Pred("OWN", var=99))], [("G", 0)], [None], ("ADVANCE",)),
    ]
    rows = MI.death_traps(em, set(), {}).get(1, [])
    check("an unconditional death is escaped only by a competitor that does not re-arm it",
          [sorted(a) for _r, al in rows for a in al] == [[2]], repr(rows))
    # ...and a death we cannot fully read must NOT be negated: KQ4's ogre grabs you under
    # conditions that render opaque, and negating the readable half demanded the Axe to walk out
    # of four ordinary rooms.
    em.machines = [mach("grabbed", [(0, GAnd([GNot(Pred("CMP", var=112, op="!=", value="0")),
                                              Pred("OPAQUE")]))],
                        [SLOT], [None], ("DEATH",))]
    check("a death whose trigger contains an opaque is left alone",
          MI.death_traps(em, {112}, {112: {0, 1}}) == {},
          repr(MI.death_traps(em, {112}, {112: {0, 1}})))
    # ...while one fully-modelled arming IS negatable -- KQ6's collapsing floor kills you only
    # while the minotaur lives, so leaving needs the flag set.
    em.machines = [mach("dieAlready", [(0, GNot(Pred("CMP", var=173, op="!=", value="0")))],
                        [SLOT], [None], ("DEATH",))]
    check("a fully-modelled arming yields the complement of its condition",
          MI.death_traps(em, {173}, {173: {0, 1}}).get(1) == [({173: {1}}, (frozenset(),))],
          repr(MI.death_traps(em, {173}, {173: {0, 1}})))

    # A machine we do NOT model is still a competitor for the slot. KQ6's `lightItUp` is gated
    # `own(tinderBox)` and all it does is start a palette fade, so `_machine_info` drops it -- and
    # it is the only thing that stops the minotaur killing you in the dark room.
    em.machines = [mach("timer", [(0, None)], [SLOT], [None], ("DEATH",))]
    em.dropped_entries = [(1, Pred("OWN", var=48), "lightItUp", SLOT)]
    check("a DROPPED machine can still be the escape",
          [sorted(a) for _r, al in MI.death_traps(em, set(), {}).get(1, []) for a in al] == [[48]],
          repr(MI.death_traps(em, set(), {})))
    em.dropped_entries = [(1, Pred("OWN", var=48), "lightItUp", ("G", 0))]
    check("...but only on the SAME slot", MI.death_traps(em, set(), {}) == {})

    # Negating a CONJUNCTION gives alternatives, and per-register projections let each through in
    # the projection that cannot see the other -- so the pair has to be walked together. Bounded
    # and self-selecting: the trap names the registers, and a game with no such trap gets none.
    ir_ = MI.IrSccReach.__new__(MI.IrSccReach)
    two = {406: [({12: {1, 2}}, (frozenset(),)), ({173: {1}}, (frozenset(),))]}
    one = {420: [({}, (frozenset({2}),))], 411: [({173: {1}}, (frozenset(),))]}
    check("a trap naming two registers asks for them jointly",
          ir_._trap_joints(two, {12: {1, 2, 3}, 173: {0, 1}}) == [(12, 173)],
          repr(ir_._trap_joints(two, {12: {1, 2, 3}, 173: {0, 1}})))
    check("...and a trap naming one register (or none) asks for nothing",
          ir_._trap_joints(one, {173: {0, 1}}) == [], repr(ir_._trap_joints(one, {173: {0, 1}})))
    check("...and an oversized product is refused",
          ir_._trap_joints(two, {12: set(range(500)), 173: set(range(50))}) == [])

# ---- Part 3: fall-through hack removed (no free start bypass) ------------
def test_no_fallthrough_bypass():
    print("Part 3: start-state fall-through hack removed")
    em = real_em()
    if em is None:
        print("  [SKIP] LSL2 IR not present"); return
    # (a) setScript capture means NO machine is stranded (absent start + no entries)
    stranded = [(i["room"], i["inst"]) for i in em.machines
                if i["states"] and i["start"] not in set(i["states"]) and not i["entries"]]
    check("no machine stranded (absent start + no entries)", not stranded, str(stranded))
    # (b) the SMV must NOT contain a free `ms = <start> : <start+1>` bypass for rm63's jump
    smv, _ = em.emit()
    import re
    # rm63Script start is 0; a bypass would be `... ms_63_rm63Script = 0 : 1` with NO guard
    bad = re.findall(r"action = \d+ & room = 63 & ms_63_rm63Script = 0 : 1;", smv)
    check("no free start fall-through for rm63 jump machine", not bad, str(bad[:2]))

# ---- Part 5: disguise gate (now the control-map oracle, not the old doit-death heuristic) --
def _ctr_vars(g, out):
    if isinstance(g, tuple) and g and g[0] == "CTR": out.add(g[1])
    elif isinstance(g, (GAnd, GOr)):
        for k in g.kids: _ctr_vars(k, out)
    elif isinstance(g, GNot): _ctr_vars(g.kid, out)

def test_disguise():
    print("Part 5: disguise gate via the control-map oracle (rm47 crossing)")
    em = real_em()
    if em is None:
        print("  [SKIP] LSL2 IR not present"); return
    # the disguise gate now comes from the oracle's PROVEN crossing-gate (control_oracle),
    # replacing the removed _doit_death_gates heuristic. See test_control_oracle.py for depth.
    xr = {g["room"] for g in em.control_gates if g.get("kind") == "crossing"}
    check("rm47 has an oracle crossing-gate", 47 in xr, str(sorted(xr)))
    # only the win-ward exit (->48) is gated, on henchStatus (L2); the retreat (->42) is FREE
    e48 = [e for e in em.ts.edges if e.src == 47 and e.dst == 48]
    check("rm47->48 exit is gated (not free)", e48 and e48[0].guard is not None)
    if e48 and e48[0].guard is not None:
        # the gate is now the derived disguise condition (gBodyWaxed & egoView==151), which
        # makes the bikini items required -- egoView==151 is item-gated via the bikini chain
        g48 = repr(e48[0].guard).replace(" ", "")
        check("rm47->48 gate is the disguise condition (egoView==151)", "102==151" in g48, g48)
    e42 = [e for e in em.ts.edges if e.src == 47 and e.dst == 42]
    check("rm47->42 retreat is NOT over-gated (free, unlike old _doit_death_gates)",
          e42 and e42[0].guard is None, repr(e42[0].guard) if e42 else "no edge")

# ---- Part 6: consistent positional model --------------------------------
def test_positions():
    print("Part 6: consistent position (x,y) instead of independent opaques")
    from extract import atom
    r = atom(SEND(V("Global", 0), MSG("inRect", N(86), N(2), N(333), N(140))))
    check("atom(inRect a b c d) -> POS rect", r == ("POS", "rect", (86, 2, 333, 140)), repr(r))
    e = atom(CMP("Eq", N(2), SEND(V("Global", 0), MSG("edgeHit"))))
    check("atom(edgeHit==2) -> POS edge", e == ("POS", "edge", 2), repr(e))
    em = real_em()
    if em is None:
        print("  [SKIP] LSL2 IR not present"); return
    smv, _ = em.emit()
    check("posx/posy declared as IVARs", "posx : 0 .. 319;" in smv and "posy : 0 .. 189;" in smv)
    check("positional guards render (posx/posy used)", smv.count("posx") + smv.count("posy") > 20)
    # consistency: east-edge crossing (posx>=316) and the rect [86,333] share posx, so a
    # crossing can't dodge the rect -- verify both render over the SAME posx.
    check("edge-east renders as posx>=316", "posx >= 316" in smv)

def run():
    print("=== test_everything ===")
    test_local_compare()
    test_local_compare_real()
    test_setscript()
    test_no_fallthrough_bypass()
    test_disguise()
    test_positions()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
