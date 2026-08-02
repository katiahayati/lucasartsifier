"""SCI1.1 PATCHING: what stands between a correct finding and a playable patch.

Detection on KQ6 is done -- 18 requirement units, `test_kq6_ground_truth` 16/16, `KNOWN_GAPS`
empty. Everything still open is downstream: turning a finding into a guard that is CORRECT, into a
source edit that APPLIES, and into a resource the interpreter will LOAD. None of that had a test,
which is why "5 of 17 placed" sat in a plan document for four days as the only record of it.

**MOST CHECKS HERE ARE DELIBERATELY RED.** They assert the end state -- every spec places, the
refusal primitive is derived, a fatal use produces a remedy -- and they are red because that state
has not been built yet. That is the point: a plan document goes stale silently, a red test does
not. Each is registered in `tools/run_tests.py` KNOWN_RED with its phase, and each turns green
exactly when its phase lands. Turning one green by weakening it defeats the only mechanism that
notices the phase is done.

The measured tables are printed on every run, red or not, so the numbers in the plan can always be
refreshed from a run rather than from memory. See docs/SCI11-PATCHING-PLAN.md for the derivations
and docs/KQ6-STATUS.md for where KQ6 stands.
"""
import os
import sys

import config
import guards as G
import missability as M

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n      {detail}" if detail and not cond
                                                        else ""))


def _placements(cfg):
    """(applied, skipped) placement rows for a game, via the same path `snapshot --placements`
    uses -- so this test and the golden can never disagree about what placed."""
    import shutil
    import tempfile
    import patcher as P
    s = M.load(cfg=cfg)
    specs = G.guard_specs(s)
    sinks = G.sink_remedies(s)
    dest = tempfile.mkdtemp(prefix="sci11test_")
    try:
        P.configure(s.em.ir)
        nums = P.assemble(dest, cfg)
        titles = {n: t for t, n in nums.items()}
        rows = (P.apply_sink_remedies(dest, sinks, titles)
                + P.apply_guards(dest, specs, titles, nums,
                                 s_drops=lambda it: s.drops.get(it, set()),
                                 rooms=set(s.rooms)))
    finally:
        shutil.rmtree(dest, ignore_errors=True)
    def where(e):
        return (e.get("title") or f"rm{e.get('from_room')}->rm{e.get('to_room')}") + (
            f"/{s.g.item_name(e['item'])}" if e.get("item") is not None else "")
    return ([where(e) for e in rows if e["applied"]],
            [(where(e), e.get("why") or "") for e in rows if not e["applied"]], s, specs)


def test_placement():
    """🔴 Every spec we did not deliberately refuse must land somewhere in the source."""
    print("\nPhase 4 -- PLACEMENT: a correct spec that lands nowhere ships nothing")
    for name in ("KQ6", "dagger"):
        cfg = config.by_name(name)
        if cfg is None or not (cfg.ir_path and os.path.exists(cfg.ir_path)):
            print(f"  (skip {name}: no IR)")
            continue
        if not os.path.isdir(cfg.resource_dir):
            print(f"  (skip {name}: resources not at {cfg.resource_dir})")
            continue
        applied, skipped, _s, _specs = _placements(cfg)
        print(f"  {name}: {len(applied)} applied / {len(applied) + len(skipped)} total")
        for w in applied:
            print(f"      [ok  ] {w}")
        for w, why in skipped:
            print(f"      [SKIP] {w:22s} {why[:78]}")
        check(f"🔴 KNOWN GAP ({name}): every non-refused spec places", not skipped,
              f"{len(skipped)} unplaced. The reasons group into the seams in "
              f"docs/SCI11-PATCHING-PLAN.md §4/§5: an edit re-found by regex instead of by the "
              f"IR node we analysed; `trigger.py` searching only the FROM room's own file; "
              f"controllability spelled for SCI0; and `guard_edge_exit` hardcoding `of Rm`.")


def test_refusal_primitive_is_derived():
    """🔴 The refusal message must be the game's OWN way of printing a literal line.

    `patcher.REFUSE` is `(proc255_0 {Not yet!})` -- LSL2's and KQ4's print procedure, hardcoded.
    **KQ6 has a `proc255_0` too and it is a different, unrelated procedure** (`Dialog.sc:199`
    calls it with no arguments, as a boolean). Here we get lucky and it fails loudly at compile
    time; in a game that exports a `proc255_0` with a compatible arity we would emit a call to
    something arbitrary and never know.

    The derivation is per game: find the call form that takes a `{literal}` and displays it, and
    reuse THAT form. KQ6's is `(Print addText: {…} init:)`; LSL2/KQ4's is `(proc255_0 {…})`, which
    the same derivation reproduces. If none can be derived, refuse to emit any refusal-bearing
    guard -- a guard that refuses silently is the "the game lied to the player" class that only
    play-testing caught last time.

    Asserted as the ABSENCE of a hardcode rather than as a string, so it cannot be satisfied by
    swapping one constant for another."""
    print("\nPhase 2 -- REFUSAL: the message must come from the game, not from LSL2")
    import patcher as P
    derived = getattr(P, "refusal_form", None)
    check("🔴 KNOWN GAP: the refusal primitive is derived per game, not a module constant",
          callable(derived),
          f"patcher.REFUSE is the constant {P.REFUSE!r}. KQ6's proc255_0 is an unrelated "
          f"boolean, so this compiles to `Unknown procedure 'proc255_0'` -- loudly here, "
          f"silently in the next game. Expected a `patcher.refusal_form(ir)` derivation.")


