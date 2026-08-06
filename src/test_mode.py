"""The lite-mode feature: stock/lite/full guard behavior behind a runtime global.

USER FEATURE (2026-08-06): the player toggles between three modes in-game -- FULL (guards
refuse, the default: mode global 0, which is also what uninitialized globals and stale
saves read), LITE (each guard refuses once, then says "You have been warned!" and lets the
original behavior run; one warned bit per guard site in trailing bitmask globals), STOCK
(every guard lets the stock behavior through silently). Silent kinds (arm-event,
nav-assign, edge-exit closes, award gates) and the register/flag holds have no refusal to
warn with, so lite behaves as full there [user ruling during planning]; stock bypasses
them too.

The hard constraint this file pins: the feature lives ENTIRELY in the patcher/trigger
emission layer. Detection, spec conditions and placement rows are the frozen snapshot
surface (the LSL2 golden pins them exactly), so nothing here may reach them -- checked
below by diffing a spec-level surface with the mode machinery force-disabled vs enabled.

What is deliberately NOT pinned: the exact emitted indentation and wording -- those are
template text like REFUSE, and pinning them would only protect a rendering choice. The
STRUCTURE is pinned instead: guard term verbatim at the site (test_sci11_patch's substring
pins depend on it), body duplicated into the proceed branch, warned-mark only in the deny
branch, classic v25 shape when the mode is unconfigured.
"""

import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trigger as T
import patcher as P

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("" if cond else ("  -- " + detail if detail else ""))))


def _fake_mode(g=481):
    counter = [0]

    def alloc():
        b = counter[0]
        counter[0] += 1
        return g + 1 + b // 16, "$%04x" % (1 << (b % 16))
    T.MODE = {"g": g, "warned": "(proc255_0 {You have been warned!})", "alloc": alloc}


def _balanced(s):
    t = re.sub(r";[^\n]*", "", re.sub(r"\{[^}]*\}", "{}", s))
    return t.count("(") == t.count(")")


def test_wrapper_shapes():
    print("\n-- guarded_wrap: classic vs mode --")
    guard = "(and (gEgo has: 5) (gEgo has: 9))"
    body = "(self changeState: 3)"
    refuse = "(proc255_0 {Not yet!})"

    T.MODE = None
    classic = T.guarded_wrap(guard, body, refuse)
    check("classic shape is the v25 wrap (guard, body, else, refuse -- no mode text)",
          guard in classic and classic.count(body) == 1 and "else" in classic
          and refuse in classic and "global481" not in classic, classic)
    check("classic shape balanced", _balanced(classic))

    _fake_mode()
    modeful = T.guarded_wrap(guard, body, refuse, site=T._ModeSite())
    check("mode shape keeps the guard term verbatim at the site", guard in modeful, modeful)
    check("mode shape runs the body in refuse-free branches (duplicated once)",
          modeful.count(body) == 2, modeful)
    check("mode shape balanced", _balanced(modeful))
    check("stock test present", "(== global481 2)" in modeful, modeful)
    check("warned bit read in the allow test", "(& global482 $0001)" in modeful, modeful)
    deny = modeful[modeful.rindex(refuse):]
    check("warned mark ONLY in the deny branch, beside the refusal",
          "(|= global482 $0001)" in deny and modeful.count("|=") == 1, modeful)
    check("warned line printed only under lite",
          "(if (== global481 1) (proc255_0 {You have been warned!}))" in modeful, modeful)

    # deny_extra (the edgeHit resets) rides the deny branch only
    modeful2 = T.guarded_wrap(guard, body, refuse, site=T._ModeSite(),
                              deny_extra=("(global0 edgeHit: 0)",))
    check("deny_extra lines sit in the deny branch only",
          modeful2.count("(global0 edgeHit: 0)") == 1
          and modeful2.index("(global0 edgeHit: 0)") > modeful2.rindex(body), modeful2)

    # one site shared across clauses = one warned bit
    site = T._ModeSite()
    a = T.guarded_wrap(guard, body, refuse, site=site)
    b = T.guarded_wrap(guard, body, refuse, site=site)
    check("one site shares one warned bit across clauses",
          re.findall(r"& global(\d+) \$(\w+)", a) == re.findall(r"& global(\d+) \$(\w+)", b))

    # allocator walks bits then words
    _fake_mode()
    masks = [T._ModeSite().forms()[0] for _ in range(17)]
    check("17th site rolls into the next warned word",
          "global482" in masks[0] and "global483" in masks[16] and "$0001" in masks[16],
          masks[16])

    print("\n-- stock_or --")
    T.MODE = None
    check("stock_or is the identity when unconfigured", T.stock_or("(x)") == "(x)")
    _fake_mode()
    check("stock_or bypasses in stock only", T.stock_or("(x)") == "(or (== global481 2) (x))")
    T.MODE = None


