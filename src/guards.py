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


def render_register(s, R, value):
    """`R == value` in the game's own spelling, or None if we cannot write it.

    Registers are ours, not the game's: a boolean flag was lowered into a synthetic per-flag global
    so the gating machinery could model it without knowing what a flag is. A PATCH has to be
    written back in the game's spelling, so this reverses the lowering using the base and the test
    proc `vocab.derive_flags` already named. A register that is not a lowered flag -- a real global,
    an object property -- has no such spelling and returns None rather than a guess."""
    ir = getattr(s.em, "ir", None)
    base = getattr(ir, "flag_synth_base", None)
    proc = getattr(ir, "flag_test_proc", None)
    if base is None or proc is None or R < base:
        return None
    test = f"({proc} {R - base})"
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
            edges = _settable_frontier(s, R, v, sites, pocket, r.get("toll_reg"))
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
                                f"no crossing commits reg{R}={v}: in-room register writes are "
                                f"modelled PERMISSIVELY, so the walk believes the pocket can be "
                                f"re-entered with its own seal still clear and the flag set on a "
                                f"second visit. Refusing is the safe direction -- placing it "
                                f"anyway would wall whoever cannot comply where it sits."]})
                continue
            for (a, b) in edges:
                out.append({"site": "edge", "from_room": a, "to_room": b, "condition": cond,
                            "items": [], "groups": [], "req": {R: [v]},
                            "pairs_with": list(r["toll_edge"]), "refused": list(base),
                            "note": note})
    return out


def _settable_frontier(s, R, v, sites, pocket, toll_reg=None):
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
    states = s._walk(J, frozenset()) if len(J) > 1 else s._pstates[R]

    def val(u):
        return u[1][idx] if len(J) > 1 else u[1]
    succ = {u: s._psucc(J if len(J) > 1 else R, u, frozenset()) & states for u in states}
    safe = {u for u in states if u[0] in sites}          # standing where the write can happen
    changed = True
    while changed:                                        # ...or able to walk to one
        changed = False
        for u in states:
            if u not in safe and (succ[u] & safe):
                safe.add(u)
                changed = True
    out = []
    for a in sorted(pocket):                              # the guard belongs to the pocket it
        #   protects; past its boundary "the writer is unreachable" is true of the whole map and
        #   says nothing about a commitment.
        lacking = [u for u in states if u[0] == a and val(u) != v]
        if not lacking or not all(u in safe for u in lacking):
            continue                                      # nobody to guard, or somebody here could
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
    out = []
    for d in s.dangerous_sinks():
        it = d["item"]
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
    for src in (joint_frontier(s), pocket_frontier(s)):
        for (a, b), rec in src.items():
            if (a, b) in frontier:
                frontier[(a, b)] = {"items": set(frontier[(a, b)]["items"]) | rec["items"],
                                    "groups": frontier[(a, b)]["groups"] + rec.get("groups", [])}
            else:
                frontier[(a, b)] = rec
    for (a, b), rec in sorted(frontier.items()):
        # Drop the literals that cannot be held AT this edge before asking whether the rest is
        # satisfiable -- demanding one of those does not close a softlock, it walls the route.
        # Reported, never silent: a guard that quietly asks for less is how an under-guard ships.
        why = unholdable_at(s, a, b, set(rec["items"]))
        gone = set(why)
        if gone:
            rec = {"items": set(rec["items"]) - gone,
                   "groups": [g for g in rec["groups"] if not (g & gone)]}
        bad = unsatisfiable(s, a, b, rec)
        sp = {"site": "edge", "from_room": a, "to_room": b,
              "condition": render_frontier(rec),
              "items": sorted(rec["items"]), "groups": [sorted(g) for g in rec["groups"]],
              "refused": bad}
        if gone:
            sp["dropped_incompatible"] = sorted(gone)
            sp["dropped_why"] = "cannot be held here: " + "; ".join(
                sorted({f"{s.g.item_name(i)} -- {r}" for i, r in why.items()}))
        if not rec["items"] and not rec["groups"]:
            # Everything this edge would have demanded is unholdable here, so there is no guard to
            # place -- but say so. Dropping the row silently is how an edge stops being guarded
            # without anyone noticing; `refused` is the channel that already exists for "we
            # deliberately emit nothing", and every reporting path prints it.
            sp["refused"] = [sp["dropped_why"] + " -- nothing left to demand at this edge"]
        specs.append(sp)
    # ...and the REGISTER-valued half of a one-visit pocket: bringing the teacup in is one guard,
    # having filled it on the way out is the other. Appended after the frontier specs because it
    # READS them -- an exit guard may only ship alongside the entrance guard that makes it
    # satisfiable, which `pocket_exit_guards` checks against `pocket_frontier`.
    specs.extend(pocket_exit_guards(s))
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
    byreg = defaultdict(set)
    trap_of = {}
    for r in s.register_flip_strandings():
        byreg[r["register"]].add(r["item"])
        trap_of[r["register"]] = r["trap"]
    for R in sorted(byreg):
        items = sorted(byreg[R])
        cond = ("(and %s)" % " ".join(f"(gEgo has: {i})" for i in items)
                if len(items) > 1 else f"(gEgo has: {items[0]})")
        specs.append({"site": "register-write", "register": R, "trap": trap_of[R],
                      "condition": cond, "items": items, "refused": []})
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
