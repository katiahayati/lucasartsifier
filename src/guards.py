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

import re
import sys

from collections import defaultdict

import missability as M
import vocab


def designer_score(s):
    """(script, item) -> the score delta the game applies when that item is consumed.

    ADVISORY ONLY -- it never gates what we emit. `changeScore` is a designer convention, not a
    semantic property (model.py: "never a win oracle"), and it is a poor RULE: 3 of our sinks carry
    no score at all, and one carries a POSITIVE score (throwing the Spinach_Dip overboard is a sink
    structurally, but it is the intended action -- the game pays you to ditch a fatal item).

    As an ORACLE it is excellent, because it shares no machinery with our analysis: all 6
    negative-score consumptions are sinks we classified independently, with zero disagreements.
    A `real use` carrying a negative score would be a lead that our detector missed something."""
    import os, re
    def _has_rooms(d):
        # must contain the decompiled ROOM scripts -- a bare "src" resolves to this repo's own
        # source directory, which exists and would silently yield nothing
        return os.path.isdir(d) and any(re.match(r"rm\d+\.sc$", f) for f in os.listdir(d))

    out = {}
    cands = [s.em.cfg.src_dir,
             os.path.join(os.path.dirname(getattr(s.em.ir, "path", "") or ""), "src")]
    src = next((d for d in cands if _has_rooms(d)), None)
    if src is None:
        return out
    for fn in sorted(os.listdir(src)):
        m = re.match(r"rm(\d+)\.sc$", fn)
        if not m:
            continue
        script = int(m.group(1))
        lines = open(os.path.join(src, fn)).read().splitlines()
        for i, line in enumerate(lines):
            mm = re.search(r"put:\s*(\d+)\s*-1", line)
            if not mm:
                continue
            for j in range(max(0, i - 6), min(len(lines), i + 7)):
                ms = re.search(r"changeScore:\s*(-?\d+)", lines[j])
                if ms:
                    out[(script, int(mm.group(1)))] = int(ms.group(1))
                    break
    return out


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


def fatal_to_carry(gate):
    """Items whose mere POSSESSION loses the game at this gate.

    Read off the DOOMED branches rather than off common negatives of the hopeful ones. Factoring
    is fragile here: rm138 state 6 is a day-by-day dispatcher, so its branches are different DAYS
    (day 5 wants the Gulp, day 6 wants Sewing_Kit or Fruit) rather than alternatives to one
    choice. `!own(dip)` therefore is not common to every hopeful branch and silently stopped being
    emitted -- while the DOOMED branch `own(13) -> JUMP 17` states the hazard directly and is
    invariant to how the days factor.

    An item qualifies only if it appears positively in NO hopeful branch: that separates "carrying
    this kills you" from "this is one of several things that saves you"."""
    helpful = set()
    for (p, n, tr) in gate["alts"]:
        helpful |= p
    fatal = set()
    for (p, n, tr) in gate["doomed"]:
        fatal |= (p - helpful)
    return fatal


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


def _own_polarity(g, it, neg=False):
    """(appears-positively, appears-negatively) for own(`it`) in a guard TREE.

    Polarity, not requirement: an own() under a GNot (or with want=False) counts as negative.
    Used to recognise the game SORTING the player on an item -- one arming demands it, a
    sibling arming demands its absence -- which is a stronger fact than either mention alone."""
    if g is None:
        return False, False
    if isinstance(g, M.Pred):
        if g.kind == "OWN" and g.var == it:
            truthy = bool(g.want) != bool(neg)
            return truthy, not truthy
        return False, False
    if isinstance(g, M.GNot):
        return _own_polarity(g.kid, it, not neg)
    kids = getattr(g, "kids", None) or (g if isinstance(g, list) else [])
    pos = negv = False
    for k in kids:
        p, n = _own_polarity(k, it, neg)
        pos, negv = pos or p, negv or n
    return pos, negv


def _render_reg_equals(s, musts):
    """`{R: v}` -> one SCI condition string in the game's own spelling, or None.

    The mask-global store gets its own grouping: its per-bit registers are OUR lowering of a
    plain global the game reads by equality, so when the demand pins the word's every observed
    bit the natural spelling is the game's own `(== global161 15)` -- exactly the comparison the
    sorter performs -- rather than four bit-tests. A partial pin renders per bit as
    `(& globalN $mask)` / `(not ...)`, the idiom the game itself reads single bits with. Every
    other register goes through `render_register`; any register with no spelling refuses the
    whole conjunction (None), because a guard that silently asks for less is an under-guard."""
    ir = getattr(s.em, "ir", None)
    mg = getattr(ir, "_mask_global_index", {}) if ir is not None else {}
    by_word, rest = {}, {}
    for R, v in musts.items():
        if R in mg:
            gi, bit = mg[R]
            by_word.setdefault(gi, {})[bit] = v
        else:
            rest[R] = v
    terms = []
    for gi, bits in sorted(by_word.items()):
        universe = sorted(b for (g2, b) in mg.values() if g2 == gi)
        if set(bits) == set(universe):
            terms.append(f"(== global{gi} {sum(1 << b for b, v in bits.items() if v)})")
        else:
            for b, v in sorted(bits.items()):
                t = f"(& global{gi} {1 << b})"
                terms.append(t if v else f"(not {t})")
    for R, v in sorted(rest.items()):
        t = render_register(s, R, v)
        if t is None:
            return None
        terms.append(t)
    if not terms:
        return None
    return terms[0] if len(terms) == 1 else "(and " + " ".join(terms) + ")"


def _conj_reg_reqs(s, guard, drop=()):
    """The single-valued register literals `guard` REQUIRES (structural, so a disjunction of two
    ways through keeps only what both demand), minus the positional registers in `drop`."""
    req = M.structural_reqs(guard, s.regs)
    return {R: next(iter(vs)) for R, vs in req.items()
            if len(vs) == 1 and R not in drop}


def _one_way_set(s, gi):
    """Is `gi` a register the game only ever writes 1 to -- a latch nothing clears?

    Judged over the emitter's RAW write sources (machine states, handler writes, arrival
    writes), not `_inroom`/`_rstep`: those exist only for GATING registers, and a success
    latch need not gate anything we model to be a truthful record of past survival."""
    vals = set()
    for info in s.em.machines + getattr(s.em, "global_machines", []):
        for paths in info["states"].values():
            for (_g, w, _gg, _c, _tr) in paths:
                vals.update(v for (g2, v) in w if g2 == gi)
    vals.update(v for (_r, _sc, g2, v, _g) in s.em.handler_writes if g2 == gi)
    vals.update(vs[gi] for vs in getattr(s.em, "init_writes", {}).values() if gi in vs)
    return vals == {1}


def sink_survival_carryins(s):
    """A sink-lost item that is later the PRICE OF SURVIVING a room: demand it at the crossings
    into that room.

    The sink itself can be unguardable and even mandatory. KQ6's lamp trade is both: deleting
    the disposal hands the player both sides (a TRADE), and the new lamp is the genie's price,
    so refusing the trade would wall the game. The loss is also perfectly legal on the route
    that never needs the item -- the short ending never sails to the Isle of the Mists. What is
    never legal is walking into the death without it: rm580's `cageInset::init` sorts the
    captured player into `makeRain` (survive) on `own(huntersLamp) & waters-poured` and
    `inTheCage` (death) otherwise, and from inside the cage nothing can be done. That is the
    unfair-death class, prevented at the last screen where prevention is possible: the
    crossings into the room. [User doctrine 2026-08-03: the trade must stay; the trip is what
    gets refused -- the same ruling as the catacombs entrance.]

    Fires only where the GAME ITSELF holds a death sorted on the item -- some machine at the
    need room mentions own(item) positively in one arming and negatively in a sibling. A mere
    action-need (mint at the genie's palace) has no such sorter, so this cannot over-demand an
    item whose loss the disjunctive-group machinery already covers.

    THE DEMAND IS THE SORTER'S WHOLE CONDITION, not the item half alone. The original premise
    here -- "the other conjuncts are established inside" -- was FALSE for the very instance it
    shipped for (USER FINDING #17, play, 2026-08-05): KQ6's cage sorter demands the lamp AND
    rain-readiness (`global161 == 15`), and every readiness bit is established off-isle or from
    inventory; rm580 only RESETS the word. So the positive arming's conjunctive register
    literals ride along (`structural_reqs`, so a disjunction keeps only what every way through
    demands), presentability-checked at each crossing like every register-valued demand.

    Two derived qualifications keep the register half from shipping a wall:
      * SUCCESS CONSUMES COMPLIANCE. The surviving arm itself RESETS the demanded register
        (makeRain sets `global161 := 0` on the way to the rain) -- so a player who already
        survived can never present the value again, and demanding it unconditionally would
        seal the befriended camp off from every winner. The same arm writes a one-way boolean
        latch nothing in the game ever clears (flag 74, befriended-forever), and the latch
        waives the WHOLE demand, item half included: `(or <latch> (and <item> <registers>))`
        [USER RULING 2026-08-06: "let you revisit the camp without the lamp once there's no
        trap there" -- with the latch up the capture cannot re-arm, so nothing is demanded].
        All facts are read off the machine's own modeled writes; if the arm resets the demand
        and no such latch exists, the register half is refused rather than walled.
      * THE LANDING PROPAGATES ONE ROOM BACK (row 5c's class). A machine at another room
        whose modeled paths EXIT into the sorter's room, armed with no player action under a
        register stage (KQ6's shore ambush: `captured`, armed via `waitForCapture` only under
        flag 25 & !14, delivering `newRoom: 580` on arrival), makes the crossing INTO that room
        the last complying moment -- leave-and-return-unready died on arrival in stock. The
        same demand is emitted on every crossing into the delivering room, conditioned on the
        stage (`(or (not <stage>) <demand>)`) so every non-ambush crossing stays free. The
        stage is the machine's own entry requirement with positional registers (previous-room,
        current-room) dropped; a player-initiated delivery (doVerb/handleEvent-sourced arming)
        does not qualify, because the player could decline it inside."""
    import extract as X
    out, seen = [], set()
    prev = M.prev_room_reg(s.em)
    positional = {prev, getattr(X, "_CURROOM", None)}
    for r in s.dangerous_sinks():
        it = r["item"]
        for N in r.get("still_needed_at", ()):
            pos_rows, neg_rows = [], []
            for info in s.em.machines:
                if info["room"] != N:
                    continue
                for _k, g in (info.get("entries") or ()):
                    p, n = _own_polarity(g, it)
                    if p:
                        pos_rows.append((info, g))
                    if n:
                        neg_rows.append(info)
            if not (pos_rows and neg_rows):
                continue
            # -- the register half: what EVERY hopeful arming of the sorter also requires
            common = None
            for _info, g in pos_rows:
                req = _conj_reg_reqs(s, g, drop=positional)
                common = req if common is None else \
                    {R: v for R, v in common.items() if req.get(R) == v}
            common = common or {}
            reg_cond, reg_refused, waivers = None, [], []
            if common:
                # success-latch analysis, off the sorter's own modeled writes
                neg_writes = {gi for info in neg_rows
                              for paths in info["states"].values()
                              for (_g, w, _gg, _c, _tr) in paths for (gi, _v) in w}
                resets, latches = False, set()
                for info, _g in pos_rows:
                    for paths in info["states"].values():
                        for (_g2, w, _gg, _c, _tr) in paths:
                            for (gi, v) in w:
                                if gi in common and v != common[gi]:
                                    resets = True
                                if (v == 1 and gi not in common and gi not in neg_writes
                                        and gi in vocab.BOOL_GLOBALS and _one_way_set(s, gi)):
                                    latches.add(gi)
                reg_cond = _render_reg_equals(s, common)
                if reg_cond is None:
                    reg_refused.append("the sorter's register demand has no spelling in the "
                                       "game's own source")
                elif resets:
                    waivers = [w for w in (render_register(s, L, 1)
                                           for L in sorted(latches)) if w]
                    if not waivers:
                        reg_refused.append(
                            "the surviving arm resets the demanded register and no one-way "
                            "success latch marks past survival -- demanding it would wall "
                            "every winner out")
                        reg_cond = None
            # The latch waives the WHOLE demand, item half included [USER RULING 2026-08-06,
            # in play: "we should let you revisit the camp without the lamp once there's no
            # trap there"]. The derivation agrees: the latch is set by the surviving arm and
            # the game arms the capture only under its negation, so with the latch up there
            # is no death left to guard against -- demanding anything is over-block. And a
            # sorter that DID re-arm under the latch would be unwinnable by the game's own
            # design, since its surviving arm already consumed the register compliance.
            if reg_cond and waivers:
                cond = "(or %s (and (gEgo has: %d) %s))" % (" ".join(waivers), it, reg_cond)
            elif reg_cond:
                cond = f"(and (gEgo has: {it}) {reg_cond})"
            else:
                cond = f"(gEgo has: {it})"
            for a, bs in s.edges.items():
                if N in bs and (a, N, it) not in seen:
                    seen.add((a, N, it))
                    rec = {"items": {it}, "groups": []}
                    refused = unsatisfiable(s, a, N, rec) + list(reg_refused)
                    # presentability: the demanded value must be REACHABLE at the crossing, or
                    # the guard refuses players who can no longer comply (finding #15's class)
                    for R, v in sorted(common.items()):
                        if reg_cond and (a, v) not in s._pstates.get(R, ()):
                            refused.append(f"reg{R}={v} is not presentable at rm{a}")
                    out.append({"site": "edge", "from_room": a, "to_room": N,
                                "condition": cond,
                                "items": [it], "groups": [],
                                "refused": refused,
                                "note": f"{s.g.item_name(it)} and the sorter's register "
                                        f"condition are the price of surviving rm{N} (the "
                                        f"game's own death sorter), and the sink at "
                                        f"rm{r['at_room']} that loses the item cannot itself "
                                        f"be guarded -- refuse the trip instead. The WHOLE "
                                        f"demand is waived once the surviving arm's own "
                                        f"one-way latch is set: with the latch up the death "
                                        f"cannot re-arm, so nothing is demanded of a revisit "
                                        f"[user ruling 2026-08-06]."})
            # -- the LANDING: a no-player-action delivery into rm N from another room makes
            #    the crossings into THAT room the last complying moment (guard oracle row 5c)
            for info in s.em.machines:
                A = info["room"]
                if A == N or (A, N, it, "landing") in seen:
                    continue
                exits_to_n = any(tr and tr[0] == "EXIT" and tr[1] == N
                                 for paths in info["states"].values()
                                 for (_g, _w, _gg, _c, tr) in paths)
                if not exits_to_n:
                    continue
                srcs = info.get("entry_sources") or []
                if any(src in ("doVerb", "handleEvent") for src in srcs):
                    continue
                stage = None
                for _k, g in (info.get("entries") or ()):
                    req = _conj_reg_reqs(s, g, drop=positional)
                    stage = req if stage is None else \
                        {R: v for R, v in stage.items() if req.get(R) == v}
                if not stage:
                    continue
                stage_cond = _render_reg_equals(s, stage)
                if stage_cond is None:
                    continue
                seen.add((A, N, it, "landing"))
                landing_cond = f"(or (not {stage_cond}) {cond})"
                for P, bs in s.edges.items():
                    if A not in bs or (P, A, it) in seen:
                        continue
                    seen.add((P, A, it))
                    rec = {"items": {it}, "groups": []}
                    refused = unsatisfiable(s, P, A, rec) + list(reg_refused)
                    for R, v in sorted(common.items()):
                        if reg_cond and (P, v) not in s._pstates.get(R, ()):
                            refused.append(f"reg{R}={v} is not presentable at rm{P}")
                    out.append({"site": "edge", "from_room": P, "to_room": A,
                                "condition": landing_cond,
                                "items": [], "groups": [],
                                "refused": refused,
                                "note": f"the landing at rm{A}: under its stage "
                                        f"({stage_cond}) rm{A}'s `{info['inst']}` delivers "
                                        f"the player into rm{N}'s death sorter with no "
                                        f"controllable moment after arrival, so this "
                                        f"crossing is the last place compliance can be "
                                        f"demanded. Free whenever the stage is off."})
    return out


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