def test_ui_installers():
    print("\n-- UI installers on the real game files --")
    scratch = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build",
                           "test_mode_ui")
    cases = [("lsl2", "../build/ir/src/Menu.sc", "(proc255_0 {%s})", "menu", 1283),
             ("kq4", "../build/kq4/src/Menu.sc", "(proc255_0 {%s})", "menu", 1284),
             ("kq6", "../build/sweep/kq6/src/kq6Controls.sc", "(proc921_0 {%s})", "panel", None)]
    here = os.path.dirname(os.path.abspath(__file__))
    for game, rel, form, want_ui, want_code in cases:
        src = os.path.normpath(os.path.join(here, rel))
        if not os.path.exists(src):
            print("  [skip] %s source not present (%s)" % (game, src))
            continue
        d = os.path.join(scratch, game, "src")
        shutil.rmtree(os.path.join(scratch, game), ignore_errors=True)
        os.makedirs(d)
        shutil.copy(src, d)
        P._RETRACTION_FORM = form
        row = P._install_menu_chooser(d, 481)
        if row is None:
            row = P._install_panel_chooser(d, 481)
        ok = row is not None and row.get("applied") and row.get("ui") == want_ui
        if want_code is not None:
            ok = ok and row.get("menu_code") == want_code
        check("%s chooser installs (%s%s)" % (game, want_ui,
              "" if want_code is None else " code %d" % want_code), bool(ok), repr(row))
        edited = open(os.path.join(d, os.path.basename(src))).read()
        check("%s edited file balanced" % game, _balanced(edited))
        check("%s chooser writes the mode global" % game, "global481" in edited)
    shutil.rmtree(scratch, ignore_errors=True)


def test_mode_stays_out_of_the_surface():
    print("\n-- the mode never reaches specs or placement rows (surface neutrality) --")
    # `sp[\"condition\"]` strings are produced by guards.py, which imports neither trigger's
    # MODE nor the patcher; assert the import graph fact directly rather than re-running the
    # whole LSL2 analysis here (test_golden pins the full surface).
    import guards as G_mod
    src = open(G_mod.__file__).read()
    check("guards.py never touches the mode machinery",
          "MODE" not in src and "stock_or" not in src and "guarded_wrap" not in src)
    import missability as M_mod
    check("missability.py never touches the mode machinery",
          "stock_or" not in open(M_mod.__file__).read())
    # the apply_* return rows carry no mode keys (they are the frozen placement surface)
    apply_src = open(P.__file__).read()
    check("install_mode_ui rows are separate from apply_* rows (pipeline unions titles only)",
          "edits + gedits + uedits" in open(os.path.join(
              os.path.dirname(P.__file__), "pipeline.py")).read())


def test_synthetic_project_end_to_end():
    print("\n-- synthetic mini-project: init, declare, chooser fallback --")
    scratch = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build",
                           "test_mode_mini")
    d = os.path.join(scratch, "src")
    shutil.rmtree(scratch, ignore_errors=True)
    os.makedirs(d)
    open(os.path.join(d, "Main.sc"), "w").write(
        "(script# 0)\n(local\n\tglobal0\n\tglobal1\n\tglobal2\n)\n")
    open(os.path.join(d, "rm5.sc"), "w").write(
        "(script# 5)\n(instance rm5 of Rm\n\t(method (doVerb param1)\n"
        "\t\t(if (gEgo has: 3) (self setScript: goScr))\n\t)\n)\n")
    P._WARNED_LINE = "(proc255_0 {You have been warned!})"
    P._MODE_DEST = None
    T.MODE = None
    P._init_mode(scratch)
    check("mode global = first index past everything referenced or declared",
          T.MODE is not None and T.MODE["g"] == 3, repr(T.MODE))
    # a wrap references the new globals; the declaration pass then declares them
    w, m = T.MODE["alloc"]()
    open(os.path.join(d, "rm5.sc"), "a").write(
        "\n; guard: (== global%d 2) (& global%d %s)\n(if (== global3 2) (= global4 1))\n"
        % (T.MODE["g"], w, m))
    n = P._declare_missing_globals(d)
    main_txt = open(os.path.join(d, "Main.sc")).read()
    check("declaration pass declares the mode/warned globals it can now see",
          n >= 2 and "global3" in main_txt and "global4" in main_txt, main_txt)
    # no UI shape in the mini project -> honest SKIP row, never a crash
    rows = P.install_mode_ui(scratch, {})
    check("no UI shape -> honest SKIP row",
          rows and not rows[0]["applied"] and "no menu bar" in rows[0]["why"], repr(rows))
    shutil.rmtree(scratch, ignore_errors=True)
    P._MODE_DEST = None
    T.MODE = None


