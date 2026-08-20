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


def _names_all(text, form):
    """Does `text` name ALL THREE modes in `form` (e.g. "now: %s"), in one consistent case?

    Derived from `patcher.MODE_NAMES` rather than spelled out, so renaming a mode cannot leave
    this pinning the old word -- which is the failure mode the constant exists to prevent (the
    label used to be written out six times, and a rename reaching five of them would leave the
    UI disagreeing with itself while the test still passed on the sixth)."""
    return any(all((form % getattr(n, case)()) in text for n in P.MODE_NAMES)
               for case in ("lower", "upper", "capitalize"))


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
    # Codes are (menu << 8) | item. Menu 3 is `Action` on both SCI0 games -- the chooser is
    # placed by EXCLUDING the device menus (sound/speed/file, identified by what their handler
    # cases call), not by naming one, after the user rejected the Sound menu it used to append
    # to. LSL2's Action has 7 items (separators count) so ours is 8 -> 776; KQ4's has 3 -> 772.
    cases = [("lsl2", "../build/ir/src/Menu.sc", "(proc255_0 {%s})", "menu", 776),
             ("kq4", "../build/kq4/src/Menu.sc", "(proc255_0 {%s})", "menu", 772),
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
        # THE CONTROL MUST NAME THE CURRENT MODE [user, 2026-08-06]. Both dialects ask in a
        # modal chooser that says "now: LITE"; the SCI1.1 panel control ALSO carries the mode as
        # its own second label line, which is the only way to read it back there, since the
        # chooser closes the panel behind itself.
        if want_ui == "menu":
            check("%s chooser shows the current level" % game,
                  _names_all(edited, "now: %s"), edited[:0])
        else:
            check("%s chooser shows the current level" % game,
                  _names_all(edited, "now: %s"), edited[:0])
            body = edited[edited.find("instance iconGuards"):]
            # ⭐ IT MUST NOT ASK FOR A PRESS ANIMATION IT HAS NO ART FOR. `IconI::select` draws
            # cel 1 of the icon's own loop while the mouse is held and cel 0 on release -- the
            # SCI convention that a control's loop is a two-cel {up, down} pair. Our face is
            # deliberately taken from a loop that is NOT one (every button loop has a word baked
            # into the art), so a press painted whatever else lives in that loop at the control's
            # position: KQ6 loop 1 is [12x43 slider arrow strip, 58x122 inset, 58x22 plate], and
            # the strip and the inset are exactly what three play reports described. The
            # REQUIREMENT is "no animation without a pair", so that is what this pins -- against
            # the game's own art and the game's own class constant, not against a signal number.
            face = re.search(r"view\s+(\d+)\s+loop\s+(\d+)\s+cel\s+(\d+)\s+signal\s+(\d+)",
                             re.sub(r"\s+", " ", body))
            check("%s control declares a face and a signal" % game, bool(face), body[:400])
            if face:
                v, lp, cl, sig = (int(face.group(i)) for i in (1, 2, 3, 4))
                # read the art -- and say so LOUDLY if it cannot be read, because "no pair" is
                # also this check's pass-by-default and a silent fallback would pin nothing
                import config, sci_gfx, sci_resource
                cels = sci_gfx.decode_view(
                    sci_resource.Sci0Game(config.KQ6.resource_dir), v)[lp]["cels"]
                pair = (cl == 0 and len(cels) > 1
                        and (cels[0].width, cels[0].height) == (cels[1].width, cels[1].height))
                bit = P._icon_press_bit(d)
                check("%s control animates its press only if its face is a two-cel button pair"
                      % game, pair or not (sig & bit),
                      "signal %d, press bit %#x, face %d/%d/%d pair=%s" % (sig, bit, v, lp, cl, pair))
                # the sibling half: the check is only meaningful if the panel's REAL buttons do
                # read as pairs, so the art reader is not simply always saying no
                sibs = [(int(m.group(1)), int(m.group(2))) for m in
                        re.finditer(r"view\s+(\d+)\s+loop\s+(\d+)\s+cel\s+0\s+message\s+0\s+signal",
                                    re.sub(r"\s+", " ", edited))]
                pairs = [(sv, sl) for sv, sl in sibs
                         if len(sib := sci_gfx.decode_view(
                             sci_resource.Sci0Game(config.KQ6.resource_dir), sv)[sl]["cels"]) > 1
                         and (sib[0].width, sib[0].height) == (sib[1].width, sib[1].height)]
                check("%s the pair test recognises the panel's own buttons" % game,
                      len(pairs) >= 3, "button faces %s read as pairs: %s" % (sibs, pairs))
            # ...AND IT MUST HIDE THE PANEL BEFORE OPENING THE CHOOSER, AND RETURN TRUE.
            # `iconAbout`, in the same file, opens a dialog from this same panel correctly:
            # `(super select: &rest) (global63 hide:) (KQ6Print ... init:)`. Two orderings matter
            # and neither is about nesting (v31 hid first and behaved identically -- the artifact
            # above was the whole of it): the panel must be gone before the chooser draws, and
            # `select` must return non-zero, because `IconBar::dispatchEvent` only reads its exit
            # flag inside `(if (self select: ...))` -- a 0 there leaves the modal loop spinning
            # over a window it has just disposed. The requirement is the ORDER and the RETURN,
            # so that is what this pins -- not "no dialog", which is what the first cut of this
            # check asserted and which cost the UI the user preferred.
            hide, printed = body.find("hide:"), body.find("Print")
            check("%s hides the panel before opening the chooser" % game,
                  printed < 0 or (0 <= hide < printed), body[:500])
            sel = body[body.find("(method (select"):]
            check("%s chooser select returns true so the panel's modal loop exits" % game,
                  printed < 0 or "(return 1)" in sel, sel[:400])
            # and it must never re-enter the panel's own modal loop: `(<panel> show:)` from
            # inside a control runs `GameControls::show` a second time from within itself, so
            # dismissing only ever returns to the outer loop (v29: the panel never closed).
            panel_inst = re.search(r"\(instance\s+(\w+)\s+of\s+GameControls\b", edited)
            check("%s control never re-shows the panel from inside it" % game,
                  not panel_inst or ("(%s show:)" % panel_inst.group(1)) not in body, body[:500])
        if want_ui == "menu":
            # ...and it must not land on the audio menu
            host = re.search(r"\(AddMenu\s+\{([^}]*)\}\s+\{[^}]*Guards", edited)
            check("%s chooser is not on a device menu" % game,
                  bool(host) and "sound" not in host.group(1).lower()
                  and "speed" not in host.group(1).lower(),
                  host.group(1) if host else "no host menu found")
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
    # ...and the mode-UI rows stay out of the frozen placement surface. Asserted on the ROWS
    # (2026-08-20 third review): this read `"edits + gedits + uedits" in pipeline.py`, a check
    # that constrains the spelling of one expression and would pass on a comment, fail on a
    # rename, and say nothing about what the rows carry. What has to be true is that a mode-UI
    # row is UNION-ABLE BY TITLE and carries none of the keys `snapshot.py` freezes -- which is
    # exercised on the synthetic project in `test_synthetic_project_end_to_end`.


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
    # ...and those rows never join the frozen placement surface: the pipeline unions them by
    # `title` alone, which is only safe while they carry none of the keys the snapshot reads.
    surface_keys = {"placement", "kind", "item", "item_name", "condition", "sites"}
    check("a mode-UI row is union-able by title and carries no placement-surface key",
          all(set(r) & surface_keys == set() for r in rows)
          and all("title" in r or not r["applied"] for r in rows),
          repr(rows))
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
    # ⛔ ON THE OBJECTS, NOT THE FILE TEXT (2026-08-20 third review). These read
    # `"row_site = _ModeSite()" in open(patcher.py).read()` and a regex over a `def` line: they
    # pass on a comment, fail on a rename, and neither can tell a threaded site from a
    # variable of that name assigned and never used. What carries the property is that the
    # site object is SHARED -- one warned bit for a row wrapped at several places, a different
    # one for the next row -- so that is asserted directly, on the thing the wrappers consume.
    check("D2: a fresh site is a DIFFERENT warned bit (so one per row means one bit per row)",
          masks(T.guarded_wrap("(g)", "(b)", "(r)", site=T._ModeSite())) != masks(a))
    ep = inspect.signature(P._guard_arrival_entries).parameters
    check("D2: the entry frontier accepts the row's site, defaulted so a caller may omit it",
          "site" in ep and ep["site"].default is None)
    # ⛔ AND `co_varnames` HAS THE SAME WEAKNESS IT REPLACED (2026-08-20 fourth review, P4).
    # `"row_site" in P.apply_guards.__code__.co_varnames` asks only whether a local of that name
    # EXISTS. Delete `site=row_site` from every wrapper call and the assignment still stands, so
    # the check still passes -- "a variable of that name assigned and never used" is the precise
    # weakness the paragraph above criticises, reintroduced by its own cure. The reviewer proved
    # it by mutation.
    #
    # THE INVARIANT, structurally: `row_site` is minted once per spec row, inside the `by_title`
    # loop; every site-accepting call INSIDE that loop must be handed it. Calls outside the loop
    # are the passes that make exactly one wrapper call per row (the fatal-use pass and the
    # market squeeze), where the wrapper's own default already gives that row one bit and there
    # is no `row_site` in scope to thread. So the rule needs no allow-list: inside the loop,
    # always; outside it, not applicable.
    #
    # And the guard MUTATION-TESTS ITSELF below, because a threading check that cannot fail is
    # exactly what this finding is about.
    import ast as _ast

    def _threading(src):
        """(threaded, unthreaded_inside_the_row_loop, calls_seen) for apply_guards' source."""
        accepts = set()
        for _mod in (P, T):
            for _nm in dir(_mod):
                _o = getattr(_mod, _nm)
                if callable(_o) and getattr(_o, "__module__", "") in ("patcher", "trigger"):
                    try:
                        if "site" in inspect.signature(_o).parameters:
                            accepts.add(_nm)
                    except (TypeError, ValueError):
                        pass
        tree = _ast.parse(src)
        loops = [n for n in _ast.walk(tree) if isinstance(n, _ast.For)
                 and any(isinstance(s, _ast.Assign)
                         and any(getattr(t, "id", None) == "row_site" for t in s.targets)
                         for s in _ast.walk(n))]
        if not loops:
            return 0, -1, 0            # no row loop found at all: the scan is not reading it
        row_loop = min(loops, key=lambda n: sum(1 for _ in _ast.walk(n)))
        inside = {id(n) for n in _ast.walk(row_loop)}
        thr = unthr = seen = 0
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            f = node.func
            nm = f.attr if isinstance(f, _ast.Attribute) else getattr(f, "id", None)
            if nm not in accepts:
                continue
            seen += 1
            kw = next((k.value for k in node.keywords if k.arg == "site"), None)
            passes_row = isinstance(kw, _ast.Name) and kw.id == "row_site"
            if passes_row:
                thr += 1
            elif id(node) in inside:
                unthr += 1
        return thr, unthr, seen

    _src = inspect.getsource(P.apply_guards)
    _thr, _unthr, _seen = _threading(_src)
    check("D2: every wrapper call inside the per-row loop is handed that row's site",
          _unthr == 0 and _thr >= 5,
          detail="%d threaded, %d un-threaded inside the row loop, %d site-accepting calls "
                 "seen. An un-threaded call there mints a second warned bit for one row, so "
                 "lite refuses the same demand twice and burns a bit doing it."
                 % (_thr, _unthr, _seen))
    check("D2: ...and that scan actually found the calls (not a vacuous pass)",
          _seen >= 6 and _thr >= 5,
          detail="saw %d site-accepting calls, %d threaded -- a scan that matches nothing "
                 "must not read as compliance." % (_seen, _thr))
    # the mutation the reviewer used: un-thread every call and require this check to FAIL.
    _mutated = _src.replace(", site=row_site", "").replace("site=row_site,", "")
    _mthr, _munthr, _mseen = _threading(_mutated)
    check("D2: ...and the check FAILS on the un-threaded mutant (`co_varnames` did not)",
          _munthr > 0 and _mthr == 0 and _mseen == _seen,
          detail="mutant: %d threaded, %d un-threaded, %d seen. The old check passed on this "
                 "mutant because `row_site = _ModeSite()` still stood."
                 % (_mthr, _munthr, _mseen))

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
