"""Guard synthesis -- the 'prevent' half of the goal.

The condition a patch enforces is derived from the WINNING REGION, never from "this item is
mentioned nearby". That distinction is the whole reason `patch.py` is disabled: its syntactic
core could not tell a protective item from a lethal one, and it shipped a guard that FORCED the
fatal Spinach_Dip and ANDed two OR-alternatives, making LSL2 unwinnable.

The rule here:

    guard(gate) = OR over the HOPEFUL paths of that gate, of their path condition,
                  keeping item literals -- positive AND negative.

`hopeful` is the same goal-reachability predicate the TRAP rule uses (missability.hopeful): can
the goal still be reached after taking this path. So a branch that kills you, or that strands you
where the goal is gone, contributes nothing to the guard -- while a branch that survives
contributes exactly its own() requirements.

On LSL2's raft gauntlet (rm138, the edge the old patcher broke) the lift carries the full ordered
`cond`, negations included:

    DEATH   : own(8) &  own(13)                          <- dip kills you even holding a good item
    EXIT 42 : own(8) & !own(13) &  own(12)
    EXIT 42 : own(8) & !own(13) & !own(12) & own(11)
    DEATH   : own(8) & !own(13) & !own(12) & !own(11)

so the derived guard is `own(8) & !own(13) & (own(12) | own(11))` -- it FORBIDS the very item the
old patch REQUIRED. Same edge, opposite conclusion, because the rule is semantic.

This module only DERIVES and reports specs. It writes no game files.
"""
from __future__ import annotations

import sys

from collections import defaultdict

import missability as M


def own_literals(guard):
    """(positive, negative) item literals of a path condition.

    Path conditions out of a lifted `cond` are conjunctions, so a literal's polarity is its
    contribution. (A disjunction of own()s *inside* one path would not be conjunctive; none occur
    in LSL2's gates, and `survival_gates` reports alternatives separately anyway.)"""
    pos, neg = set(), set()
    def walk(g, pol):
        if g is None:
            return
        if isinstance(g, list):
            for x in g:
                walk(x, pol)
        elif isinstance(g, M.Pred):
            if g.kind == "OWN":
                (pos if pol else neg).add(g.var)
        elif isinstance(g, (M.GAnd, M.GOr)):
            for k in g.kids:
                walk(k, pol)
        elif isinstance(g, M.GNot):
            walk(g.kid, not pol)
    walk(guard, True)
    return pos, neg


def survival_gates(s):
    """Decision points where WHAT YOU CARRY decides whether the game stays winnable.

    A gate qualifies when at least one own()-guarded path is hopeful and at least one is not:
    that is precisely a point where the player can be sorted into winning and losing futures, so
    it is where a guard is worth placing. Gates with no losing path need no guard, and gates with
    no winning path are unwinnable regardless (reported separately, never patched)."""
    goal_ok = M.goal_reaching_rooms(s.edges, s.em.cfg.goal_rooms)
    out = []
    for info in s.em.machines:
        gr = M.goal_reaching(info, goal_ok)
        for K, paths in sorted(info["states"].items()):
            alts, doomed = [], []
            for (g, w, gg, c, tr) in paths:
                pos, neg = own_literals(g)
                if not (pos or neg):
                    continue
                (alts if M.hopeful(info, K, tr, gr, goal_ok) else doomed).append((pos, neg, tr))
            if alts and doomed:
                out.append({"room": info["room"], "state": K, "alts": alts, "doomed": doomed})
    return out


def absorb_ordering(alts):
    """Drop the negations an ordered `cond` leaves behind.

    A lifted `cond` gives alternative i the condition `ci & !c1 & ... & !c(i-1)`, so the Fruit
    branch reads "Fruit AND NOT Sewing_Kit" purely because the Sewing_Kit branch was tested first.
    Their disjunction is just `c1 | ... | cn` -- `(A & !B) | B` is `A | B` -- so a negative literal
    is dropped when that item appears POSITIVELY in a sibling hopeful alternative.

    A prohibition survives this: Spinach_Dip is positive only in a DOOMED branch, never in a
    hopeful sibling, so `!own(13)` is kept. That is the difference between "you happened to be
    tested later" and "carrying this loses the game"."""
    positives = set()
    for (p, n, tr) in alts:
        positives |= p
    return [(p, n - positives, tr) for (p, n, tr) in alts]


