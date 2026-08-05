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
from sexpr import read_file, Sym, Str, Said  # noqa: E402

CONTROLLABLE_METHODS = {"handleEvent", "doVerb"}


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
    hits = [(i, m, t) for (i, m, t, _recv) in ss if t in targets and i is not None]
    if not hits:
        # ...or the room does not `setScript:` anything: it CALLS one of the helper script's
        # exported procedures and the cutscene starts itself. KQ6's capture is this shape --
        # `rm340::init` runs `(proc342_2)`, which does `setScript: toGehenna`, which ends in
        # `newRoom: 405`. The guards grab you on ARRIVAL, so there is no exit to guard; the call
        # is the commit point.
        want = {t[1] for t in targets
                if isinstance(t, tuple) and len(t) == 2 and t[0] == "proc"}
        phits = [(i, m, nm) for (i, m, nm) in pc
                 if i is not None and any(nm.startswith("proc%d_" % s) for s in want)]
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
            for (i, m, t, _r) in ss
            if norm(t) == norm(target) and i is not None and m in CONTROLLABLE_METHODS]


def find_proc_calls(forms, names, methods=("init",)):
    """Calls to any of `names` inside one of `methods` -- one placement per call site.

    Restricted to `init` by default because this exists for ARRIVAL captures, where the game
    commits for you the moment you walk in. A call from `notify`/`cue` is mid-cutscene: refusing
    there leaves the scene half-run, which is the hang this module's whole controllable/
    uncontrollable split is about."""
    _nr, _cs, _ss, pc = analyze_room(forms)
    return [{"kind": "proc-call", "trigger_instance": i, "trigger_method": m,
             "target_script": nm, "target_pattern": re.escape(nm)}
            for (i, m, nm) in pc if i is not None and nm in names and m in methods]


def reaching_procs(forms, to_room):
    """Exported procedures of THIS file whose cutscene chain ends in `newRoom: to_room`.

    A helper script exports several procedures and only one of them leads where we care: n342 has
    `proc342_0` (an ordinary arrival), `proc342_1` and `proc342_2` (the guards seizing you), and
    only the last reaches `newRoom: 405`. Guarding the wrong one would refuse a normal arrival --
    a wall, not a gate -- which is why this is derived instead of taking the first call found.

    Walks BACKWARD over `setScript:` armings: who performs the newRoom, who arms them, and so on
    until an exported `procN_M` is reached. Owner scope is the enclosing instance or procedure."""
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


def wrap_all_armings_in_source(text, placement, guard_sexpr, refuse):
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
    for (bs, be) in sorted(spans, reverse=True):
        wrapped = (f"(if {guard_sexpr}\n\t\t\t\t{region[bs:be]}\n\t\t\telse\n"
                   f"\t\t\t\t{refuse}  ; softlock-guard\n\t\t\t)")
        region = region[:bs] + wrapped + region[be:]
        n += 1
    return text[:m0] + region + text[m1:], n


def _mentions_oncontrol(form):
    """Does this subtree test where the ego is STANDING? `(gEgo onControl: 1)`.

    SCI1.1's positional movement: the room's `doit` compares `onControl` against a control-colour
    mask and calls `newRoom:` when the player walks onto it. That is a player-initiated crossing --
    they walked there -- even though `doit` is not one of the handler methods."""
    if isinstance(form, Sym):
        return form.name == "onControl" or (form.is_selector() and form.sel == "onControl")
    if isinstance(form, list):
        return any(_mentions_oncontrol(x) for x in form)
    return False


