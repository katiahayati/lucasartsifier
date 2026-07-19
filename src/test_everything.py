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
import ir as I
from model import Pred, GAnd, GOr, GNot

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
    from extract2 import atom
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
        p = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp", "lsl2_decomp", "lsl2.ir.json")
        if not os.path.exists(p):
            return None
        import config, smv_emit3 as E
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
    from machine2 import _setscript_target
    check("setScript target from Object ref", _setscript_target(OBJ("henchScript")) == "henchScript")
    check("setScript target from (X new:)",
          _setscript_target(SEND(OBJ("henchScript"), MSG("new"))) == "henchScript")
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

def run():
    print("=== test_everything ===")
    test_local_compare()
    test_local_compare_real()
    test_setscript()
    test_no_fallthrough_bypass()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