def factor(alts):
    """Hoist literals common to EVERY alternative, so the rendered guard reads the way a human
    would write it: `own(8) & !own(13) & (own(12) | own(11))` rather than a raw DNF."""
    alts = absorb_ordering(alts)
    pos_sets = [p for (p, n, tr) in alts]
    neg_sets = [n for (p, n, tr) in alts]
    common_pos = set.intersection(*pos_sets) if pos_sets else set()
    common_neg = set.intersection(*neg_sets) if neg_sets else set()
    rest = [(p - common_pos, n - common_neg) for (p, n, tr) in alts]
    rest = [r for r in rest if r[0] or r[1]]
    return common_pos, common_neg, rest


def render(common_pos, common_neg, rest, name=None):
    """SCI-flavoured s-expression for the guard condition."""
    def lit(i, ok=True):
        return f"(gEgo has: {i})" if ok else f"(not (gEgo has: {i}))"
    terms = [lit(i) for i in sorted(common_pos)] + [lit(i, False) for i in sorted(common_neg)]
    if rest:
        branches = []
        for (p, n) in rest:
            ls = [lit(i) for i in sorted(p)] + [lit(i, False) for i in sorted(n)]
            branches.append(ls[0] if len(ls) == 1 else "(and " + " ".join(ls) + ")")
        uniq = sorted(set(branches))
        terms.append(uniq[0] if len(uniq) == 1 else "(or " + " ".join(uniq) + ")")
    if not terms:
        return None
    return terms[0] if len(terms) == 1 else "(and " + " ".join(terms) + ")"


def frontier_guards(s):
    """Guards derived from STRANDINGS -- the other half of the synthesis.

    `survival_gates` only fires where the GAME ITSELF tests an item and sorts you into winning and
    losing branches. A stranding is invisible to that: nothing at rm57 mentions the parachute, you
    simply can no longer come back for it once you board. So the condition comes from the
    reachability analysis instead.

    Straight off `edge_strandings`, the SAME core the report reads -- one library, no drift. An
    earlier version walked the boundary of "can still reach a source" itself and emitted three
    junk guards, one of them on rm78 -> rm178, the sole entrance to the ENDING, which would have
    refused a legitimate win. `edge_strandings` already requires the unit to be STILL NEEDED past
    the edge, which rules that out by construction."""
    out = {}
    for es in s.edge_strandings():
        out[(es["from_room"], es["to_room"])] = {"items": set(es["items"]),
                                                 "groups": [set(g) for g in es["groups"]]}
    return out


def unsatisfiable(s, a, b, rec):
    """Which parts of this guard CANNOT be satisfied before crossing a->b.

    A guard demanding something unobtainable converts a softlock into a permanent wall -- strictly
    worse than the bug it fixes -- so this is a hard refusal, not a warning. Non-empty means the
    guard must not be emitted."""
    pre = M.reachable({x: (set(y) - {b} if x == a else set(y)) for x, y in s.edges.items()},
                      {s.em.cfg.start_room})
    bad = []
    for it in sorted(rec["items"]):
        if not (s.sources.get(it, set()) & pre):
            bad.append(s.g.item_name(it))
    for grp in rec["groups"]:
        if not any(s.sources.get(i, set()) & pre for i in grp):
            bad.append("(" + " or ".join(s.g.item_name(i) for i in sorted(grp)) + ")")
    return bad


def render_frontier(rec):
    terms = [f"(gEgo has: {i})" for i in sorted(rec["items"])]
    for grp in rec["groups"]:
        if len(grp) == 1:
            terms.append(f"(gEgo has: {next(iter(grp))})")
        else:
            terms.append("(or " + " ".join(f"(gEgo has: {i})" for i in sorted(grp)) + ")")
    if not terms:
        return None
    return terms[0] if len(terms) == 1 else "(and " + " ".join(terms) + ")"


def droppability_frontier(s, item):
    """Edges past which `item` can no longer be DROPPED -- where a `not (has: X)` must be
    enforced. The exact mirror of the obtainability test in `edge_strandings`, and the reason
    placement is a real question: the Spinach_Dip may only be forbidden while you can still ditch
    it (ship rooms), so guarding `!own(13)` at the raft would convert a death into a permanent
    wall. Same filters -- irreversible commits only, no death sinks."""
    targets = s.drops.get(item, set())
    if not targets:
        return []
    rev = defaultdict(set)
    for a, bs in s.edges.items():
        for b in bs:
            rev[b].add(a)
    keep = M.reachable(rev, set(targets))          # rooms from which a drop site is reachable
    out = []
    for a in sorted(keep):
        if a not in s.reach_rooms:
            continue
        for b in sorted(s.edges.get(a, ())):
            if b in keep or b not in s.reach_rooms:
                continue
            if a in s.edges.get(b, set()):
                continue                            # reversible walk -> not a commit
            if s.goal_rooms_set() and not (s.goal_rooms_set() & s.rooms_after(b)):
                continue                            # death sink, not a commit
            out.append((a, b))
    return out