def commit_entry_frontier(s, room):
    """Rooms with a crossing INTO `room` from OUTSIDE its pocket -- where an ARRIVAL COMMIT's
    demand can sit without wrapping an interior return.

    An arrival commit (KQ6's catacombs seizure: `rm340::init` calls the guards' proc the moment
    you walk in) cannot be refused in place -- play finding #5, the refusal left a half-armed
    scene and hung the game -- so its demand belongs on the last CONTROLLABLE crossing into the
    room. But "every file with a `newRoom:` into it" is the wrong site list: the pocket behind
    the room (350/370/405/440 behind rm340) re-enters it on every internal return, and wrapping
    those walls a player who is already inside -- the compliance doctrine, violated. Play pass
    2026-08-04 measured exactly that failure when the site list came from text search.

    The model already knows the difference: `reach_avoiding({room})` is the gate-aware set of
    rooms reachable WITHOUT ever entering `room`, so a predecessor inside it crosses the
    frontier from outside, and one absent from it can only be making an interior return."""
    outside = s.reach_avoiding(frozenset({room}))
    return sorted(a for a, bs in s.edges.items()
                  if room in bs and a != room and a in outside)


def defer_to_entry(s, sp):
    """A demand refused at a SOLE-EXIT pocket, re-sited: the register stage that discriminates
    the spec's crossing, and the pocket's predecessor rooms where that stage is presentable AND
    the demand is still satisfiable. None when the crossing cannot be discriminated -- a
    stage-less deferral would gate EVERY entry to the pocket, including the crossings this
    demand says nothing about.

    The site list is ALL predecessors, deliberately NOT `commit_entry_frontier`: that frontier
    is built for a one-visit pocket (rooms crossing in from `reach_avoiding`), and a game that
    STARTS behind its own act-break card (LB2: the intro's 0->1 break) makes the whole game
    "inside the pocket", leaving only the intro rooms. A sole-exit pocket is a different shape:
    every entry is a fresh committed crossing, so every predecessor is a candidate refusal
    site, and what protects the player is not the frontier but the two per-site filters --
    the stage (a wrap at the wrong act is vacuous by the game's own register) and COMPLIANCE
    (`unsatisfiable` at the site's own crossing: a site where the demanded items can no longer
    be sourced is refused, because a demand you cannot meet is a wall, the failure this project
    holds to be worse than the softlock).

    LB2's act-break card is the shape this exists for: script 26 holds exactly one `newRoom:`,
    inside the very cutscene an arm-event would decline to start, so a refusal in place leaves
    the player on the title card with nothing left to run (docs/LB2-ORACLE.md §7i, measured by
    reading the emitted source). The controllable moment is the crossing INTO the card -- the
    same doctrine as the arrival-commit re-site -- and what distinguishes "the act-1 break" from
    "the act-4 break" there is not position but register state: the out-edge's own `_emeta`
    requirement (the act counter), the discriminator the landing propagation already spells as
    `(or (not <stage>) <demand>)`.

    Positional registers (previous-room, current-room) are dropped from the stage for the same
    reason `_guard_arrival_entries` drops prev-room clause heads: at the frontier they name
    where the player is standing NOW, which is never the pocket. Beyond that the reading is
    STRICT in the refusing direction: every meta alternative must yield a non-empty stage of
    single-valued, spellable registers, or the whole deferral returns None -- one stage-free or
    unspellable way through means the demand cannot be scoped, and an under-stage gates
    crossings the spec says nothing about."""
    import extract as X
    a, b = sp["from_room"], sp["to_room"]
    positional = {M.prev_room_reg(s.em), getattr(X, "_CURROOM", None)}
    alts, conds = [], []
    for (req, _sets, _alt) in s._emeta.get((a, b), ()):
        keep = {R: vs for R, vs in req.items() if R not in positional}
        if not keep or any(len(vs) != 1 for vs in keep.values()):
            return None
        musts = {R: next(iter(vs)) for R, vs in keep.items()}
        cond = _stage_spelling(s, musts)
        if cond is None:
            return None
        if cond not in conds:
            alts.append(musts)
            conds.append(cond)
    if not conds:
        return None
    stage = conds[0] if len(conds) == 1 else "(or %s)" % " ".join(conds)
    rec = {"items": set(sp.get("items") or ()), "groups": [set(g) for g in sp.get("groups") or ()]}

    def _presentable(r):
        return any(all((r, v) in s._pstates.get(R, ()) for R, v in musts.items())
                   for musts in alts)

    rooms = []
    for r in sorted(x for x, bs in s.edges.items() if a in bs and x != a):
        # STAGE presentability: a site that can never stand at the stage would carry a dead
        # guard (on LB2 this is what keeps act-break wraps out of the intro rooms, whose ESC
        # skip crosses at act 0 only)...
        if not _presentable(r):
            continue
        # ...and COMPLIANCE at the site's own crossing, the same question the spec itself was
        # asked at its edge: refusing where the player can no longer comply is a wall.
        if unsatisfiable(s, r, a, rec):
            continue
        rooms.append(r)
    if not rooms:
        return None

    # Model knowledge the placement's arrival-commit triage consumes (patcher._defer_triage_site):
    # a deferral site that is itself inside a commit re-sites up its delivering chain, and every
    # hop owes the same two per-site filters the rooms above just passed. `alts` carries the
    # stage's register alternatives for the vacuity check; `positional`/`prev_g` name the
    # registers whose tests mean "where the player stands NOW" and the one that names the
    # delivering room.
    def _site_ok(x, target):
        if not _presentable(x):
            return "stage not presentable"
        bad = unsatisfiable(s, x, target, rec)
        if bad:
            return "demand unsourceable at the hop (%s)" % ", ".join(bad)
        return None

    # DEMAND FORWARDING (the §7c debt, demand half): when the arrival-commit triage later
    # refuses every site, this demand may still ride the register's SOLE PRODUCING FLIP one
    # stage earlier -- the nearest controllable commit on the only path to this crossing.
    # Provable only when (a) the stage is one scalar test, (b) NOTHING ELSE ANYWHERE produces
    # that value -- no in-room step outside the pocket and no edge leaving any other room --
    # (c) exactly one sibling edge out of the pocket commits the write, with a single
    # from-value to spell the host's stage, and (d) the demand is satisfiable before the HOST
    # crossing (the same `unsatisfiable` wall-test every placement owes). Anything short of all
    # four -> None, and the refusal stands as before.
    #
    # (b) IS TWO CHECKS BECAUSE A REGISTER IS WRITTEN IN TWO PLACES. `_inroom` holds the writes
    # a room's own steps perform; a write that rides a MOVEMENT is in `_emeta`'s `sets`, and
    # scanning that for `x == a` alone -- which is what the host search does -- asks "how many
    # ways out of the pocket commit this", never "is the pocket the only place the commit can
    # happen". A flip edge leaving any other room lets the player stand at the stage having
    # never crossed the hold, and the demand would be reported COVERED at a crossing it does
    # not gate. The two spellings of one write are this codebase's oldest bug shape
    # ([[same-rule-two-places]]); here they were two halves of one proof.
    fwd = None
    m_st = re.match(r"^\(==\s*global(\d+)\s+(-?\d+)\)$", stage.strip())
    if m_st:
        reg, w = int(m_st.group(1)), int(m_st.group(2))
        others = [r for r, vs in s._inroom.get(reg, {}).items() if w in vs and r != a]
        others += [(x, y) for (x, y), rows_ in s._emeta.items() if x != a
                   for mrow in rows_ if mrow[1].get(reg) == w]
        hosts = [(x, y, mrow) for (x, y), rows_ in s._emeta.items() if x == a
                 for mrow in rows_ if mrow[1].get(reg) == w]
        if not others and len(hosts) == 1:
            hx, hy, hrow = hosts[0]
            hreq = hrow[0].get(reg) or set()
            if len(hreq) == 1 and not unsatisfiable(s, hx, hy, rec):
                fwd = {"host": (hx, hy),
                       "host_stage": "(== global%d %d)" % (reg, next(iter(hreq)))}
    return {"stage": stage, "rooms": rooms, "alts": alts, "fwd": fwd,
            "positional": {g for g in positional if g is not None},
            "prev_g": M.prev_room_reg(s.em),
            "preds": lambda r: sorted(x for x, bs in s.edges.items() if r in bs and x != r),
            "site_ok": _site_ok}


# The lowering maps that say "this register is OURS, not a global the game reads" -- one per
# store that records where its registers came from. `_stage_spelling` consults them before it
# will spell a register as a plain `(== globalN v)`, so a store missing from this list would
# have its registers spelled as globals the game never reads: a stage naming a phantom.
#
# HAND-MAINTAINED AND PINNED. It has to be hand-maintained -- a store's index attribute is named
# by the store -- so `test_deletion_soundness` derives the set from a built model and fails if
# an attribute appears that is not listed here. The item-bit store deliberately has no entry: it
# records no index map, and its registers are caught by the synthetic-base test instead, which
# is the backstop for every store allocated after `lower_flags`.
STORE_INDEX_ATTRS = ("_obj_prop_index", "_room_local_index", "_prop_flag_index",
                     "_mask_global_index")

_AMBIGUOUS = {}


def ambiguous_registers(ir):
    """Registers claimed by MORE THAN ONE store -- which must not be spelled at all.

    "Allocation order IS register identity" is the invariant the seven lowerings rest on, and
    nothing was checking it. MEASURED 2026-08-14 (review §3.6): KQ6's registers 386-396 are
    claimed by both the object-property store and the property-flag store -- reg393 is
    `(rgLair cliffFace:)` to one and word 709 bit 12 to the other -- because each allocator
    starts above the highest global it can SEE, and the flag store's last eleven registers are
    allocated for bits with no rewritten site, so the property store's scan never saw them.
    LSL2, KQ4 and LB2 have no overlap.

    Two of the eleven (386, 393) are modelled, so this is live rather than theoretical, and the
    consequence is the phantom-spelling bug this codebase has shipped twice: `render_register`
    tries the stores in a fixed order, so an ambiguous register would be written back as
    whichever store happens to be checked first -- a guard testing something the game does not
    mean there.

    REFUSED, NOT RESOLVED. Making the allocators disjoint would renumber a store, and the last
    time registers were renumbered a user-confirmed finding dissolved into noise (see
    `lower_prop_flags`' own note) -- that is a change that moves a watched surface and wants a
    human. Refusing to spell the ambiguous ones costs nothing today (no shipped spec names one)
    and cannot mis-spell tomorrow."""
    hit = _AMBIGUOUS.get(id(ir))
    if hit is not None and hit[0] is ir:
        return hit[1]
    seen, dup = set(), set()
    for name in STORE_INDEX_ATTRS:
        for R in (getattr(ir, name, None) or {}):
            (dup if R in seen else seen).add(R)
    _AMBIGUOUS[id(ir)] = (ir, dup)
    return dup