def test_fatal_uses_produces_a_remedy():
    """🔴 A dangerous ACTION must produce a spec, not just a finding.

    `guard_specs` consumes edge strandings, joint strandings, survival gates, register flips and
    (since 2026-07-31) toll pockets. It does NOT consume `fatal_uses`. KQ6 has one: the `skull`
    thrown into rm420's gears -- a move the game invites, that looks like the solution, that costs
    a required item and kills you. User: *"that's exactly the kind of bad use we need to
    prevent."*

    The remedy is to refuse the ACTION (guard the arming of `throwSkull`), which needs a new spec
    site kind -- `action` -- reusing the existing setscript/arm-event placement machinery."""
    print("\nPhase 5 -- FATAL USES: a finding with no remedy is a finding we cannot ship")
    if not (config.KQ6.ir_path and os.path.exists(config.KQ6.ir_path)):
        print("  (skip: no KQ6 IR)")
        return
    s = M.load(cfg=config.KQ6)
    fatal = s.fatal_uses()
    specs = G.guard_specs(s)
    sites = {sp.get("site") for sp in specs}
    print(f"  KQ6 fatal_uses: {[(s.g.item_name(f['item']), f['machine']) for f in fatal]}")
    print(f"  spec site kinds emitted: {sorted(x for x in sites if x)}")
    check("🔴 KNOWN GAP: a fatal use produces a remedy spec", bool(fatal) and "action" in sites,
          f"{len(fatal)} fatal use(s) and no `action` spec. The skull is flagged and nothing "
          f"would stop the player throwing it.")


def test_verify_closes_every_kq6_finding():
    """`guards.verify` reports nothing remaining and nothing new -- GREEN since 2026-08-02.

    The last three closed by three principles, each already in the codebase:
      * handkerchief + skeletonKey -- carry-OUTs of the Realm toll pocket, so the demand belongs
        at the pocket's exit frontier: `pocket_carryout_frontier` places both at rm640->rm650,
        the last crossing after which their sources are unreachable (the model has no 650->640
        return edge -- the interior is one-way -- so this sits TIGHTER than the guard oracle's
        rm680->rm155, which presumed a walk-back the room graph does not have);
      * the wrong-door stranding rows died to two rules `edge_strandings` now applies to its own
        output: an edge that ITSELF demands an item cannot strand it (the toll detector's
        "forced, not missable"), and an edge where the item CANNOT BE HELD cannot strand it
        (`unholdable_at` -- the same call that already shapes the specs).
    Both filters are SINGLETON-only: measured on groups they fire exactly once corpus-wide, on
    LSL2's play-validated raft guard, which is ruled untouchable.

    With this green, `python -m pipeline <kq6> --report` exits 0."""
    print("\nPhase 5 -- VERIFY: the guards must close every finding and create none")
    if not (config.KQ6.ir_path and os.path.exists(config.KQ6.ir_path)):
        print("  (skip: no KQ6 IR)")
        return
    s = M.load(cfg=config.KQ6)
    specs = G.guard_specs(s)
    co = [sp for sp in specs if sp["site"] == "edge"
          and (sp["from_room"], sp["to_room"]) == (640, 650)]
    check("the Realm carry-outs are demanded at the pocket's exit frontier (rm640->rm650)",
          len(co) == 1 and set(co[0]["items"]) == {17, 44} and not co[0]["refused"],
          f"{[(sp['condition'], sp['refused']) for sp in co]}")
    refused = [sp for sp in specs if sp["refused"]]
    v = G.verify(s, specs)          # NOTE: mutates `s`; nothing may read it after this
    print(f"  fixed {len(v['fixed'])} + {len(v['groups_fixed'])} group(s); "
          f"remaining {[s.g.item_name(i) for i in v['remaining']]}; "
          f"NEW {[s.g.item_name(i) for i in v['NEW']]}; {len(refused)} spec(s) refused")
    check("no guard INTRODUCES a softlock (this one must never go red)",
          not v["NEW"] and not v["groups_new"],
          f"NEW={[s.g.item_name(i) for i in v['NEW']]} groups_new={v['groups_new']}")
    check("every KQ6 finding is closed by a guard (remaining is empty)",
          not v["remaining"],
          f"remaining={[s.g.item_name(i) for i in v['remaining']]}")
    # ...and what stays refused is exactly the two `flag == 0` half-questions -- deliberate
    # negatives that close nothing, not unshipped findings. A third refusal appearing here is a
    # regression wearing a polite face.
    check("the only refusals are the flag==0 half-questions",
          all(sp.get("req") and all(vs == [0] for vs in sp["req"].values()) for sp in refused),
          f"{[(sp.get('from_room'), sp.get('to_room'), sp.get('req')) for sp in refused]}")


def run():
    print("=== test_sci11_patch: the road from a correct finding to a playable patch ===")
    test_refusal_primitive_is_derived()
    test_fatal_uses_produces_a_remedy()
    test_placement()
    test_verify_closes_every_kq6_finding()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
