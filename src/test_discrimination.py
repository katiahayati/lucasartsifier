"""`compile._paths_of` may only skip a fan-out that CANNOT CHANGE A STEP.

The rule (see `compile._records`' block comment): enumerating paths through a subtree is worth
its cost only where two paths can produce different `Step`s, and `_interp` is the authority on
which nodes can do that. A subtree recording none of them yields the same Step on every path,
differing only in `Pred("OPAQUE")` conjuncts, so one path stands for all of them.

That is a soundness claim about an optimisation, and it has exactly two failure modes:

  1. `_records` FALLS BEHIND `_interp`. A case the interpreter grows and the mirror does not
     reads as invisible, so the branch that decides it stops being enumerated and a real
     distinction is silently lost. `test_walkers.py` cannot see this -- it compares walkers
     across FILES and these two are one file -- so the pairing is checked here, from the source,
     the same way `test_walkers` derives its matrix rather than listing it.

  2. the rule COLLAPSES SOMETHING THAT MATTERS. Pinned two ways: fixtures for the shapes that
     must survive (below), and a full differential against a NAIVE enumerator carried in this
     file, over every machine state body of two real games. The naive one is the oracle -- it is
     what `_paths_of` was before the rule -- and the assertion is that the ruled enumeration
     yields the same set of Step EFFECTS and the same `_has_opaque` answer.

⭐ The KQ5 near-miss is fixture-pinned below (`ctr_test_survives`). A first version of
`_readable` asked `atom(test)` instead of `_ctr_or(test, pol, atom(test))`, which reads right
and is wrong: `_ctr_or` lowers a Local/Temp-vs-literal comparison to a ("CTR", ...) atom the
machine walk resolves concretely, and those are the machine-internal latches. It cost KQ5 its
entire market squeeze -- the Golden_Needle / Gold_Coin `starves rm[5, 9, 13]` rows and the
getSled / getPie sinks -- and no fixture then existed to say so.

Run: python3 test_discrimination.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ir as I
import compile as C
import config
import machine as M
import missability as MS

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------- 1. the pairing
def _body_of(func_name, text):
    """Source of one top-level `def`, up to the next top-level `def`."""
    m = re.search(r"^def %s\(.*?(?=^def )" % re.escape(func_name), text, re.M | re.S)
    return m.group(0) if m else ""


def _node_types(body):
    """Every IR node-type literal this source dispatches on: `tp == "X"`, `t == "X"`,
    `tp in ("X", "Y")`. Same derivation shape as test_walkers' matrix -- read the source, do
    not keep a list, because a list is the bug this is looking for."""
    out = set()
    for m in re.finditer(r'\b(?:tp|t)\s*==\s*"([A-Za-z_]+)"', body):
        out.add(m.group(1))
    for m in re.finditer(r'\b(?:tp|t)\s+in\s+\(([^)]*)\)', body):
        out.update(re.findall(r'"([A-Za-z_]+)"', m.group(1)))
    return out


def pairing():
    text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "compile.py")).read()
    interp = _node_types(_body_of("_interp", text))
    records = _node_types(_body_of("_records", text))
    check("interp_cases_found", len(interp) >= 5, f"parsed {sorted(interp)}")
    missing = interp - records
    check("records_mirrors_interp", not missing,
          "node types `_interp` records and `_records` does not name: %s -- a branch deciding "
          "one of these would stop being enumerated" % sorted(missing))
    # The mirror may be WIDER (conservative) but every extra must still be a type _interp could
    # meet; flag a stray so the pair cannot drift the other way unnoticed either.
    check("records_names_nothing_alien", not (records - interp - {"Self"}),
          f"named only by _records: {sorted(records - interp - {'Self'})}")


# --------------------------------------------------------------------------- 2. fixtures
def _num(v):
    return {"t": "Number", "value": v, "kids": []}


def _var(vtype, idx):
    return {"t": "Variable", "vtype": vtype, "index": idx, "kids": []}


def _prop(name):
    return {"t": "Property", "name": name, "kids": []}


def _eq(a, b):
    return {"t": "Eq", "kids": [a, b]}


def _if(test, then, els=None):
    return {"t": "If", "kids": [test, then] + ([els] if els is not None else [])}


def _lst(*kids):
    return {"t": "List", "kids": list(kids)}


def _send(recv, sel, *params):
    return {"t": "Send", "kids": [recv, {"t": "SendMessage",
                                         "kids": [{"t": "Selector", "name": sel}] + list(params)}]}


def _opaque_send(n=0):
    """A send nothing models: a Print with a literal. Records nothing, asserts nothing."""
    return _send({"t": "Object", "name": "Print%d" % n, "kids": []}, "say", _num(n))


def _opaque_test(n=0):
    """A comparison `_interp` can only lower to OPAQUE: a property against a literal."""
    return _eq(_prop("cel%d" % n), _num(n))


def fixtures():
    # (a) a branch over unreadable tests with no recorded effect -> ONE path, still opaque
    dead = _if(_opaque_test(1), _opaque_send(1), _opaque_send(2))
    paths = C._paths_of(dead)
    check("opaque_branch_collapses", len(paths) == 1, f"got {len(paths)} paths")
    st = C._interp(paths[0], lambda gi, v: False, state_k=0)
    check("collapsed_keeps_an_opaque", MS._has_opaque(C._conj(st.guard)),
          "the collapsed path must still carry an opaque, or `_has_opaque` changes answer")
    check("collapsed_has_no_effects", not C.step_effects(st) and st.trans[0] == "PARK")

    # (b) three nested opaque branches: 8 paths without the rule, still 1 with it
    nest = _lst(_if(_opaque_test(1), _opaque_send(1), _opaque_send(2)),
                _if(_opaque_test(2), _opaque_send(3), _opaque_send(4)),
                _if(_opaque_test(3), _opaque_send(5), _opaque_send(6)))
    check("opaque_product_collapses", len(C._paths_of(nest)) == 1,
          f"got {len(C._paths_of(nest))}")

    # (c) an EXIT inside must survive -- the whole point of enumerating
    live = _if(_opaque_test(1),
               _send({"t": "Object", "name": "gCurRoom", "kids": []}, "newRoom", _num(42)),
               _opaque_send(2))
    ps = C._paths_of(live)
    check("exit_branch_survives", len(ps) == 2, f"got {len(ps)} paths")
    trans = {C._interp(p, lambda gi, v: False, state_k=0).trans for p in ps}
    check("exit_reaches_interp", ("EXIT", 42) in trans, f"got {trans}")

    # (d) a register write inside must survive
    wr = _if(_opaque_test(1),
             {"t": "Assignment", "kids": [_var("Global", 101), _num(7)]},
             _opaque_send(2))
    check("global_write_survives", len(C._paths_of(wr)) == 2)

    # (e) ⭐ THE KQ5 NEAR-MISS. The test is a LOCAL vs a literal, which `atom()` alone cannot
    # read but `_ctr_or` lowers to a CTR the machine walk resolves concretely. Collapsing it
    # cost KQ5 its market squeeze.
    ctr = _if(_eq(_var("Local", 3), _num(2)), _opaque_send(1), _opaque_send(2))
    check("ctr_test_survives", len(C._paths_of(ctr)) == 2,
          "a Local-vs-literal test is a CTR atom, not an opaque one")
    ctr_t = _if(_eq(_var("Temp", 1), _num(5)), _opaque_send(1), _opaque_send(2))
    check("ctr_temp_test_survives", len(C._paths_of(ctr_t)) == 2)

    # (f) a readable test -- an own() / register comparison -- must survive too
    reg = _if(_eq(_var("Global", 101), _num(3)), _opaque_send(1), _opaque_send(2))
    check("register_test_survives", len(C._paths_of(reg)) == 2)

    # (g) a cue arm is an effect: `(= seconds 5)` ADVANCEs the machine
    cue = _if(_opaque_test(1),
              {"t": "Assignment", "kids": [_prop("seconds"), _num(5)]},
              _opaque_send(2))
    check("cue_arm_survives", len(C._paths_of(cue)) == 2)


# --------------------------------------------------------------- 3. differential vs the naive
def _naive_paths(node):
    """`_paths_of` WITHOUT the rule -- the oracle. Kept here, not imported, precisely so the
    optimisation cannot silently become its own reference."""
    if node is None:
        return [[]]
    shape = I.control_shape(node)
    kind = shape[0]
    if kind == "seq":
        res = [[]]
        for f in shape[1]:
            nxt = []
            for pre in res:
                for sub in _naive_paths(f):
                    nxt.append(pre + sub)
            res = nxt
            if len(res) > C.PATH_CAP:
                break
        return res
    if kind == "branch":
        out = []
        for conds, body in shape[1]:
            prefix = [("T", t, pol) for (t, pol) in conds]
            for p in _naive_paths(body):
                out.append(prefix + p)
        return out or [[]]
    if kind == "loop":
        init, incr, body = shape[1], shape[3], shape[4]
        if body is None:
            return _naive_paths(_lst(init))
        return _naive_paths(_lst(init)) + _naive_paths(_lst(init, body, incr))
    return [[("D", node)]]


def _sig(st):
    """Everything `_interp` RECORDED -- i.e. everything downstream can tell apart, minus the
    opaque conjuncts the rule is allowed to fold."""
    return (st.trans, tuple(sorted(st.writes)), tuple(sorted(st.gets)),
            tuple(sorted(st.drops)), tuple(sorted(st.moves)), st.cues,
            tuple(sorted(map(repr, st.counters))), tuple(sorted(map(repr, st.gincs))),
            st.vexit)


def differential(name, cfg):
    """Every machine state body of a real game: ruled vs naive, same Step effects."""
    ir = I.load_ir(cfg.ir_path)
    mb = M.MachineBuilder(ir, lambda gi, v: False)
    mb.derive_room_valued()
    mb.prime()
    bodies = []
    for _sn, sc in ir.scripts.items():
        for m in mb.machines(sc):
            bodies.extend((m.script, m.inst, K, b) for K, b in (m.bodies or {}).items())
    bad_sig, bad_opq, n_naive, n_ruled = [], [], 0, 0
    for sn, inst, K, body in bodies:
        naive = _naive_paths(body)
        ruled = C._paths_of(body)
        n_naive += len(naive)
        n_ruled += len(ruled)
        died = lambda gi, v: False
        sn_ = {_sig(C._interp(p, died, state_k=K)) for p in naive}
        sr_ = {_sig(C._interp(p, died, state_k=K)) for p in ruled}
        if sn_ != sr_:
            bad_sig.append((sn, inst, K, sorted(sn_ ^ sr_)[:1]))
        on_ = any(MS._has_opaque(C._conj(C._interp(p, died, state_k=K).guard)) for p in naive)
        or_ = any(MS._has_opaque(C._conj(C._interp(p, died, state_k=K).guard)) for p in ruled)
        if on_ != or_:
            bad_opq.append((sn, inst, K, on_, or_))
    check(f"{name}_effects_preserved", not bad_sig,
          f"{len(bad_sig)} of {len(bodies)} bodies changed Step effects, e.g. {bad_sig[:2]}")
    check(f"{name}_opaque_preserved", not bad_opq,
          f"{len(bad_opq)} bodies changed their `_has_opaque` answer, e.g. {bad_opq[:2]}")
    check(f"{name}_actually_collapses", n_ruled < n_naive,
          f"the rule saved nothing on {name}: {n_naive} -> {n_ruled} paths")
    print(f"      ({name}: {len(bodies)} bodies, {n_naive} naive paths -> {n_ruled} ruled)")


def run():
    print("compile._paths_of discrimination rule")
    pairing()
    fixtures()
    differential("lsl2", config.LSL2)
    differential("kq4", config.KQ4)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(run())