def _stage_spelling(s, musts):
    """`_render_reg_equals` plus the ONE case a stage may add: a promoted PLAIN global.

    `render_register` refuses real globals, and for a DEMAND that is right: a demand is the
    game being made to test something, and only a store's own reversal proves the game reads
    that register in that spelling. A STAGE is a weaker claim -- it scopes OUR refusal to the
    crossing the spec means -- and for a promoted gating register the game's own tests are the
    promotion evidence (LB2 reads global123 at 239 sites, by equality; that is why it is a
    register at all). So a register no store lowering claims, below the synthetic base, promoted,
    and demanded at a value the walk itself reaches, is spelled directly as `(== globalN v)`.
    Everything else still refuses -- a guessed stage gates crossings the spec says nothing
    about. Kept OUT of `render_register` on purpose: widening the demand spelling corpus-wide
    is its own change with its own measurement, not a rider on the sole-exit deferral."""
    got = _render_reg_equals(s, musts)
    if got is not None:
        return got
    ir = getattr(s.em, "ir", None)
    claimed = set()
    for name in STORE_INDEX_ATTRS:
        claimed |= set(getattr(ir, name, {}) or {})
    base = getattr(ir, "flag_synth_base", None)
    terms = []
    for R, v in sorted(musts.items()):
        t = render_register(s, R, v)
        if t is None:
            if (R in claimed or (base is not None and R >= base) or R not in s.regs
                    or not any(vv == v for (_r, vv) in s._pstates.get(R, ()))):
                return None
            t = f"(== global{R} {v})"
        terms.append(t)
    return terms[0] if len(terms) == 1 else "(and " + " ".join(terms) + ")"


def unholdable_at(s, a, b, items):
    """Of `items`, those you CANNOT be holding when you cross a->b -> `{item: why}`.

    A guard is a conjunction the player has to satisfy all at once, and `unsatisfiable` only ever
    asked each literal on its own ("is a source still reachable"). That misses an exclusion between
    the guard and the EDGE, and demanding something unholdable does not close a softlock -- it
    WALLS the route, the exact failure this project holds to be worse than the bug.

    TWO ways an edge's own demand can exclude a literal, and KQ6's castle has one of each, one per
    door. They are separate rules because they are separate mechanisms, not two readings of one.

    ROOM COST -- getting what the edge demands means visiting somewhere that takes the literal
    away. The short door `rm220 -> rm730` needs Beauty's clothes; the Realm of the Dead is gated on
    flag 14; the ONLY room that writes flag 14 is rm580 (the Druids); and rm580's escape burns the
    clothes. So the handkerchief and the skeleton key, which exist only inside the Realm, can never
    be in your hands at that door. Test: refuse the rooms that take away what the edge demands,
    walk gate-aware from the start, drop any literal with no source left. A room that both SOURCES
    and DROPS the item is an exchange COUNTER, not a loss -- `sources[brush] == drops[brush] ==
    280` -- and pruning it would wrongly delete every item traded over that counter, so it is kept.

    EXCHANGE -- the literal and the edge's demand are the SAME OBJECT, traded. The long door
    `rm230 -> rm710` needs the paint brush, and the brush is the mechanical nightingale after three
    trades across the pawn shop counter (bird -> flute -> tinderbox -> brush). `missability.
    exchange_slots` derives that at most one member of that set can be held, so demanding the brush
    is demanding NOT the bird. This is the case the ROOM rule structurally cannot see, and for the
    reason above: its counter exemption is what keeps the pawn shop off the prune list.

    Still deliberately narrow, and now honestly so. It removes literals a guard could never hold;
    it does NOT work out which of two winning ROUTES you are on. KQ6's `mint` survives at the long
    door -- nothing about that route costs it, it is simply not needed there -- and that remains a
    per-route NEED question we cannot express. See docs/SCI11-PATCHING-PLAN.md."""
    demanded = s.edge_demands(a, b)
    if not demanded:
        return {}
    out = {}
    # `prune` = rooms that would COST you what the edge demands: they drop `q` and do not hand it
    # back. Refusing them is how "can you still be holding q here" is asked as a reachability
    # question.
    #
    # TWO EXEMPTIONS, and they are different claims:
    #   - {b}       -- the DESTINATION. You must be holding `q` AT THE CROSSING, which happens
    #                  before you are in `b`, so whatever `b` does to `q` afterwards cannot stop
    #                  you arriving with it. KQ6's rm730 takes Beauty's clothes on the way in;
    #                  that is the door consuming its own key, not a reason the key is unholdable.
    #                  Pruning `b` would ask you to reach `q`'s source without ever entering the
    #                  room you are trying to enter.
    #   - sources   -- an exchange COUNTER, a room that both takes the item and gives it back.
    #                  `sources[brush] == drops[brush] == 280`; pruning the pawn shop would delete
    #                  every item traded over it.
    # MEASURED 2026-07-31: the first is inert on all three games (0 of 24 frontier edges change
    # answer without it, including rm220->rm730 where `b` really does drop what the edge demands).
    # Kept anyway, because it is the correct reading rather than a fitted one, and because
    # dropping it can only ever prune MORE and so guard LESS.
    prune = set()
    for q in demanded:
        prune |= (set(s.drops.get(q, ())) - {b}) - set(s.sources.get(q, ()))
    if prune:
        keep = s.reach_avoiding(prune)
        for it in items:
            if not (set(s.sources.get(it, ())) & keep):
                out[it] = ("every source of it is behind %s, which takes away %s -- and this "
                           "crossing demands that"
                           % (["rm%d" % r for r in sorted(prune)][:4],
                              [s.g.item_name(i) for i in sorted(demanded)]))
    for (S, R) in s.exchange_slots():
        held = demanded & S
        if not held:
            continue
        for it in (set(items) & S) - demanded:
            out[it] = ("rm%d trades %s for one another, so holding it excludes %s, which this "
                       "crossing demands"
                       % (R, [s.g.item_name(i) for i in sorted(S)],
                          [s.g.item_name(i) for i in sorted(held)]))
    return out


def register_flip_frontier(s):
    """{(a, b): rec} -- register strandings whose SEAL IS ENTERED BY AN EDGE WRITE, demanded at
    those edges. What is committed COMMITS (the teacup rule, applied to remedies): when the flip
    that seals an item rides a room crossing -- LB2's act break, where `rm26->rm420` itself
    writes `123 := 5` -- the crossing IS the seal's entering write, and the demand belongs on it
    exactly as a carry-in demand belongs on a pocket's entry. Merged into `guard_specs`' frontier
    union, so the standard filters (unholdable_at, unsatisfiable) and placements (including the
    sole-exit deferral, which is how an act-break edge places at all) apply unchanged.

    THE MECHANISM SELECTS ITSELF against the register-write HOLD (`site: register-write`): a
    free-running trap's write lives in a `doit`, not on an edge (KQ4's nightfall, KQ6's wedding
    fuse), so it has NO flip edges and keeps the hold path -- while a player-committed flip has
    no free-running writer, which is why LB2's holds never placed ("no free-running trap write
    found"). A flip edge is an edge whose meta WRITES the value from a state that excludes it
    (`sets[R] == v`, `v not in req[R]`) -- arriving already at v is not entering the seal.

    JOINT rows reduce to the same rule: the positional component (previous-room) names the
    from-room -- `(12,123) = (26,5)` is entered exactly by the rm26 edges that write `123:=5`,
    because `prev := 26` is what leaving rm26 means -- and only the value-CHANGING component
    needs a flip edge. A joint row whose prev component does not match any flip edge's from-room
    contributes nothing (the (110,2)/(330,3) pressPass witnesses: the same stranding seen from
    non-causal states; the (26,2) row carries the demand).

    AND THE SAME RETIREMENT FILTER AS THE EDGE ROWS (`crossing_retires_need`): a row whose
    `still_needed_at` rooms are all unreachable past the flip edge's own commit puts no demand
    there -- the scalar `reg123=5` pressPass row is the case (the flat projection of an act-2
    stranding; its rm335 need is sealed from act 3 on, so demanding the pass at the 4->5 break
    would wall it). The joint rows, whose needs live inside the post-flip region, keep their
    demands untouched. Rows without a `still_needed_at` (the flip-trap mapping below) are never
    retired -- no need set, no evidence."""
    prev = M.prev_room_reg(s.em)

    def flip_edges(R, v, from_room=None):
        # A PREV-ROOM register's exclusion is STRUCTURAL, not spelled in the edge's req: standing
        # in rm85, prev != 85 by construction, because `prev := 85` is what leaving rm85 means --
        # the same fact the JOINT reduction below already uses ("the positional component names
        # the from-room"). The req test below cannot see it (no edge constrains prev in its own
        # req), which left KQ5's kidnap row [REFUSED]/UNENFORCED: the one crossing that strands
        # the Hammer carried no demand. Every edge out of room v writes the value from a state
        # that excludes it; the caller's `land` filter then keeps only the arrivals the walk
        # measured as sealing.
        if R == prev:
            return {(a, b) for (a, b) in s._emeta
                    if a == v and b != v and (from_room is None or a == from_room)}
        sites = set()
        for (a, b), metas in s._emeta.items():
            if from_room is not None and a != from_room:
                continue
            for (req, sets, _alts) in metas:
                if sets.get(R) == v and req.get(R) and v not in req[R]:
                    sites.add((a, b))
                    break
        return sites

    def staged_flip_edges(R, v):
        """Flip edges whose WRITE is unconstrained -- the crossing writes `v` whatever the
        register held, so the req test above cannot see the entry. KQ5's harpy departure is
        the case: `rm49->rm48` sets flag 54 with no flag-54 req of its own (you can sail home
        again later). The crossing still ENTERS the seal -- from the pre-flip state -- but
        the demand may bind ONLY there: a post-flip player re-crossing must never be walled
        (the items it would demand are exactly what the flip sealed away). So these edges
        carry a STAGE, the pre-flip test, for the spec builder to fold in as
        `(or <already flipped> <items>)` -- and they qualify only when the flip is ONE-WAY
        (every write of R anywhere is `v`), because with a writer back the pre-flip test
        does not mean "first commitment"."""
        writes = {sets[R] for metas in s._emeta.values()
                  for (_rq, sets, _al) in metas if R in sets}
        writes |= {vv for vs in (s._inroom.get(R) or {}).values() for vv in vs}
        if writes != {v}:
            return set()
        sites = set()
        for (a, b), metas in s._emeta.items():
            for (req, sets, _alts) in metas:
                if sets.get(R) == v and not req.get(R):
                    sites.add((a, b))
                    break
        return sites

    out = defaultdict(lambda: {"items": set(), "groups": []})
    rows = list(s.register_strandings()) + [
        {"register": r["register"], "value": r["trap"], "item": r["item"]}
        for r in s.register_flip_strandings()]
    for r in rows:
        R, V = r["register"], r["value"]
        stage = None
        if isinstance(R, tuple):
            comps = dict(zip(R, V))
            from_room = comps.get(prev)
            sites = set()
            for Ri, vi in comps.items():
                if Ri != prev:
                    sites |= flip_edges(Ri, vi, from_room=from_room)
        else:
            sites = flip_edges(R, V)
            if not sites and R != prev:
                sites = staged_flip_edges(R, V)
                if sites:
                    stage = (R, V)
        need = set(r.get("still_needed_at") or ())
        # ...AND THE EDGE MUST LAND WHERE THE FLIP STRANDS (2026-08-14). `flip_edges` selects
        # by the WRITE -- an edge whose meta sets the value from a state that excludes it --
        # and for a POSITIONAL register every edge out of a room performs that write, because
        # `prev := a` is what leaving rm a means. The walk has already measured which of those
        # arrivals actually seals the item (`flip_rooms`), and an edge landing anywhere else
        # is a different crossing that happens to write the same value: it enters no seal, so
        # it carries no demand. KQ5's cellar is the live instance -- the kidnap is one of
        # several ways out of rm85, and only the arrival in rm86 strands the Hammer.
        # `register_flip_strandings` rows carry no flip_rooms and are untouched (an empty set
        # filters nothing, the permissive direction).
        land = set(r.get("flip_rooms") or ())
        for (a, b) in sites:
            if land and b not in land:
                continue
            if need and s.crossing_retires_need(a, b, r["item"], need):
                continue
            out[(a, b)]["items"].add(r["item"])
            if stage is not None:
                # rides the rec to the spec builder; a merge that finds two different stages
                # on one edge, or a stage beside an unstaged claim, refuses the edge loudly
                # rather than demanding at the wrong moment (none exist in the corpus today)
                prior = out[(a, b)].get("stage")
                if prior is not None and prior != stage:
                    out[(a, b)]["stage_conflict"] = True
                out[(a, b)]["stage"] = stage
    return dict(out)


