"""Controllable-trigger trace (task #16).

A frontier `newRoom: N` that strands the player usually lives at the LAST state
of a `changeState` cutscene -- an UNCONTROLLABLE transition (it auto-advances via
cues and has already consumed resources). Guarding it there crashes the game
(rm26 boarding). The fix: guard the CONTROLLABLE trigger -- the player-facing
handler (`handleEvent`/`Said`) that STARTS the cutscene via `(self changeState:
K)` -- so refusal happens before any animation or consumption.

Same controllable/uncontrollable supervisor principle as timer-deletion.

Algorithm:
  1. locate the frontier `newRoom: N` -> (instance I, changeState state S).
  2. if it's already in a controllable handler -> guard it directly (safe).
  3. else collect `(self changeState: K)` calls in I's CONTROLLABLE methods
     (self == I, so cross-instance calls like cloudScript's are excluded) with
     K <= S; the entry state is K* = max such K. That call site is the trigger.
  4. guard the trigger: wrap `(self changeState: K*)` in the item check.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from sexpr import (code_finditer, code_search, depth1_else,  # noqa: E402
                   form_chain, head_of, line_indent, mark_line, read_file, skip_noncode,
                   Sym, Str, Said)

CONTROLLABLE_METHODS = {"handleEvent", "doVerb"}

# ---------------------------------------------------------------------------
# Runtime guard mode (full / lite / stock), configured by `patcher._init_mode`.
#
# The mode is a GLOBAL the player sets in-game (0 = full, 1 = lite, 2 = stock --
# 0 must be full because uninitialized globals and stale saves read 0, and the
# default experience is the guarded one). A refusal-bearing wrap dispatches on
# it at run time; detection and placement never see it. `MODE is None` -- the
# state before `_init_mode`, and permanently for a game with no derivable
# display form -- emits the classic always-refuse shape, byte-identical to what
# every existing golden was built with.
#
#   MODE = {"g": <mode global index>,
#           "warned": "<the (proc.. {You have been warned!}) line>",
#           "alloc": callable -> (warned-word global index, "$%04x" mask)}
#
# Each SITE (one placement application -- a multi-clause wrap shares one bit,
# "every guard fires once" is per guard, not per clause) owns one warned bit in
# a trailing bitmask global, allocated lazily so a placement that fails to land
# does not burn one. LITE semantics: the first firing refuses exactly as full
# does and sets the bit; later firings print the warned line and let the
# original body run. STOCK lets the body run silently. Warned bits and the mode
# live in ordinary globals, so both persist through save/restore and reset on
# restart, like every other game variable.
MODE = None


class _ModeSite:
    """One guard site's lazily-allocated warned bit, shared across its clauses."""

    def __init__(self):
        self._forms = None

    def forms(self):
        """(allow_test, warn_line, mark_line), or None when the mode is unconfigured."""
        if MODE is None:
            return None
        if self._forms is None:
            g = MODE["g"]
            w, mask = MODE["alloc"]()
            self._forms = (
                "(or (== global%d 2) (and (== global%d 1) (& global%d %s)))" % (g, g, w, mask),
                "(if (== global%d 1) %s)" % (g, MODE["warned"]),
                # THE MARK IS UNCONDITIONAL, not lite-only [user, play, 2026-08-06: refused at
                # the mists trail in FULL, switched to lite, refused again -- "I kinda feel like
                # it should say You've been warned the second time"]. The bit means "this guard
                # has already told you about this danger", and a full-mode refusal did exactly
                # that. Costs full mode nothing: its allow test requires mode 1 or 2, so the bit
                # is never consulted there -- it only decides what LITE does after a switch.
                "(|= global%d %s)" % (w, mask))
        return self._forms


def stock_or(cond):
    """`cond`, bypassed in stock mode. For the SILENT guard kinds (arm-event, nav-assign,
    edge-exit close, award gate) and the register/flag holds: they never speak, so warn-once
    does not apply -- lite behaves as full there [user ruling 2026-08-06] -- but stock must
    let the stock behavior through."""
    if MODE is None:
        return cond
    return "(or (== global%d 2) %s)" % (MODE["g"], cond)


def stock_and(cond):
    """`cond`, WITHDRAWN in stock mode -- the conjunctive twin of `stock_or`, for the sites
    that ADD a condition rather than demand one. A strengthened flag READ becomes
    `(or <test> <cond>)`; under stock the added disjunct must contribute nothing, so it
    carries this wrapper and evaluates false while the mode global says stock. Same silent-kind
    doctrine as `stock_or`: these never speak, so lite behaves as full."""
    if MODE is None:
        return cond
    return "(and (not (== global%d 2)) %s)" % (MODE["g"], cond)


def guarded_wrap(guard_sexpr, body, refuse, site=None, deny_extra=(),
                 indent="\t\t\t", marker="; softlock-guard"):
    """The refusal-bearing wrap, in one place for every kind that says no.

    Classic (mode unconfigured): `(if <guard> <body> else <refuse>)` -- the exact v25 shape.
    Mode-aware: the else branch dispatches on the mode global --

        (if <guard>
            <body>
        else
            (if <stock, or lite-and-already-warned>
                <print the warned line (lite only)>
                <body>                                  ; proceed
            else
                <deny_extra lines, e.g. edgeHit resets>
                <refuse>
                <mark this site warned (lite only)>
            )
        )

    The body is duplicated once (pure text; the compiler sees two identical branches), which
    keeps the guard condition verbatim at the site -- nothing is hoisted into a helper, so a
    reader of the patched source still sees what is demanded where. `deny_extra` carries the
    mechanical lines that must accompany a refusal (guard_edgehit_clause's motion/flag resets).
    A `;` marker is always followed by a newline before any paren resumes (the balance gotcha,
    2026-08-06)."""
    b = indent + "\t"
    body = body.strip()
    forms = site.forms() if site is not None else None
    if forms is None:
        return (f"(if {guard_sexpr}\n{b}{body}\n{indent}else\n"
                + "".join(f"{b}{ln}\n" for ln in deny_extra)
                + f"{b}{refuse}  {marker}\n{indent})")
    allow, warn, mark = forms
    return (f"(if {guard_sexpr}\n{b}{body}\n{indent}else\n"
            f"{b}(if {allow}\n"
            f"{b}\t{warn}\n"
            f"{b}\t{body}\n"
            f"{b}else\n"
            + "".join(f"{b}\t{ln}\n" for ln in deny_extra)
            + f"{b}\t{refuse}\n"
            f"{b}\t{mark}\n"
            f"{b})  {marker}\n{indent})")


def is_sym(x, n=None):
    return isinstance(x, Sym) and (n is None or x.name == n)


def _message_send(form):
    if not (isinstance(form, list) and len(form) >= 2
            and isinstance(form[1], Sym) and form[1].is_selector()):
        return None
    recv = form[0].name if isinstance(form[0], Sym) else None
    groups, cur, args = [], None, []
    for tok in form[1:]:
        if isinstance(tok, Sym) and tok.is_selector():
            if cur is not None:
                groups.append((cur, args))
            cur, args = tok.sel, []
        else:
            args.append(tok)
    if cur is not None:
        groups.append((cur, args))
    return recv, groups


NAV_SELECTORS = ("north", "south", "east", "west")


def _nav_read(a0):
    """`'north'` when a0 is `(<recv> north:)` -- a nav-property read used as the destination.

    SCI1.1 spells a static exit as `(gCurRoom newRoom: (gCurRoom north:))` with `north 650`
    declared on the room -- the destination is a literal, one indirection away. Without this the
    site is invisible and the edge reports no-trigger (KQ6's rm640->rm650 Realm carry-out)."""
    ms = _message_send(a0) if isinstance(a0, list) else None
    if ms:
        _recv, groups = ms
        if len(groups) == 1 and groups[0][0] in NAV_SELECTORS and not groups[0][1]:
            return groups[0][0]
    return None


def nav_props(forms):
    """{direction: room} declared in this file's instance property lists (`north 650`).

    A direction declared twice with DIFFERENT values resolves to nothing -- the read is dynamic
    then, and guessing would place a guard on the wrong edge. Zero is "no exit", not a room."""
    seen = defaultdict(set)
    for f in forms:
        if not (isinstance(f, list) and len(f) >= 3 and is_sym(f[0], "instance")):
            continue
        for part in f:
            if isinstance(part, list) and part and is_sym(part[0], "properties"):
                toks = part[1:]
                for k, v in zip(toks, toks[1:]):
                    if isinstance(k, Sym) and k.name in NAV_SELECTORS \
                            and isinstance(v, int) and v:
                        seen[k.name].add(v)
    return {d: next(iter(vs)) for d, vs in seen.items() if len(vs) == 1}


def _script_id(form):
    """`("ScriptID", script, export)` if this form is a `(ScriptID S N)` call, else None."""
    if (isinstance(form, list) and len(form) >= 3 and is_sym(form[0], "ScriptID")
            and isinstance(form[1], int) and isinstance(form[2], int)):
        return ("ScriptID", form[1], form[2])
    return None


def exports_of(forms):
    """`(script_number, {export_index: name})` from a file's own `(script# N)` and `(public ...)`.

    An SCI1.1 room arms a cutscene in another script BY EXPORT NUMBER, so this is what turns
    `(ScriptID 344 3)` in rm340.sc into `catchNiteMare` in nightMare.sc."""
    num, exports = None, {}
    for f in forms:
        if not isinstance(f, list) or not f:
            continue
        if is_sym(f[0], "script#") and len(f) > 1 and isinstance(f[1], int):
            num = f[1]
        elif is_sym(f[0], "public"):
            rest = f[1:]
            for name, idx in zip(rest[0::2], rest[1::2]):
                if isinstance(name, Sym) and isinstance(idx, int):
                    exports[idx] = name.name
    return num, exports


def find_arming(forms, targets):
    """A controllable `setScript:` in THIS file that arms any of `targets`.

    `targets` holds both spellings of the same cutscene -- its instance NAME and its
    `("ScriptID", script, export)` -- because the file that arms it and the file that owns it are
    often not the same file. Returns the same shape `find_trigger` does, plus the source PATTERN
    to rewrite, since a ScriptID arming is not spelled with the instance's name."""
    _nr, _cs, ss, pc = analyze_room(forms)
    hits = [(i, m, t) for (i, m, t, _recv, _pos) in ss if t in targets and i is not None]
    if not hits:
        # ...or the room does not `setScript:` anything: it CALLS one of the helper script's
        # exported procedures and the cutscene starts itself. KQ6's capture is this shape --
        # `rm340::init` runs `(proc342_2)`, which does `setScript: toGehenna`, which ends in
        # `newRoom: 405`. The guards grab you on ARRIVAL, so there is no exit to guard; the call
        # is the commit point.
        want_nums = {t[1] for t in targets if isinstance(t, tuple) and len(t) == 2
                     and t[0] == "proc" and isinstance(t[1], int)}
        # ...exact names when the caller has RESOLVED which procedures arm the crossing
        # (`reaching_procs`); the script-number form remains for callers who have not, but it
        # takes the first call found and n342's proc342_0 is an ordinary arrival -- resolution
        # is what keeps a normal arrival from being refused as if it were the seizure.
        want_names = {t[1] for t in targets if isinstance(t, tuple) and len(t) == 2
                      and t[0] == "proc" and isinstance(t[1], str)}
        phits = [(i, m, nm) for (i, m, nm) in pc
                 if i is not None and (nm in want_names
                                       or any(nm.startswith("proc%d_" % s) for s in want_nums))]
        if not phits:
            return None
        inst, meth, nm = phits[0]
        return {"kind": "proc-call", "trigger_instance": inst, "trigger_method": meth,
                "target_script": nm, "target_pattern": re.escape(nm)}
    if not hits:
        return None
    controllable = [h for h in hits if h[1] in CONTROLLABLE_METHODS]
    inst, meth, target = (controllable or hits)[0]
    pattern = (r"\(ScriptID\s+%d\s+%d\s*\)" % (target[1], target[2])
               if isinstance(target, tuple) else re.escape(target))
    return {"kind": "setscript" if controllable else "arm-event",
            "trigger_instance": inst, "trigger_method": meth,
            "target_script": target if isinstance(target, str) else "ScriptID %d %d" % target[1:],
            "target_pattern": pattern}


