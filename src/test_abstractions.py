"""Unit tests for the three model-reduction / fidelity transforms, in ISOLATION:
  - compile2.carry_cues        (SCI cross-state cue carry: PARK -> ADVANCE where covered)
  - compile2.compress_chains   (collapse effect-free ADVANCE runs)
  - smv_emit3 opaque elimination (existentially project unresolvable guards out; ~0 free bools)

These pin the transforms we WROTE (right output for a given input). They do NOT and cannot
find a MISSED abstraction (an unmodeled construct) -- that shows up only as end-to-end
divergence (the winnability run / the missability sweep). See docs/ARCHITECTURE.md.
"""
import sys
import compile2 as C
import smv_emit3 as E
from guard_ast import GAnd, GOr, GNot

PASS, FAIL = [], []
def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def _step(trans, cues=0, guard=None, writes=None, gets=None, counters=None):
    s = C.Step()
    s.trans, s.cues = trans, cues
    s.guard = guard or []
    s.writes = writes or []
    s.gets = gets or []
    s.counters = counters or []
    return s


def test_carry_cues():
    print("test_carry_cues")
    # s0 arms 2 cues -> the carried cue flips the Print-only PARK at s1 to ADVANCE (rm84/s79),
    # while the lone single-cue s2 leaves 0 surplus so the s3 PARK stays parked.
    sbs = {0: [_step(("ADVANCE",), cues=2)], 1: [_step(("PARK",))],
           2: [_step(("ADVANCE",), cues=1)], 3: [_step(("PARK",))]}
    C.carry_cues(sbs, 0)
    check("2-cue state flips the following PARK to ADVANCE", sbs[1][0].trans == ("ADVANCE",))
    check("single-cue state leaves no surplus (downstream PARK stays)", sbs[3][0].trans == ("PARK",))

    # a lone single-cue advance never flips the next park (the conservative guarantee)
    sbs = {0: [_step(("ADVANCE",), cues=1)], 1: [_step(("PARK",))]}
    C.carry_cues(sbs, 0)
    check("lone single cue does NOT flip a park", sbs[1][0].trans == ("PARK",))

    # 3 cues -> surplus carries through TWO parks, then exhausts
    sbs = {0: [_step(("ADVANCE",), cues=3)], 1: [_step(("PARK",))],
           2: [_step(("PARK",))], 3: [_step(("PARK",))]}
    C.carry_cues(sbs, 0)
    check("3 cues flip the next two parks", sbs[1][0].trans == ("ADVANCE",) and sbs[2][0].trans == ("ADVANCE",))
    check("surplus exhausts (third park stays)", sbs[3][0].trans == ("PARK",))

    # an EXIT breaks the spine: surplus does not leap a terminal transition
    sbs = {0: [_step(("ADVANCE",), cues=3)], 1: [_step(("EXIT", 9))], 2: [_step(("PARK",))]}
    C.carry_cues(sbs, 0)
    check("surplus does not carry past an EXIT-only state", sbs[2][0].trans == ("PARK",))


def test_compress_chains():
    print("test_compress_chains")
    # 0..4 effect-free ADVANCE, 5 EXIT -> transitions into the run skip to 5.
    sbs = {k: [_step(("ADVANCE",))] for k in range(5)}
    sbs[5] = [_step(("EXIT", 99))]
    C.compress_chains(sbs, set(), 0)
    check("effect-free run redirects to the first non-transparent state", sbs[0][0].trans == ("JUMP", 5))

    # a state with a WRITE is opaque to compression (its effect must run)
    sbs = {0: [_step(("ADVANCE",))], 1: [_step(("ADVANCE",), writes=[(148, 100)])], 2: [_step(("EXIT", 9))]}
    C.compress_chains(sbs, set(), 0)
    check("a state with a write is NOT skipped", sbs[0][0].trans == ("ADVANCE",))

    # an entry-target state is not skipped (a re-entry may land there)
    sbs = {0: [_step(("ADVANCE",))], 1: [_step(("ADVANCE",))], 2: [_step(("EXIT", 9))]}
    C.compress_chains(sbs, {1}, 0)
    check("an entry-target state is NOT skipped", sbs[0][0].trans == ("ADVANCE",))

    # a guarded (branching) state is not transparent (single-path only)
    sbs = {0: [_step(("ADVANCE",))],
           1: [_step(("ADVANCE",), guard=["g"]), _step(("ADVANCE",), guard=["!g"])],
           2: [_step(("EXIT", 9))]}
    C.compress_chains(sbs, set(), 0)
    check("a branching state is NOT skipped", sbs[0][0].trans == ("ADVANCE",))


def test_opaque_elimination():
    print("test_opaque_elimination")
    em = E.OpEmitter.__new__(E.OpEmitter)      # bypass heavy __init__; set only what gexpr reads
    em.loc_dom = {(1, "L", 0): (0, 3)}
    em.loc_const, em.reg_dom, em.reg_const = {}, {}, {}
    em.n_opaque = 0
    g = lambda tree: em.gexpr(tree, 1)
    R = ("CTR", ("L", 0), "==", 1)     # resolvable -> "c_1_L_0 = 1"
    O = ("CTR", ("L", 9), "==", 1)     # unresolvable (L9 not in loc_dom) -> OPAQUE

    check("real atom renders", g(R) == "c_1_L_0 = 1")
    check("opaque atom projects to TRUE", g(O) == "TRUE")
    check("real & opaque -> real (opaque dropped)", g(GAnd([R, O])) == "(c_1_L_0 = 1)")
    check("NOT(real & opaque) -> TRUE (else always available)", g(GNot(GAnd([R, O]))) == "TRUE")
    check("OR(opaque, opaque) -> TRUE", g(GOr([O, O])) == "TRUE")
    check("NOT(opaque) -> TRUE", g(GNot(O)) == "TRUE")
    check("NOT(OR(opaque,opaque)) via De Morgan -> TRUE", g(GNot(GOr([O, O]))) == "TRUE")
    check("real & NOT(real2 & opaque) -> real (else-part inert)",
          g(GAnd([R, GNot(GAnd([("CTR", ("L", 0), "==", 2), O]))])) == "(c_1_L_0 = 1)")
    check("zero opaque IVARs minted", em.n_opaque == 0)
    # differential: an opaque conjunct is INERT -- availability equals the real part alone
    check("opaque conjunct does not change availability", g(GAnd([R, O])) == "(" + g(R) + ")")


def run():
    print("=== test_abstractions ===")
    test_carry_cues()
    test_compress_chains()
    test_opaque_elimination()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