def analyze_room(forms):
    """newRoom sites, changeState-call sites and setScript-call sites, tagged with (instance,
    method, ...). setScript is the OTHER way a controllable handler starts an uncontrollable
    sequence: `(self setScript: closer)` where the `closer` Script does the frontier newRoom --
    KQ4's rm45 amulet handover. Same shape as changeState, a different selector."""
    newroom_sites = []   # (instance, method, state, room, positional)
    cs_calls = []        # (instance, method, state_target, receiver)
    ss_calls = []        # (instance, method, target_script_name, receiver)
    proc_calls = []      # (instance, method, procedure name) -- `(proc342_2)`, how a room runs a
    #                      helper script's cutscene when it does not `setScript:` anything itself

    def walk(form, inst, meth, state, pos=False):
        if not isinstance(form, list) or not form:
            return
        h = form[0]
        if is_sym(h, "instance") or is_sym(h, "class"):
            name = form[1].name if len(form) > 1 and isinstance(form[1], Sym) else "?"
            for s in form[2:]:
                walk(s, name, meth, state, pos)
            return
        if is_sym(h, "method"):
            sig = form[1]
            mname = sig[0].name if isinstance(sig, list) and sig and isinstance(sig[0], Sym) else "?"
            for s in form[2:]:
                walk(s, inst, mname, None, False)
            return
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
                        walk(b, inst, meth, st, pos)
            return
        # A `cond`/`if` whose TEST asks where the ego is standing makes its body positional -- the
        # player walked onto that control colour, so the crossing is theirs to refuse.
        if is_sym(h, "cond"):
            for clause in form[1:]:
                if isinstance(clause, list) and clause:
                    cpos = pos or _mentions_oncontrol(clause[0])
                    for b in clause[1:]:
                        walk(b, inst, meth, state, cpos)
            return
        if is_sym(h, "if"):
            tpos = pos or (len(form) > 1 and _mentions_oncontrol(form[1]))
            for s in form[2:]:
                walk(s, inst, meth, state, tpos)
            return
        if isinstance(h, Sym) and not h.is_selector() and re.fullmatch(r"proc\d+_\d+", h.name):
            proc_calls.append((inst, meth, h.name))
            for s in form[1:]:
                walk(s, inst, meth, state, pos)
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
                elif sel == "changeState" and isinstance(a0, int):
                    cs_calls.append((inst, meth, a0, recv))
                elif sel == "setScript" and isinstance(a0, Sym):
                    ss_calls.append((inst, meth, a0.name, recv))
                elif sel == "setScript" and _script_id(a0):
                    # `(global2 setScript: (ScriptID 344 3))` -- SCI1.1 arms a cutscene that lives
                    # in ANOTHER script by export number rather than by name. Recorded under a
                    # canonical key so the armer can be matched to the script that owns the
                    # `newRoom` (see `exports_of` / `find_arming`).
                    ss_calls.append((inst, meth, _script_id(a0), recv))
                for a in args:
                    walk(a, inst, meth, state, pos)
            walk(form[0], inst, meth, state, pos)
            return
        for s in form:
            walk(s, inst, meth, state, pos)

    for f in forms:
        walk(f, None, None, None, False)
    return newroom_sites, cs_calls, ss_calls, proc_calls