def find_all_armings(forms, target):
    """EVERY controllable arming of `target` -- a machine with N ways in needs N wraps.

    Play-found (KQ6 rm220, 2026-08-03): `wearClothingScr` is armed from egoDoVerbCode::doVerb
    AND from guardHut::doVerb -- using the clothes on the HUT walked straight through the short
    door's guard, because find_trigger returns the first controllable arming and the placement
    wrapped only that one. Wrapping one door of an N-door commitment is a bypass, not a guard."""
    _nr, _cs, ss, _pc = analyze_room(forms)
    def norm(t):
        return t if isinstance(t, str) else "ScriptID %d %d" % t[1:]
    return [{"kind": "setscript", "trigger_instance": i, "trigger_method": m,
             "target_script": norm(t),
             "target_pattern": (re.escape(t) if isinstance(t, str)
                                else r"\(ScriptID\s+%d\s+%d\s*\)" % (t[1], t[2]))}
            for (i, m, t, _r, _pos) in ss
            if norm(t) == norm(target) and i is not None and m in CONTROLLABLE_METHODS]


def find_proc_calls(forms, names, methods=("init",)):
    """Calls to any of `names` inside one of `methods` -- one placement per call site.

    Restricted to `init` by default because this exists for ARRIVAL captures, where the game
    commits for you the moment you walk in. A call from `notify`/`cue` is mid-cutscene: refusing
    there leaves the scene half-run, which is the hang this module's whole controllable/
    uncontrollable split is about. `methods=None` lifts the restriction for callers who are
    CLASSIFYING the call sites (is any of them an init arrival-commit?) rather than placing
    a refusal on them."""
    _nr, _cs, _ss, pc = analyze_room(forms)
    return [{"kind": "proc-call", "trigger_instance": i, "trigger_method": m,
             "target_script": nm, "target_pattern": re.escape(nm)}
            for (i, m, nm) in pc
            if i is not None and nm in names and (methods is None or m in methods)]


def _arming_graph(forms, to_room):
    """(producers, owner_of_arming) for this file's `newRoom: to_room`: the owners that perform
    it, and for every `setScript:` target, the owners (instances or procedures) that arm it."""
    owner_of_arming, producers = defaultdict(set), set()

    def scan(form, owner):
        if not isinstance(form, list) or not form:
            return
        h = form[0]
        if is_sym(h, "instance") or is_sym(h, "class"):
            name = form[1].name if len(form) > 1 and isinstance(form[1], Sym) else owner
            for s in form[2:]:
                scan(s, name)
            return
        if is_sym(h, "procedure"):
            sig = form[1] if len(form) > 1 else None
            name = (sig[0].name if isinstance(sig, list) and sig and isinstance(sig[0], Sym)
                    else owner)
            for s in form[2:]:
                scan(s, name)
            return
        ms = _message_send(form)
        if ms:
            _recv, groups = ms
            for sel, args in groups:
                a0 = args[0] if args else None
                if sel == "newRoom" and a0 == to_room and owner:
                    producers.add(owner)
                elif sel == "setScript" and isinstance(a0, Sym) and owner:
                    owner_of_arming[a0.name].add(owner)
        for s in form:
            scan(s, owner)

    for f in forms:
        scan(f, None)
    return producers, owner_of_arming


def reaching_procs(forms, to_room):
    """Exported procedures of THIS file whose cutscene chain ends in `newRoom: to_room`.

    A helper script exports several procedures and only one of them leads where we care: n342 has
    `proc342_0` (an ordinary arrival), `proc342_1` and `proc342_2` (the guards seizing you), and
    only the last reaches `newRoom: 405`. Guarding the wrong one would refuse a normal arrival --
    a wall, not a gate -- which is why this is derived instead of taking the first call found.

    Walks BACKWARD over `setScript:` armings: who performs the newRoom, who arms them, and so on
    until an exported `procN_M` is reached. Owner scope is the enclosing instance or procedure."""
    producers, owner_of_arming = _arming_graph(forms, to_room)
    seen, frontier, out = set(producers), list(producers), set()
    while frontier:
        cur = frontier.pop()
        if re.fullmatch(r"proc\d+_\d+", cur):
            out.add(cur)
            continue
        for up in owner_of_arming.get(cur, ()):
            if up not in seen:
                seen.add(up)
                frontier.append(up)
    return out


def reaching_owners(forms, to_room):
    """Every owner -- instance OR procedure -- from which `newRoom: to_room` is reachable along
    this file's own arming graph: the set whose armings are ways IN to the crossing.

    The complement is the point (play-found 2026-08-05): nightMare.sc exports `blowinIt`, rm340
    arms it by export number, and it hands off to `playTheFlute` (script 85) -- never to
    `catchNiteMare`, the instance that owns `newRoom: 155`. An export outside this set is
    flavor: wrapping its arming taxes the player while the crossing rides free."""
    producers, owner_of_arming = _arming_graph(forms, to_room)
    seen, frontier = set(producers), list(producers)
    while frontier:
        cur = frontier.pop()
        for up in owner_of_arming.get(cur, ()):
            if up not in seen:
                seen.add(up)
                frontier.append(up)
    return seen


def find_nav_assign(forms, target_room):
    """A NAV-PROPERTY ASSIGNMENT that routes this room INTO `target_room` -- the shortcut
    spelling the cliff bypass hid behind (play-found 2026-08-04, the v12 catacombs guard):
    `rm300::init` does `(self north: 340)` once the puzzles are solved, and the shared region
    code exits with `newRoom: (global2 north:)` -- so the crossing exists in the model (the
    edge was derived) while the room's own file contains no `newRoom:` for find_trigger to see.

    Returns a placement for the ASSIGNMENT, with the `fallback` value the game's own
    other-route assignment to the same property in the same file (`(self north: 320)`), or
    None when there is no unique fallback -- re-deciding a route is only safe when the game
    itself names the other route."""
    hits, values = [], {}

    def walk(form, inst, meth):
        if not isinstance(form, list) or not form:
            return
        h = form[0]
        if is_sym(h, "instance") or is_sym(h, "class"):
            name = form[1].name if len(form) > 1 and isinstance(form[1], Sym) else inst
            for s in form[2:]:
                walk(s, name, meth)
            return
        if is_sym(h, "method"):
            sig = form[1]
            mname = sig[0].name if isinstance(sig, list) and sig and isinstance(sig[0], Sym) \
                else "?"
            for s in form[2:]:
                walk(s, inst, mname)
            return
        ms = _message_send(form)
        if ms:
            recv, groups = ms
            for sel, args in groups:
                if sel in ("north", "south", "east", "west") and args \
                        and isinstance(args[0], int) and recv in ("self",):
                    values.setdefault(sel, set()).add(args[0])
                    if args[0] == target_room and inst is not None:
                        hits.append((inst, meth, sel, args[0]))
        for s in form:
            walk(s, inst, meth)

    for f in forms:
        walk(f, None, None)
    for (inst, meth, prop, val) in hits:
        others = values.get(prop, set()) - {val}
        if len(others) == 1:
            return {"kind": "nav-assign", "trigger_instance": inst, "trigger_method": meth,
                    "prop": prop, "target_room": val, "fallback": next(iter(others))}
    return None


_STATE_DISPATCH = re.compile(r"\(=\s*\S+\s+param\d+\)|param\d+")

_MASKED = {}


def code_only(text):
    """`text` with every COMMENT, message string and Said spec blanked to spaces.

    Same span, character for character, so an offset computed on the original indexes the same
    place here -- which is the whole point: the callers work in offsets into the real file and
    only want to know whether a piece of CODE says something.

    It exists because `arming_contexts` decides `handsoff_before` -- is this arming an arrival
    commit, the classification LB2's play test made expensive -- by searching the source between
    two offsets for `handsOff:`, and source contains prose. A room whose comment mentions the
    handsOff it used to have, or a `Print {…}` line quoting one, read as the game taking the
    controls away. The misclassification runs both ways and neither is benign: a false commit
    re-sites a guard away from the site it belongs on.

    The three forms are SCI's own and the same three `_block_span` already skips: `;` to end of
    line, `{...}` strings, `'...'` Said specs. Cached per text object, since the callers ask
    repeatedly about spans of one file."""
    hit = _MASKED.get(id(text))
    if hit is not None and hit[0] == text:
        return hit[1]
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == ";":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif c in "{'":
            close = "}" if c == "{" else "'"
            j = text.find(close, i + 1)
            j = n - 1 if j < 0 else j
            out.append(" " * (j - i + 1))
            i = j + 1
        else:
            out.append(c)
            i += 1
    masked = "".join(out)
    _MASKED[id(text)] = (text, masked)
    return masked


def _named_regions(text):
    """[(name, start, end)] for every `(instance NAME ...)` / `(class NAME ...)` block. Shared
    code often lives on a CLASS (KQ6's CliffRoom), so both spellings are one enumeration."""
    out = []
    for m in re.finditer(r"\((?:instance|class)\s+(\w+)\b", text):
        try:
            s, e = _block_span(text, m.start())
        except Exception:                          # noqa: BLE001 -- unbalanced tail
            continue
        out.append((m.group(1), s, e))
    return out


def find_cue_chain_armings(room_text, cand_text, room_global, target_script):
    """Controllable armings of the script CHAIN that delivers a room-cue exit -- the refusal
    site an arm-event placement cannot be (play feedback 2026-08-04: the silent arm-gate let
    the player climb a whole cliff face and then just... stopped).

    The shape: the room's `cue` method arms the exit machine under a switch case
    (`(1 (setScript: nextCliffUp))`), and what CUES the room is a script chain in shared code
    (KQ6's rCliffs: the top rock's `takeStep` state arms `nextScreenUp`, which does
    `(global2 cue: 1)`). The player's controllable moment is where that chain is ARMED from a
    handler. So: read the delivering case value(s) off the room's cue method, find the scripts
    in `cand_text` that cue the room with one of them, walk the arming chain backward
    (`reaching_procs`' idea, over setScript instead of procs), and return every CONTROLLABLE
    arming -- ALL of them, a machine with N armings needs N wraps (finding #4, and again #8).
    Chains that cue a different case (the DOWN-climb cues 0/-1) never enter the walk, which is
    what makes refusing here unable to strand a descending player."""
    cases = set()
    for m in re.finditer(r"\(method\s+\(cue\b", room_text):
        s, e = _block_span(room_text, m.start())
        region = room_text[s:e]
        for am in re.finditer(r"setScript:\s*%s\b" % re.escape(target_script), region):
            head = enclosing_clause_head(region, am.start())
            try:
                cases.add(int(head))
            except (TypeError, ValueError):
                pass
    if not cases:
        return []
    regions = _named_regions(cand_text)

    def owner_at(pos):
        for (name, s, e) in regions:
            if s <= pos < e:
                return name, s, e
        return None, None, None

    def method_at(pos, s, e):
        best = None
        for mm in re.finditer(r"\(method\s+\((\w+)", cand_text[s:e]):
            try:
                ms, me = _block_span(cand_text, s + mm.start())
            except Exception:                      # noqa: BLE001
                continue
            if ms <= pos < me:
                best = mm.group(1)
        return best

    cuers = set()
    for m in re.finditer(r"\(global%d\s+cue:\s*(-?\d+)\s*\)" % room_global, cand_text):
        if int(m.group(1)) in cases:
            name, _s, _e = owner_at(m.start())
            if name:
                cuers.add(name)
    _ANY = r"(?:[^()]|\([^()]*\))*"
    out, keys = [], set()
    targets, seen = sorted(cuers), set(cuers)
    for _depth in range(6):
        nxt = []
        for tgt in targets:
            for am in re.finditer(r"\(%ssetScript:\s*%s\b%s\)" % (_ANY, re.escape(tgt), _ANY),
                                  cand_text):
                name, s, e = owner_at(am.start())
                if not name:
                    continue
                meth = method_at(am.start(), s, e)
                if meth in CONTROLLABLE_METHODS:
                    k = (name, meth, tgt)
                    if k not in keys:
                        keys.add(k)
                        out.append({"kind": "setscript", "trigger_instance": name,
                                    "trigger_method": meth, "target_script": tgt,
                                    "target_pattern": re.escape(tgt)})
                elif name not in seen:
                    seen.add(name)
                    nxt.append(name)
        if not nxt:
            break
        targets = nxt
    return out


