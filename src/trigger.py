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


def analyze_room(forms):
    """newRoom sites and changeState-call sites, tagged with (instance, method,
    switch-state)."""
    newroom_sites = []   # (instance, method, state, room)
    cs_calls = []        # (instance, method, state_target, receiver)

    def walk(form, inst, meth, state):
        if not isinstance(form, list) or not form:
            return
        h = form[0]
        if is_sym(h, "instance") or is_sym(h, "class"):
            name = form[1].name if len(form) > 1 and isinstance(form[1], Sym) else "?"
            for s in form[2:]:
                walk(s, name, meth, state)
            return
        if is_sym(h, "method"):
            sig = form[1]
            mname = sig[0].name if isinstance(sig, list) and sig and isinstance(sig[0], Sym) else "?"
            for s in form[2:]:
                walk(s, inst, mname, None)
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
                        walk(b, inst, meth, st)
            return
        ms = _message_send(form)
        if ms:
            recv, groups = ms
            for sel, args in groups:
                a0 = args[0] if args else None
                if sel == "newRoom" and isinstance(a0, int):
                    newroom_sites.append((inst, meth, state, a0))
                elif sel == "changeState" and isinstance(a0, int):
                    cs_calls.append((inst, meth, a0, recv))
                for a in args:
                    walk(a, inst, meth, state)
            walk(form[0], inst, meth, state)
            return
        for s in form:
            walk(s, inst, meth, state)

    for f in forms:
        walk(f, None, None, None)
    return newroom_sites, cs_calls


def find_trigger(forms, target_room):
    """Return the guard placement for a frontier newRoom into `target_room`."""
    nr, cs = analyze_room(forms)
    sites = [s for s in nr if s[3] == target_room]
    if not sites:
        return {"kind": "not-found", "target_room": target_room}
    inst, meth, state, _ = sites[0]
    if meth in CONTROLLABLE_METHODS:
        return {"kind": "direct", "instance": inst, "method": meth,
                "target_room": target_room}
    # newRoom is inside a cutscene (changeState). Find the controllable trigger.
    cands = [(k, m) for (i, m, k, recv) in cs
             if i == inst and m in CONTROLLABLE_METHODS and recv == "self"
             and (state is None or k <= state)]
    if not cands:
        return {"kind": "no-trigger", "instance": inst, "cutscene_state": state,
                "target_room": target_room}
    kstar, trig_meth = max(cands, key=lambda km: km[0])
    return {"kind": "trigger", "instance": inst, "trigger_method": trig_meth,
            "trigger_state": kstar, "cutscene_state": state, "target_room": target_room}


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
        return _wrap_matches_in(text, None, pat, guard_sexpr, refuse)
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


def _enclosing_clause_body(region, pos):
    """Innermost cond-clause containing `pos`: return (body_start, body_end) = the
    span after the clause's condition/`else` head, so a guard wraps the whole
    committed action. None if `pos` is not inside a cond-clause."""
    cond_span = None
    for m in re.finditer(r"\(cond\b", region):
        s, e = _block_span(region, m.start())
        if s <= pos < e and (cond_span is None or s > cond_span[0]):
            cond_span = (s, e)
    if cond_span is None:
        return None
    cs, ce = cond_span
    k = cs + 1
    mk = re.match(r"\s*cond\b", region[k:])
    if mk:
        k += mk.end()
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
                return _clause_body(region, clause_s, clause_e)
            k = clause_e
        else:
            k += 1
    return None


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