def find_trigger(forms, target_room):
    """Return the guard placement for a frontier newRoom into `target_room`."""
    nr, cs, ss, _pc = analyze_room(forms)
    nav = nav_props(forms)
    sites = [s for s in nr if s[3] == target_room
             or (isinstance(s[3], tuple) and s[3][0] == "nav"
                 and nav.get(s[3][1]) == target_room)]
    if not sites:
        return {"kind": "not-found", "target_room": target_room}
    inst, meth, state, _, positional = sites[0]
    if inst is None:
        # A `newRoom` in a bare procedure: nothing to scope an edit to. Report it as unfound
        # rather than crashing the wrapper, which locates every site by its instance.
        return {"kind": "no-trigger", "instance": None, "cutscene_state": state,
                "target_room": target_room}
    if meth in CONTROLLABLE_METHODS:
        return {"kind": "direct", "instance": inst, "method": meth,
                "target_room": target_room}
    if positional:
        # SCI1.1's positional exit: `doit` sees the ego standing on a control colour and calls
        # `newRoom:`. `doit` is not a handler method, but the move IS the player's -- they walked
        # there -- so it is refusable, and refusing it is exactly what an edge guard wants. Wrap
        # the whole cond-clause, not just the call: its siblings hand control off and animate.
        return {"kind": "direct", "instance": inst, "method": meth, "positional": True,
                "target_room": target_room}
    # newRoom is inside a cutscene (changeState). Find the controllable trigger.
    cands = [(k, m) for (i, m, k, recv) in cs
             if i == inst and m in CONTROLLABLE_METHODS and recv == "self"
             and (state is None or k <= state)]
    if cands:
        kstar, trig_meth = max(cands, key=lambda km: km[0])
        return {"kind": "trigger", "instance": inst, "trigger_method": trig_meth,
                "trigger_state": kstar, "cutscene_state": state, "target_room": target_room}
    # ...or the newRoom lives in a Script `inst` that a controllable handler STARTS with
    # `(self setScript: inst)` -- KQ4's rm45 amulet handover (`(self setScript: closer)`, and
    # `closer` does `newRoom: 690`). Guard that setScript call.
    # `i2 is not None` because the wrapper locates the edit by `(instance <i2> ...)`: an arming
    # made from a bare PROCEDURE has no instance to scope to, so there is no site to rewrite.
    ss_cands = [(i2, m2) for (i2, m2, target, recv) in ss
                if target == inst and m2 in CONTROLLABLE_METHODS and i2 is not None]
    if ss_cands:
        i2, m2 = ss_cands[0]
        return {"kind": "setscript", "trigger_instance": i2, "trigger_method": m2,
                "target_script": inst, "target_room": target_room}
    # ...or the Script is armed by a setScript in an UNCONTROLLABLE method -- an ADVERSARIAL event
    # the player cannot refuse (KQ4's whale swallow: `Room31::init` does `(global0 setScript:
    # whaleActions)` on a Random roll; nightfall is the same shape in `KQ4::newRoom`). There is no
    # player action to guard, so we gate the ARMING itself: the event fires only when the survival
    # item is held. If it is missing the event simply does not arm -- exactly the prevention.
    arm_cands = [(i2, m2) for (i2, m2, target, recv) in ss if target == inst and i2 is not None]
    if arm_cands:
        i2, m2 = arm_cands[0]
        return {"kind": "arm-event", "trigger_instance": i2, "trigger_method": m2,
                "target_script": inst, "target_room": target_room}
    return {"kind": "no-trigger", "instance": inst, "cutscene_state": state,
            "target_room": target_room}


# --------------------------------------------------------------------------
# region-scoped source wrapping
# --------------------------------------------------------------------------
def _block_span(text, start_idx):
    """Given index of a '(', return (start, end) covering the balanced form,
    skipping {..} strings and '..' Said specs."""
    depth, i, n = 0, start_idx, len(text)
    while i < n:
        c = text[i]
        if c == "{":
            i = text.find("}", i) + 1
            continue
        if c == "'":
            i = text.find("'", i + 1) + 1
            continue
        if c == ";":
            i = text.find("\n", i)
            if i < 0:
                break
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return start_idx, i + 1
        i += 1
    return start_idx, n


def _find_region(text, header_re):
    m = re.search(header_re, text)
    if not m:
        return None
    return _block_span(text, m.start())