def _immediate_children(text, s, e):
    """(kind, start, end) for every top-level element of text[s:e]: 'form' for a balanced
    `(...)`, 'tok' for a bare token -- skipping `{..}` strings, `'..'` Said specs and `;`
    comments, the same skip set as `_block_span`. The structural primitive `arming_contexts`
    descends with."""
    out, i = [], s
    while i < e:
        c = text[i]
        if c == "{":
            j = text.find("}", i)
            i = (j + 1) if 0 <= j < e else e
            continue
        if c == "'":
            j = text.find("'", i + 1)
            i = (j + 1) if 0 <= j < e else e
            continue
        if c == ";":
            j = text.find("\n", i)
            i = (j + 1) if 0 <= j < e else e
            continue
        if c == "(":
            fs, fe = _block_span(text, i)
            out.append(("form", fs, min(fe, e)))
            i = fe
            continue
        if c.isspace() or c == ")":
            i += 1
            continue
        j = i
        while j < e and not text[j].isspace() and text[j] not in "(){;')":
            j += 1
        out.append(("tok", i, j))
        i = j
    return out


def arming_contexts(text, target_script, ego=None):
    """Every `setScript: <target_script>` site in this file, with the CONDITION PATH the game
    itself runs before arming -- what the sole-exit deferral's arrival-commit triage reads.

    Play-found (LB2, 2026-08-11): the deferral's arm-gate at rm250 sat INSIDE the commit -- the
    hands-off cab ride from rm300 had already hidden the ego when `rm250::init` declined to arm
    `sACTBREAK`, leaving a hidden ego with no script. Whether a site is such a commit is written
    in the arming's own context: the method it runs in, the tests on the path to it, and whether
    the game takes the controls away first. This returns that context; classifying it is the
    caller's job (it needs model knowledge this file does not have).

    Per arming: `instance`/`method` that perform it; `heads` = the positive-branch tests
    enclosing it, innermost last (`if` tests, `cond` clause heads); `cases` = (discriminator
    text, value) for enclosing `switch` cases; `poisoned` = True when the path runs through an
    `else` arm, whose condition is only spelled as the negation of its siblings -- a path this
    reader refuses to reconstruct; `handsoff_before` = a `handsOff:` send or an ego `hide:` on
    the straight-line path from the method entry to the arming, the game taking the controls
    before the arming runs; `state_case` = the enclosing changeState state number, when the
    method dispatches on one. Head/case text is whitespace-normalized source syntax."""
    _ANY = r"(?:[^()]|\([^()]*\))*"
    pat = re.compile(r"\(%ssetScript:\s*%s\b%s\)" % (_ANY, re.escape(target_script), _ANY))
    regions = _named_regions(text)
    out = []
    for am in pat.finditer(text):
        p = am.start()
        inst = span = None
        for (name, s0, e0) in regions:
            if s0 <= p < e0:
                inst, span = name, (s0, e0)
        if span is None:
            continue
        meth = meth_span = None
        for mm in re.finditer(r"\(method\s+\((\w+)", text[span[0]:span[1]]):
            ms, me = _block_span(text, span[0] + mm.start())
            if ms <= p < me:
                meth, meth_span = mm.group(1), (ms, me)
        if meth_span is None:
            continue
        heads, cases, poisoned, state_case = [], [], False, None
        segments = []                      # straight-line spans executed before the arming
        cur = meth_span
        seg_start = None
        branch = None                      # innermost enclosing branch span (for -_branch tests)
        while True:
            kids = _immediate_children(text, cur[0] + 1, cur[1] - 1)
            if seg_start is not None:
                nxt = next(((a, b) for (k, a, b) in kids if a <= p < b), None)
                if nxt:
                    segments.append((seg_start, nxt[0]))
            toks = [(a, b) for (k, a, b) in kids if k == "tok"]
            headsym = text[toks[0][0]:toks[0][1]] if toks else ""
            child = next(((a, b) for (k, a, b) in kids if k == "form" and a <= p < b), None)
            if child is None:
                break
            first_form = next(((a, b) for (k, a, b) in kids if k == "form"), None)
            if headsym == "if":
                test = kids[1] if len(kids) > 1 else None
                else_tok = next(((a, b) for (k, a, b) in kids if k == "tok"
                                 and text[a:b] == "else"), None)
                if test and not (test[1] <= p < test[2]):
                    if else_tok and p >= else_tok[1]:
                        poisoned = True
                        seg_start = else_tok[1]
                        branch = (else_tok[1], cur[1] - 1)
                    else:
                        heads.append(re.sub(r"\s+", " ", text[test[1]:test[2]]).strip())
                        seg_start = test[2]
                        branch = (test[2], else_tok[0] if else_tok else cur[1] - 1)
            elif headsym in ("cond",):
                # child is the clause; its own first element is the test (or `else`)
                ck = _immediate_children(text, child[0] + 1, child[1] - 1)
                if ck:
                    (k0, a0, b0) = ck[0]
                    if k0 == "tok" and text[a0:b0] == "else":
                        poisoned = True
                    elif not (a0 <= p < b0):
                        heads.append(re.sub(r"\s+", " ", text[a0:b0]).strip())
                    seg_start = b0
                    branch = (b0, child[1] - 1)
            elif headsym in ("switch", "switchto"):
                disc = kids[1] if len(kids) > 1 else None
                ck = _immediate_children(text, child[0] + 1, child[1] - 1)
                if ck and disc:
                    (k0, a0, b0) = ck[0]
                    v = text[a0:b0]
                    dtxt = re.sub(r"\s+", " ", text[disc[1]:disc[2]]).strip()
                    if k0 == "tok" and v == "else":
                        poisoned = True
                    elif k0 == "tok" and re.fullmatch(r"-?\d+", v):
                        # THE MACHINE'S OWN STATE DISPATCH, recognised by its FORM. This used to
                        # ask whether the discriminator text contained the substring "state",
                        # which is a bet on what a decompiler names a property (review §1.4) --
                        # and getting it wrong turns a state number into a path CONDITION.
                        # SCI's idiom is `(switch (= <prop> param1) ...)`: the method's own
                        # parameter, stored. A game that switches on the parameter directly
                        # spells the same dispatch. Measured over all four games' changeState
                        # switches (1712 of them): the name test and this one agree everywhere,
                        # including on KQ6's one switch that is neither (its discriminator is
                        # `value`, and it is not a state dispatch).
                        if meth == "changeState" and _STATE_DISPATCH.fullmatch(dtxt):
                            state_case = int(v)
                        else:
                            cases.append((dtxt, int(v)))
                    else:
                        poisoned = True    # a symbolic case: value unresolved here
                    seg_start = b0
                    branch = (b0, child[1] - 1)
            else:
                if seg_start is None and headsym == "method":
                    seg_start = first_form[1] if first_form else cur[0] + 1
            if child[0] == am.start():
                break
            cur = child
        segments.append((seg_start if seg_start is not None else meth_span[0], p))
        hide_pat = (re.compile(r"\(%s\b%shide:" % (re.escape(ego), _ANY))
                    if ego else None)

        code = code_only(text)             # comments and message strings are not sends

        def _taken(a, b):
            return (re.search(r"handsOff:", code[a:b]) is not None
                    or bool(hide_pat and hide_pat.search(code[a:b])))
        handsoff = any(_taken(a, b) for (a, b) in segments if a is not None and a < b)
        # ...and branch-wide: a branch that takes the controls AFTER the arming (rm480's
        # case-740 hides the ego two statements later) is just as much a commit -- refusing
        # the arming lets the rest of the branch run against a scene that never starts.
        handsoff_branch = handsoff
        if not handsoff_branch and branch is not None and am.end() < branch[1]:
            handsoff_branch = _taken(am.end(), branch[1])
        out.append({"instance": inst, "method": meth, "pos": p,
                    "heads": heads, "cases": cases, "poisoned": poisoned,
                    "state_case": state_case, "handsoff_before": handsoff,
                    "handsoff_branch": handsoff_branch,
                    "target_script": target_script})
    return out


def wrap_all_armings_in_source(text, placement, guard_sexpr, refuse, site=None):
    """Wrap EVERY `setScript: <target>` clause in the placement's method -- the multi-site twin
    of `wrap_trigger_in_source`'s setscript branch, which wraps only the first match. KQ6's
    rock-stepping arms `takeStep` from FOUR geometric clauses of one handler; wrapping one is a
    bypass wearing a guard's face. Clause spans are collected up front and wrapped back-to-front
    so earlier offsets stay valid, and two armings inside one clause wrap once."""
    inst, meth = placement["trigger_instance"], placement["trigger_method"]
    inst_span = _find_region(text, r"\((?:instance|class)\s+%s\b" % re.escape(inst))
    if not inst_span:
        return text, 0
    i0, i1 = inst_span
    meth_rel = _find_region(text[i0:i1], r"\(method\s+\(%s\b" % re.escape(meth))
    if not meth_rel:
        return text, 0
    m0, m1 = i0 + meth_rel[0], i0 + meth_rel[1]
    region = text[m0:m1]
    _ANY = r"(?:[^()]|\([^()]*\))*"
    tpat = placement.get("target_pattern") or re.escape(placement["target_script"])
    spans = []
    for ssm in re.finditer(r"\(%ssetScript:\s*%s\b%s\)" % (_ANY, tpat, _ANY), region):
        clause = _enclosing_clause_body(region, ssm.start())
        span = clause if clause else (ssm.start(), ssm.end())
        # overlap = the same or a nested clause; wrapping both would corrupt the outer one
        if not any(bs < span[1] and span[0] < be for (bs, be) in spans):
            spans.append(span)
    n = 0
    # ONE warned bit for all clauses -- and for every other call the caller makes for the same
    # guard, when it threads its own site in (a spec row is wrapped at several armings, cue-chain
    # arms and entry rooms; a site minted here would give each of them its own warning).
    site = site if site is not None else _ModeSite()
    for (bs, be) in sorted(spans, reverse=True):
        region = (region[:bs] + guarded_wrap(guard_sexpr, region[bs:be], refuse, site=site)
                  + region[be:])
        n += 1
    return text[:m0] + region + text[m1:], n


def _mentions_oncontrol(form, octx=None):
    """Does this subtree test where the ego is STANDING? `(gEgo onControl: 1)`.

    SCI1.1's positional movement: the room's `doit` compares `onControl` against a control-colour
    mask and calls `newRoom:` when the player walks onto it. That is a player-initiated crossing --
    they walked there -- even though `doit` is not one of the handler methods.

    `octx` is the method's set of variables ASSIGNED from an onControl read -- rm550 hoists
    the read (`(= temp0 (global0 onControl: 1))`) and dispatches its cond on `temp0`, so a
    test mentioning such a variable is the same standing-position question one indirection
    away (play finding #11: the inline-only reading left the hoisted spelling classified as
    an adversarial arm-event, and its un-gated handsOff sibling hung the game)."""
    if isinstance(form, Sym):
        return (form.name == "onControl" or (form.is_selector() and form.sel == "onControl")
                or (octx is not None and not form.is_selector() and form.name in octx))
    if isinstance(form, list):
        return any(_mentions_oncontrol(x, octx) for x in form)
    return False


def _mentions_ego_position(form, ego=None):
    """Does this subtree read WHERE THE EGO IS, in the COORDINATE spelling -- `(< (gEgo y:) 150)`?

    The same standing-position fact `_mentions_oncontrol` reads in control-mask form, spelled
    with no `onControl` anywhere: KQ5's rm85 arms the kidnap on `(< (global0 y:) 150)` in
    `doit`, and the mask-only reading classified it an adversarial arm-event -- whose bare
    arming wrap left the `(proc0_2)` handsOff sibling un-gated, the exact shape of play
    finding #11. RESTRICTED TO THE EGO, which is why the caller must thread the ego's global
    index: a cond on another actor's x/y is animation logic, not a player-initiated crossing,
    and reading those as positional would hand arm-clause wraps to scenes the player never
    walked into. `ego=None` (callers that cannot name the ego) reads nothing -- the
    permissive direction is the old classification, not a guess."""
    if ego is None or not isinstance(form, list):
        return False
    ms = _message_send(form)
    if ms:
        recv, groups = ms                      # _message_send returns the receiver NORMALIZED
        name = recv if isinstance(recv, str) else \
            (recv.name if isinstance(recv, Sym) else None)
        # `edgeHit` is the third spelling of the same fact: the ego WALKED to a screen edge
        # and the engine recorded which one. A clause dispatching on `(gEgo edgeHit:)` is a
        # player-initiated crossing exactly as an onControl mask or a coordinate compare is --
        # KQ5's rooms spell their scripted edge exits this way (rm036's `doit` reads it twice
        # and `newRoom:`s the result). ARGUMENT-FREE ONLY: `(gEgo edgeHit: 0)` is the WRITE
        # that clears the code, not a read of where the player stands.
        if name == "global%d" % ego \
                and any(sel in ("x", "y", "edgeHit") and not args for sel, args in groups):
            return True
    return any(_mentions_ego_position(x, ego) for x in form if isinstance(x, list))