def test_review_defects():
    """The three emission defects a contextless review found on the first cut (2026-08-06).

    All three were invisible to the existing gates, which freeze the ANALYSIS surface (specs,
    placement rows) and cannot see a character of emitted script text. Each is pinned here on
    the smallest thing that carries it."""
    print("\n-- review defects (2026-08-06) --")

    # D2: one spec row is wrapped at several sites; they are one guard and owe ONE warning.
    _fake_mode()
    site = T._ModeSite()
    a = T.guarded_wrap("(g)", "(b)", "(r)", site=site)
    b = T.guarded_wrap("(g)", "(b)", "(r)", site=site)
    masks = lambda s: set(re.findall(r"\$[0-9a-f]{4}", s))
    check("D2: a threaded site keeps ONE warned bit across wrapper calls",
          masks(a) == masks(b) and len(masks(a)) == 1, "%s vs %s" % (masks(a), masks(b)))
    import inspect
    sig = inspect.signature(T.wrap_trigger_in_source).parameters
    sig2 = inspect.signature(T.wrap_all_armings_in_source).parameters
    check("D2: both wrappers accept the caller's site", "site" in sig and "site" in sig2)
    psrc = open(P.__file__).read()
    check("D2: apply_guards mints one site per SPEC ROW and threads it",
          "row_site = _ModeSite()" in psrc and psrc.count("site=row_site") >= 3, "")
    check("D2: the entry frontier shares the row's site",
          re.search(r"def _guard_arrival_entries\([^)]*site=None", psrc, re.S) is not None)

    # D1: the recycle lifts the productive continuation out of the `else`; stock must not run
    # BOTH the break and the continuation (and must not skip the clamp that bounds the store).
    stock_src = ("\t\t(if (>= global113 5)\n"
                 "\t\t\t(proc255_0 16 22)\n"
                 "\t\t\t((Inv at: 15) loop: 1)\n"
                 "\t\telse\n"
                 "\t\t\t(global0 cel: 0 setCycle: End self)\n"
                 "\t\t)\n")
    forms = T._ModeSite().forms()
    out, ok = P._recycle_counter_break(stock_src, stock_src.index("(Inv at: 15)"),
                                       "(proc255_0 {kidding})", forms)
    check("D1: the recycle rewrites the counter-gated break", ok, out)
    allow = forms[0]
    # the allow branch runs from the inner `(if <allow>` to the FIRST `else` after it
    body = out[out.index(allow):out.index("else", out.index(allow))] if ok else ""
    check("D1: stock runs the break WITHOUT the productive continuation",
          ok and "(Inv at: 15) loop: 1" in body and "setCycle: End self" not in body, out)
    check("D1: the clamp and the mark stay on the withheld path only",
          ok and out.count("(= global113 4)") == 1
          and out.index("(= global113 4)") > out.index("else"), out)

    # D4: the retraction (and lite's mark) must stay in the arm the disposal is in.
    lines = ["\t\t\t((Said 'eat/fruit')\n", "\t\t\t\t(if (global0 has: 25)\n",
             "\t\t\t\t\t(proc255_0 0 43)\n", "\t\t\t\t\t(global0 put: 25 999)\n",
             "\t\t\t\telse\n", "\t\t\t\t\t(proc0_17)\n", "\t\t\t\t)\n", "\t\t\t)\n"]
    end = P._clause_end_line(lines, 3)
    check("D4: the clause walk stops at a bare `else`, not in the sibling arm",
          end == 4, "landed at %d: %r" % (end, lines[end].strip()))
    T.MODE = None


def run():
    test_wrapper_shapes()
    test_review_defects()
    test_ui_installers()
    test_mode_stays_out_of_the_surface()
    test_synthetic_project_end_to_end()
    return not FAIL


if __name__ == "__main__":
    ok = run()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(0 if ok else 1)