def joint_frontier(s):
    """Commit edges for the JOINT-window strandings -- the grid / one-time-flag softlocks that
    `edge_strandings` structurally cannot see, so `frontier_guards` misses them.

    Each joint-only item crosses a one-time gate exactly once. Which edge to guard depends on which
    side of the gate is DEEP (reachable only after the flag flips, past the grid gate):
      * NEED deep  -> the item must be carried IN: gate the ENTRY to the flip room.
        KQ4's Dead_Fish is used on the island (rm43), so gate the whale swallow rm31->44.
      * SOURCE deep -> the item must be carried OUT: gate the source room's EXITS.
        KQ4's Golden_Bridle is found on the island (rm43), so gate the island exit rm43->rm31.
    Items the edge detector already covers (the endgame Scarab/Fruit/Hen the joint re-sees) are
    skipped -- they keep their rm45->690 guard. LSL2 has no joint findings, so this returns {} and
    cannot touch its guard specs."""
    js = s.joint_strandings()
    if not js:
        return {}
    import grid
    grid_edges = {(r, ex) for r, exits in grid.analyze(s.em, s._prev_room_global()).items()
                  for ex in exits}
    edge_items = {c["item"] for c in s.analyze()}
    out = defaultdict(lambda: {"items": set(), "groups": []})
    for j in js:
        it = j["item"]
        if it in edge_items:
            continue
        # flip rooms for THIS finding's OWN flags -- not a global union over every joint finding,
        # which stamps this item's guard on an unrelated gate's entries and skews `shallow` (B#5).
        flip_rooms = set()
        for F in j["flags"]:
            for room, vals in s._inroom.get(F, {}).items():
                if any(v != 0 for v in vals):
                    flip_rooms.add(room)
            for room, vs in s.em.init_writes.items():
                if F in vs and vs[F] != 0:
                    flip_rooms.add(room)
        pruned = {a: {b for b in bs if (a, b) not in grid_edges and b not in flip_rooms}
                  for a, bs in s.edges.items()}
        shallow = M.reachable(pruned, {s.em.cfg.start_room})
        src, need = set(j["source_rooms"]), set(s.required.get(it, set()))
        src_deep, need_deep = not (src & shallow), not (need & shallow)
        if need_deep and not src_deep:                # need deep -> carry IN: gate the flip entries
            flip_ins = {(a, b) for b in flip_rooms for a, bs in s.edges.items() if b in bs}
            for (a, b) in flip_ins:
                out[(a, b)]["items"].add(it)
        elif src_deep:                                # source deep (incl. BOTH deep) -> carry OUT:
            for r in src:                             # gate the source exits. Both-deep is a narrow
                for b in s.edges.get(r, ()):          # window that MAY wall -- placed, not dropped.
                    out[(r, b)]["items"].add(it)
        # else NEITHER deep: no one-time seal lies on the source->need path -- nothing to gate.
        # (Was silently skipped by a non-exhaustive if/elif; now an explicit, documented no-op.)
    return dict(out)


def pocket_frontier(s):
    """Commit edges for the ONE-VISIT-POCKET carry-ins -- the third family `edge_strandings`
    structurally cannot see, and the simplest of the three to place.

    A carry-in row already names its own boundary. The toll edge IS the frontier: it is the one
    crossing after which the pocket's use site can never be reached again, which is precisely what
    made the item strandable. So there is no deep/shallow question to answer as `joint_frontier`
    has to -- the detector did that work when it derived the pocket.

    KQ6's teacup lands on `rm340 -> rm155`, the Realm entrance, joining the coin and the mirror
    that are already demanded there. It cannot wall anything: the cup is freely obtainable at rm480
    before the crossing, which `unsatisfiable` re-checks for every literal anyway.

    LSL2 and KQ4 have no tolls at all, so this returns {} on both and cannot touch their specs."""
    out = defaultdict(lambda: {"items": set(), "groups": []})
    for r in s.toll_strandings():
        if r["pattern"] != "one-visit-pocket-carry-in":
            continue                          # carry-OUTs are a different placement question: the
                                              # boundary is the pocket's EXITS, not its entrance
        a, b = r["toll_edge"]
        out[(a, b)]["items"].add(r["item"])
    return dict(out)


def pocket_carryout_frontier(s):
    """Commit edges for the one-visit pocket CARRY-OUTS -- obtained inside, needed outside, so
    the demand belongs at the pocket's EXITS: the last crossing after which the item's source can
    never be reached again, and before which every player can still walk back for it.

    The guard oracle states the KQ6 instance outright (row 4, user-tested): "we should not let
    you leave the realm of the dead without it" -- the handkerchief (rm630) and the skeleton key
    (rm640) demanded at rm680 -> rm155, beside the cup-filled and mirror-shown flags the register
    half already places there. Their castle-door demands were never the right site: the door is
    four days of walking past the last place a lacking player could comply.

    LSL2 and KQ4 have no tolls at all, so this returns {} on both and cannot touch their specs."""
    out = defaultdict(lambda: {"items": set(), "groups": []})
    for r in s.toll_strandings():
        if r["pattern"] != "one-visit-toll-pocket":
            continue                          # carry-INs are placed at the toll edge instead
        edges = _carryout_frontier(s, r["item"], set(r["pocket"]), r.get("toll_reg"),
                                   tuple(r["toll_edge"]) if r.get("toll_item") is not None
                                   else None)
        for (a, b) in edges:
            out[(a, b)]["items"].add(r["item"])
    return dict(out)


def _carryout_frontier(s, item, pocket, toll_reg=None, toll_edge=None):
    """Edges after which `item`'s SOURCE is lost for good -- the ITEM twin of
    `_settable_frontier`, and deliberately its mirror line for line: same joint (the pocket's
    seal, plus prevRoom when a funnel splits on it), same committed walk, same spent-toll
    compliance fixpoint. The one semantic difference: an item is not a walk dimension, so
    "lacking" cannot be read off a state -- EVERY state at `a` counts as possibly lacking, which
    is the conservative direction (the guard only places where even the worst state can still
    walk back and comply)."""
    sites = set(s.sources.get(item, ())) & set(pocket)
    if not sites:
        return []
    prev = M.prev_room_reg(s.em)
    split = any(prev in req for p in pocket for q in s.edges.get(p, ())
                for (req, _sets, _alts) in s._emeta.get((p, q), ()))
    named = set()
    if toll_reg in s.regs:
        named.add(toll_reg)
    if prev in s.regs and split:
        named.add(prev)
    if not named and toll_edge is not None and prev in s.regs:
        # AN ITEM TOLL IS ITS OWN SEAL. "No seal to judge in" was written for the register
        # spelling (KQ6's Realm), and refused the ITEM spelling outright -- KQ5's temple, where
        # the Staff is SPENT opening the door (`put: 7 214`), had both its carry-out rows
        # detected and NO guard emitted, because rm18's exits name no register. But the fact
        # that makes the pocket one-visit is already in this function's hands: `csucc` below
        # deletes the toll edge from the successor graph, which IS "the toll is spent, the door
        # will not reopen". Only a register toll needs a register dimension; an item toll needs
        # only the committed walk, and `prev` -- promoted in every game -- is the dimension the
        # funnel walk already uses.
        named.add(prev)
    if not named:
        return []                             # no seal to judge in -- nothing provable, refuse
    J = tuple(sorted(named)) if len(named) > 1 else next(iter(named))
    commit = frozenset(named)
    states = s._walk(J, frozenset(), commit=commit)
    succ = {u: s._psucc(J, u, frozenset(), commit) & states for u in states}
    csucc = (succ if toll_edge is None else
             {u: {w for w in succ[u] if not (u[0] == toll_edge[0] and w[0] == toll_edge[1])}
              for u in states})
    safe = {u for u in states if u[0] in sites}
    changed = True
    while changed:
        changed = False
        for u in states:
            if u not in safe and (csucc[u] & safe):
                safe.add(u)
                changed = True
    out = []
    for a in sorted(pocket):
        here = [u for u in states if u[0] == a]
        if not here or not all(u in safe for u in here):
            continue                          # nobody can stand here, or somebody here could not
                                              # comply -- guarding would trap them
        for b in sorted(s.edges.get(a, ())):
            after = [w for u in here for w in succ[u] if w[0] == b]
            if after and not any(w in safe for w in after):
                out.append((a, b))            # crossing loses the last source
    return out


def render_register(s, R, value):
    """`R == value` in the game's own spelling, or None if we cannot write it.

    Registers are ours, not the game's: each store was lowered into synthetic globals so the
    gating machinery could model it without knowing what a flag or a property is. A PATCH has to
    be written back in the game's spelling, so this reverses the lowering PER STORE, using the
    maps each lowering already records. A register with no reversible spelling -- a real global,
    a lowered room local (its spelling would be a local another script cannot see) -- returns
    None rather than a guess.

    THE STORE IS CHECKED BEFORE THE FLAG BLOCK, and the order is load-bearing: the flag base had
    no upper bound, so an OBJECT-PROPERTY register rendered as a phantom flag test -- KQ6's
    reg466 is `(rgDead stateOf690:)`, and it shipped in two compiled guards as
    `(proc913_0 294)`, a flag the game never reads. Caught 2026-08-02 by classifying the shipped
    conditions against the stores' own maps; the spelling below is the game's, via the owner's
    export (`((ScriptID 70 0) stateOf690:)`), so the guard needs no `use` header."""
    ir = getattr(s.em, "ir", None)
    if ir is not None and R in ambiguous_registers(ir):
        return None                        # two stores claim it: no spelling is provably right
    op = getattr(ir, "_obj_prop_index", {}) if ir is not None else {}
    if R in op:
        sn, sel = op[R]
        sc = ir.scripts.get(sn)
        inst = next((o for o in (sc.objects if sc else ()) if sel in getattr(o, "props", {})),
                    None)
        exports = list(getattr(sc, "exports", ()) or ())
        if inst is None or inst.name not in exports:
            return None                        # not a named export -> no cross-script spelling
        test = f"((ScriptID {sn} {exports.index(inst.name)}) {sel}:)"
        if value == 0:
            return f"(not {test})"
        return test if value == 1 else f"(== {test} {value})"
    if R in (getattr(ir, "_room_local_index", {}) if ir is not None else {}):
        return None
    # PROPERTY-WORD bit flags render in their own spelling -- and the check must come before the
    # proc-flag block below for the same reason the object-property check does: that block has no
    # upper bound, so a prop-flag register would render as a phantom proc-flag number otherwise.
    pf = getattr(ir, "_prop_flag_index", {}) if ir is not None else {}
    if R in pf:
        tsel = (getattr(ir, "_prop_flag_sels", None) or {}).get("test")
        (sn, ex), word, bit = pf[R]
        if tsel is None:
            return None
        test = f"((ScriptID {sn} {ex}) {tsel}: {word} {1 << bit})"
        return test if value else f"(not {test})"
    base = getattr(ir, "flag_synth_base", None)
    proc = getattr(ir, "flag_test_proc", None)
    if base is None or proc is None or R < base:
        return None
    # BOUNDED BY THE FLAGS THE GAME ACTUALLY HAS. "At or past the base" is not "is a flag":
    # every store lowered after `lower_flags` allocates further up the same synthetic range,
    # and this fallback claimed all of them. Measured on KQ6, where the mask-global store
    # (global161's four bits) landed at registers 555-558: register 555 rendered as
    # `(proc913_0 383)`, a flag number past the end of a 224-bit array the game never reads
    # there. The 2026-08-02 fix for the same defect reordered the checks above instead of
    # bounding this one, so the next two stores reopened it; `flag_indices` is the set the
    # lowering itself consumed, so a register outside it is refused rather than mis-spelled.
    n = R - base
    known = getattr(ir, "flag_indices", None)
    if known is not None and n not in known:
        return None
    test = f"({proc} {n})"
    return test if value else f"(not {test})"