def analyze_room(forms, ego=None):
    """newRoom sites, changeState-call sites and setScript-call sites, tagged with (instance,
    method, ...). setScript is the OTHER way a controllable handler starts an uncontrollable
    sequence: `(self setScript: closer)` where the `closer` Script does the frontier newRoom --
    KQ4's rm45 amulet handover. Same shape as changeState, a different selector."""
    newroom_sites = []   # (instance, method, state, room, positional)
    cs_calls = []        # (instance, method, state_target, receiver)
    ss_calls = []        # (instance, method, target_script_name, receiver)
    proc_calls = []      # (instance, method, procedure name) -- `(proc342_2)`, how a room runs a
    #                      helper script's cutscene when it does not `setScript:` anything itself

    def walk(form, inst, meth, state, pos=False, octx=None):
        if not isinstance(form, list) or not form:
            return
        h = form[0]
        if is_sym(h, "instance") or is_sym(h, "class"):
            name = form[1].name if len(form) > 1 and isinstance(form[1], Sym) else "?"
            for s in form[2:]:
                walk(s, name, meth, state, pos, octx)
            return
        if is_sym(h, "method"):
            sig = form[1]
            mname = sig[0].name if isinstance(sig, list) and sig and isinstance(sig[0], Sym) else "?"
            mctx = set()                   # onControl-derived variables, fresh per method
            for s in form[2:]:
                walk(s, inst, mname, None, False, mctx)
            return
        # `(= temp0 (gEgo onControl: 1))` -- the hoisted spelling of the standing-position test.
        # Record the variable so the cond that dispatches on it still reads as positional.
        if is_sym(h, "=") and octx is not None and len(form) >= 3 \
                and isinstance(form[1], Sym) and _mentions_oncontrol(form[2], octx):
            octx.add(form[1].name)
        if is_sym(h, "switch") or is_sym(h, "switchto"):
            seq = 0
            for clause in form[2:]:
                if isinstance(clause, list) and clause:
                    if isinstance(clause[0], int):
                        st = clause[0]
                    elif is_sym(clause[0], "else"):
                        st = state
                    else:
                        st = seq  # switchto: implicit sequential
                    seq += 1
                    for b in clause[1:]:
                        walk(b, inst, meth, st, pos, octx)
            return
        # A `cond`/`if` whose TEST asks where the ego is standing makes its body positional -- the
        # player walked onto that control colour, so the crossing is theirs to refuse.
        if is_sym(h, "cond"):
            for clause in form[1:]:
                if isinstance(clause, list) and clause:
                    cpos = pos or _mentions_oncontrol(clause[0], octx) \
                        or _mentions_ego_position(clause[0], ego)
                    for b in clause[1:]:
                        walk(b, inst, meth, state, cpos, octx)
            return
        if is_sym(h, "if"):
            tpos = pos or (len(form) > 1 and (_mentions_oncontrol(form[1], octx)
                                              or _mentions_ego_position(form[1], ego)))
            for s in form[2:]:
                walk(s, inst, meth, state, tpos, octx)
            return
        if isinstance(h, Sym) and not h.is_selector() and re.fullmatch(r"proc\d+_\d+", h.name):
            proc_calls.append((inst, meth, h.name))
            for s in form[1:]:
                walk(s, inst, meth, state, pos, octx)
            return
        ms = _message_send(form)
        if ms:
            recv, groups = ms
            for sel, args in groups:
                a0 = args[0] if args else None
                if sel == "newRoom" and isinstance(a0, int):
                    newroom_sites.append((inst, meth, state, a0, pos))
                elif sel == "newRoom" and _nav_read(a0):
                    # destination = the room's own declared nav property, resolved by the
                    # caller against nav_props(forms) -- see find_trigger.
                    newroom_sites.append((inst, meth, state, ("nav", _nav_read(a0)), pos))
                elif sel == "newRoom" and isinstance(a0, Sym):
                    # destination = a VARIABLE the room computed earlier: `(gGame newRoom: local0)`.
                    # The third destination shape, and the one that made LB2's act break
                    # unguardable -- `find_trigger` matched only literals, so the crossing into
                    # the inquest reported "no controllable trigger" while the analysis knew the
                    # edge perfectly well. Resolved by the caller, which knows the target room and
                    # so only has to confirm the variable can hold it -- see find_trigger.
                    newroom_sites.append((inst, meth, state, ("var", a0.name), pos))
                elif sel == "changeState" and isinstance(a0, int):
                    cs_calls.append((inst, meth, a0, recv))
                elif sel == "setScript" and isinstance(a0, Sym):
                    ss_calls.append((inst, meth, a0.name, recv, pos))
                elif sel == "setScript" and _script_id(a0):
                    # `(global2 setScript: (ScriptID 344 3))` -- SCI1.1 arms a cutscene that lives
                    # in ANOTHER script by export number rather than by name. Recorded under a
                    # canonical key so the armer can be matched to the script that owns the
                    # `newRoom` (see `exports_of` / `find_arming`).
                    ss_calls.append((inst, meth, _script_id(a0), recv, pos))
                for a in args:
                    walk(a, inst, meth, state, pos, octx)
            walk(form[0], inst, meth, state, pos, octx)
            return
        for s in form:
            walk(s, inst, meth, state, pos, octx)

    for f in forms:
        walk(f, None, None, None, False)
    return newroom_sites, cs_calls, ss_calls, proc_calls


def _var_assigned_rooms(forms):
    """{variable name: {room numbers assigned to it}} over this file's `(= <var> <int>)`.

    DELIBERATELY NOT a second `extract.var_room_values`. That function DERIVES a destination set --
    it has to decide which literals are rooms at all, which needs the class table and hence the IR.
    Here the destination is already known (`target_room` came from the analysed edge), so the only
    question is the much weaker "can this variable hold that room", and the answer is a plain scan
    of the source we are about to edit. Answering it here keeps the patcher reading the file it
    patches instead of carrying a resolution it cannot verify against the text."""
    out = defaultdict(set)

    def walk(form):
        if not isinstance(form, list):
            return
        if (len(form) == 3 and is_sym(form[0], "=") and isinstance(form[1], Sym)
                and isinstance(form[2], int)):
            out[form[1].name].add(form[2])
        for s in form:
            walk(s)

    for f in forms:
        walk(f)
    return out


def _edge_dispatch_vars(forms):
    """Variable names assigned from an `edgeToRoom:` read -- `(= temp0 (self edgeToRoom: ...))`.

    `edgeToRoom` maps an edge code to the room's OWN direction properties, so a variable
    holding its result can hold exactly the rooms `nav_props` declares -- the DYNAMIC spelling
    of the same one-indirection static exit `_nav_read` already resolves (`(gCurRoom newRoom:
    (gCurRoom north:))`). KQ5 spells nearly every scripted edge exit this way (rm036::doit:
    `(= temp0 (self edgeToRoom: (global0 edgeHit:)))` then `(global2 newRoom: temp0)`), and
    without this the site is invisible and the edge reports no-trigger."""
    out = set()

    def walk(form):
        if not isinstance(form, list):
            return
        if len(form) == 3 and is_sym(form[0], "=") and isinstance(form[1], Sym):
            ms = _message_send(form[2]) if isinstance(form[2], list) else None
            if ms and any(sel == "edgeToRoom" for sel, _args in ms[1]):
                out.add(form[1].name)
        for s in form:
            walk(s)

    for f in forms:
        walk(f)
    return out


def _split_if(form):
    """`(if H then... else else...)` as text -> (H, [then...], [else...]), each piece verbatim.

    Purely textual, same contract as `_block_span`: comments and `{...}` strings skipped, an
    unparseable form returns (None, [], []) so the caller declines the site instead of editing
    it. A form with no `else` returns an empty else list -- fork-reading callers (patcher's
    `_fork_head`) require both directions and refuse such a site."""
    m = re.match(r"\(\s*if\b", form)
    if not m:
        return None, [], []
    i, n = m.end(), len(form) - 1
    parts = []
    while i < n:
        c = form[i]
        if c in " \t\n\r":
            i += 1
            continue
        if c == ";":
            j = form.find("\n", i)
            if j < 0:
                break
            i = j
            continue
        if c == "(":
            b = _block_span(form, i)
            if not b:
                return None, [], []
            parts.append(form[b[0]:b[1]])
            i = b[1]
            continue
        mm = re.match(r"[^\s()]+", form[i:])
        parts.append(mm.group(0))
        i += mm.end()
    if not parts:
        return None, [], []
    head, rest = parts[0], parts[1:]
    if "else" in rest:
        k = rest.index("else")
        return head, rest[:k], rest[k + 1:]
    return head, rest, []


