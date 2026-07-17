"""Phase 1 -- read the game's own class library instead of guessing its semantics.

Every deep bug of 2026-07-16 was a hand-transcription of a file sitting in the source
directory we already parse. `machine.py`'s whitelist is `System.sc`'s `Script` class,
copied from memory:

    (class Script of Obj
        (properties client 0  state -1  start 0  cycles 0  seconds 0 ...)
        (method (doit ...) (cond (cycles  (if (not (-- cycles)) (self cue:)))
                                 (seconds ... (if (not (-- seconds)) (self cue:)))))
        (method (init who) (= client who) (self changeState: start)))

    (class Actor ...
        (method (has param1 &tmp temp0)
            (if (= temp0 (gInventory at: param1)) (temp0 ownedBy: self))))

So: `(= seconds N)` is a deferred cue. `(X setScript: s)` runs `s` from `start` -- a
PROPERTY, not the 0 we hardcode. And `(ego has: X)` IS `((gInventory at: X) ownedBy:
ego)` -- the possession "channel" a census went looking for is the definition, four
lines up.

model.py's own comment on these files reads: "They carry no rooms, so they stay inert."
They carry the semantics.

DERIVE, THEN VERIFY. Each fact is read out of the class library and checked against the
shape we expect. A game whose library disagrees gets a loud failure rather than a silent
mis-model -- which is the whole difference between reading and transcribing.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sexpr import Sym                                      # noqa: E402
from model import head_is, is_sym                          # noqa: E402


class DictionaryError(Exception):
    """The class library does not say what we rely on it saying."""


def class_defs(game):
    """name -> {super, props, methods} for every `(class X of Y ...)` in the game.

    These live in the unnumbered scripts (System.sc, Actor.sc, Game.sc) that
    `load_game` files under synthetic negative keys.
    """
    out = {}
    for s in game.scripts.values():
        for f in getattr(s, "forms", []) or []:
            if not (head_is(f, "class") and len(f) >= 2 and isinstance(f[1], Sym)):
                continue
            name = f[1].name
            sup = f[3].name if len(f) >= 4 and is_sym(f[2], "of") \
                and isinstance(f[3], Sym) else None
            props, methods = {}, {}
            for sub in f[2:]:
                if head_is(sub, "properties"):
                    toks = sub[1:]
                    for i in range(0, len(toks) - 1, 2):
                        if isinstance(toks[i], Sym):
                            props[toks[i].name] = toks[i + 1]
                elif head_is(sub, "method") and isinstance(sub[1], list) and sub[1] \
                        and isinstance(sub[1][0], Sym):
                    methods[sub[1][0].name] = sub[2:]
            out[name] = {"super": sup, "props": props, "methods": methods}
    return out


def _find(body, pred):
    """Depth-first search of a method body for the first form matching `pred`."""
    for f in body:
        if not isinstance(f, list):
            continue
        if pred(f):
            return f
        hit = _find(f, pred)
        if hit is not None:
            return hit
    return None


def possession(classes):
    """How does this game ask 'do you have it?' -> (has_selector, owner_selector).

    Derived from `Actor::has`, whose body is `((Inventory at: X) ownedBy: self)`. That
    equivalence is why `has:` and `ownedBy` are ONE channel: model.py treats the first
    as a first-class predicate and renders the second opaque, so a possession test
    written the second way is invisible. KQ4 rm18 writes it the second way.
    """
    for cname in ("Actor", "Ego", "Act"):
        body = classes.get(cname, {}).get("methods", {}).get("has")
        if not body:
            continue
        send = _find(body, lambda f: len(f) >= 2 and isinstance(f[1], Sym)
                     and f[1].is_selector() and f[1].sel.startswith("ownedBy"))
        if send is not None:
            return "has", send[1].sel
    raise DictionaryError(
        "no `has` method found on Actor/Ego/Act, or its body does not resolve to an "
        "`ownedBy`-style check. Possession is the core predicate of this whole "
        "analysis; refusing to guess it.")


def script_semantics(classes):
    """The Script state machine's own rules, read rather than whitelisted.

    Returns {entry_prop, cue_vars, state_prop}. `entry_prop` is the one that matters:
    machine.py hardcodes entry state 0, but `Script::init` says `changeState: start`,
    and `start` is a per-instance property.
    """
    sc = classes.get("Script")
    if not sc:
        raise DictionaryError("no `Script` class in the class library; machine.py's "
                              "entire model of intra-room progression is built on it.")

    # (method (init who) ... (self changeState: start))
    init = sc["methods"].get("init", [])
    cs = _find(init, lambda f: len(f) >= 3 and isinstance(f[1], Sym)
               and f[1].sel == "changeState")
    if cs is None or not isinstance(cs[2], Sym):
        raise DictionaryError(
            "Script::init does not end in `(self changeState: <prop>)`. That call is "
            "what `setScript:` means; we will not assume state 0.")
    entry_prop = cs[2].name
    if entry_prop not in sc["props"]:
        raise DictionaryError(f"Script::init enters at `{entry_prop}`, which is not a "
                              f"Script property: {sorted(sc['props'])}")

    # (method (doit) (cond (cycles ... (self cue:)) (seconds ... (self cue:))))
    doit = sc["methods"].get("doit", [])
    cue_vars = {t.name for f in doit for t in _flat(f)
                if isinstance(t, Sym) and t.name in sc["props"]
                and t.name in ("cycles", "seconds", "ticks")}
    if not cue_vars:
        raise DictionaryError("Script::doit arms no cue from any property; the "
                              "`(= seconds N)` idiom would be unreadable.")
    return {"entry_prop": entry_prop, "cue_vars": cue_vars,
            "state_prop": "state" if "state" in sc["props"] else None,
            "default_entry": sc["props"].get(entry_prop, 0)}


def _flat(f):
    if not isinstance(f, list):
        yield f
        return
    for x in f:
        yield from _flat(x)


def instance_entry(game, script_num, inst, sem):
    """The state THIS Script instance starts at: its own `start`, else the class default.

    `Script::init` does `changeState: start`, so an instance that declares
    `(properties start 5)` enters at 5. machine.py assumed 0 for everything.
    """
    for f in getattr(game.scripts.get(script_num), "forms", []) or []:
        if not (head_is(f, "instance") and len(f) > 1 and is_sym(f[1], inst)):
            continue
        for sub in f[2:]:
            if head_is(sub, "properties"):
                toks = sub[1:]
                for i in range(0, len(toks) - 1, 2):
                    if isinstance(toks[i], Sym) and toks[i].name == sem["entry_prop"]:
                        if isinstance(toks[i + 1], int):
                            return toks[i + 1]
    d = sem["default_entry"]
    return d if isinstance(d, int) else 0


def load(game):
    """The whole dictionary, derived and verified."""
    classes = class_defs(game)
    has_sel, owner_sel = possession(classes)
    sem = script_semantics(classes)
    return {"classes": classes, "has_selector": has_sel, "owner_selector": owner_sel,
            "script": sem}


def main():
    import config
    from model import load_game
    for cfg in (config.LSL2, config.KQ4):
        config.ACTIVE = cfg
        g = load_game(cfg.src_dir)
        name = cfg.name.split(":")[0]
        try:
            d = load(g)
        except DictionaryError as e:
            print(f"{name}: DICTIONARY ERROR -- {e}")
            continue
        s = d["script"]
        print(f"{name}")
        print(f"   classes read           : {len(d['classes'])}")
        print(f"   possession             : `{d['has_selector']}:` IS "
              f"`{d['owner_selector']}: self`   (Actor::has)")
        print(f"   Script entry           : changeState: `{s['entry_prop']}` "
              f"(default {s['default_entry']})   <- machine.py hardcodes 0")
        print(f"   deferred cue armed by  : {sorted(s['cue_vars'])}   (Script::doit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