def sink_remedies(s):
    """Remedies for DANGEROUS PURE SINKS -- and they are not guards.

    A guard would refuse the player's command. But a pure sink is by definition a clause that does
    nothing EXCEPT destroy the item, so the minimal fix is to delete the consumption itself
    (`put: X -1`) and leave the clause's text and score penalty alone. That is provably
    side-effect-free: "arms nothing, writes nothing a guard reads" is exactly the property that
    classified it as a sink, so removing its one effect cannot perturb anything else. The player
    still gets the joke and the -5; they just keep the bottle.

    SAFETY: refuse when merely HOLDING the item can lose the game, because then letting the player
    keep it trades one softlock for another. The Spinach_Dip is the case -- it is fatal to carry
    into rm138 -- which is why prohibitions are tracked separately from requirements."""
    forbidden = set()
    for gt in survival_gates(s):
        _, cn, _ = factor(gt["alts"])
        forbidden |= cn
    out = []
    for d in s.dangerous_sinks():
        it = d["item"]
        refused = ([f"{s.g.item_name(it)} is fatal to CARRY -- keeping it would trade one "
                    f"softlock for another"] if it in forbidden else [])
        out.append({"site": "consumption", "room": d["room"], "script": d["script"],
                    "item": it, "op": "remove_consumption",
                    "edit": f"delete `(gEgo put: {it} -1)`",
                    "why": f"wastes {s.g.item_name(it)}, still needed at "
                           f"rm{d['still_needed_at']} and not re-obtainable",
                    "refused": refused})
    return out


def guard_specs(s):
    """ONE spec per placement site, merging both derivations.

    Sites are of two kinds. A `gate` is where the game itself tests you and branches into winning
    and losing futures (rm138's raft). An `edge` is a structural commit where nothing is tested at
    all and you simply cannot come back (rm57 boarding). Negative literals are RELOCATED off the
    gate to the last edge where the item is still droppable -- enforcing them at the gate is the
    permanent-wall bug."""
    specs = []
    for (a, b), rec in sorted(frontier_guards(s).items()):
        bad = unsatisfiable(s, a, b, rec)
        specs.append({"site": "edge", "from_room": a, "to_room": b,
                      "condition": render_frontier(rec),
                      "items": sorted(rec["items"]), "groups": [sorted(g) for g in rec["groups"]],
                      "refused": bad})
    for gt in survival_gates(s):
        cp, cn, rest = factor(gt["alts"])
        pos_spec = render(cp, set(), rest)
        if pos_spec:
            specs.append({"site": "gate", "room": gt["room"], "state": gt["state"],
                          "condition": pos_spec, "items": sorted(cp), "refused": []})
        for it in sorted(cn):                       # each prohibition at ITS OWN site
            sites = droppability_frontier(s, it)
            for (a, b) in sites:
                specs.append({"site": "edge", "from_room": a, "to_room": b,
                              "condition": f"(not (gEgo has: {it}))", "items": [], "forbid": [it],
                              "refused": [] if sites else [f"{s.g.item_name(it)} undroppable"],
                              "note": f"prohibition relocated from rm{gt['room']} -- last point "
                                      f"the item can still be got rid of"})
            if not sites:
                specs.append({"site": "gate", "room": gt["room"], "state": gt["state"],
                              "condition": f"(not (gEgo has: {it}))", "items": [], "forbid": [it],
                              "refused": [f"{s.g.item_name(it)} cannot be dropped anywhere -- "
                                          f"guarding this would wall the game"]})
    return specs


def apply_guards(s, specs):
    """Inject the emitted guards into the movement model, so the sweep can be re-run against a
    GUARDED game. Conjunctive items intersect every DNF alternative; a disjunctive group expands
    them (traversable iff SOME alternative is fully held).

    Note what this canNOT check: prohibitions. The walk models "items you do not hold", so a
    `not (has: X)` guard has no representation here and is excluded from this pass."""
    for sp in specs:
        if sp["site"] != "edge" or sp["refused"] or sp.get("forbid"):
            continue
        key = (sp["from_room"], sp["to_room"])
        variants = s._emeta.get(key)
        if not variants:
            continue
        req = frozenset(sp.get("items", ()))
        out = []
        for (rq, sets, alts) in variants:
            base = [a | req for a in (alts or (frozenset(),))]
            for g in sp.get("groups", []):
                base = [b | {m} for b in base for m in g]
            out.append((rq, sets, tuple(base)))
        s._emeta[key] = out
    s._reob.clear(); s._rw.clear(); s._after.clear()
    s._pstates = {R: s._walk(R, frozenset()) for R in s.regs}
    return s