def find_trigger(forms, target_room, ego=None):
    """Return the guard placement for a frontier newRoom into `target_room`.

    `ego` (a global index, or None) feeds the coordinate spelling of the positional test --
    see `_mentions_ego_position`. Callers that know the game's ego should thread it; None
    keeps the mask-only reading."""
    nr, cs, ss, _pc = analyze_room(forms, ego=ego)
    nav = nav_props(forms)
    assigned = _var_assigned_rooms(forms)
    # A variable assigned from `edgeToRoom:` can hold every declared direction's room -- the
    # dynamic nav read (see _edge_dispatch_vars). Union, not replace: a file may also assign
    # the same variable a literal.
    for v in _edge_dispatch_vars(forms):
        assigned[v] |= set(nav.values())
    sites = [s for s in nr if s[3] == target_room
             or (isinstance(s[3], tuple) and s[3][0] == "nav"
                 and nav.get(s[3][1]) == target_room)
             or (isinstance(s[3], tuple) and s[3][0] == "var"
                 and target_room in assigned.get(s[3][1], ()))]
    if not sites:
        return {"kind": "not-found", "target_room": target_room}
    inst, meth, state, dest, positional = sites[0]
    # A VARIABLE destination serves several rooms from one statement, so a guard wrapped around it
    # would refuse them all: LB2's act break sends you to five different rooms and only the one
    # into the inquest is a frontier. Carry the discriminator so the placement ANDs it in and the
    # refusal speaks only for the crossing we mean.
    dest_test = ("(== %s %d)" % (dest[1], target_room)
                 if isinstance(dest, tuple) and dest[0] == "var" else None)
    # ...and the wrapper needs the variable's NAME as well as the test: a var-destination
    # `newRoom:` has no literal for the direct pattern to find (rm036's `(global2 newRoom:
    # temp0)`), so the site is located by the variable instead.
    dest_var = dest[1] if isinstance(dest, tuple) and dest[0] == "var" else None
    if inst is None:
        # A `newRoom` in a bare procedure: nothing to scope an edit to. Report it as unfound
        # rather than crashing the wrapper, which locates every site by its instance.
        return {"kind": "no-trigger", "instance": None, "cutscene_state": state,
                "target_room": target_room, "dest_test": dest_test}
    if meth in CONTROLLABLE_METHODS:
        return {"kind": "direct", "instance": inst, "method": meth,
                "target_room": target_room, "dest_test": dest_test, "dest_var": dest_var}
    if positional:
        # SCI1.1's positional exit: `doit` sees the ego standing on a control colour and calls
        # `newRoom:`. `doit` is not a handler method, but the move IS the player's -- they walked
        # there -- so it is refusable, and refusing it is exactly what an edge guard wants. Wrap
        # the whole cond-clause, not just the call: its siblings hand control off and animate.
        return {"kind": "direct", "instance": inst, "method": meth, "positional": True,
                "target_room": target_room, "dest_test": dest_test, "dest_var": dest_var}
    # newRoom is inside a cutscene (changeState). Find the controllable trigger.
    cands = [(k, m) for (i, m, k, recv) in cs
             if i == inst and m in CONTROLLABLE_METHODS and recv == "self"
             and (state is None or k <= state)]
    if cands:
        kstar, trig_meth = max(cands, key=lambda km: km[0])
        return {"kind": "trigger", "instance": inst, "trigger_method": trig_meth,
                "trigger_state": kstar, "cutscene_state": state, "target_room": target_room, "dest_test": dest_test}
    # ...or the newRoom lives in a Script `inst` that a controllable handler STARTS with
    # `(self setScript: inst)` -- KQ4's rm45 amulet handover (`(self setScript: closer)`, and
    # `closer` does `newRoom: 690`). Guard that setScript call.
    # `i2 is not None` because the wrapper locates the edit by `(instance <i2> ...)`: an arming
    # made from a bare PROCEDURE has no instance to scope to, so there is no site to rewrite.
    ss_cands = [(i2, m2) for (i2, m2, target, recv, _p) in ss
                if target == inst and m2 in CONTROLLABLE_METHODS and i2 is not None]
    if ss_cands:
        i2, m2 = ss_cands[0]
        return {"kind": "setscript", "trigger_instance": i2, "trigger_method": m2,
                "target_script": inst, "target_room": target_room, "dest_test": dest_test}
    # ...or the arming is POSITIONAL: a `doit` clause that tests where the ego is STANDING and
    # arms the crossing's cutscene. Play-found twice on rm550's mists crossing (2026-08-04):
    # `(cond (... (global1 handsOff:) (setScript: walkNorthScript)))` in doit. The bare
    # arm-event wrap left the handsOff sibling un-gated and HUNG the game (finding #11); the
    # refusal-bearing clause wrap then MACHINE-GUNNED -- doit re-evaluates every cycle while
    # the ego stands on the control, so "Not yet!" fired forever and never stopped the walk
    # (finding #12). A doit clause is not a click: it has no once-per-action shape to hang a
    # refusal on. So the positional arming gets the whole-clause NO-ELSE gate: lampless, the
    # crossing simply never starts, and the trail reads as a wall -- the game's own idiom for
    # the same pocket (rm560's east edge closes silently).
    pos_cands = [(i2, m2) for (i2, m2, target, recv, p) in ss
                 if target == inst and p and i2 is not None]
    if pos_cands:
        i2, m2 = pos_cands[0]
        return {"kind": "arm-clause", "trigger_instance": i2, "trigger_method": m2,
                "target_script": inst, "target_room": target_room, "dest_test": dest_test}
    # ...or the Script is armed by a setScript in an UNCONTROLLABLE method -- an ADVERSARIAL event
    # the player cannot refuse (KQ4's whale swallow: `Room31::init` does `(global0 setScript:
    # whaleActions)` on a Random roll; nightfall is the same shape in `KQ4::newRoom`). There is no
    # player action to guard, so we gate the ARMING itself: the event fires only when the survival
    # item is held. If it is missing the event simply does not arm -- exactly the prevention.
    arm_cands = [(i2, m2) for (i2, m2, target, recv, _p) in ss if target == inst and i2 is not None]
    if arm_cands:
        i2, m2 = arm_cands[0]
        # ...UNLESS THE ARMING IS THE ROOM'S ONLY WAY OUT, in which case gating it is not a
        # prevention but a WALL: the player stands in a room that has nothing left to run.
        #
        # "If it is missing the event simply does not arm" is sound for an event the room merely
        # OFFERS -- KQ4's whale, KQ6's rm440/rm480, all rooms with ordinary exits besides. LB2's
        # act-break card is the other shape: script 26 contains exactly one `newRoom:`, inside the
        # cutscene we would be refusing to arm, so a player without the five inquest items would
        # sit on the title card forever. The rule reads the file rather than naming a game: an
        # arm-event is safe only while some newRoom site lives OUTSIDE the script being gated.
        outside = [s for s in nr if s[0] != inst]
        if not outside:
            # `target_script` rides along for the deferral triage, whose contexts are the
            # armings of the gated script -- which for a sole exit is `inst` itself. The key
            # was missing for as long as no triage chain hop ever landed on a true sole-exit
            # room; the hermit deferral was the first to (KeyError, 2026-08-19).
            return {"kind": "sole-exit", "instance": inst, "target_script": inst,
                    "trigger_instance": i2, "trigger_method": m2,
                    "target_room": target_room, "dest_test": dest_test}
        # THE PREMISE IS OPEN PLAY NEXT DOOR, and two context shapes break it (play-found
        # 2026-08-18, the hermit departure hang -- no refusal, no exits, nothing left to run):
        #
        #   * an outside `newRoom:` counts as a way out only if it is REACHABLE without the
        #     gated script. KQ5's cdHermitRoom spells the trap: goGetBoatScript's `newRoom: 44`
        #     sits outside the gated cartoon2, but its every arming lives INSIDE cartoon2 --
        #     withhold the cutscene and no path arms the way home. An exit whose armings are
        #     all inside the gate is inside the gate.
        #   * a `changeState` arming is the machine handing FORWARD its own continuation, not
        #     an adversary arming next to open play (those arm from the free-running methods:
        #     init, doit, newRoom, cue). Withholding a continuation parks the machine in the
        #     client's script slot, and a room whose doit dispatches on `script` never reaches
        #     its edge exits again (rm046's bringCedric; the 2026-08-04 finding-#11 class).
        #
        # ANNOTATED, NOT RECLASSIFIED. The deferral triage (`_defer_triage_site`) receives
        # arm-events too, and it already judges these very contexts itself (committed vs
        # benign, play-validated on LB2's rm480 chase chain, dagger-frozen); changing the kind
        # under it crashed that path outright. Only the MAIN placement loop -- where a bare
        # arm-event wrap would ship the silent hold as-is -- converts an unsound hold into
        # the chain's controllable refusal or the sole-exit flow (see apply_guards).
        armers = defaultdict(set)
        for (i3, _m3, tgt3, _r3, _p3) in ss:
            armers[tgt3].add(i3)
        live = [s for s in outside
                if not (s[0] in armers and armers[s[0]] <= {inst})]
        sound = any(m3 != "changeState" for (_i3, m3) in arm_cands)
        row = {"kind": "arm-event", "trigger_instance": i2, "trigger_method": m2,
               "target_script": inst, "target_room": target_room, "dest_test": dest_test}
        if not (sound and live):
            row["unsound_hold"] = True
            # THE CHAIN CLIMB, first choice (USER ruling 2026-08-19, the hermit: "prevent
            # you from starting the whole cutscene by giving the shell until you have all
            # you need"). The gated machine's armings are changeState handoffs, but a
            # handoff machine may itself be armed from a CONTROLLABLE handler one or more
            # hops up -- giveShell from hermit_a::handleEvent, the give click. That is the
            # last controllable moment before the committed chain, and the refusal belongs
            # there (the arrival-commit doctrine, in-file). Doors whose climb dead-ends in
            # a free-running method are REPORTED (`chain_unwrapped`), never silently
            # skipped -- whether they are sealed (bringCedric arms only off a flag written
            # inside the very chain being guarded) is for the caller and the oracle to
            # verify, and an unreported door is finding #4.
            hop_seen = {inst}
            level = sorted({i3 for (i3, m3) in arm_cands if m3 == "changeState"})
            climbed_from = None
            for _depth in range(3):
                nxt = []
                for carrier in level:
                    if carrier in hop_seen:
                        continue
                    hop_seen.add(carrier)
                    ups = [(i4, m4) for (i4, m4, t4, _r4, _p4) in ss
                           if t4 == carrier and i4 is not None]
                    ctl = [(i4, m4) for (i4, m4) in ups if m4 in CONTROLLABLE_METHODS]
                    if ctl:
                        row["chain_arm"] = {"trigger_instance": ctl[0][0],
                                            "trigger_method": ctl[0][1],
                                            "target_script": carrier}
                        climbed_from = carrier
                        break
                    nxt += [i4 for (i4, m4) in ups
                            if m4 == "changeState" and i4 not in hop_seen]
                if climbed_from or not nxt:
                    break
                level = sorted(set(nxt))
            if climbed_from:
                others = sorted({i3 for (i3, m3) in arm_cands
                                 if m3 == "changeState" and i3 != climbed_from})
                if others:
                    row["chain_unwrapped"] = others
            # No controllable moment up the chain leaves only the annotation: the main loop
            # routes such a row into the sole-exit flow (deferral, else honestly unplaced).
            # A "decline-fork" cure -- conjoining the demand into the gated cutscene's own
            # decline arm -- was BUILT here and REMOVED BY USER RULING 2026-08-19: its one
            # real-world site (cdHermitRoom's goGetBoatScript) turned out to raise flag 105
            # on the way out, a commitment DEFERRAL wearing a decline's clothes, and the
            # ruling is that the refusal belongs before the chain starts, not inside it.
        return row
    return {"kind": "no-trigger", "instance": inst, "cutscene_state": state,
            "target_room": target_room, "dest_test": dest_test}


# --------------------------------------------------------------------------
# region-scoped source wrapping
# --------------------------------------------------------------------------
def _block_span(text, start_idx):
    """Given index of a '(', return (start, end) covering the balanced form, skipping comments,
    `{..}` message text and `'..'` Said specs -- `sexpr.skip_noncode`'s taxonomy, which is where
    that rule now lives ([[same-rule-two-places]]).

    It used to be spelled inline here, and the inline copy could HANG: an unterminated `{` or
    `'` made `find` return -1, so `i` became 0 and the walk restarted from the top of the file
    forever. The shared rule bounds both quoted forms to their own LINE and treats an
    unterminated one as an ordinary character. Every `'...'` in the corpus is on one line
    (measured: no line carries a stray quote), so no span moves."""
    depth, i, n = 0, start_idx, len(text)
    while i < n:
        nxt = skip_noncode(text, i, n)
        if nxt is not None:
            i = max(nxt, i + 1)
            continue
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return start_idx, i + 1
        i += 1
    return start_idx, n


def _find_region(text, header_re):
    """The balanced form headed by the first CODE match of `header_re`, or None.

    ⛔ A HEADER QUOTED IN A MESSAGE IS NOT A HEADER, and this one is not latent (2026-08-20
    review's hand-off list, item 2: R1 is a property of "scan raw text for a candidate, then span
    from it"). KQ6's and LB2's `WriteFeature.sc` is a source-code GENERATOR whose message strings
    are themselves SCI source -- `{ \\t(method (doVerb theVerb)\\0d\\n\\t\\t(switch theVerb\\0d\\n}`
    -- and that message holds the FIRST `(method (doVerb` in the file. With a raw `re.search`
    this returned (9255, 9815): 560 bytes beginning in the middle of a string, every span
    computed inside it arithmetic on text that is not code, and the placement that asked would
    have rewritten it. Census of the five source trees: 7,747 `(method (` matches, two inside
    non-code, and both of them this."""
    m = code_search(text, header_re)
    if not m:
        return None
    return _block_span(text, m.start())


