"""Apply §1.34: an incremented global with no script-local literal domain falls back to the
GAME-WIDE literal range (bounded 64), each fanned branch an ordered step k -> k+delta."""
p='src/machine.py'; s=open(p).read()
old='def _glob_domains(script):\n    """{global: sorted values} for globals this script uses as a COUNTER.\n'
assert s.count(old)==1
new='''_GAME_LITERALS = {}         # id(ir) -> {global: (min, max)} over every literal the game compares
#                              or assigns the global against
RANGE_CAP = 64              # the joints' cap precedent: a resource bound, never a game rule


def _game_literal_range(ir):
    """{global: (lo, hi)} -- every literal ANY script compares a global against (`==`/`!=`/a
    switch case) or assigns to it (`(= G lit)`). The one-scope-wider reading `_glob_domains`
    falls back to (GK1 docs §1.34)."""
    key = id(ir)
    got = _GAME_LITERALS.get(key)
    if got is not None:
        return got
    lits = {}
    for sc in ir.scripts.values():
        bodies = [a for o in sc.objects for a in o.methods.values()]
        bodies += list((getattr(sc, "procs", None) or {}).values())
        for ast in bodies:
            for n in I.walk(ast):
                tp = n.get("t")
                ks = n.get("kids") or []
                if tp == "Switch" and ks and I.is_global(ks[0]):
                    for c in ks[1:]:
                        if c.get("t") == "Case" and c.get("kids"):
                            v = I.as_int(c["kids"][0])
                            if v is not None:
                                lits.setdefault(ks[0]["index"], set()).add(v)
                elif tp in ("Eq", "Ne") and len(ks) == 2:
                    for x, y in ((ks[0], ks[1]), (ks[1], ks[0])):
                        if I.is_global(x) and I.as_int(y) is not None:
                            lits.setdefault(x["index"], set()).add(I.as_int(y))
                elif tp == "Assignment" and len(ks) == 2 and I.is_global(ks[0]) \\
                        and I.as_int(ks[1]) is not None:
                    lits.setdefault(ks[0]["index"], set()).add(I.as_int(ks[1]))
    got = _GAME_LITERALS[key] = {gi: (min(vs), max(vs)) for gi, vs in lits.items()}
    return got


def _glob_domains(script, ir=None):
    """{global: sorted values} for globals this script uses as a COUNTER.

    ⭐ THE GAME-WIDE FALLBACK (2026-09-03, GK1 docs §1.34). A script that increments a global
    it never compares yielded {} and the increment was DROPPED -- "unknown domain, never
    guess". GK1's day is advanced in rm370 (which compares it, so those steps fanned) AND in
    the bayou ritual (rm480), Germany's departure (rm500) and the dream (rm550), none of
    which compares the day: days 6 -> 7 -> 8 -> 9 vanished from the model and the endgame
    stayed reachable only through rm750's `(= day 9)` clamp. The fallback reads the literals
    the code tests the global against ONE SCOPE WIDER -- every integer between the smallest
    and the largest literal the whole game compares or assigns it against -- and each fanned
    branch stays an ORDERED step `k -> k+delta` (the permissive direction is an ordered step,
    never a free write). Bounded at `RANGE_CAP` values, the joints' cap precedent: past it the
    increment is dropped exactly as before (KQ5's scores, ranges of 122-201 values, stay out).
    Static blast radius (incremented globals with an empty local domain): LSL2 9 sites, KQ4 9,
    KQ6 1, KQ5 8, LB2 10, GK1 3.
'''
s=s.replace(old,new)
old='''    return {gi: sorted(vs) for gi, vs in vals.items() if gi in incs}
'''
assert s.count(old)==1
new='''    out = {gi: sorted(vs) for gi, vs in vals.items() if gi in incs}
    if ir is not None:
        rng = _game_literal_range(ir)
        for gi in incs:
            if gi in out or gi not in rng:
                continue
            lo, hi = rng[gi]
            if hi - lo + 1 <= RANGE_CAP:
                out[gi] = list(range(lo, hi + 1))
    return out
'''
s=s.replace(old,new)
old='        m.glob_dom = _glob_domains(script)\n'
assert s.count(old)==1
s=s.replace(old,'        m.glob_dom = _glob_domains(script, self.ir)\n')
open(p,'w').write(s); print("134 applied")