def pocket_exit_guards(s):
    """Demand, at a one-visit pocket's EXITS, the state you can only reach INSIDE it.

    The other half of a carry-in, and the half that actually closes the softlock. `pocket_frontier`
    makes you BRING the teacup into the Realm of the Dead; nothing yet makes you FILL it, and the
    Styx water can only be drawn in there. The user's ruling names both: "if you go in without the
    teacup you can't win; if you go out without the water in the teacup you can't win."

    ⚠️ AN EXIT GUARD ALONE IS A WALL, and this is why the two are emitted together rather than
    separately. Refuse to leave until a flag is set, and a player who arrived without the means to
    set it is sealed in the pocket forever -- a softlock converted into something strictly worse.
    So the emission precondition is that the ENTRANCE guard demanding what the flag COSTS is going
    out in the same patch. That is checked, not assumed.

    Three more conditions, each derived and each refusing rather than guessing:
      * the write must be CONFINED to the pocket -- if you can set it outside, leaving costs
        nothing;
      * it must be renderable in the game's spelling (see `render_register`);
      * and the guard must sit where the player CAN STILL COMPLY. That is the whole placement
        question and it is the mirror of `droppability_frontier`: a prohibition may only be
        enforced while the item can still be dropped, so a requirement may only be enforced while
        the flag can still be set. The frontier is therefore the last crossing after which no
        writer is reachable -- NOT the pocket's outer boundary.

    KQ6 is the case that forced that distinction, and getting it wrong ships a wall. The Realm's
    outer boundary is `rm155 -> rm200`, and rm155 is a FUNNEL: its two exits are split by the
    previous-room register (`155 -> 600` needs `prev == 340`), so a player arriving from rm680 with
    an empty cup can no longer reach rm660 to fill it. Demanding the flag there would seal them in
    the transit room. One edge earlier, at `rm680 -> rm155`, they can still walk back through
    Charon's bank and fill it -- so that is where the guard belongs.

    The reachability question is a JOINT one and cannot be answered per register: the fact that
    closes rm155 lives in the previous-room register while the flag lives in its own. The joint is
    self-selecting, exactly as `missability._trap_joints` selects one -- it is R together with the
    registers the source room's own out-edges are gated on."""
    entrance = pocket_frontier(s)
    out = []
    for r in s.toll_strandings():
        if r["pattern"] != "one-visit-pocket-carry-in":
            continue
        pocket = set(r["pocket"])
        demanded = entrance.get(tuple(r["toll_edge"]), {}).get("items", set())
        writes, _moved, _exits = s._uses_in(r["item"], pocket)
        for (R, v) in sorted(writes):
            sites = {room for room, vals in s._inroom.get(R, {}).items() if v in vals}
            sites |= {room for room, steps in s._rstep.get(R, {}).items()
                      if any(to == v for (_frm, to) in steps)}
            if not sites or (sites - pocket):
                continue                      # settable outside -> leaving strands nothing
            cost, cond = s._reg_cost(R, {v}), render_register(s, R, v)
            base = []
            if not cond:
                base.append(f"reg{R} has no spelling in the game's own source")
            if not cost:
                base.append(f"reg{R}:={v} costs no item, so no entrance guard can pair with it")
            elif not (cost <= demanded):
                base.append(f"the entrance guard at rm{r['toll_edge'][0]}->rm{r['toll_edge'][1]} "
                            f"does not demand {[s.g.item_name(i) for i in sorted(cost)]}, so this "
                            f"would seal a player who arrived without it INTO the pocket")
            note = (f"the last crossing after which reg{R}={v} can no longer be set -- only "
                    f"{sorted(sites)} sets it, inside the one-visit pocket {sorted(pocket)}, and "
                    f"{s.g.item_name(r['item'])} is what pays for it")
            edges = _settable_frontier(s, R, v, sites, pocket, r.get("toll_reg"),
                                       toll_edge=(tuple(r["toll_edge"])
                                                  if r.get("toll_item") is not None else None))
            if not edges:
                # NO PLACEMENT COULD BE JUSTIFIED, and that is reported rather than returned as
                # silence -- an exit guard vanishing without a word is how a half-closed softlock
                # ships. Say it at the pocket's outer boundary, which is where a reader will look.
                a, b = next(iter(sorted({(p, q) for p in pocket for q in s.edges.get(p, ())
                                         if q not in pocket})), (r["toll_edge"][0],
                                                                 r["toll_edge"][1]))
                out.append({"site": "edge", "from_room": a, "to_room": b, "condition": cond,
                            "items": [], "groups": [], "req": {R: [v]},
                            "pairs_with": list(r["toll_edge"]), "note": note,
                            "refused": base + [
                                f"no crossing is a last chance for reg{R}={v}: judged with "
                                f"committed entry writes and a spent toll, every edge either "
                                f"never loses the writer or would stop a player who can no "
                                f"longer comply where it sits. Refusing is the safe direction -- "
                                f"placing it anyway would wall that player in."]})
                continue
            for (a, b) in edges:
                out.append({"site": "edge", "from_room": a, "to_room": b, "condition": cond,
                            "items": [], "groups": [], "req": {R: [v]},
                            "pairs_with": list(r["toll_edge"]), "refused": list(base),
                            "note": note})
    return out


def _settable_frontier(s, R, v, sites, pocket, toll_reg=None, toll_edge=None):
    """Edges after which `R == v` can never be reached again, and before which it always can.

    The placement rule for a register-valued guard, and the reason it is not simply "the pocket's
    exits": enforcing a requirement somewhere the player can no longer satisfy it is a WALL, which
    this project holds to be worse than the softlock it would close.

    Both halves are demanded, and the second is what rules rm155 out on KQ6:
      * crossing `a -> b` must LOSE the writer -- no state at b can reach one, or there is nothing
        to commit to yet;
      * and EVERY reachable state at `a` that does not already satisfy the guard must still be able
        to reach a writer, or that state's player is refused an exit they cannot earn.

    Judged in the JOINT projection of R with whatever gates the source rooms' own out-edges, since
    a funnel room splits its traffic on a register that is not R."""
    # THREE registers, and each earns its place by a question the others cannot answer:
    #   R          -- has the flag been set;
    #   prevRoom   -- the FUNNEL. A transit room whose out-edges are split by where you came from
    #                 is what makes "I will go back and fill it" false. DERIVED, not named:
    #                 `prev_room_reg` reads the Game loop, and a synthetic emitter with no IR has
    #                 none, so it drops out of the joint and the walk falls back to the scalar one;
    #   the TOLL   -- what makes the pocket one-visit AT ALL. Leave this out and the walk strolls
    #                 back in through the front door and reports that nothing was ever lost. It is
    #                 the pocket's own sealing register, so the row already carries it; nothing
    #                 here picks a register by name or number.
    # Bounded at three, and every member is supplied by the finding rather than searched for.
    prev = M.prev_room_reg(s.em)
    split = any(prev in req for p in pocket for q in s.edges.get(p, ())
                for (req, _sets, _alts) in s._emeta.get((p, q), ()))
    named = {R}
    if prev in s.regs and split:
        named.add(prev)
    if toll_reg in s.regs:
        named.add(toll_reg)
    J = tuple(sorted(named)) if len(named) > 1 else (R,)
    idx = J.index(R)
    # COMMITTED, not permissive. This is the walk whose whole product is a placement PROOF, and
    # the detection default credits the player with movement the game does not have: an in-room
    # write is an optional successor, so the walk kept a state outside the pocket with the seal
    # still clear and strolled back in to "comply later" -- which is why every register-valued
    # exit guard refused. `commit` forces exactly the writes that are unconditional on arrival
    # (`em.init_writes` -- the class is derived, no register is named), so a one-visit pocket's
    # seal actually seals. Detection walks stay permissive; only this proof changes direction.
    commit = frozenset(J)
    states = s._walk(J if len(J) > 1 else R, frozenset(), commit=commit)

    def val(u):
        return u[1][idx] if len(J) > 1 else u[1]
    succ = {u: s._psucc(J if len(J) > 1 else R, u, frozenset(), commit) & states
            for u in states}
    # An ITEM toll commits the same way an entry write does, in the other store: the row
    # established that the crossing CONSUMES its payment and nothing re-supplies it (that is what
    # made the pocket one-visit at all), so "walk back in and comply" is not available to any
    # player this guard addresses. The walk cannot say "once" -- it is memoryless -- but it can
    # say the next-best true thing: compliance may not be proved THROUGH a second crossing.
    # `states` keeps the toll edge (the first crossing is real; it is how the pocket's states
    # exist); only the compliance fixpoint below loses it. Register-sealed pockets need nothing
    # here -- `commit` already keeps their seal honest -- so this is exactly the item-toll half.
    csucc = (succ if toll_edge is None else
             {u: {w for w in succ[u] if not (u[0] == toll_edge[0] and w[0] == toll_edge[1])}
              for u in states})
    safe = {u for u in states if u[0] in sites}          # standing where the write can happen
    changed = True
    while changed:                                        # ...or able to walk to one
        changed = False
        for u in states:
            if u not in safe and (csucc[u] & safe):
                safe.add(u)
                changed = True
    out = []
    for a in sorted(pocket):                              # the guard belongs to the pocket it
        #   protects; past its boundary "the writer is unreachable" is true of the whole map and
        #   says nothing about a commitment.
        lacking = [u for u in states if u[0] == a and val(u) != v]
        if not lacking or not all(u in safe for u in lacking):
            continue                                      # nobody to guard, or somebody here could
        if not any(u[0] == a and val(u) == v for u in states):
            # The demanded value is UNPRESENTABLE here: no reachable committed state at `a`
            # carries it, so the guard would refuse every player -- winners included. Play-found
            # (KQ6 finding #15, 2026-08-05): rm690's only live exit rewrites stateOf690 to 0 on
            # the way out, so the "shown" value the rm680->rm155 guard demanded existed at the
            # site for NOBODY, and the placed arm-event suppressed the win ride and hung the
            # game. Being able to reach the writer is not compliance; HOLDING its value at the
            # crossing is, and nobody can.
            continue
                                                          # not comply -- guarding traps them
        for b in sorted(s.edges.get(a, ())):
            after = [w for u in lacking for w in succ[u] if w[0] == b and val(w) != v]
            if after and not any(w in safe for w in after):
                out.append((a, b))                        # crossing loses the last writer, and
                                                          # only for the players who still lack it
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


def fold_respell(s, a, b, rec):
    """Re-spell a frontier spec's conjuncts by their CONSUMERS' OWN reading -- the owner-store
    correction ([[an-item-some-armings-demand-is-not-a-gate]]'s rule applied to edge guards).

    KQ5's roc edge is the case that forced it (USER playtest prep, 2026-08-18b): the lamb's
    need past rm40->rm41 is rm42's hatch fold, which reads `owner(19) == 34` -- the eagle was
    FED, at rm34, BEHIND the edge -- while the spec spelled it `(gEgo has: 19)`. That demands
    the exact state the fold condemns (carrying it across = nothing can feed the eagle any
    more) and turns back the winning one (banked, hands empty): the Spinach_Dip shape, caught
    before it shipped to play.

    The derivation, per unit: the need rooms PAST the edge decide the spelling.
      * a need room whose demand for the item is an `ownedby_death_folds` row is satisfied by
        THAT room's own read -- the owner test over the fold's destinations. Possession is an
        alternative only when some producer of (item -> dest) lies past the edge (there is
        still somewhere to bank it); producers are the `put:` sites, handler and machine both.
      * a need room the folds do not explain keeps the possession spelling -- both can be
        demanded at once (carry for the possession need AND banked for the fold), which is the
        conservative conjunction.
      * a GROUP converts only when EVERY past-edge need room is fold-covered for some member
        -- the group rode in on a member's fold room, and that room accepts exactly what its
        fold names (rm42 does not take the pie; `(or (has 2) (has 19))` there guards nothing).
        Any unexplained room keeps the group as spelled.
    An owner atom subsumed by a kept possession conjunct is dropped; one whose producers are
    unreachable EVERYWHERE is a refusal, not a guard. Games with no fold rows (all four frozen
    ones, measured) pass through untouched by construction.

    Returns (rec2, atoms, refusals)."""
    folds = {}
    for r in s.ownedby_death_folds():
        folds.setdefault(r["need_room"], {}).setdefault(r["item"], set()).add(r["dest"])
    if not folds:
        return rec, [], []
    fwd = s.rooms_after(b)
    prods = {}                     # (item, dest) -> rooms that put it there
    for row in list(getattr(s.em, "handler_drops", ())):
        room, _sc, it, _g, dest = row
        prods.setdefault((it, dest), set()).add(room)
    for row in list(getattr(s.em, "machine_moves", ())):
        room, _sc, it, _g, dest, _inst = row
        prods.setdefault((it, dest), set()).add(room)

    def atom_for(it, R):
        parts = []
        for dst in sorted(folds[R][it]):
            parts.append("(== ((gInv at: %d) owner:) %d)" % (it, dst))
        atom = parts[0] if len(parts) == 1 else "(or %s)" % " ".join(parts)
        past = any(prods.get((it, dst), set()) & fwd for dst in folds[R][it])
        anywhere = any(prods.get((it, dst), set()) & s.reach_rooms for dst in folds[R][it])
        return atom, past, anywhere

    items2, atoms, refused = [], [], []
    for it in sorted(rec["items"]):
        nr = s._unit_need_rooms(frozenset({it})) & fwd
        fold_rooms = {R for R in nr if it in folds.get(R, {})}
        poss = nr - fold_rooms
        if poss or not fold_rooms:
            items2.append(it)
        for R in sorted(fold_rooms):
            atom, past, anywhere = atom_for(it, R)
            if not anywhere:
                refused.append("owner demand for item %d at rm%d has no reachable producer"
                               % (it, R))
                continue
            if it in items2 and past:
                continue           # `(gEgo has: it)` already implies this atom's alternative
            if past:
                atom = "(or (gEgo has: %d) %s)" % (it, atom)
            atoms.append(atom)
    groups2 = []
    for g in rec["groups"]:
        nr = s._unit_need_rooms(frozenset(g)) & fwd
        if nr and all(any(m in folds.get(R, {}) for m in g) for R in nr):
            for R in sorted(nr):
                parts = []
                for m in sorted(g):
                    if m in folds.get(R, {}):
                        atom, past, anywhere = atom_for(m, R)
                        if not anywhere:
                            continue
                        if past:
                            atom = "(or (gEgo has: %d) %s)" % (m, atom)
                        parts.append(atom)
                if parts:
                    atoms.append(parts[0] if len(parts) == 1
                                 else "(or %s)" % " ".join(parts))
        else:
            groups2.append(g)
    # ...and the fold demands THIS CROSSING seals, whether or not the requirement maps
    # carried the item here. The lamb taught the gap twice in one day: with the sled one-way
    # derived, the lamb's reob boundary moved to rm32->rm33 and the roc edge silently lost
    # `owner(19)==34` -- but crossing rm40->rm41 is what kills the eagle-feed's producers,
    # so a player who crossed the sled CARRYING the lamb (legal there) and never fed would
    # sail past an unguarded roc into the nest death. A fold row whose need room lies ahead
    # of this edge while EVERY producer of its value lies behind is this edge's demand, in
    # the fold's own owner spelling; rows whose producers survive past the edge are some
    # later crossing's business (or a carry-in context's), not this one's.
    for r in s.ownedby_death_folds():
        if r["need_room"] not in fwd:
            continue
        rooms_p = set()
        for (it2, dst2) in {(r["item"], r["dest"])}:
            rooms_p |= prods.get((it2, dst2), set())
        if not rooms_p or rooms_p & fwd or not rooms_p & s.reach_rooms:
            continue
        atom = "(== ((gInv at: %d) owner:) %d)" % (r["item"], r["dest"])
        atoms.append(atom)
    seen, deduped = set(), []
    for x in atoms:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return {"items": set(items2), "groups": groups2}, deduped, refused


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
    scores = designer_score(s)
    forbidden = set()
    for gt in survival_gates(s):
        _, cn, _ = factor(gt["alts"])
        forbidden |= cn
    # A SPEND THE MARKET ALREADY REFUSES GETS NO RETRACTION (USER-found at the eagle,
    # 2026-08-18b: "just kidding" played, then the full feed scene, then the eagle flew off
    # unfed with the pie retained). An IMPURE sink -- the put: arms the scene -- is exactly
    # what the retraction cannot hold: withholding the disposal lets the commitment run
    # anyway, and by editing first it also consumed the market wrap's own anchor, so the
    # refusal that should have preceded the scene never placed. The market's case wrap
    # refuses BEFORE anything arms; where it covers a (script, item), it is the whole
    # remedy. Pure jokes (the EATs) keep their kinder retraction -- the market defers to
    # those in the other direction, and the two exclusions together are a partition.
    covered = {(r["script"], r["item"]) for r in market_remedies(s)}
    out = []
    for d in s.dangerous_sinks():
        it = d["item"]
        if (d["script"], it) in covered:
            continue
        refused = ([f"{s.g.item_name(it)} is fatal to CARRY -- keeping it would trade one "
                    f"softlock for another"] if it in forbidden else [])
        score = scores.get((d["script"], it))
        dest = d.get("dest", -1)              # the game's disposal destination (LSL2 -1, KQ4 999),
        #                                       DERIVED from the actual put/moveTo, not assumed.
        out.append({"site": "consumption", "room": d["room"], "script": d["script"],
                    "corroboration": (None if score is None else f"designer_score={score}"),
                    "item": it, "op": "remove_consumption", "dest": dest,
                    "edit": f"delete `(gEgo put: {it} {dest})`",
                    "why": f"wastes {s.g.item_name(it)}, still needed at "
                           f"rm{d['still_needed_at']} and not re-obtainable",
                    "refused": refused})
    return out