def _turnback_emit(guard_sexpr, body, og, tb, refuse, site, region=None, span=None):
    """The turn-back wrap + its Script instance TEMPLATE, shared by every positional-refusal
    kind (arm-clause armings, positional direct exits) so the two cannot drift
    ([[same-rule-two-places]]). `body` is the clause body being held. The returned instance
    text carries two `%s` slots for the caller's derived safe target (xe, ye).

    `region`/`span` are the text this wrap replaces `region[span]` in, so the trailing marker
    can be kept off whatever stock wrote after it on that line (`sexpr.mark_line`, N1)."""
    ego = og.get("ego", "global0")
    room = og.get("room", "global2")
    game = og.get("game", "global1")
    turned = ("  ; softlock-guard: turned back" if region is None else
              mark_line(region, span[1], "  ; softlock-guard: turned back",
                        line_indent(region, span[0])))
    forms = site.forms()
    if forms is None:
        wrapped = (f"(if {guard_sexpr}\n\t\t\t\t{body}\n\t\t\telse\n"
                   f"\t\t\t\t(if (not ({room} script:))\n"
                   f"\t\t\t\t\t({room} setScript: {tb})\n"
                   f"\t\t\t\t)\n\t\t\t)" + turned)
    else:
        # The turn-back IS this kind's refusal; the mark rides its once-per-approach
        # arming gate (doit re-fires every cycle -- the gate is what keeps the
        # turn-back, and so the mark, from machine-gunning). In lite-once-warned the
        # warned line prints and the body arms the crossing as the game built it.
        allow, warn, mark = forms
        wrapped = (f"(if {guard_sexpr}\n\t\t\t\t{body}\n\t\t\telse\n"
                   f"\t\t\t\t(if {allow}\n"
                   f"\t\t\t\t\t{warn}\n"
                   f"\t\t\t\t\t{body.strip()}\n"
                   f"\t\t\t\telse\n"
                   f"\t\t\t\t\t(if (not ({room} script:))\n"
                   f"\t\t\t\t\t\t({room} setScript: {tb})\n"
                   f"\t\t\t\t\t\t{mark}\n"
                   f"\t\t\t\t\t)\n"
                   f"\t\t\t\t)\n\t\t\t)" + turned)
    # THE INPUT LOCK IS SPOKEN IN THE GAME'S OWN TONGUE, or not at all. The template
    # said `(gGame handsOff:)` unconditionally, and KQ5 -- the first game outside the
    # LSL2/KQ4 dialect to receive a turn-back -- never sends that selector anywhere in
    # its 211 scripts, so the guard was the one script in the game that could not
    # compile. The caller derives the pair (`obj_globals["hands"]`): the handsOff:
    # spelling where the game speaks it, its own idiom otherwise (KQ5 locks input with
    # `(User canControl: 0)` -- rm012's lamb throw does exactly that), and NO lock when
    # neither is spoken -- a brief uncontrolled walk-back beats an uncompilable file.
    hands = og.get("hands", (f"({game} handsOff:)", f"({game} handsOn:)"))
    h_off = ("\t\t\t\t%s\n" % hands[0]) if hands else ""
    h_on = ("\t\t\t\t%s\n" % hands[1]) if hands else ""
    # THE WALK-BACK IS THE GAME'S OWN WALKER, or the straight-line one only where no better
    # exists. `MoveTo` walks a straight line and a BLOCKED straight line never completes, so
    # its cue never fires and the input lock never lifts -- rm085's turn-back hung the game on
    # the legitimate approach (USER-found, 2026-08-18b); rm040's only worked because open snow
    # is straight-line-walkable. Games that speak `PolyPath` (KQ5 does, in these very rooms)
    # get the obstacle-aware walker the game itself uses for exactly these moves; SCI0 titles
    # have no such class and keep MoveTo -- their turn-backs were play-validated with it.
    motion = og.get("motion", "MoveTo")
    if og.get("chase_room"):
        # A TURN-BACK IN A CHASE ROOM TAKES NO LOCK AND WAITS FOR NOTHING (USER-found at the
        # yeti: the refusal's input lock plus its scripted walk delivered a fleeing player
        # into the hunter's arms -- stock never locks input here, and the chase exclusion's
        # whole point is that the player's legs are the counter). Refuse, start the walk,
        # dispose immediately: the player can cancel the walk with any click, the room
        # script frees at once so the next approach refuses again, and the modal line is
        # what paces re-triggering. The ego ends off the trigger either way.
        instance_tpl = (
            "\n(instance %s of Script\n\t(properties)\n\n"
            "\t(method (changeState param1)\n"
            "\t\t(switch (= state param1)\n"
            "\t\t\t(0\n\t\t\t\t%s  ; softlock-guard line\n"
            "\t\t\t\t(= cycles 1)\n\t\t\t)\n"
            "\t\t\t(1\n\t\t\t\t(%s setMotion: %s %%s %%s)\n"
            "\t\t\t\t(self dispose:)\n\t\t\t)\n"
            "\t\t)\n\t)\n)\n" % (tb, refuse, ego, motion))
        return wrapped, instance_tpl
    instance_tpl = (
        "\n(instance %s of Script\n\t(properties)\n\n"
        "\t(method (changeState param1)\n"
        "\t\t(switch (= state param1)\n"
        "\t\t\t(0\n%s\t\t\t\t%s  ; softlock-guard line\n"
        "\t\t\t\t(= cycles 1)\n\t\t\t)\n"
        "\t\t\t(1\n\t\t\t\t(%s setMotion: %s %%s %%s self)\n\t\t\t)\n"
        "\t\t\t(2\n%s\t\t\t\t(self dispose:)\n\t\t\t)\n"
        "\t\t)\n\t)\n)\n" % (tb, h_off, refuse, ego, motion, h_on))
    return wrapped, instance_tpl