def verify(s, specs):
    """Re-run the detector against the guarded model: every softlock must be gone, and -- the part
    that actually matters -- NO NEW ones may appear. A guard that fixes one stranding by creating
    another is the failure mode that got patch.py disabled."""
    before = {c["item"] for c in s.analyze()}
    before_groups = {frozenset(r["items"]) for r in s.group_strandings()}
    apply_guards(s, specs)
    after = {c["item"] for c in s.analyze()}
    after_groups = {frozenset(r["items"]) for r in s.group_strandings()}
    return {"fixed": sorted(before - after), "remaining": sorted(after & before),
            "NEW": sorted(after - before),
            "groups_fixed": [sorted(g) for g in before_groups - after_groups],
            "groups_new": [sorted(g) for g in after_groups - before_groups]}


def main():
    s = M.load()
    nm = s.g.item_name
    gates = survival_gates(s)
    print(f"survival gates (carrying the wrong things loses the game): {len(gates)}\n")
    for gt in gates:
        cp, cn, rest = factor(gt["alts"])
        cond = render(cp, cn, rest)
        print(f"rm{gt['room']} state {gt['state']}")
        print(f"   guard: {cond}")
        if cp or cn:
            need = ", ".join(nm(i) for i in sorted(cp))
            forbid = ", ".join(nm(i) for i in sorted(cn))
            print(f"   always need: [{need}]   must NOT carry: [{forbid}]")
        for (p, n) in rest:
            print(f"   alternative: {[nm(i) for i in sorted(p)]}")
        for (p, n, tr) in gt["doomed"]:
            why = "dies" if tr[0] == "DEATH" else f"strands ({tr[0]})"
            print(f"   losing branch {why}: carrying {[nm(i) for i in sorted(p)] or 'nothing useful'}"
                  + (f" while lacking {[nm(i) for i in sorted(n)]}" if n else ""))
        print()

    print("=" * 78)
    fg = frontier_guards(s)
    print(f"frontier guards (structural strandings -- the game never tests these): {len(fg)}\n")
    refused = 0
    for (a, b), rec in sorted(fg.items()):
        bad = unsatisfiable(s, a, b, rec)
        names = [nm(i) for i in sorted(rec["items"])]
        names += ["(" + " or ".join(nm(i) for i in sorted(g)) + ")" for g in rec["groups"]]
        print(f"rm{a} -> rm{b}")
        if bad:
            refused += 1
            print(f"   REFUSED -- cannot be satisfied before this edge: {bad}")
            print(f"   (emitting it would wall the game, which is worse than the softlock)")
        else:
            print(f"   guard: {render_frontier(rec)}")
            print(f"   needs: {names}")
        print()
    print(f"{len(fg) - refused} emitted, {refused} refused as unsatisfiable")

    print("=" * 78)
    specs = guard_specs(s)
    print(f"MERGED SPECS -- one per placement site: {len(specs)}\n")
    for sp in specs:
        where = (f"rm{sp['from_room']} -> rm{sp['to_room']}" if sp["site"] == "edge"
                 else f"rm{sp['room']} state {sp['state']}")
        print(f"  {where:<22} {'REFUSED ' + str(sp['refused']) if sp['refused'] else sp['condition']}")
        if sp.get("note"):
            print(f"  {'':<22} ^ {sp['note']}")

    print("=" * 78)
    sinks = sink_remedies(s)
    print(f"DANGEROUS PURE SINKS -- actions that waste an item you still need: {len(sinks)}\n")
    for sk in sinks:
        print(f"  rm{sk['room']} (script {sk['script']}): {sk['edit']}")
        print(f"       {sk['why']}")
        if sk["refused"]:
            print(f"       REFUSED: {sk['refused'][0]}")
    print()

    print("=" * 78)
    r = verify(s, specs)
    print("VERIFY -- re-run the detector against the GUARDED model\n")
    print(f"  softlocks fixed : {[nm(i) for i in r['fixed']]}")
    print(f"  groups fixed    : {[[nm(i) for i in g] for g in r['groups_fixed']]}")
    print(f"  still remaining : {[nm(i) for i in r['remaining']] or 'none'}")
    print(f"  NEW introduced  : {[nm(i) for i in r['NEW']] or 'NONE'}"
          f"   {'<-- would be a regression' if r['NEW'] else ''}")
    print(f"  new groups      : {r['groups_new'] or 'NONE'}")
    ok = not r["remaining"] and not r["NEW"] and not r["groups_new"]
    print(f"\n  {'PASS' if ok else 'FAIL'}: guards close every detected softlock and create none")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