def market_remedies(s):
    """Refuse the payments the market condemns -- one spec per `market_squeezes` row.

    The remedy the USER approved (2026-08-17, the design; 2026-08-17b, the build): guard the
    three shops, never the gypsy or the princess -- the tight slots must keep taking their
    tokens, and every row the detector emits is a spend at a slot that merely TOLERATES the
    token while some tight consumer starves. Because the market proved each row fatal in EVERY
    live state (holding the token pins the residual enough that no ordering saves the spend),
    the guard needs no runtime re-obtainability conjunct: it is a plain refusal of that (site,
    token) payment, routed through the game's own refusal form.

    PLACEMENT IS THE CASE, NOT THE MACHINE. A shop's cutscene (`soldCloak`) is armed from one
    switch case per accepted token, so the wrap selects the case whose head literal IS the
    condemned item and holds its whole body -- `trigger.wrap_forbidden_case`. The `anchor`
    names the committed act inside that case: the `setScript:` arming for a purchase, the
    handler's own `put:` for a throw or an eat (where the clause IS the act). The condition
    keeps the corpus-wide `(not (gEgo has: X))` spelling; inside item X's own case it is
    identically false, which is exactly the unconditional refusal the matching derived.

    ⛔ A PURE SINK'S RETRACTION OUTRANKS THE MARKET'S REFUSAL, and the market defers to it.
    KQ5's pie is the case: eating it is a pure sink (message + `put:`, nothing else), so
    `sink_remedies` already withholds the disposal while LETTING THE JOKE PLAY -- strictly
    kinder than a refusal. Wrapping the same case here as well stacked a refusal OUTSIDE the
    retraction and full mode never reached the joke again (measured on the emitted source).
    The deferral is exactly the pure-sink set: an IMPURE spend of the same item (the pie fed
    to the eagle arms `feedEagle`, so the retraction cannot place there) keeps its market wrap.

    Emits nothing on a game whose market has no fatal spends -- LSL2, KQ4, KQ6 and LB2 today,
    measured -- so the frozen surfaces carry an empty key, not an absent one."""
    # ...and "a retraction exists" means BOTH halves: the clause is pure AND `dangerous_sinks`
    # actually carries the row `sink_remedies` will act on. The lamb's EAT is pure too, but its
    # danger is stated only by the market (the sink sweep excuses it through the eagle's group),
    # so no retraction ever ships for it and deferring would leave the spend unguarded.
    pure = {(p["script"], p["item"]) for p in s.pure_sinks()}
    remedied = pure & {(d["script"], d["item"]) for d in s.dangerous_sinks()}
    out = []
    for r in s.market_squeezes():
        if r.get("inst") is None and (r["script"], r["item"]) in remedied:
            continue          # the sink retraction already holds this exact clause, more kindly
        anchor = (r"setScript:\s*%s\b" % re.escape(r["inst"])) if r.get("inst") else \
                 (r"put:\s*%d\b" % r["item"])
        out.append({
            "site": "market", "room": r["at_room"], "script": r["script"],
            "machine": r.get("inst"), "item": r["item"], "forbid": [r["item"]],
            "anchor": anchor,
            "condition": f"(not (gEgo has: {r['item']}))",
            "why": (f"paying with {s.g.item_name(r['item'])} here starves rm{r['starves']} -- "
                    f"the market has no assignment left for "
                    f"{[s.g.item_name(t) for t in r['starved_accepts']]}"),
            "refused": []})
    # ...and the IMPURE dangerous sinks the retraction cannot hold. A pure sink's cure is the
    # retraction above (strictly kinder: the joke plays, the item stays); an impure spend does
    # more than destroy -- KQ5's fish thrown at the cat arms the chase machine and BANKS the
    # pool value rm86's fork reads -- so withholding its `put:` would advance the scene while
    # unfilling the bank it claims to fill: unsound, not merely unplaceable. The remedy is the
    # same market-case refusal, and it needs no matching for its un-walling: `dangerous_sinks`
    # proved this spend LOSES THE GAME, and a winning line never contains a losing move, so
    # refusing it cannot take anything from a winning player. (KQ5's cat scene also arms only
    # under a non-refused pool member in hand -- the refusal never strands the scene itself.)
    #
    # TRADES ARE EXCLUDED: a clause that also GETs hands the player the other side of an
    # exchange (KQ6's lamp peddler, user-ruled working-as-designed), and whether an exchange
    # starves anything is the matching's question, judged in the owner graph
    # ([[a-trade-is-a-destruction]]) -- never refused off a sink row.
    covered = {(r["script"], r["item"]) for r in s.market_squeezes()}
    get_keys = {s._clause_key(room, g) for room, _sc, _it, g in s.em.handler_gets}
    for d in s.dangerous_sinks():
        key = (d["script"], d["item"])
        if key in pure or key in covered:
            continue      # the retraction (kinder) or a market row (same wrap) holds it already
        covered.add(key)
        if any(s._clause_key(room, g) in get_keys
               for room, sc, it, g, _dst in s.em.handler_drops
               if sc == d["script"] and it == d["item"]):
            continue      # a TRADE -- the matching's territory, never refused from a sink row
        out.append({
            "site": "market", "room": d["at_room"], "script": d["script"],
            "machine": None, "item": d["item"], "forbid": [d["item"]],
            "anchor": r"put:\s*%d\b" % d["item"],
            "condition": f"(not (gEgo has: {d['item']}))",
            "why": (f"spending {s.g.item_name(d['item'])} here loses the game -- still needed "
                    f"at rm{d['still_needed_at']}, not re-obtainable, and the clause does more "
                    f"than destroy, so the retraction cannot hold it"),
            "refused": []})
    return out


def window_remedies(s):
    """Re-open the one-shot window until its demand is BANKED -- one spec per `window_closures`
    window, the remedy half of the fold+closure pair.

    KQ5's cat chase is the case: flag 83 goes up when the chase STARTS (rm006::doit), not when
    it is won, so losing the race closes the only door to the state rm86's kidnap fork demands
    (some throwable owned by room 6) -- and the punishment is a timer death in a cellar hours
    later. The design is the USER-shaped two-clause form (2026-08-14, clause 2 ruled REQUIRED):

      1. HOLD every durable closer's raise behind V, the bank test -- the flip waits until the
         demand it would seal is already banked. The chase still plays; losing no longer closes
         anything, so the player can walk out and try again.
      2. Conjoin the SAME V, disjunctively, onto every READ of the closer -- "the window has
         closed" becomes "the window has closed OR the bank is filled". With 1, that is the
         whole meaning correction: the closer flag stops meaning "the chase started" and starts
         meaning "the mouse business is settled". It is also what enforces the standing rule
         that ⛔ a patched chase must NEVER replay after success: the arming that tests the
         closer now refuses while V holds.

    V is spelled in the CONSUMER'S OWN idiom -- rm086 reads the bank as
    `(== ((gInv at: 8) owner:) 6)` over the pool, and the guard repeats that reading exactly,
    which is [[a-trade-is-a-destruction]]'s owner graph paying off at run time a second time
    (the market's re-obtainability conjunct was the first).

    A window is remediable only when EVERY closer is accounted for -- one unheld closer still
    shuts it and the patch would claim a cure it does not deliver. Two accounts exist:
      - DURABLE: a lowered boolean flag raised to its closing value; hold its raise (the set
        proc the flag derivation already named) and strengthen its reads. Only the raise
        polarity (w == 1) has a derived spelling today; anything else is refused, not guessed.
      - PER-VISIT: a lowered ROOM LOCAL whose recorded entry reset differs from the closing
        value -- the script reloads on entry and the latch re-opens by itself (rm006's local0,
        "you lost this race", holds only until the player walks back in). No hold is needed,
        and none would have a cross-script spelling anyway.
    Anything else -- an un-spellable store, a local with no differing reset, a clear-polarity
    closer -- lands in `refused` and the whole spec ships unplaceable rather than half-held.

    The holds are SILENT guard kinds (nothing is refused to the player's face; a scene arms or
    does not), so lite behaves as full and only stock bypasses -- the patcher applies that
    dispatch at placement time; the conditions emitted here stay mode-free (test_mode pins
    this file out of the mode machinery)."""
    rows = s.window_closures()
    if not rows:
        return []
    ir = getattr(s.em, "ir", None)
    rli = getattr(ir, "_room_local_index", None) or {}
    resets = getattr(ir, "_room_local_resets", None) or {}
    base = getattr(ir, "flag_synth_base", None)
    known = getattr(ir, "flag_indices", None) or frozenset()
    setp = getattr(ir, "flag_set_proc", None)
    testp = getattr(ir, "flag_test_proc", None)
    windows = {}
    for r in rows:
        key = (tuple(tuple(x) for x in r["demand_group"]), r["need_room"])
        windows.setdefault(key, r)
    out = []
    for (group, need_room), row in sorted(windows.items(), key=lambda kv: kv[0][1]):
        members = sorted({tuple(x) for x in group})
        conds = ["(== ((gInv at: %d) owner:) %d)" % (it, dst) for it, dst in members]
        vcond = conds[0] if len(conds) == 1 else "(or %s)" % " ".join(conds)
        holds, per_visit, refused = [], [], []
        for (R, w) in sorted({tuple(c) for c in row["closes_on"]}):
            if R in rli:
                sn, idx = rli[R]
                init = resets.get(sn, {}).get(R)
                if init is not None and init != w:
                    per_visit.append([R, "local%d of script %d resets to %d on entry"
                                      % (idx, sn, init)])
                else:
                    refused.append("closer reg%d: room local with no differing entry reset -- "
                                   "nothing re-opens it" % R)
                continue
            if (base is not None and R >= base and (R - base) in known
                    and w == 1 and setp and testp):
                holds.append({"register": R, "trap": w, "flag": R - base,
                              "set_proc": setp, "test_proc": testp})
                continue
            refused.append("closer reg%d=%d has no holdable spelling" % (R, w))
        if not holds and not refused:
            refused.append("every closer resets on re-entry -- no durable closure to hold")
        out.append({"site": "window", "need_room": need_room,
                    "items": [it for it, _d in members],
                    "banked_at": sorted({dst for _it, dst in members}),
                    "producer_rooms": row["producer_rooms"],
                    "condition": vcond, "holds": holds, "self_resetting": per_visit,
                    "why": ("the window these items are banked through closes by itself; "
                            "hold the closure until banked, and never re-arm once banked"),
                    "refused": refused})
    return out


