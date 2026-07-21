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
    simply can no longer come back for it once you board. So the condition has to come from the
    reachability analysis instead -- the items a commit edge strands, required at the edge that
    strands them.

    Returns {(from_room, to_room): {"items": {...}, "groups": [{...}], "why": [...]}}. Items are
    ANDed (each is independently required past the edge); a disjunctive group contributes an OR."""
    by_edge = defaultdict(lambda: {"items": set(), "groups": [], "why": []})
    for c in s.analyze():
        for e in c["frontier_edges"]:
            a, b = (int(x[2:]) for x in e.split("->"))
            rec = by_edge[(a, b)]
            rec["items"].add(c["item"])
            rec["why"].append(f"{c['item_name']} (from rm{c['source_rooms']}) needed at rm{c['need_room']}")
    for row in s.group_strandings():
        for e in frontier_for(s, frozenset(row["items"])):
            by_edge[e]["groups"].append(set(row["items"]))
            by_edge[e]["why"].append(" or ".join(row["item_names"]) + f" needed at rm{row['need_room']}")
    return by_edge


def frontier_for(s, items):
    """Commit edges past which NONE of `items` can be obtained any more -- the placement rule.
    A literal is enforced at the last edge where it is still satisfiable, never at the gate."""
    keep = s.reobtainable_rooms(items)
    goal_ok = M.goal_reaching_rooms(s.edges, s.em.cfg.goal_rooms)
    out = []
    for a in sorted(keep):
        for b in sorted(s.edges.get(a, ())):
            if b not in keep and b in s.reach_rooms and b in goal_ok:
                out.append((a, b))          # b in goal_ok screens out death rooms, not commits
    return out


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
    for (a, b), rec in sorted(fg.items()):
        pos = sorted(rec["items"])
        terms = [f"(gEgo has: {i})" for i in pos]
        for grp in rec["groups"]:
            terms.append("(or " + " ".join(f"(gEgo has: {i})" for i in sorted(grp)) + ")")
        cond = terms[0] if len(terms) == 1 else "(and " + " ".join(terms) + ")"
        print(f"rm{a} -> rm{b}")
        print(f"   guard: {cond}")
        print(f"   needs: {[nm(i) for i in pos] + ['(' + ' or '.join(nm(i) for i in sorted(g)) + ')' for g in rec['groups']]}")
        for w in rec["why"][:5]:
            print(f"     - {w}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
