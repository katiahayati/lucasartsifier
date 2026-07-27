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