def fuse_arming_remedies(s):
    """The whale-shape arm hold for `missability.fuse_death_armings` rows (docs/KQ5-ORACLE.md
    §23): the encounter must not ARM until the player can survive it. The spawn procedure's
    own arming condition gains the derived demand -- ONE wrap at the proc covers every call
    site, and a withheld spawn is indistinguishable from the stock no-spawn roll (KQ5's
    proc550_16 spawns nothing 20% of the time by the game's own design), which is the
    arm-event soundness premise satisfied structurally: a spawnless castle room IS the open
    play next door.

    The condition renders FACTORED: atoms every demand alternative shares are hoisted out of
    the OR, so KQ5 ships `(and (proc0_12 63) (gEgo has: 24) (or (proc0_12 62) (gEgo has:
    37)))` -- the USER's ruling spelled in the game's own flag test -- rather than the
    expanded DNF. Same truth table; the site stays readable.

    Refused, never half-shipped: no proc to wrap (the spawn is not proc-shaped), a flag
    demand with no derivable flag-test spelling, or an empty demand."""
    ir = s.em.ir
    testp = getattr(ir, "flag_test_proc", None)
    out, seen = [], set()
    for r in s.fuse_death_armings():
        alts = [frozenset([("flag", f) for f in a["flags"]]
                          + [("own", i) for i in a["items"]])
                for a in r["demand_alts"]]
        key = (r["machine"], tuple(sorted(tuple(sorted(a)) for a in alts)))
        if key in seen or not alts:
            continue
        seen.add(key)
        refused = []
        proc = r.get("arm_proc")
        if not proc:
            refused.append("the spawn is not proc-shaped -- no single arming site to wrap")
        if any(k == "flag" for a in alts for (k, _v) in a) and not testp:
            refused.append("a flag demand with no derivable flag-test spelling")

        def _tok(t):
            k, v = t
            return "(%s %d)" % (testp, v) if k == "flag" else "(gEgo has: %d)" % v

        common = frozenset.intersection(*alts)
        rests = [sorted(a - common) for a in alts]
        parts = [_tok(t) for t in sorted(common)]
        if all(rests):
            ors = ["(and %s)" % " ".join(_tok(t) for t in rr) if len(rr) > 1 else _tok(rr[0])
                   for rr in rests]
            parts.append(ors[0] if len(ors) == 1 else "(or %s)" % " ".join(ors))
        # an empty rest means that alternative IS the common core -- the OR is vacuous
        if not parts:
            refused.append("empty demand -- nothing to hold the arming on")
        cond = (parts[0] if len(parts) == 1 else "(and %s)" % " ".join(parts)) \
            if parts else None
        out.append({"site": "fuse-arm",
                    "script": proc["script"] if proc else None,
                    "proc": proc["name"] if proc else None,
                    "machine": r["machine"], "arm_rooms": r["arm_rooms"],
                    "items": sorted({i for a in r["demand_alts"] for i in a["items"]}),
                    "flags": sorted({f for a in r["demand_alts"] for f in a["flags"]}),
                    "condition": cond, "fuse": r["fuse"], "death": r["death"],
                    "why": "an unanswered encounter arms a remote death fuse (fuse %s -> "
                           "phase %s -> %s); the encounter must not arm until survivable"
                           % (r["fuse"], r["phases"], r["death"]),
                    "refused": refused})
    return out


def fold_carryins(s):
    """Owner-value demands on the CROSSING an entry-fold's context names -- patch B's derivation.

    `ownedby_death_folds` states a demand the fold's own room can no longer satisfy: arriving
    at KQ5's rm86 with `prev == 85` (the kidnap), some throwable must already be OWNED by room
    6 or `yourStuck` is a pure-timer death -- and the Rope is sourced INSIDE rm86, so the
    kidnap is mandatory and a gate cannot live there. But an entry-fold whose context names
    the previous room IS a fact about one crossing: `{12: 85}` means the losing arm arms
    exactly on rm85 -> rm86, so the demand's last controllable moment is that crossing --
    the same doctrine as `sink_survival_carryins` (the mists), in the owner store's spelling.

    The condition is the CONSUMER'S OWN reading (`(== ((gInv at: X) owner:) 6)` over the
    demand group -- rm086's kidnap fork spells it exactly so), the same rendering
    `window_remedies` ships; the patcher derives the game's `gInv` global at placement.

    A-BEFORE-B, derived: if the demanded value's producers sit behind a window that CLOSES
    (`window_closures` claims the group), this demand is only satisfiable in a game where the
    window remedy holds that window open -- so the spec requires a PLACEABLE `window_remedies`
    row for the same group and refuses without one. Refusing the kidnap while the bank can
    never be filled again would wall a mandatory crossing forever, which is worse than the
    softlock. A group no closure claims keeps its producers alive by the closure detector's
    own liveness reading, and carries no gate.

    STATE-FORK rows (KQ5's rm42 hatch: context {}) name no crossing and emit nothing --
    their demands already ride the item frontiers (the roc edge carries the lamb)."""
    prev = M.prev_room_reg(s.em)
    closures = {(tuple(sorted(tuple(x) for x in r["demand_group"])), r["need_room"])
                for r in s.window_closures()}
    placeable = {(tuple(sp["items"]), sp["need_room"]): not sp["refused"]
                 for sp in window_remedies(s)}
    out, seen = [], set()
    for r in s.ownedby_death_folds():
        ctx = r.get("context") or {}
        a = ctx.get(prev)
        if a is None:
            continue
        b = r["need_room"]
        group = sorted({tuple(x) for x in r["demand_group"]})
        if (a, b, tuple(group)) in seen:
            continue
        seen.add((a, b, tuple(group)))
        conds = ["(== ((gInv at: %d) owner:) %d)" % (it, dst) for it, dst in group]
        cond = conds[0] if len(conds) == 1 else "(or %s)" % " ".join(conds)
        refused = []
        # THE CHASE EXCLUSION, ACROSS THE ROOM SEAM (USER-prompted, 2026-08-18b: "why are we
        # turning you back in the first place?"). A fold whose context room ARMS AN EGO-CHASE
        # under the NEGATION of this very demand is not an independent trap -- it is the
        # chase's CATCH, staged one screen over (KQ5's yeti: rm036's init arms `chaseEgo` iff
        # `owner(Pie) != 36`, so every crossing this fold condemns is made mid-chase, and the
        # rm35 kill is the yeti catching a player who ran with the counter in hand). The
        # exclusion's own rationale applies uniformly: a race the player can decline -- feed,
        # duck, or not run -- gets no gate, and the death is Sierra's lesson (the KGB-beach
        # class). The demand stays a FINDING (the row is how the pie's necessity is known);
        # only the crossing guard is declined, visibly.
        for info in s.em.machines:
            if info.get("room") != a or not info.get("chase_states"):
                continue
            for (_k, eg) in (list(info.get("entries", ()))
                             + list(info.get("init_entries", ()))):
                spine = M._conj_spine([eg] if not isinstance(eg, list) else eg)
                if any(isinstance(x, M.GNot) and M._is_owner_atom(x.kid)
                       and (x.kid.var, x.kid.value) in set(map(tuple, group))
                       for x in spine):
                    refused.append(
                        "the fold is rm%d's chase catching you (its hunter arms on the "
                        "complement of this demand) -- a declinable race, no gate owed" % a)
                    break
            if refused:
                break
        gkey = (tuple(group), b)
        ikey = (tuple(it for it, _d in group), b)
        if gkey in closures and not placeable.get(ikey):
            refused.append("the window producing this value closes and no placeable window "
                           "remedy holds it open -- demanding it here would wall the crossing")
        out.append({"site": "edge", "from_room": a, "to_room": b, "condition": cond,
                    "items": [], "groups": [], "owner_group": [list(g) for g in group],
                    "why": (f"arriving at rm{b} from rm{a} is unsurvivable unless the value "
                            f"is already banked -- the fold's demand rides its crossing"),
                    "refused": refused})
    return out


def resource_remedies(s):
    """Prevent RESOURCE-EXHAUSTION softlocks by deleting the WASTEFUL degradation write -- the
    fourth store's analogue of `sink_remedies` (which deletes a wasteful item DROP).

    A degradation is wasteful when its clause arms nothing (the pure-sink test, per CLAUSE). KQ4's
    bow spends an arrow shooting into the air (`shootBow`, which arms nothing), while the unicorn and
    Lolotte shots ARM their machines -- so ONLY the into-air increment is removed and the two-arrow
    puzzle stays intact. A single-valued 'dead' property (the shovel's broken flag `loop:=1`) IS the
    degradation itself -- breaking a tool is never productive -- so it is removed outright and the
    shovel never snaps. Only items `resource_exhaustion` actually FLAGS are touched; LSL2 has none,
    so this returns []. The object name rides along because a Main-scope write (`shootBow`) lives in
    its own file, not Main.sc."""
    flagged = {r["item"] for r in s.resource_exhaustion()}
    if not flagged:
        return []
    out = []
    for tup in getattr(s.em.ts, "item_prop_writes", ()):
        room, it, prop, val, g, *rest = tup
        if it not in flagged:
            continue
        sp = M._IPROP_SPEC.get((it, prop), {})
        if sp.get("counter"):
            if val != "inc" or s._clause_productive(room, g):
                continue                       # keep productive shots; drop only the arms-nothing waste
            why = f"spends an arrow while arming nothing -- {s.g.item_name(it)} needed later"
        elif val in sp.get("values", ()) and len(sp.get("values", ())) == 1:
            why = f"degrades {s.g.item_name(it)} to an unusable state, still needed elsewhere"
        else:
            continue                           # re-settable property (the re-baitable pole) -- no
        out.append({"site": "resource", "item": it, "item_name": s.g.item_name(it),
                    "property": prop, "value": val, "room": room,
                    "script": rest[0] if rest else None, "counter": bool(sp.get("counter")),
                    "op": "remove_degradation", "why": why})
    return out