def wrap_trigger_in_source(text, placement, guard_sexpr, refuse="(NotNow)"):
    """Wrap the controllable trigger's `(self changeState: K)` (scoped to the
    right instance+method) in the item guard. For a 'direct' placement, wrap the
    `newRoom: N` instead."""
    if placement["kind"] == "direct":
        pat = re.compile(r"\([^()]*newRoom:\s*%d\b[^()]*\)" % placement["target_room"])
        if placement.get("positional"):
            # The whole cond-clause, not just the call: a positional exit's siblings take control
            # away and start the walk-off animation, so leaving them to run and refusing only the
            # room change hangs the game with hands off. Same care as the setScript case below.
            m = pat.search(text)
            if not m:
                return text, 0
            clause = _enclosing_clause_body(text, m.start())
            if clause:
                bs, be = clause
                wrapped = (f"(if {guard_sexpr}\n\t\t\t\t{text[bs:be]}\n\t\t\telse\n"
                           f"\t\t\t\t{refuse}  ; softlock-guard\n\t\t\t)")
                return text[:bs] + wrapped + text[be:], 1
        return _wrap_matches_in(text, None, pat, guard_sexpr, refuse)
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
        wrapped = (f"(if {guard_sexpr}\n\t\t\t\t{region[bs:be]}\n\t\t\telse\n"
                   f"\t\t\t\t{refuse}  ; softlock-guard\n\t\t\t)")
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
        # ONE level of nesting on either side of the selector: SCI1.1 writes both the receiver and
        # the target as calls -- `((ScriptID 344 2) setScript: (ScriptID 344 3))` -- and a pattern
        # that allows no parentheses cannot see that statement at all.
        _ANY = r"(?:[^()]|\([^()]*\))*"
        ssm = re.search(r"\(%ssetScript:\s*%s%s\)" % (_ANY, tpat, _ANY), region)
        if not ssm:
            return text, 0
        clause = _enclosing_clause_body(region, ssm.start())
        if clause:
            bs, be = clause
            wrapped = (f"(if {guard_sexpr}\n\t\t\t\t{region[bs:be]}\n\t\t\telse\n"
                       f"\t\t\t\t{refuse}  ; softlock-guard\n\t\t\t)")
            new_meth = region[:bs] + wrapped + region[be:]
        else:
            new_meth, _ = _wrap_matches_in(
                region, None, re.compile(r"\(%ssetScript:\s*%s%s\)" % (_ANY, tpat, _ANY)),
                guard_sexpr, refuse)
        return text[:m0] + new_meth + text[m1:], 1
    if placement["kind"] == "arm-event":
        # Gate the ARMING of an adversarial event: wrap `(<recv> setScript: <target>)` so it fires
        # only when the guard holds. NO `else` -- if the item is missing the event just does not arm
        # (you are never swallowed without the feather), which is the prevention itself. The refuse
        # branch of the controllable cases makes no sense here: there is no player to tell "not now".
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
        # Gate EVERY arming site for this event -- KQ4's Room31::init both STARTS the swallow (the
        # Random roll) and RESUMES it on re-entry (global105==14); both must require the item, so
        # the whale is never active without the feather. No `else`: a missing item just doesn't arm.
        pat = re.compile(r"\([^()]*setScript:\s*%s\b[^()]*\)" % re.escape(target))
        n = [0]

        def repl(m):
            n[0] += 1
            return (f"(if {guard_sexpr}\n\t\t\t\t{m.group(0)}\n\t\t\t)"
                    f"  ; softlock-guard: arm only when survivable")
        new_meth = pat.sub(repl, region)
        return text[:m0] + new_meth + text[m1:], n[0]
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

        def repl(m):
            n[0] += 1
            return (f"(if {guard_sexpr}\n\t\t\t\t{m.group(0)}\n\t\t\telse\n"
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
        wrapped = (f"(if {guard_sexpr}\n\t\t\t\t{region[bs:be]}\n\t\t\telse\n"
                   f"\t\t\t\t{refuse}  ; softlock-guard\n\t\t\t)")
        new_meth = region[:bs] + wrapped + region[be:]
    else:
        new_meth, _ = _wrap_matches_in(
            region, None, re.compile(r"\(self\s+changeState:\s*%d\s*\)" % k),
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


def _wrap_matches_in(region, _unused, pat, guard_sexpr, refuse):
    n = 0

    def repl(m):
        nonlocal n
        n += 1
        return f"(if {guard_sexpr}\n\t\t\t\t{m.group(0)}\n\t\t\telse\n\t\t\t\t{refuse}  ; softlock-guard\n\t\t\t)"
    return pat.sub(repl, region), n


if __name__ == "__main__":
    import glob
    src = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(__file__), "..", "vendor/sci-decomp-archive/lsl2/src")
    for room, target in [(26, 27), (38, 131)]:
        forms = read_file(os.path.join(src, f"rm{room}.sc"))
        p = find_trigger(forms, target)
        print(f"rm{room} newRoom:{target}  ->  {p}")