def wrap_trigger_in_source(text, placement, guard_sexpr, refuse="(NotNow)", site=None):
    """Wrap the controllable trigger's `(self changeState: K)` (scoped to the
    right instance+method) in the item guard. For a 'direct' placement, wrap the
    `newRoom: N` instead.

    `site` carries the lite-mode warned bit. Pass the SPEC ROW's site: one demand wrapped at
    two armings, or at six entry rooms, is one guard and owes the player one warning."""
    site = site if site is not None else _ModeSite()
    if placement["kind"] == "direct":
        # A VARIABLE destination has no literal to find -- locate the site by the variable the
        # classifier resolved (rm036's `(global2 newRoom: temp0)`); the crossing is already
        # discriminated by the dest_test the caller conjoined into the guard.
        pat = (re.compile(r"\([^()]*newRoom:\s*%s\b[^()]*\)" % re.escape(placement["dest_var"]))
               if placement.get("dest_var")
               else re.compile(r"\([^()]*newRoom:\s*%d\b[^()]*\)" % placement["target_room"]))
        # SCOPED TO THE CLASSIFIED SITE, like every other kind here. This branch used to hand
        # the WHOLE FILE to `_wrap_matches_in`, so it wrapped every textual `newRoom: N` --
        # including the ones in `changeState` cutscene tails, which is exactly what this
        # module's opening docstring exists to prevent. Measured: Dagger's blackWidowInset
        # took three extra wraps (spiderRush/bitParchment/touchSpider) and KQ4's Room698/699
        # took one each (creditActions, playMusic).
        #
        # AND THROUGH THE CLAUSE, also like every other kind: refusing only the room change
        # leaves the committing siblings to run first -- `handsOff:` then a refusal is the
        # rm38 hang the sibling branches' comments memorialise, and an award paid before the
        # refusal is farmable by repeating a refused action (Dagger rm454/rm520 `points:`).
        inst, meth = placement.get("instance"), placement.get("method")
        span = _find_region(text, r"\((?:instance|class)\s+%s\b" % re.escape(inst)) if inst \
            else None
        if span is None:
            return text, 0                     # unclassifiable site: honestly unplaced beats
        i0, i1 = span                          # a wrap somewhere we did not analyse
        if meth:
            mrel = _find_region(text[i0:i1], r"\(method\s+\(%s\b" % re.escape(meth))
            if mrel:
                i0, i1 = i0 + mrel[0], i0 + mrel[1]
        region = text[i0:i1]
        m = pat.search(region)
        if not m:
            return text, 0
        clause = _enclosing_clause_body(region, m.start())
        bs, be = clause if clause else (m.start(), m.end())
        if placement.get("positional"):
            # A POSITIONAL direct exit machine-guns under a spoken refusal: `doit` re-fires
            # every cycle the ego stands on the control (finding #12 -- KQ5's temple door,
            # rediscovered in the emitted source with the naked `guarded_wrap` below). The
            # refusal must be the turn-back: say the line once, walk the ego somewhere PROVEN
            # SAFE, hand the controls back. Two derivable targets, in order: the clause's own
            # coordinate boundary (its literal names the zone's edge), else THE ROOM'S OWN
            # WALK-IN POSITION -- the spot the game itself stands the ego on at init, which a
            # positional exit's control strip cannot contain (the player walked here from
            # there). Neither derivable, or no refusal line -> the silent whole-clause gate:
            # nothing runs, nothing spams, and the player walks off the strip themselves.
            og = placement.get("obj_globals") or {}
            ego_g = og.get("ego", "global0")
            head = enclosing_clause_head(region, m.start()) or ""
            bm = re.search(r"\(([<>])=?\s*\(%s\s+([xy]):\)\s+(-?\d+)\)" % re.escape(ego_g),
                           head)
            tgt = None
            if bm:
                op, axis, k = bm.group(1), bm.group(2), int(bm.group(3))
                esc = k + 15 if op == "<" else k - 15
                tgt = ((f"({ego_g} x:)", str(esc)) if axis == "y"
                       else (str(esc), f"({ego_g} y:)"))
            else:
                init_rel = _find_region(text[span[0]:span[1]], r"\(method\s+\(init\b")
                init_txt = (text[span[0] + init_rel[0]:span[0] + init_rel[1]]
                            if init_rel else "")
                im = re.search(r"\(%s\b(?:[^()]|\([^()]*\))*?posn:\s+(-?\d+)\s+(-?\d+)"
                               % re.escape(ego_g), init_txt, re.S)
                if im:
                    tgt = (im.group(1), im.group(2))
            tb = "sgTurnBack"
            if refuse and tgt and tb not in text:
                wrapped, instance_tpl = _turnback_emit(guard_sexpr, region[bs:be], og, tb,
                                                       refuse, site, region, (bs, be))
                new_text = text[:i0] + region[:bs] + wrapped + region[be:] + text[i1:]
                return new_text + (instance_tpl % tgt), 1
            wrapped = (f"(if {stock_or(guard_sexpr)}\n\t\t\t\t{region[bs:be]}\n\t\t\t)"
                       + mark_line(region, be,
                                   "  ; softlock-guard: positional gate, silent by design",
                                   line_indent(region, bs)))
            return text[:i0] + region[:bs] + wrapped + region[be:] + text[i1:], 1
        wrapped = guarded_wrap(guard_sexpr, region[bs:be], refuse, site=site)
        return text[:i0] + region[:bs] + wrapped + region[be:] + text[i1:], 1
    if placement["kind"] == "proc-call":
        # Guard the CALL to a helper script's procedure -- the whole enclosing cond-clause, so the
        # siblings that set up the scene cannot run ahead of the refusal. Same care as `setscript`.
        inst, meth = placement["trigger_instance"], placement["trigger_method"]
        inst_span = _find_region(text, r"\(instance\s+%s\b" % re.escape(inst))
        if not inst_span:
            return text, 0
        i0, i1 = inst_span
        meth_rel = _find_region(text[i0:i1], r"\(method\s+\(%s\b" % re.escape(meth))
        if not meth_rel:
            return text, 0
        m0, m1 = i0 + meth_rel[0], i0 + meth_rel[1]
        region = text[m0:m1]
        pm = re.search(r"\(%s\s*\)" % placement["target_pattern"], region)
        if not pm:
            return text, 0
        clause = _enclosing_clause_body(region, pm.start())
        bs, be = clause if clause else (pm.start(), pm.end())
        wrapped = guarded_wrap(guard_sexpr, region[bs:be], refuse, site=site)
        return text[:m0] + region[:bs] + wrapped + region[be:] + text[m1:], 1
    if placement["kind"] == "setscript":
        # Guard `(<recv> setScript: <target>)` in the controllable handler (its whole cond-clause,
        # so score/sound siblings cannot fire before the refusal -- same care as the changeState case).
        inst, meth = placement["trigger_instance"], placement["trigger_method"]
        target = placement["target_script"]
        inst_span = _find_region(text, r"\(instance\s+%s\b" % re.escape(inst))
        if not inst_span:
            return text, 0
        i0, i1 = inst_span
        meth_rel = _find_region(text[i0:i1], r"\(method\s+\(%s\b" % re.escape(meth))
        if not meth_rel:
            return text, 0
        m0, m1 = i0 + meth_rel[0], i0 + meth_rel[1]
        region = text[m0:m1]
        tpat = placement.get("target_pattern") or (re.escape(target) + r"\b")
        # THE ARMING STATEMENT IS THE SEND THAT CARRIES THE SELECTOR, not a flat regex span --
        # the same lesson the arm-event branch already carries (KQ5's henchman): locate the
        # selector, then expand to the INNERMOST BALANCED FORM enclosing it. The old
        # one-level-of-nesting pattern (`((ScriptID 344 2) setScript: (ScriptID 344 3))`) is
        # subsumed; what it could not see was a DEEPER argument -- KQ5's boat departure,
        # `(global2 setScript: castOffScript 0 (== (global0 view:) 661))`, two levels down,
        # which left the boat click an unwrapped second door beside the walked-edge guard.
        ssm = re.search(r"setScript:\s*%s" % tpat, region)
        if not ssm:
            return text, 0
        s0 = region.rfind("(", 0, ssm.start())
        span = None
        while s0 != -1:
            b0, b1 = _block_span(region, s0)
            if b1 > ssm.end():
                span = (b0, b1)
                break
            s0 = region.rfind("(", 0, s0)
        if span is None:
            return text, 0
        clause = _enclosing_clause_body(region, span[0])
        if clause:
            bs, be = clause
            wrapped = guarded_wrap(guard_sexpr, region[bs:be], refuse, site=site)
            new_meth = region[:bs] + wrapped + region[be:]
        else:
            bs, be = span
            wrapped = guarded_wrap(guard_sexpr, region[bs:be], refuse, site=site)
            new_meth = region[:bs] + wrapped + region[be:]
        return text[:m0] + new_meth + text[m1:], 1
    if placement["kind"] == "proc-arm":
        # The helper file's OWN arming of the crossing -- a bare procedure the room calls at a
        # refusal-safe moment. KQ6's Realm entry: `(nightMare setScript: catchNiteMare)` inside
        # `proc344_1`, reached from `rm340::notify` AFTER the cast scene has done `handsOn:`
        # (openBook.sc restores the UI before `(global2 notify:)`) and BEFORE the ride consumes
        # the skull (`catchNiteMare` state 0 is the `put: 11`) -- refused, the mare just stands
        # there and the cast repeats once the missing items are in hand. Wrap ONLY the arming
        # form, never its enclosing clause: the `else` sibling is the game's own other outcome
        # (`coldEmbers`) and must stay free.
        _ANY = r"(?:[^()]|\([^()]*\))*"
        alts = "|".join(re.escape(t) for t in
                        placement.get("arm_targets") or [placement["target_script"]])
        n_total = 0
        for proc in placement["target_procs"]:
            span = _find_region(text, r"\(procedure\s+\(%s\b" % re.escape(proc))
            if not span:
                continue
            p0, p1 = span
            pat = re.compile(r"\(%ssetScript:\s*(?:%s)\b%s\)" % (_ANY, alts, _ANY))
            new_region, n = _wrap_matches_in(text[p0:p1], site, pat, guard_sexpr, refuse)
            text = text[:p0] + new_region + text[p1:]
            n_total += n
        return text, n_total
    if placement["kind"] == "arm-event":
        # Gate the ARMING of an adversarial event: wrap `(<recv> setScript: <target>)` so it fires
        # only when the guard holds. NO `else` -- if the item is missing the event just does not arm
        # (you are never swallowed without the feather), which is the prevention itself. The refuse
        # branch of the controllable cases makes no sense here: there is no player to tell "not now".
        inst, meth = placement["trigger_instance"], placement["trigger_method"]
        target = placement["target_script"]
        # instance OR class: KQ5's boatRegion is a CLASS, and its init auto-arms the sail
        # (play-found 2026-08-19); the direct branch has accepted both spellings all along.
        inst_span = _find_region(text, r"\((?:instance|class)\s+%s\b" % re.escape(inst))
        if not inst_span:
            return text, 0
        i0, i1 = inst_span
        meth_rel = _find_region(text[i0:i1], r"\(method\s+\(%s\b" % re.escape(meth))
        if not meth_rel:
            return text, 0
        m0, m1 = i0 + meth_rel[0], i0 + meth_rel[1]
        region = text[m0:m1]
        # Gate EVERY arming site for this event -- KQ4's Room31::init both STARTS the swallow (the
        # Random roll) and RESUMES it on re-entry (global105==14); both must require the item, so
        # the whale is never active without the feather. No `else`: a missing item just doesn't arm.
        #
        # THE ARMING STATEMENT IS THE SEND THAT CARRIES THE SELECTOR, not a flat regex span:
        # KQ5's henchman arms itself inside a multi-selector cascade with a nested argument --
        # `(self view: (if ...) setCycle: Walk ... setScript: theHenchManScript)` -- which no
        # `[^()]*` pattern can see. Locate the selector, then expand to the INNERMOST BALANCED
        # FORM enclosing it; for the flat single-selector send every prior game spells, that is
        # exactly the span the old pattern matched.
        gs = stock_or(guard_sexpr)     # silent kind: stock bypasses, lite behaves as full
        spans = []
        for am in re.finditer(r"setScript:\s*%s\b" % re.escape(target), region):
            s0 = region.rfind("(", 0, am.start())
            b = None
            while s0 != -1:
                b0, b1 = _block_span(region, s0)
                if b1 > am.end():
                    b = (b0, b1)
                    break
                s0 = region.rfind("(", 0, s0)
            if b and b not in spans:
                spans.append(b)
        n = 0
        for (b0, b1) in sorted(spans, reverse=True):
            wrapped = (f"(if {gs}\n\t\t\t\t{region[b0:b1]}\n\t\t\t)"
                       + mark_line(region, b1,
                                   "  ; softlock-guard: arm only when survivable",
                                   line_indent(region, b0)))
            region = region[:b0] + wrapped + region[b1:]
            n += 1
        return text[:m0] + region + text[m1:], n
    if placement["kind"] == "arm-clause":
        # A POSITIONAL arming's gate. One guard, three play findings (2026-08-04, all rm550):
        # the bare arm-event wrap left a handsOff sibling un-gated and HUNG (#11); a refusal
        # in the clause MACHINE-GUNNED, because doit re-fires every cycle (#12); the silent
        # no-else gate let the ego walk off the screen, because the zone WAS the wall (#13).
        # The game's own idiom for a declined positional crossing is the castle guard post's:
        # a tiny TURN-BACK script -- say the line once, walk the ego a few steps back, hand
        # the controls over. Once-per-approach falls out structurally: the arming is guarded
        # on `(not (<room> script:))` and the turn-back ends with the ego off the zone.
        # The back-off direction is DERIVED from the crossing script's own first motion
        # target (away from it, along its dominant axis). With no refusal line or no motion
        # target to derive from, fall back to the silent whole-clause gate.
        inst, meth = placement["trigger_instance"], placement["trigger_method"]
        target = placement["target_script"]
        inst_span = _find_region(text, r"\((?:instance|class)\s+%s\b" % re.escape(inst))
        if not inst_span:
            return text, 0
        i0, i1 = inst_span
        meth_rel = _find_region(text[i0:i1], r"\(method\s+\(%s\b" % re.escape(meth))
        if not meth_rel:
            return text, 0
        m0, m1 = i0 + meth_rel[0], i0 + meth_rel[1]
        region = text[m0:m1]
        tpat = placement.get("target_pattern") or (re.escape(target) + r"\b")
        _ANY = r"(?:[^()]|\([^()]*\))*"
        ssm = re.search(r"\(%ssetScript:\s*%s%s\)" % (_ANY, tpat, _ANY), region)
        if not ssm:
            return text, 0
        clause = _enclosing_clause_body(region, ssm.start())
        bs, be = clause if clause else (ssm.start(), ssm.end())
        og = placement.get("obj_globals") or {}
        ego = og.get("ego", "global0")
        room = og.get("room", "global2")
        game = og.get("game", "global1")
        tspan = _find_region(text, r"\(instance\s+%s\b" % re.escape(target))
        tm = re.search(r"(?:setMotion:\s+)?(?:MoveTo|PolyPath)\s+(-?\d+)\s+(-?\d+)",
                       text[tspan[0]:tspan[1]]) if tspan else None
        # THE CLAUSE NAMES ITS OWN ESCAPE when its test is an ego-coordinate compare: the
        # boundary literal IS the zone's edge, so the back-off is "past it, along that axis" --
        # `(< (gEgo y:) 150)` walks back to y = 165. Derived from the guarded clause itself,
        # which cannot pick a wrong axis; the crossing script's first motion target (below)
        # stays as the fallback for mask-form zones, whose boundary no literal states. Without
        # this, rm85's turn-back walked SIDEWAYS (the thug's approach motion is x-dominant),
        # the ego never left the y<150 zone, and the once-per-approach argument -- "the
        # turn-back ends with the ego off the zone" -- was false: the guard machine-gunned
        # (finding #12's shape, one derivation short).
        head = enclosing_clause_head(region, ssm.start()) or ""
        bm = re.search(r"\(([<>])=?\s*\(%s\s+([xy]):\)\s+(-?\d+)\)" % re.escape(ego), head)
        bnd = None
        if bm:
            op, axis, k = bm.group(1), bm.group(2), int(bm.group(3))
            esc = k + 15 if op == "<" else k - 15
            bnd = (f"({ego} x:)", str(esc)) if axis == "y" else (str(esc), f"({ego} y:)")
        tb = "sgTurnBack"
        if refuse and (bnd or tm) and tb not in text:
            if bnd:
                xe, ye = bnd
            else:
                tx, ty = int(tm.group(1)), int(tm.group(2))
                if abs(ty - 95) >= abs(tx - 160):  # dominant axis of the crossing, sign away
                    xe = f"({ego} x:)"
                    ye = f"({'+' if ty < 95 else '-'} ({ego} y:) 35)"
                else:
                    xe = f"({'+' if tx < 160 else '-'} ({ego} x:) 35)"
                    ye = f"({ego} y:)"
            wrapped, instance_tpl = _turnback_emit(guard_sexpr, region[bs:be], og, tb,
                                                   refuse, site, region, (bs, be))
            new_text = text[:m0] + region[:bs] + wrapped + region[be:] + text[m1:]
            return new_text + (instance_tpl % (xe, ye)), 1
        wrapped = (f"(if {stock_or(guard_sexpr)}\n\t\t\t\t{region[bs:be]}\n\t\t\t)"
                   + mark_line(region, be,
                               "  ; softlock-guard: positional gate, silent by design",
                               line_indent(region, bs)))
        return text[:m0] + region[:bs] + wrapped + region[be:] + text[m1:], 1
    if placement["kind"] == "nav-assign":
        # Re-decide a ROUTE, do not refuse an action: `(self north: 340)` becomes
        #   (if <guard> (self north: 340) else (self north: <fallback>))
        # so a non-compliant player simply takes the game's own long way (where the real gate
        # sits), and nothing is half-run -- an assignment has no scene to hang. No refusal
        # line: the player is not being told no, they are being routed.
        inst, meth = placement["trigger_instance"], placement["trigger_method"]
        inst_span = _find_region(text, r"\(instance\s+%s\b" % re.escape(inst))
        if not inst_span:
            return text, 0
        i0, i1 = inst_span
        meth_rel = _find_region(text[i0:i1], r"\(method\s+\(%s\b" % re.escape(meth))
        if not meth_rel:
            return text, 0
        m0, m1 = i0 + meth_rel[0], i0 + meth_rel[1]
        region = text[m0:m1]
        pat = re.compile(r"\(self\s+%s:\s*%d\s*\)"
                         % (re.escape(placement["prop"]), placement["target_room"]))
        n = [0]
        gs = stock_or(guard_sexpr)     # a route re-decision never speaks: stock takes the
        #                                shortcut, lite keeps the re-route exactly as full does

        def repl(m):
            n[0] += 1
            return (f"(if {gs}\n\t\t\t\t{m.group(0)}\n\t\t\telse\n"
                    f"\t\t\t\t(self {placement['prop']}: {placement['fallback']})"
                    f"  ; softlock-guard: the long way keeps its gate\n\t\t\t)")
        new_meth = pat.sub(repl, region)
        return text[:m0] + new_meth + text[m1:], n[0]
    if placement["kind"] != "trigger":
        return text, 0
    inst, meth, k = placement["instance"], placement["trigger_method"], placement["trigger_state"]
    inst_span = _find_region(text, r"\(instance\s+%s\b" % re.escape(inst))
    if not inst_span:
        return text, 0
    i0, i1 = inst_span
    meth_rel = _find_region(text[i0:i1], r"\(method\s+\(%s\b" % re.escape(meth))
    if not meth_rel:
        return text, 0
    m0, m1 = i0 + meth_rel[0], i0 + meth_rel[1]
    region = text[m0:m1]
    csm = re.search(r"\(self\s+changeState:\s*%d\s*\)" % k, region)
    if not csm:
        return text, 0
    # Guard the WHOLE enclosing cond-clause body, not just the changeState call:
    # side-effecting siblings before it (score, (Ok), flag sets) must not run
    # before the refusal. rm38 awarded the score + played "Ok" then "Not now!"
    # because only the changeState was wrapped. Falls back to wrapping the
    # changeState alone when it is not inside a cond-clause.
    clause = _enclosing_clause_body(region, csm.start())
    if clause:
        bs, be = clause
        wrapped = guarded_wrap(guard_sexpr, region[bs:be], refuse, site=site)
        new_meth = region[:bs] + wrapped + region[be:]
    else:
        new_meth, _ = _wrap_matches_in(
            region, site, re.compile(r"\(self\s+changeState:\s*%d\s*\)" % k),
            guard_sexpr, refuse)
    return text[:m0] + new_meth + text[m1:], 1