def guard_specs(s):
    """ONE spec per placement site, merging both derivations.

    Sites are of two kinds. A `gate` is where the game itself tests you and branches into winning
    and losing futures (rm138's raft). An `edge` is a structural commit where nothing is tested at
    all and you simply cannot come back (rm57 boarding). Negative literals are RELOCATED off the
    gate to the last edge where the item is still droppable -- enforcing them at the gate is the
    permanent-wall bug."""
    specs = []
    # frontier_guards (edge strandings) + joint_frontier (grid/one-time-flag strandings), unioning
    # items on a shared commit -- KQ4's whale swallow rm31->44 gets the feather (edge) AND the fish
    # (joint), so one guard demands both before you are swallowed.
    frontier = frontier_guards(s)
    rff = register_flip_frontier(s)
    for src in (joint_frontier(s), pocket_frontier(s), pocket_carryout_frontier(s), rff):
        for (a, b), rec in src.items():
            if (a, b) in frontier:
                old = frontier[(a, b)]
                merged = {"items": set(old["items"]) | rec["items"],
                          "groups": old["groups"] + rec.get("groups", [])}
                # a STAGED claim (demand only pre-flip) merging with an unstaged one, or with
                # a different stage, cannot share one condition -- refuse loudly downstream
                if old.get("stage") != rec.get("stage") \
                        or old.get("stage_conflict") or rec.get("stage_conflict"):
                    merged["stage_conflict"] = True
                elif rec.get("stage") is not None:
                    merged["stage"] = rec["stage"]
                frontier[(a, b)] = merged
            else:
                frontier[(a, b)] = rec
    for (a, b), rec in sorted(frontier.items()):
        # Drop the literals that cannot be held AT this edge before asking whether the rest is
        # satisfiable -- demanding one of those does not close a softlock, it walls the route.
        # Reported, never silent: a guard that quietly asks for less is how an under-guard ships.
        why = unholdable_at(s, a, b, set(rec["items"]))
        gone = set(why)
        # ...plus what the stranding core already dropped from its own rows at this edge, for the
        # same reasons: the row filter must not turn a reported drop into a silent one, so those
        # reasons ride through to dropped_incompatible/dropped_why. ANNOTATION ONLY -- a row drop
        # is not in this rec by construction, and it must not prune a GROUP that legitimately
        # shares a member with it, so only `why`/`gone` (this spec's own exclusions) prune.
        ann = {**getattr(s, "_stranding_drops", {}).get((a, b), {}), **why}
        if gone:
            rec = {"items": set(rec["items"]) - gone,
                   "groups": [g for g in rec["groups"] if not (g & gone)]}
        # the owner-store correction: past-edge needs that are fold demands are spelled by
        # their consumer's own reading (see fold_respell) -- the possession conjuncts keep
        # their satisfiability check below, the owner atoms carry their own refusals.
        rec2, fold_atoms, fold_refused = fold_respell(s, a, b, rec)
        bad = unsatisfiable(s, a, b, rec2) + fold_refused
        base = render_frontier(rec2)
        terms = ([base] if base else []) + fold_atoms
        cond = (terms[0] if len(terms) == 1 else "(and " + " ".join(
            ([base[5:-1]] if base and base.startswith("(and ") else ([base] if base else []))
            + fold_atoms) + ")") if terms else None
        stage = rec.get("stage")
        if rec.get("stage_conflict"):
            bad = bad + ["stage conflict: a staged (pre-flip-only) demand and an unstaged one "
                         "met on this edge; demanding at the wrong moment walls a player, so "
                         "nothing ships until the claims are reconciled"]
        elif stage is not None and cond:
            # THE STAGED FLIP EDGE (see register_flip_frontier.staged_flip_edges): the demand
            # binds only on the COMMITTING crossing -- the one made pre-flip. A post-flip
            # player re-crossing holds none of the sealed items by construction, and an
            # unstaged demand here would wall them on the wrong side (KQ5: the returning
            # sailor, shell-less forever, refused the boat home). The stage is spelled in the
            # game's own flag test so the wrap reads at the site exactly what the model
            # proved: `(or (proc0_12 54) <items>)` -- already committed, or fully equipped.
            R2, _v2 = stage
            ir2 = s.em.ir
            base2 = getattr(ir2, "flag_synth_base", None)
            testp2 = getattr(ir2, "flag_test_proc", None)
            if base2 is not None and testp2 and R2 >= base2:
                cond = "(or (%s %d) %s)" % (testp2, R2 - base2, cond)
            else:
                bad = bad + ["staged flip edge: no flag spelling derives for register %r, and "
                             "an unstaged demand walls the post-flip crossing" % (R2,)]
        sp = {"site": "edge", "from_room": a, "to_room": b,
              "condition": cond,
              "items": sorted(rec2["items"]), "groups": [sorted(g) for g in rec2["groups"]],
              "refused": bad}
        if fold_atoms:
            sp["owner_atoms"] = fold_atoms
        rec = rec2
        if ann:
            sp["dropped_incompatible"] = sorted(ann)
            sp["dropped_why"] = "cannot be held here: " + "; ".join(
                sorted({f"{s.g.item_name(i)} -- {r}" for i, r in ann.items()}))
        if not rec["items"] and not rec["groups"] and not fold_atoms:
            # Everything this edge would have demanded is unholdable here, so there is no guard to
            # place -- but say so. Dropping the row silently is how an edge stops being guarded
            # without anyone noticing; `refused` is the channel that already exists for "we
            # deliberately emit nothing", and every reporting path prints it.
            sp["refused"] = [sp["dropped_why"] + " -- nothing left to demand at this edge"]
        specs.append(sp)
    # ...and the OWNER-VALUED demands the entry-folds put on their own crossings (patch B):
    # conjoined onto the frontier spec for the same edge when one exists -- rm85->rm86 demands
    # the Hammer (the flip frontier) AND the banked throwable (the fold) in ONE guard, one no --
    # appended standalone otherwise, refusals included so an unplaceable demand stays visible.
    for fc in fold_carryins(s):
        host = next((sp for sp in specs if sp["site"] == "edge" and not sp["refused"]
                     and sp["from_room"] == fc["from_room"]
                     and sp["to_room"] == fc["to_room"]), None)
        if host is not None and not fc["refused"]:
            host["condition"] = "(and %s %s)" % (host["condition"], fc["condition"])
            host.setdefault("owner_groups", []).extend(fc["owner_group"])
            host.setdefault("merged", []).append(fc["condition"])
        else:
            specs.append(fc)
    # ...and the REGISTER-valued half of a one-visit pocket: bringing the teacup in is one guard,
    # having filled it on the way out is the other. Appended after the frontier specs because it
    # READS them -- an exit guard may only ship alongside the entrance guard that makes it
    # satisfiable, which `pocket_exit_guards` checks against `pocket_frontier`.
    specs.extend(pocket_exit_guards(s))
    # An unguardable sink whose item later decides a death: demand the item at the crossings
    # into the death's room instead (the mists doctrine -- refuse the trip, keep the trade).
    specs.extend(sink_survival_carryins(s))
    # ...and the market's fatal payments (KQ5's shops, the lamb's wastes) -- refusals of a
    # (site, token) pair, placed on the token's own dispatch case. See market_remedies.
    specs.extend(market_remedies(s))
    # ...and the one-shot windows (`window_closures`): hold each durable closer's raise until
    # the demand it seals is banked, and never re-arm a banked scene. See window_remedies.
    specs.extend(window_remedies(s))
    # ...and the remote death fuses (`fuse_death_armings`): the whale-shape arm hold -- the
    # encounter's spawn procedure refuses to arm until the derived kit is in hand. Silent
    # kind (a withheld spawn is the stock no-spawn roll). See fuse_arming_remedies.
    specs.extend(fuse_arming_remedies(s))
    for gt in survival_gates(s):
        cp, cn, rest = factor(gt["alts"])
        pos_spec = render(cp, set(), rest)
        if pos_spec:
            specs.append({"site": "gate", "room": gt["room"], "state": gt["state"],
                          "condition": pos_spec, "items": sorted(cp), "refused": []})
        for it in sorted(cn | fatal_to_carry(gt)):  # each prohibition at ITS OWN site
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
    # FATAL USES -- the dangerous ACTION, which strands nothing and spends nothing because you do
    # not survive to notice. Nothing else here produces a spec for one, so KQ6's skull-in-the-gears
    # was a finding with no remedy: flagged, and nothing would stop the player doing it.
    #
    # The remedy is to refuse the ACTION, spelled as a prohibition on the item that pays for it --
    # `(not (gEgo has: X))` on the arming of the fatal machine. Holding it, you are told no; not
    # holding it, the move was never available. The wording matters as much as the guard: the
    # player is being stopped from a move the game itself invited, so it goes through the same
    # derived refusal line as every other guard rather than failing silently.
    #
    # No new placement machinery: the arming of a named machine inside a room is what
    # `trigger.find_arming` already locates, which is how the Realm entry got placed.
    for f in s.fatal_uses():
        specs.append({"site": "action", "room": f["room"], "machine": f["machine"],
                      "item": f["item"], "forbid": [f["item"]],
                      "condition": f"(not (gEgo has: {f['item']}))",
                      "why": f"using {s.g.item_name(f['item'])} here is always fatal and spends it",
                      "refused": []})
    # register-flip strandings: HOLD the free-running trap's flip until every item it would seal is
    # in hand. KQ4's nightfall (global100:=1) shuts the day-only doors to the Diamond_Pouch and
    # Fishing_Pole; gate that one write on holding both, so the sunset waits for the day list. One
    # spec per trap register, conjoining its sealed items. LSL2 has no trap -> nothing.
    # Keyed by (register, FLIP VALUE), not register alone: the spec's own semantics is "hold
    # THE FLIP to v until the items IT seals are in hand", and a register that strands
    # different items at different values (LB2's act counter: the pressPass at the 1->2 break,
    # the salts and grapes at 4->5) must not conjoin them into one demand -- the single-spec
    # form emitted `reg123=2: (pass AND salts AND grapes)`, a wall (the salts do not exist
    # until act 4). One register with one flip value (KQ6's letter, KQ4's nightfall) is
    # byte-identical under either key.
    byreg = defaultdict(set)
    for r in s.register_flip_strandings():
        byreg[(r["register"], r["trap"])].add(r["item"])
    # ...and the CAUSAL flips (`register_strandings`): a plot register whose one-way flip cuts
    # off an item's source while a later room still demands it. Same remedy, same spec: hold the
    # flip until the item is in hand. KQ6's letter is the case -- flag 166 ("the wedding has
    # started", rm880's guards returning) seals rm781 while rm730/rm870 still ask for the
    # vizier's letter -- and KQ4's nightfall is the shape's play-validated precedent. LSL2/KQ4
    # report zero causal rows, so this is KQ6-only today.
    for r in s.register_strandings():
        # A JOINT row (register is a TUPLE, 2026-08-09) has no remedy of this shape and must not
        # invent one: the spec holds ONE register's write until the items are in hand, and a seal
        # that only exists at `12 == 420 AND 123 == 5` names no single write to hold -- neither
        # component's flip is by itself the point of no return. Emitting `register: (12, 123)`
        # would hand the patcher a global that does not exist. Detection-only until the causal
        # component is derived per row (docs/LB2-ORACLE.md §7y); measured to change nothing on
        # LSL2/KQ4/KQ6, which report no joint rows at all.
        if isinstance(r["register"], tuple):
            continue
        byreg[(r["register"], r["value"])].add(r["item"])
    for (R, trap) in sorted(byreg):
        items = sorted(byreg[(R, trap)])
        cond = ("(and %s)" % " ".join(f"(gEgo has: {i})" for i in items)
                if len(items) > 1 else f"(gEgo has: {items[0]})")
        # A flip with ENTERING EDGES is player-committed, and its demand already rides those
        # edges (`register_flip_frontier` -- see its docstring for why the two mechanisms are
        # mutually exclusive by construction). The hold spec is superseded, not emitted as
        # placeable: the free-running placer would find nothing anyway ("no free-running trap
        # write found" was LB2's permanent row), and an unplaced spec that another spec already
        # covers reads as an open gap when it is a closed one.
        edge_carried = sorted((a, b) for (a, b), rec in rff.items()
                              if set(items) & rec["items"])
        refused = []
        if edge_carried:
            refused.append(f"superseded: the flip is edge-committed and the demand "
                           f"rides the flip edge specs "
                           f"({', '.join(f'rm{a}->rm{b}' for a, b in edge_carried)})")
        elif not any(trap in vs for vs in (s._inroom.get(R) or {}).values()):
            # A REGISTER THE GAME ONLY WRITES ON CROSSINGS HAS NO FREE-RUNNING WRITE TO HOLD
            # (2026-08-14). The hold remedy freezes a write site until the sealed items are in
            # hand -- and prevRoom's "write to 340" is the engine's room switch itself, not a
            # statement anywhere. Emitting the spec as placeable sent the patcher hunting for
            # a site that structurally cannot exist ("no free-running trap write found", an
            # applied=False row beside a claim of coverage), which is the same defect the
            # snapshot's REFUSED convention exists to prevent: a spec we cannot act on must
            # say so itself. Model-level and VALUE-specific -- it asks whether THIS trap value
            # has an in-room write, not whether the register has any: the letter's flag 338
            # keeps its placed hold because the rFlag lowering puts its region-homed writes in
            # `_inroom[338]`, while reg12's stray in-room writes name other values and vouch
            # for nothing here.
            #
            # The message says only what is established. It does NOT claim another spec covers
            # the demand: `edge_carried` above is precisely that claim, and we are in the
            # branch where it is empty, so this row's demand is currently enforced NOWHERE.
            # (The crossing that performs the flip is where such a demand would have to live;
            # building that site is the interceptor work, not something this spec can assert.)
            refused.append(f"no hold site: no in-room write sets register {R} to {trap}, so "
                           f"the hold form has no target -- and no edge spec carries this "
                           f"demand, so it is UNENFORCED")
        specs.append({"site": "register-write", "register": R, "trap": trap,
                      "condition": cond, "items": items, "refused": refused})
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
            # A REGISTER-valued guard conjoins onto the edge's register requirement rather than its
            # item alternatives -- otherwise the one guard that closes a pocket carry-in would be
            # invisible to `verify`, which is the pass that exists to catch a guard creating a new
            # softlock. Intersect where the edge already constrains the same register: both hold.
            rq = dict(rq)
            for R, vals in (sp.get("req") or {}).items():
                rq[R] = (rq[R] & set(vals)) if R in rq else set(vals)
            out.append((rq, sets, tuple(base)))
        s._emeta[key] = out
    s._reob.clear(); s._rw.clear(); s._after.clear(); s._avoid.clear()
    # ⛔ AND THE MOVEMENT MEMO ITSELF. `_psucc` is cached over `_emeta`, which the loop above has
    # just rewritten -- a stale entry here would walk the UNGUARDED game, i.e. exactly the model
    # this pass exists to stop trusting.
    s._psucc_cache.clear()
    # ...and the register-stranding rows, which are a cache over this same movement model.
    # `verify` exists to prove a guard creates no NEW softlock, so a detector answering from
    # its pre-guard result would report the one thing this pass must never miss. Nothing reads
    # it after `apply_guards` today; that is the reason to clear it now rather than the reason
    # not to ([[same-rule-two-places]] -- the four caches above learned this the hard way).
    s._regstrand_cache = None
    # Over `proj`, NOT `regs`. `_pstates` is keyed by `self.proj` = regs + the death-trap JOINTS
    # (missability._build_product), and every reachability walk iterates `proj` -- so rebuilding it
    # from `regs` alone DELETES the joint keys and `rooms_after` dies with `KeyError: (12, 173)`.
    # KQ6 has one joint, LSL2 has none, which is why `verify` looked fine for as long as it did.
    s._pstates = {R: s._walk(R, frozenset()) for R in s.proj}
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
                 else f"rm{sp['room']} {sp['machine']}" if sp["site"] == "action"
                 else f"rm{sp['room']} state {sp.get('state')}")
        print(f"  {where:<22} {'REFUSED ' + str(sp['refused']) if sp['refused'] else sp['condition']}")
        if sp.get("note"):
            print(f"  {'':<22} ^ {sp['note']}")

    print("=" * 78)
    sinks = sink_remedies(s)
    print(f"DANGEROUS PURE SINKS -- actions that waste an item you still need: {len(sinks)}\n")
    for sk in sinks:
        print(f"  rm{sk['room']} (script {sk['script']}): {sk['edit']}")
        print(f"       {sk['why']}")
        if sk.get("corroboration"):
            print(f"       corroborated independently: {sk['corroboration']} (advisory)")
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
