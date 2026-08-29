"""Unit tests for the three model-reduction / fidelity transforms, in ISOLATION:
  - compile.carry_cues        (SCI cross-state cue carry: PARK -> ADVANCE where covered)
  - compile.compress_chains   (collapse effect-free ADVANCE runs)
  - opmodel opaque elimination (existentially project unresolvable guards out; ~0 free bools)

These pin the transforms we WROTE (right output for a given input). They do NOT and cannot
find a MISSED abstraction (an unmodeled construct) -- that shows up only as end-to-end
divergence (the winnability run / the missability sweep). See docs/ARCHITECTURE.md.
"""
import sys
import compile as C
import opmodel as E
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

    # ...and a carried cue does NOT revive a script that disposed itself. The END still counts
    # for the surplus arithmetic (it arms nothing, so it spends one like a PARK does).
    sbs = {0: [_step(("ADVANCE",), cues=3)], 1: [_step(("END",))], 2: [_step(("PARK",))],
           3: [_step(("PARK",))]}
    C.carry_cues(sbs, 0)
    check("a carried cue does NOT flip an END back to ADVANCE", sbs[1][0].trans == ("END",))
    check("...and the surplus it spends is still counted (one park after, not two)",
          sbs[2][0].trans == ("ADVANCE",) and sbs[3][0].trans == ("PARK",))


def _send(recv, sel, params=()):
    return {"t": "Send", "kids": [recv, {"t": "SendMessage",
                                         "kids": [{"t": "Selector", "name": sel}] + list(params)}]}


def test_ends_script():
    """`(self dispose:)` / `(client setScript: 0)` -- the two spellings of "this script is over".

    A PARK meant both "waiting for a cue" and "gone", and `state_musts` needs them apart: it
    crosses the first and stops at the second (GK1 rm270's knockOnDoor -- state 7 waits on a
    `doVerb:` conversation, state 5's day-4 branch disposes)."""
    print("test_ends_script")
    SELF, CLIENT = {"t": "Self"}, {"t": "Property", "name": "client"}
    OTHER = {"t": "Object", "name": "egoHead"}
    GROOM = {"t": "Variable", "vtype": "Global", "index": 2}
    NUM0, NUM5 = {"t": "Number", "value": 0}, {"t": "Number", "value": 5}
    HOSTS = frozenset({("G", 2)})              # armed by `(global2 setScript: thisMachine ...)`
    check("(self dispose:) ends the script", C._ends_script(SELF, "dispose", []))
    check("(egoHead dispose:) does NOT -- that is another object",
          not C._ends_script(OTHER, "dispose", []))
    check("(client setScript: 0) ends the script", C._ends_script(CLIENT, "setScript", [NUM0]))
    check("(client setScript: 5) ends it too -- the slot is handed to another Script",
          C._ends_script(CLIENT, "setScript", [NUM5]))
    check("(egoHead setScript: 0) does NOT -- not a slot this machine runs in",
          not C._ends_script(OTHER, "setScript", [NUM0], HOSTS))
    # ⭐ KQ6's minotaur: the host's own name. Without `hosts` this reads as somebody else's
    # script and the gored branch walks on into the survivor's states.
    check("(global2 setScript: X) ends a machine ARMED into global2",
          C._ends_script(GROOM, "setScript", [OTHER, NUM0], HOSTS))
    check("...and does not end one armed somewhere else",
          not C._ends_script(GROOM, "setScript", [OTHER, NUM0], frozenset({("G", 0)})))
    check("a bare `(x setScript:)` READS the slot and ends nothing",
          not C._ends_script(GROOM, "setScript", [], HOSTS))

    # ⭐ THE TWIN RULE. `_records` decides what `_paths_of` hands `_interp` at all, so an
    # interpreter that reads a node `_records` rejects reads nothing: measured on a full GK1
    # rebuild, knockOnDoor's two disposing states stayed PARK until this line agreed.
    check("_records keeps a disposing send (or _interp never sees it)",
          C._records(_send(SELF, "dispose")))
    check("_records keeps (client setScript: 0)", C._records(_send(CLIENT, "setScript", [NUM0])))
    check("_records keeps a host setScript ONLY with the same hosts _interp gets",
          C._records(_send(GROOM, "setScript", [OTHER, NUM0]), HOSTS)
          and not C._records(_send(GROOM, "setScript", [OTHER, NUM0])))
    # ...and the hosts reach `_records` through the memo `_paths_of` seeds.
    body = {"t": "Send", "kids": _send(GROOM, "setScript", [OTHER, NUM0])["kids"]}
    check("_paths_of carries the hosts into the enumeration",
          C._paths_of(body, hosts=HOSTS) == [[("D", body)]] and C._paths_of(body) == [[]])

    # ...and end to end through the interpreter.
    st = C._interp([("D", _send(SELF, "dispose"))], lambda *a: False, state_k=0)
    check("a disposing path compiles to END", st.trans == ("END",))
    st = C._interp([("D", _send(OTHER, "dispose"))], lambda *a: False, state_k=0)
    check("a path disposing something else still PARKs", st.trans == ("PARK",))
    st = C._interp([("D", _send(GROOM, "setScript", [OTHER, NUM0]))], lambda *a: False,
                   state_k=0, hosts=HOSTS)
    check("handing this machine's own slot away compiles to END", st.trans == ("END",))
    # a path that ARMS a cue and also disposes keeps its ADVANCE: dropping a fall-through is the
    # tight direction and nothing has measured that case (see `_interp`).
    st = C._interp([("D", _send({"t": "Object", "name": "madam"}, "setCycle",
                                [{"t": "Object", "name": "End"}, SELF])),
                    ("D", _send(SELF, "dispose"))], lambda *a: False, state_k=0)
    check("arming a cue wins over disposing (permissive)", st.trans == ("ADVANCE",))


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
    test_ends_script()
    test_compress_chains()
    test_opaque_elimination()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