def _enclosing_clause_span(region, pos):
    """Innermost cond-clause OR switch-case containing `pos`: return the clause's own
    (start, end) span, or None. The shared scan behind `_enclosing_clause_body` and
    `enclosing_clause_head` -- the same clause found two ways is how a wrap and its stage
    condition drift apart."""
    best = None
    for kw in ("cond", "switch"):
        for m in re.finditer(r"\(%s\b" % kw, region):
            s, e = _block_span(region, m.start())
            if s <= pos < e and (best is None or s > best[0]):
                best = (s, e, kw)
    if best is None:
        return None
    cs, ce, kw = best
    k = cs + 1
    mk = re.match(r"\s*%s\b" % kw, region[k:])
    if mk:
        k += mk.end()
    if kw == "switch":
        # skip the dispatch HEAD expression -- clauses start after it
        while k < ce and region[k] in " \t\r\n":
            k += 1
        if k < ce and region[k] == "(":
            _, k = _block_span(region, k)
        else:
            m2 = re.match(r"[^\s()]+", region[k:])
            k += (m2.end() if m2 else 1)
    while k < ce - 1:
        c = region[k]
        if c in " \t\r\n":
            k += 1
        elif c == ";":
            nl = region.find("\n", k)
            k = ce if nl < 0 else nl + 1
        elif c == "(":
            clause_s, clause_e = _block_span(region, k)
            if clause_s <= pos < clause_e:
                return clause_s, clause_e
            k = clause_e
        else:
            k += 1
    return None


def hold_machine_advance(text, machine, guard_sexpr):
    """Hold a cutscene machine at its leading TIMED WAIT STATE until the guard is banked.

    The sole-exit shape's third answer, after refuse-the-arming (a wall: the machine is the
    room's only way out) and the entry deferral (unsatisfiable when the demand's only source
    is INSIDE the room the machine runs in). KQ5's roc nest: `hatch` st0 is `(= cycles 45)`,
    the eggs crack on a timer while the locket sits grabbable beside you -- the USER-ruled
    remedy (2026-08-18b) is that the timer simply does not elapse until the demand is met.

    The emission is the game's own wait idiom -- `(-- state)` before the timer re-arm
    (rm055's goDoorScript st6 spells exactly this to wait on audio) -- so the held state
    re-enters itself each tick until the guard holds, then advances as built. SILENT by
    design: nothing is refused to the player's face, the scene just waits, so stock mode
    bypasses via `stock_or` and lite behaves as full (the register/flag-hold contract).

    The held state is DERIVED: the machine's numerically first changeState arm whose body
    writes a bare timer (`(= cycles N)` / `(= seconds N)` / `(= ticks N)`). No such state ->
    (text, 0), honestly unplaced -- a machine that never pauses has nowhere to wait."""
    span = _find_region(text, r"\((?:instance|class)\s+%s\b" % re.escape(machine))
    if not span:
        return text, 0
    i0, i1 = span
    mrel = _find_region(text[i0:i1], r"\(method\s+\(changeState\b")
    if not mrel:
        return text, 0
    m0, m1 = i0 + mrel[0], i0 + mrel[1]
    region = text[m0:m1]
    best = None
    for am in re.finditer(r"\(\s*(\d+)\s*\n", region):
        bs, be = _block_span(region, am.start())
        body = region[bs:be]
        tm = re.search(r"\(=\s+(?:cycles|seconds|ticks)\s+\d+\s*\)", body)
        if tm and (best is None or int(am.group(1)) < best[0]):
            best = (int(am.group(1)), bs, be, am.end() - am.start())
    if best is None:
        return text, 0
    _k, bs, be, head_len = best
    hold = ("\n\t\t\t\t(if (not %s)\n"
            "\t\t\t\t\t; softlock-guard: the scene waits until the demand is banked\n"
            "\t\t\t\t\t(-- state)\n"
            "\t\t\t\t)\n" % stock_or(guard_sexpr))
    new_region = region[:bs + head_len] + hold + region[bs + head_len:]
    return text[:m0] + new_region + text[m1:], 1


def wrap_forbidden_case(text, anchor_pat, token, guard_sexpr, refuse, site=None):
    """Wrap the switch case whose HEAD IS `token` around each `anchor_pat` match -- the market
    refusal's placement primitive.

    KQ5's shops dispatch on the offered item -- `(switch (gInv indexOf: (gIconBar curInvIcon:))
    (9 (= local6 2) (gRoom setScript: soldCloak) ...))` -- so every forbidden payment has its
    OWN case, and the case head literal IS the item number the market row names. Selecting the
    case by that head is what lets a guard spelled `(not (gEgo has: 9))` be placed only where
    the 9 was offered: inside its own case the condition is identically false, so the wrap is
    the unconditional refusal the matching derived, and the sibling cases -- the payments that
    keep the market solvable -- are never touched. (A condition alone cannot do this: wrapping
    every arming of `soldCloak` with `(not (has: 9))` would refuse the NEEDLE payment of any
    player merely carrying the heart.)

    The anchor names the committed ACT -- the `setScript:` that arms the purchase cutscene, or
    the handler's own `put:` for a throw/eat clause -- and the whole case body is wrapped, the
    same siblings-must-not-outrun-the-refusal care as every other kind here. Matches that share
    one case (Main's two lamb `put:` spellings) collapse to one wrap. Returns (text, n)."""
    site = site if site is not None else _ModeSite()
    # A PUT THE SAME BRANCH RE-GETS IS NOT A SPEND, and its branch must stay stock. KQ5's
    # lamb EAT (USER-corrected 2026-08-18b: "it HAS to be half the leg of lamb") is the case:
    # the case's first-bite arm does `put: 19 <room>` then `get: 19` -- the lamb SURVIVES as
    # the half (a cel write, the item-property store), it scores, and it sets the hunger flag
    # rm32's death demands -- while only the else arm's bare `put: 19 1` destroys it. Wrapping
    # the whole case walls the designed, REQUIRED move. So a put-anchored wrap descends: for
    # each anchor site, find its innermost enclosing `(if ...)` inside the case; an arm that
    # re-gets the token is skipped, an arm that does not is held ALONE. Cases with no such
    # fork (the cat's and dog's lamb throws) keep the whole-case wrap byte-identically.
    is_put = "put:" in anchor_pat

    def _if_arms(txt, pos):
        """The innermost `(if ...)` enclosing pos that has a top-level `else`:
        (then_start, then_end, else_start, else_end) as body spans, or None.

        The enclosing form comes from `sexpr.form_chain` and the `else` from
        `sexpr.depth1_else` -- this was a raw `rfind("(if")` plus a fourth private copy of the
        else-walk, and neither skipped a comment or a message (2026-08-20 third review)."""
        for (s0, s1) in form_chain(txt, pos):
            if head_of(txt, s0) != "if":
                continue
            else_at = depth1_else(txt, s0, s1)
            if else_at is None:
                return None
            k = s0 + 3                               # then-arm body: after the condition form
            while txt[k] in " \t\n":
                k += 1
            _cs, ce = _block_span(txt, k)            # the condition form
            return (ce, else_at, else_at + 4, s1 - 1)
        return None

    get_pat = re.compile(r"get:\s*%s\b" % re.escape(str(token)))
    by_case = {}                       # case span -> [(match_pos, arm_span or None)]
    for m in re.finditer(anchor_pat, text):
        span = _enclosing_clause_span(text, m.start())
        if span is None:
            continue
        if enclosing_clause_head(text, m.start()) != str(token):
            continue
        arm = None
        if is_put:
            arms = _if_arms(text[span[0]:span[1]], m.start() - span[0])
            if arms:
                ts, te, es, ee = (span[0] + x for x in arms)
                arm = (ts, te) if ts <= m.start() < te else (es, ee)
        by_case.setdefault(span, []).append((m.start(), arm))
    spans, arm_wraps = [], []
    for span, hits in by_case.items():
        # the narrowing engages ONLY when some arm re-gets the token (the half-lamb shape);
        # a case whose fork never re-gets keeps the whole-case wrap byte-identically (the
        # cat's and dog's race-check `if local0` would otherwise churn shipped emissions).
        keeps = [a for (_p, a) in hits
                 if a is not None and get_pat.search(text[a[0]:a[1]])]
        if keeps:
            for (_p, a) in hits:
                if a is not None and not get_pat.search(text[a[0]:a[1]]) \
                        and a not in arm_wraps:
                    arm_wraps.append(a)
        elif span not in spans:
            spans.append(span)
    n = 0
    for (bs, be) in sorted(arm_wraps, reverse=True):
        wrapped = guarded_wrap(guard_sexpr, text[bs:be], refuse, site=site)
        text = text[:bs] + "\n\t\t\t\t" + wrapped + "\n\t\t\t" + text[be:]
        n += 1
    for (cs, ce) in sorted(spans, reverse=True):
        body = _clause_body(text, cs, ce)
        if body is None:
            continue
        bs, be = body
        wrapped = guarded_wrap(guard_sexpr, text[bs:be], refuse, site=site)
        text = text[:bs] + wrapped + text[be:]
        n += 1
    return text, n


def _enclosing_clause_body(region, pos):
    """Innermost cond-clause OR switch-case containing `pos`: return (body_start, body_end) =
    the span after the clause's condition/case head, so a guard wraps the whole committed
    action. None if `pos` is inside neither.

    Switch cases joined 2026-08-04 (finding #7, play-found): SCI1.1 verb dispatch is
    `(switch param1 (49 (global1 handsOff:) (setScript ...)))`, and with only cond recognised
    the wrap fell back to the bare setScript -- letting the handsOff sibling fire before the
    refusal, which leaves the player with dead controls: "Not yet!", then a hang. The whole
    reason this function exists is that siblings must not run ahead of a refusal."""
    span = _enclosing_clause_span(region, pos)
    return _clause_body(region, *span) if span else None


def enclosing_clause_head(region, pos):
    """The HEAD (test expression) of the innermost cond-clause containing `pos`, as source
    text, or None. What an arrival commit's stage condition is: the game's own test of whether
    this clause -- the one that commits the player -- runs at all."""
    span = _enclosing_clause_span(region, pos)
    if not span:
        return None
    cs, ce = span
    k = cs + 1
    while k < ce and region[k] in " \t\r\n":
        k += 1
    if k < ce and region[k] == "(":
        hs, he = _block_span(region, k)
    else:
        m = re.match(r"[^\s()]+", region[k:])
        if not m:
            return None
        hs, he = k, k + m.end()
    return re.sub(r"\s+", " ", region[hs:he]).strip()


def _clause_body(region, cs, ce):
    """Body span of a clause `(head body...)` at [cs, ce): everything after head."""
    k = cs + 1
    while k < ce and region[k] in " \t\r\n":
        k += 1
    if k < ce and region[k] == "(":
        _, he = _block_span(region, k)
    else:
        m = re.match(r"[^\s()]+", region[k:])
        he = k + (m.end() if m else 1)
    bs = he
    while bs < ce and region[bs] in " \t\r\n":
        bs += 1
    be = ce - 1
    while be > bs and region[be - 1] in " \t\r\n":
        be -= 1
    return bs, be


def _wrap_matches_in(region, site, pat, guard_sexpr, refuse):
    n = 0
    site = site if site is not None else _ModeSite()

    def repl(m):
        nonlocal n
        n += 1
        return guarded_wrap(guard_sexpr, m.group(0), refuse, site=site)
    return pat.sub(repl, region), n


if __name__ == "__main__":
    import glob
    src = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(__file__), "..", "vendor/sci-decomp-archive/lsl2/src")
    for room, target in [(26, 27), (38, 131)]:
        forms = read_file(os.path.join(src, f"rm{room}.sc"))
        p = find_trigger(forms, target)
        print(f"rm{room} newRoom:{target}  ->  {p}")
