"""Every flag-shaped bit store is lowered, not only the most common one (2026-09-03, GK1 §1.42).

GK1 keeps TWO word-arrays in the flag idiom: its flags (base global 127) and the conversation
system's TOPIC-SAID array (base 182): `proc50_5` tests "topic N asked", `proc50_6` tests AND sets
it (returning what it found), `proc50_7` tests and clears, `proc50_8` tests the negation. Every
Teller's "second time you ask" and every topic offered "iff not yet asked" reads through it, and
`derive_flags` kept only the most common base, so all 435 sites were opaque -- R4's wall and the
once-only go-home phantom both live there.

The read-back writer is rewritten EXACTLY where its value is used: as the test of an `if` /
`cond` arm the test reads the OLD bit and the set heads every arm that runs after the test; as
a bare statement it is the set. Census: 233 + 77 of the 312 `proc50_6` sites; the 2 nested in
an `or` lower as plain sets (the write matters, the read stays opaque there).

✅ PROMOTED 2026-09-05: the PRIMARY store's set proc returns the bit too and the games use it as
a test -- KQ6 **22** sites (the note said 24; measured, it is 22), LB2 8, GK1 3 -- so the same
rewrite is ON for it now. The USER set the criterion before the measurement: fine if it only
makes a flag visible, a BUG if it changes a finding. Full gate on the box says it changes
NOTHING -- KQ6's golden shows byte-for-byte its two already-declared lines and no others, its
oracle is 19/0, LB2's oracle shows exactly its six declared pins, LB2's watched surface is
unmoved, and every emitted tree is unchanged. The capture is real (KQ6 flag 90: empty domain ->
`[0, 1]`); these are score-once latches gating POINTS and NARRATION, so nothing's reachability
turns on them. Runs on the cached GK1 model + two fresh IRs."""
import sys

import config
import ir as I
import missability as M
import vocab as V

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def _calls(ir, names):
    out = []
    for sn, sc in ir.scripts.items():
        for o in sc.objects:
            for mn, ast in o.methods.items():
                for n in I.walk(ast):
                    if n.get("t") in ("PublicCall", "LocalCall") and n.get("name") in names \
                            and I.as_int((n.get("kids") or [None])[0]) is not None:
                        out.append((sn, o.name, mn))
    return out


def main():
    print("=== test_topic_store: every bit-array store is lowered ===")
    cfg = config.by_name("gk1")
    fresh = I.load_ir(cfg.ir_path)
    fl = V.derive_flags(fresh)
    check("GK1 derives TWO stores: the flags (127) and the topic-said array (182)",
          fl is not None and fl[0] == 127 and [b for b, _p in fl[3]] == [182], f"got {fl and (fl[0], [b for b, _p in fl[3]])}")
    topic = dict(fl[3])[182] if fl and dict(fl[3]).get(182) else {}
    check("the topic store's ops: test / test-and-set / test-and-clear / not-test",
          topic == {"proc50_5": "test", "proc50_6": "tset", "proc50_7": "tclear", "proc50_8": "ntest"},
          f"got {topic}")
    for g in ("KQ6", "dagger"):
        cfg2 = getattr(config, g, None) or config.by_name(g)
        fl2 = V.derive_flags(I.load_ir(cfg2.ir_path))
        check(f"{g} derives exactly ONE store (the census: no other game has two)",
              fl2 is not None and fl2[3] == [], f"got extra {fl2 and fl2[3]}")

    # -- the lowered model ---------------------------------------------------------------------
    s = M.load(cfg=cfg)
    ir = s.em.ir
    stores = getattr(ir, "extra_flag_stores", None) or []
    check("the build lowered the topic store to its own synthetic block", len(stores) == 1
          and stores[0]["global"] == 182 and stores[0]["base"] > getattr(ir, "flag_synth_base", 0),
          f"got {[(st['global'], st['base']) for st in stores]}")
    left = _calls(ir, {"proc50_5", "proc50_8"})
    check("no literal test / not-test of the topic store survives the lowering", not left, f"left {left[:5]}")
    left6 = _calls(ir, {"proc50_6"})
    check("at most the 2 or-nested test-and-set calls survive (lowered as plain sets by the fallback "
          "-- they are rewritten in place, so none should remain as calls)", len(left6) <= 2, f"left {left6[:6]}")
    # the exact rewrite at a known site: grace::cue `(if (proc50_6 13) (++ iconValue))`
    grace = ir.scripts[1050].by_name.get("grace")
    ok = False
    if grace is not None and "cue" in grace.methods:
        for n in I.walk(grace.methods["cue"]):
            if n.get("t") == "If" and I.is_global((n.get("kids") or [None])[0]):
                g = n["kids"][0]["index"]
                arms = n["kids"][1:]
                heads = [a.get("kids", [None])[0] for a in arms if isinstance(a, dict) and a.get("t") == "List"]
                if len(arms) == 2 and all(isinstance(h, dict) and h.get("t") == "Assignment"
                                          and I.is_global(h["kids"][0]) and h["kids"][0]["index"] == g
                                          for h in heads):
                    ok = True
                    break
    check("a `(if (proc50_6 N) ...)` site reads the OLD bit and sets it at the head of BOTH arms", ok)
    tb = stores[0]["base"] if stores else None
    check("the topic registers are modeled (reg_dom on a lowered topic bit)",
          tb is not None and any(gi in s.em.reg_dom for gi in range(tb, tb + 200)),
          f"base {tb}")
    import guards as G
    r = G.render_register(s, tb + 13, 1) if tb is not None else None
    check("a topic register renders back in the game's spelling", r == "(proc50_5 13)", f"got {r!r}")

    # -- the declared red: the primary store's read-back writers used as tests -----------------
    kq6 = I.load_ir(config.KQ6.ir_path)
    fk = V.derive_flags(kq6)
    n_tests = 0
    if fk:
        setters = {n for n, op in fk[1].items() if op in ("set", "clear", "tset", "tclear")}
        for sc in kq6.scripts.values():
            for o in sc.objects:
                for ast in o.methods.values():
                    for n in I.walk(ast):
                        if n.get("t") == "If" and n.get("kids"):
                            t = n["kids"][0]
                            k = (t.get("kids") or [None])[0] if isinstance(t, dict) and t.get("t") == "Not" else t
                            if isinstance(k, dict) and k.get("t") in ("PublicCall", "LocalCall") and k.get("name") in setters:
                                n_tests += 1
    check("KQ6's primary-store set/clear calls in test position are read as test-and-set "
          "(the exact rewrite is ON for the primary store)",
          fk is not None and n_tests > 0 and any(op in ("tset", "tclear") for op in fk[1].values()),
          f"{n_tests} test-position set/clear calls on KQ6; ops = {fk and sorted(set(fk[1].values()))} -- "
          f"bless-gated: capturing them moves the KQ6/LB2 surfaces")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
