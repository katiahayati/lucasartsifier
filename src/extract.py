"""Extraction over the sci-tools typed IR (Phase 3 of PLAN-v2 / ENGINE-DIRECTION Plan A).

Walks each room's typed control-flow AST and composes PATH CONDITIONS along the control
flow into a gated transition system: movement edges, item acquisitions, register writes,
deaths. Because the AST is typed and complete, effect-timing follows the machine's own
control flow -- there is no ENTRY/SELF/EXIT reconstruction heuristic (the seam that lost
the parachute).

Guards reuse model.py's tree (GAnd/GOr/GNot/Pred), but identifiers are IR-canonical:
Pred.var is a global INDEX for CMP, an item number for OWN.

This is built incrementally; this first cut does movement + item acquisitions (guards over
OWN/SAID/POS/CMP/opaque), validated against the old model before registers/machine-state.
"""
from __future__ import annotations

import config

import collections
import contextlib
import os
from dataclasses import dataclass, field

import ir as I
import vocab as V
from guard_ast import GAnd, GOr, GNot, Pred

# The ego global(s) (gEgo -- the get/put/has/edgeHit receiver) and the current-room global
# (gCurRoomNum). DERIVED per game in install_vocabulary: ego from the store wrapper's holder
# globals (`(= global0 ego)`), current-room from the Game loop. The values below are the SCI
# template DEFAULTS, used only if a game has no derivable store/Game-loop (never for LSL2/KQ4,
# both of which derive ego={0}, current-room=11).
_EGO = frozenset({0})
_CURROOM = 11


def _is_ego(node):
    """Is `node` a reference to one of the derived ego globals?"""
    return any(I.is_global(node, g) for g in _EGO)


NAV_SELECTORS = ("north", "south", "east", "west")

# `register` is the third argument of `setScript:` -- SCI's way of telling one Script instance
# WHICH job it is doing this time. It is a standard `Script` selector (script 999, alongside
# client/caller), i.e. engine vocabulary like `newRoom` or `has`, not a game's own name.
#
# It matters because one machine can serve two exits: KQ6's `walkOut` is armed `setScript: walkOut
# 0 1` behind the minotaur flag and `walkOut 0 0` without it, and its body reads
# `(if register (newRoom: 340) else (newRoom: 409))`. Merge the two and the flag-gated escape from
# the catacombs looks free, because the ungated arming also reaches the same state.
#
# Modelled as a CARRIED LOCAL under a reserved key, so the machinery that already threads an
# arming context's local writes (`entry_locals` + `_ctr_ok`) prunes the arm this entry did not
# choose. The key cannot collide with a real local: variable types are Local/Temp, giving key
# letters "L"/"T".
REG_KEY = ("R", 0)


def _is_register(n):
    """`register` read as this object's own property, or `(<obj> register:)`."""
    if not isinstance(n, dict):
        return False
    if n.get("t") == "Property":
        return n.get("name") == "register"
    if n.get("t") == "Send":
        try:
            _r, msgs = I.send_pairs(n)
        except Exception:                                   # noqa: BLE001
            return False
        return len(msgs) == 1 and msgs[0][0] == "register" and not msgs[0][1]
    return False


# ---- guard atoms from a test expression ----------------------------------
def atom(n):
    """A boolean test node -> a guard tree (Pred / GAnd / GOr / GNot). Unknown player
    actions (Said, position) and anything we cannot decide become opaque preds."""
    if n is None:
        return None
    tp = n["t"]
    if tp == "Not":
        return GNot(atom(n["kids"][0])) if n["kids"] else Pred("OPAQUE")
    if tp == "And":
        return GAnd([atom(k) for k in n["kids"]])
    if tp == "Or":
        return GOr([atom(k) for k in n["kids"]])
    if tp == "Said":
        return Pred("SAID")
    if tp == "Send":
        return _send_atom(n)
    if tp in ("Eq", "Ne", "Gt", "Ge", "Lt", "Le", "Ugt", "Uge", "Ult", "Ule"):
        return _cmp_atom(n, tp)
    if tp == "Variable" and n["vtype"] == "Global":
        return Pred("CMP", var=n["index"], op="!=", value="0")   # truthiness of a global
    if tp == "Variable" and n["vtype"] in ("Local", "Temp"):
        # truthiness of a tracked local -- `(if local1 ...)` is `local1 != 0`, the same CTR a
        # `(== local1 N)` compare yields, so the machine compiler can resolve it against the
        # carried counter value. rm214's knockDoor gates its door-opens states on exactly this.
        return ("CTR", (n["vtype"][0], n["index"]), "!=", 0)
    if _is_register(n):
        return ("CTR", REG_KEY, "!=", 0)          # `(if register ...)` -- see REG_KEY
    if tp == "Number":
        return None if n["value"] != 0 else Pred("OPAQUE")       # constant test
    if tp in ("PublicCall", "LocalCall"):
        m = _oneof_atom(n)
        if m is not None:
            return m
    return Pred("OPAQUE")


def _oneof_atom(n):
    """`(oneOf x a b c)` -> `x==a OR x==b OR x==c`, else None.

    SCI's system script provides a variadic membership test, and SCI1.1 games use it wherever
    SCO0 would have written a chain of `or`s -- KQ6 gates 18 room transitions on one. Lowering it
    to the disjunction it already means costs nothing new: each disjunct goes through the SAME
    `_cmp_atom` path as a written-out compare, so a membership test on a global becomes an
    ordinary register gate and one on anything else stays opaque, exactly as the spelled-out form
    would. `derive_oneof` supplies the proc names structurally, so this is inert on games without
    one."""
    if not _ONEOF or n.get("name") not in _ONEOF:
        return None
    ks = n.get("kids") or []
    if len(ks) < 2:
        return None
    subject, vals = ks[0], [I.as_int(k) for k in ks[1:]]
    if not vals or any(v is None for v in vals):
        return None                       # a non-literal candidate list decides nothing here
    kids = [_cmp_atom({"t": "Eq", "kids": [subject, {"t": "Number", "value": v}]}, "Eq")
            for v in vals]
    # Bail (-> the caller's opaque, which is satisfiable) if any disjunct is undecidable or
    # unconstrained: an opaque subject decides nothing, and a free disjunct makes the whole OR
    # free. Both are the permissive reading, which is the safe direction for a guard.
    if any(k is None or (isinstance(k, Pred) and k.kind == "OPAQUE") for k in kids):
        return None
    return GOr(kids) if len(kids) > 1 else kids[0]


_OPS = {"Eq": "==", "Ne": "!=", "Gt": ">", "Ge": ">=", "Lt": "<", "Le": "<=",
        "Ugt": ">", "Uge": ">=", "Ult": "<", "Ule": "<="}
_REV = {"==": "==", "!=": "!=", ">": "<", ">=": "<=", "<": ">", "<=": ">="}


def _cmp_atom(n, tp):
    """A comparison test -> a guard. Global vs literal -> Pred CMP; LOCAL/Temp vs literal ->
    a CTR tuple `("CTR", (vt_char, idx), op, val)` (same format compile uses for machine
    bodies), so gexpr resolves it against the tracked local. `henchStatus==0` and the like
    used to fall through to OPAQUE -- the 'everything means everything' local-guard hole."""
    ks = n["kids"]
    if len(ks) < 2:
        return Pred("OPAQUE")
    a, b = ks[0], ks[1]
    op = _OPS[tp]
    # GLOBAL vs literal (op reversed if the global is on the right, e.g. `(< 5 gX)` = gX>5)
    if I.is_global(a) and I.as_int(b) is not None:
        return Pred("CMP", var=a["index"], op=op, value=str(I.as_int(b)))
    if I.is_global(b) and I.as_int(a) is not None:
        return Pred("CMP", var=b["index"], op=_REV[op], value=str(I.as_int(a)))
    # `register` vs literal -- which job this Script was armed for. See REG_KEY.
    for x, y in ((a, b), (b, a)):
        if _is_register(x) and I.as_int(y) is not None:
            return ("CTR", REG_KEY, op if x is a else _REV[op], I.as_int(y))
    # LOCAL/TEMP vs literal -> tracked-local CTR guard (the previously-dropped 196)
    if I.is_local_or_temp(a) and I.as_int(b) is not None:
        return ("CTR", (a["vtype"][0], a["index"]), op, I.as_int(b))
    if I.is_local_or_temp(b) and I.as_int(a) is not None:
        return ("CTR", (b["vtype"][0], b["index"]), _REV[op], I.as_int(a))
    # `(<inv> indexOf: (<iconbar> curInvIcon:)) == N` -- SCI1 "use item N": N is the number of the
    # item selected in the icon bar. Requires holding N, the same requirement SCO writes `has: N`
    # (rm214 gates the temple door on `== 7`, the staff). `!=` carries no ownership info -- you
    # selected something else but may still hold N -- so only `==` is a gate.
    for x, y in ((a, b), (b, a)):
        if I.is_selected_item(x) and I.as_int(y) is not None:
            return Pred("OWN", var=I.as_int(y)) if op == "==" else None
    # `(<iconbar> curInvIcon:) == (<inv> at: N)` -- the KQ6/QFG/Dagger spelling of the same "use item
    # N": the selected item OBJECT compared to inventory slot N.
    for x, y in ((a, b), (b, a)):
        if _is_curinvicon(x):
            it = _at_item(y)
            if it is not None:
                return Pred("OWN", var=it) if op == "==" else None
    # `((Inv at: N) owner:) == <room>` -- the direct-property-read spelling of `ownedBy:`. The
    # location property is DERIVED (owner), and `ownedBy:` IS `(== owner param1)`, so this is the
    # SAME location store and the SAME LOC pred: KQ5/KQ6/Dagger gate the yeti and doors on an item's
    # owner where LSL2 wrote `(item ownedBy: room)`. `==` means "item is there", `!=` its negation;
    # a relational op on a location is meaningless, so only == / != are recognised (else opaque).
    for x, y in ((a, b), (b, a)):
        it = _item_loc_read(x)
        if it is not None and op in ("==", "!="):
            where = ("room" if I.is_global(y, _CURROOM)
                     else I.as_int(y) if I.as_int(y) is not None else "other")
            loc = Pred("LOC", var=it, op="ownedBy", value=where)
            return loc if op == "==" else GNot(loc)
    # `(== ((Inv at: 17) loop:) 1)` -- the FOURTH store: state living in an item's own property.
    # Went to OPAQUE, which threw the fact away; carried as IPROP it is at least preserved.
    ip = item_prop_read(a)
    if ip is not None and I.as_int(b) is not None:
        return Pred("IPROP", var=ip, op=op, value=I.as_int(b))
    ip = item_prop_read(b)
    if ip is not None and I.as_int(a) is not None:
        return Pred("IPROP", var=ip, op=_REV[op], value=I.as_int(a))
    # `(edgeHit) == N` -> the ego is at screen edge N (a POSITION guard over (x,y)).
    if _is_ego_edgehit(a) and I.as_int(b) is not None and op == "==":
        return ("POS", "edge", I.as_int(b))
    if _is_ego_edgehit(b) and I.as_int(a) is not None and op == "==":
        return ("POS", "edge", I.as_int(a))
    # SCI1 doVerb item-use: `(== param1 <msg>)` where param1 is the clicked icon's message (see
    # vocab.doverb_item_messages) and <msg> is an inventory item's message -> the player is USING
    # that item, i.e. OWN(item index). Only inside a doVerb body (_VERB_PARAM set) so a parameter
    # compared elsewhere is never misread; _ITEM_MSG excludes base verbs, so a verb number falls
    # through to opaque = free player choice. `!=` carries no ownership info (like curInvIcon).
    if _VERB_PARAM is not None and _ITEM_MSG:
        for x, y in ((a, b), (b, a)):
            if (isinstance(x, dict) and x.get("t") == "Variable" and x.get("vtype") == "Parameter"
                    and x.get("index") == _VERB_PARAM and I.as_int(y) in _ITEM_MSG):
                return Pred("OWN", var=_ITEM_MSG[I.as_int(y)]) if op == "==" else None
    # property / onControl / distance compares -> opaque (control-map / undecidable)
    return Pred("OPAQUE")


def _is_ego_edgehit(n):
    """`(gEgo edgeHit:)` -- returns which screen edge the ego is at."""
    if isinstance(n, dict) and n.get("t") == "Send":
        recv, msgs = I.send_pairs(n)
        if _is_ego(recv):
            return any(sel == "edgeHit" for sel, _ in msgs)
    return False


def item_prop_read(n):
    """`((Inv at: 17) loop:)` -> `(item, property)` if that pair is tracked state, else None.

    Only pairs the game both writes and reads count -- a `view:` read is cosmetic, a `loop:` read
    on the fishing pole is asking whether it is baited. The distinction is discovered, not listed.
    """
    if not (isinstance(n, dict) and n.get("t") == "Send"):
        return None
    recv, msgs = I.send_pairs(n)
    it = _at_item(recv)
    if it is None:
        return None
    for sel, params in msgs:
        if not params and (it, sel) in _IPROPS:
            return (it, sel)
    return None


def _item_loc_read(n):
    """`((Inv at: N) <locationprop>:)` -> item N, else None. The location property is derived per
    game (`owner`), so this is the direct-read form of `ownedBy:` -- same store, same LOC pred.
    Returns None before the vocabulary is installed or on a non-item send."""
    if _VOCAB is None or not (isinstance(n, dict) and n.get("t") == "Send"):
        return None
    recv, msgs = I.send_pairs(n)
    it = _at_item(recv)
    if it is None:
        return None
    return it if any(sel == _VOCAB.prop and not params for sel, params in msgs) else None


def _is_curinvicon(n):
    """`(<iconbar> curInvIcon:)` -- the inventory item OBJECT the player has selected. KQ6/QFG/Dagger
    compare it directly to `(inv at: N)`; KQ5 wraps it in `indexOf` (see ir.is_selected_item)."""
    if not (isinstance(n, dict) and n.get("t") == "Send"):
        return False
    _recv, msgs = I.send_pairs(n)
    return any(sel == "curInvIcon" for sel, _params in msgs)


def _at_item(n):
    """`(gInv at: N)` -> N. The object handle for inventory item N."""
    if isinstance(n, dict) and n.get("t") == "Send":
        recv, msgs = I.send_pairs(n)
        for sel, params in msgs:
            if sel == "at" and params:
                return I.as_int(params[0])
    return None


# ---- the item-LOCATION store: DERIVED, not catalogued ---------------------
# We used to hand-write a recogniser per spelling -- `gEgo get:`, `gEgo put:`, `(Inv at: N)
# moveTo:`, a raw `owner:` write -- and each new game produced another one. They are not four
# idioms. They are ONE property write, and the game says so in its own class table:
#
#     (class InvI of Obj  (properties ... owner 0 loop 0 ...)
#       (method (ownedBy param1) (return (== owner param1)))       ; READ  the location
#       (method (moveTo param1)  (= owner param1) (return self)))  ; WRITE the location
#
#     (class Ego ... (method (put param1 param2) ((global9 at: param1) moveTo: ...)))
#
# vocab.Vocabulary reads that and derives which selectors move an item and where the item and
# destination sit in each. Both games independently yield the same table, and the two exclusions
# the hand-written version made by eye (Window's same-named `moveTo: x y`) fall out of the
# receiver and arity of the class's own method. See docs/HOW-IT-WORKS and TODO A0.
EGO = V.EGO      # destination sentinel: the item is now HELD

_VOCAB = None    # installed by extract(); one game per process
_IPROPS = {}     # (item, property) -> values written -- the FOURTH store, discovered
#   the same way gating registers are: written AND read. See vocab.item_property_registers.
_ITEM_MSG = {}   # SCI1 doVerb: item message-number -> inventory index (vocab.doverb_item_messages).
#   Empty on SCO0, so the doVerb item-use recognizer below is inert on LSL2/KQ4/KQ5.
_VERB_PARAM = None   # while walking a `doVerb` body, the Parameter index of its verb-or-item arg
#   (SCI1 param1); None everywhere else. Scopes the item-use recognition to doVerb, so a parameter
#   compared in any other method is never misread as an item. Cleared when following a call.
_DOVERB_PARAM = 1    # `(method (doVerb param1) ...)` -- param1 is Parameter index 1 in the IR
#   (uniformly, across every SCI1/1.1 doVerb: it is the method's single argument, the clicked verb).
_ONEOF = frozenset()   # membership procedures: `f(x, a, b, c)` == "is x one of a,b,c?" -- derived
#   structurally by vocab.derive_oneof, since the proc's number differs per game. Empty on SCO0
#   (LSL2/KQ4 have none), so the recognizer below is inert there.
_MENUS = frozenset()   # transfer sites whose ITEM is picked at run time -- {(frozenset(items),
#   dest)}. `item_transfers` expands a menu to one entry per item, which is the right reading for
#   "where can this come from" and loses the one fact a guard needs: a single statement hands over
#   a single item. See vocab.item_menus / missability.exchange_slots. Empty on LSL2/KQ4/Dagger.


@contextlib.contextmanager
def verb_param_scope(method_name):
    """Set the doVerb verb-param context for the duration of walking `method_name`'s body, so
    `atom` recognizes `(== param1 <item.message>)` as OWN inside a doVerb in ANY walker -- not just
    extract._walk, but the machine lift too. That is what carries an item-use requirement onto a
    cutscene the doVerb ARMS with `setScript:` (the catacombs/dagger class), where the exit is
    machine-owned rather than a flat edge. No-op for any other method, so it never widens capture
    outside a doVerb."""
    global _VERB_PARAM
    saved = _VERB_PARAM
    _VERB_PARAM = _DOVERB_PARAM if method_name == "doVerb" else None
    try:
        yield
    finally:
        _VERB_PARAM = saved


def install_vocabulary(ir):
    """Derive this game's item-location vocabulary AND its ego / current-room globals. Returns the
    vocabulary, or None if the game has no recognisable store -- which is a finding, not something
    to paper over with a default.

    The ego global(s) and the current-room global are derived here too (into `_EGO`/`_CURROOM`),
    from the store wrapper's holder globals and the Game loop respectively, so the extraction reads
    the game's own layout instead of assuming the SCI template's 0/11. Both fall back to the
    template default only when a game has no derivable store or Game loop."""
    global _VOCAB, _IPROPS, _EGO, _CURROOM, _ITEM_MSG, _ONEOF, _MENUS
    _VOCAB = V.Vocabulary.from_ir(ir)
    _IPROPS = (V.item_property_registers(ir, _VOCAB.store_class, _VOCAB.prop, _at_item)
               if _VOCAB else {})
    _ITEM_MSG = V.doverb_item_messages(ir)
    _ONEOF = frozenset(V.derive_oneof(ir))
    _MENUS = frozenset(V.item_menus(ir, _VOCAB, _at_item))
    holders = frozenset().union(*_VOCAB.holders.values()) if _VOCAB and _VOCAB.holders else frozenset()
    _EGO = holders or frozenset({0})
    _CURROOM = current_room_global(ir)
    if _CURROOM is None:
        _CURROOM = 11
    return _VOCAB


def item_transfers(recv, sel, params):
    """`item_transfer`, but one entry per item when the game picks from a fixed menu (a shop
    counter's `(gEgo get: (switch slot (0 48) (1 3) ...))`). Callers that record an effect per
    item iterate this; `item_transfer` keeps the single-item shape for everything else."""
    tr = item_transfer(recv, sel, params)
    if tr is None:
        return ()
    it, dest = tr
    return tuple((i, dest) for i in it) if isinstance(it, tuple) else (tr,)


def item_transfer(recv, sel, params):
    """An inventory-transfer send -> `(item, dest)`, else None. `dest` is EGO or an int
    (a room number, real or pseudo; -1 = nowhere, SCI's own idiom).

    The selector table is DERIVED per game -- see install_vocabulary. What stays here is the one
    structural fact that is not vocabulary: how an item is REFERRED to, `(<inv> at: N)`."""
    if _VOCAB is None:
        return None
    return _VOCAB.transfer(recv, sel, params, _at_item)


def walk_stream(node, pc, on_leaf, on_loop=None, undecided=None):
    """Visit every statement under `node`, carrying the composed path condition.

    The control flow comes from `ir.control_shape`, so this function -- and every walker built on
    it -- learns a new statement form the moment that classifier does. `on_leaf(node, pc)` gets
    each effect/operand node and decides what it means; that part is the caller's and SHOULD
    differ between walkers.

    Loop policy here is "visit everything inside it", which is the permissive reading a streaming
    walker wants. compile makes the other choice on the same shape.
    """
    shape = I.control_shape(node)
    kind = shape[0]
    if kind == "seq":
        for k in shape[1]:
            walk_stream(k, pc, on_leaf)
        return
    if kind == "branch":
        for conds, body in shape[1]:
            ext = []
            for (test, pol) in conds:
                a = atom(test)
                ext.append(a if pol else (GNot(a) if a is not None else None))
            walk_stream(body, pc + ext, on_leaf)
        return
    if kind == "loop":
        # `on_loop` lets a caller note that it is INSIDE a loop and restore afterwards -- the
        # bulk-inventory walk needs that context and nothing else does.
        restore = on_loop(node) if on_loop else None
        lpc = pc + ([undecided] if undecided is not None else [])
        for k in shape[1:]:
            walk_stream(k, lpc, on_leaf, on_loop, undecided)
        if restore is not None:
            restore()
        return
    if node is None:
        return
    on_leaf(node, pc)
    for k in node.get("kids", ()):
        walk_stream(k, pc, on_leaf, on_loop, undecided)


_INIT_SELECTORS = {}        # ir id -> selectors that put an object in the cast


def init_selectors(ir):
    """`species -> selectors that put an instance of it IN THE CAST`, from the game's class table.

    `init` is the one every SCI game spells, but it is not the only one, and a catalogue of
    selector names is what this codebase keeps being punished for (see `vocab.Vocabulary`). KQ6's
    `View` -- the ancestor of every Prop and Actor -- defines a second:

        (method (addToPic)
          (if (global5 contains: self) (|= signal $8021)
          else (|= signal $0020) (self init:)))          ; <-- an init, by another name

    So `(gates cel: 0 signal: 16384 addToPic:)` DOES put the gates in the cast, and reading only
    the literal selector made rm480's `else` branch look like "not in the cast" -- the gates then
    appeared clickable only when you had arrived from rm490, i.e. only once you had already been
    where the gate takes you, which strands the red scarf behind it.

    Scoped by CLASS, not unioned, because the same name means different things on different
    classes: `Cursor::setLoop` and `Talker::say` also `(self init:)`, and treating every `setLoop:`
    as a cast site would make the whole rule vacuous. An object contributes only the aliases its
    own ancestry defines, which is the same "resolve through the class table" discipline
    `vocab.Vocabulary` uses for item moves."""
    key = id(ir)
    if key in _INIT_SELECTORS:
        return _INIT_SELECTORS[key]
    classes = {o.species: o for s in ir.scripts.values() for o in s.objects if o.is_class}
    own = {}
    for sp, o in classes.items():
        names = set()
        for mn, body in o.methods.items():
            for n in I.walk(body):
                if n.get("t") != "Send":
                    continue
                recv, msgs = I.send_pairs(n)
                if (isinstance(recv, dict) and recv.get("t") == "Self"
                        and any(sel == "init" for sel, _p in msgs)):
                    names.add(mn)
                    break
        own[sp] = names
    memo = {}

    def resolve(sp, seen=()):
        if sp in memo:
            return memo[sp]
        o = classes.get(sp)
        if o is None or sp in seen:
            return frozenset({"init"})
        out = frozenset(own.get(sp, ()) | {"init"} | resolve(o.super, seen + (sp,)))
        memo[sp] = out
        return out

    _INIT_SELECTORS[key] = {sp: resolve(sp) for sp in classes}
    return _INIT_SELECTORS[key]


def cast_conditions(script, proc_guard=None, machine_guard=None, init_sels=None):
    """`objname -> [guard|None]`: the conditions under which this script puts an object IN THE CAST.

    An object that is not `init:`ed does not exist for the player -- it cannot be clicked, cued or
    animated -- so anything its methods would have done is gated on whatever gated its `init`. That
    is the same principle `Extractor._inherit_arming` applies to EDGES (`init` is in `ARMING`); this
    is the reusable form of it, so a consumer that is not walking rooms can ask the same question.
    KQ6's rm340 needs it:

        (if (proc913_0 1) (= local2 23) (minoOpening init:) else (= local2 20))

    `minoOpening` is the cave mouth to the minotaur's lair, and its `doVerb` arms `goToLair`. It is
    in the cast ONLY once the minotaur is dead, which is exactly what the room's `doit` says on the
    other route in (`(and (== (gEgo onControl: 1) 512) (proc913_0 1))`). Miss it and the lair has an
    unguarded entrance, so the catacombs can be beaten carrying nothing.

    Both `init` spellings, because Sierra uses them interchangeably in the same method:
      * `(minoOpening init:)`               -- the object is the receiver
      * `(<list> add: a b c eachElementDo: #init)` -- one send, `add:` naming the objects and
        `eachElementDo:` naming the selector. Recognised by the `init` SELECTOR argument, not by
        the list's name, so any collection works.

    Only objects DECLARED in this script are reported: `self`, `super` and the globals a room sends
    `init:` to are not things whose methods we are about to attribute. A `None` in the list means an
    unconditional init -- consumers must treat that as "always in the cast", which is the permissive
    answer and the reason this is inert almost everywhere.

    `proc_guard(name)` supplies the condition a PROCEDURE runs under, since a proc's body has no
    path condition of its own -- it runs because something called it. KQ6 redraws the
    hole-in-the-wall that way: `proc404_1` inits the hole actor, and every one of its three call
    sites is `(if (== (rLab holeCoords:) <this cell>) (proc404_1))`.

    `machine_guard(objname)` is the SAME rule for a `changeState` body, which likewise has no path
    condition of its own -- it runs because the machine was armed and reached that state, so its
    precondition is the machine's ENTRY. Sierra puts an object into the cast from inside a cutscene
    all the time, and read standalone every one of those inits is unconditional, which makes the
    disjunction vacuous and hands the object to the player for free. KQ6's hole-in-the-wall is the
    case, in three rooms with three spellings of the same act:

        (instance putHoleOnWall of Script (method (changeState param1) (switch (= state param1)
           (0 (global0 put: 18 global11) ...)          ; the hole leaves your inventory...
           (2 (theHole init:) ...))))                  ; ...and becomes a thing on the wall

    `putHoleOnWall` is armed from `hiwEastWall::doVerb 25`, i.e. from USING the hole, so `theHole`
    exists only once you have carried the hole in and put it up. Everything hanging off it inherits
    that: looking through it (which is how you learn where the minotaur's lair is) and taking it
    back down (which is why every maze room looked like a place you could pick the hole up).

    Since a machine's entry is itself computed FROM the casts -- an arming inside a conditionally
    init'ed object's method inherits that condition -- the two are mutually recursive and the
    caller must supply the guard from a previous pass. See `MachineBuilder.prime`."""
    # name -> the selectors that put THIS object in the cast, resolved through its own ancestry.
    declared = {o.name: (init_sels or {}).get(o.species if o.is_class else o.super) or {"init"}
                for o in script.objects}
    out = {}

    def leaf(n, pc):
        if n.get("t") != "Send":
            return
        recv, msgs = I.send_pairs(n)
        rname = recv.get("name") if isinstance(recv, dict) else None
        # `(<list> add: a b c eachElementDo: #init)` names the objects in one message and the
        # selector in another, so the selector is collected across the whole send.
        bulk = {p.get("name") for sel, params in msgs if sel == "eachElementDo" for p in params
                if isinstance(p, dict) and p.get("t") == "Selector"}
        for sel, params in msgs:
            if sel in declared.get(rname, ()):
                out.setdefault(rname, []).append(_conj(pc))
            if bulk:
                for p in params:
                    if (isinstance(p, dict) and p.get("t") == "Object"
                            and bulk & set(declared.get(p.get("name"), ()))):
                        out.setdefault(p["name"], []).append(_conj(pc))

    for o in script.objects:
        for mn, body in o.methods.items():
            seed = [machine_guard(o.name)] if (machine_guard and mn == "changeState") else []
            walk_stream(body, seed, leaf)
    for pn, body in script.procs.items():
        walk_stream(body, [proc_guard(pn)] if proc_guard else [], leaf)
    return out


def local_write_conditions(script, cast=None, proc_guard=None, machine_guard=None):
    """`(vtype, index) -> [(value, guard|None)]`: the conditions under which this script sets a LOCAL.

    The same question `cast_conditions` asks about `init:`, asked about a local assignment, and it
    is asked for the same reason: SCI rooms use a local as a "what was the player doing" latch, and
    an entry gated on that latch is not an independent way in -- it is the CONTINUATION of whoever
    set it. `_drop_continuation_entries` already knows that shape for `cue`; this supplies the other
    half, the condition to inherit.

    KQ6's old lamp is the case. `theHuntersLamp::doVerb 5` sets `local1 := 1` and arms `getLamp`;
    walking to the lamp crosses the boiling pond, so `rm520::doit` pre-empts with
    `setScript: bravePond`, and `bravePond`'s last state re-arms `getLamp` iff `local1`. Read
    standalone that second arming is gated on nothing an item model can see, which makes the
    disjunction vacuous and the lamp look freshly obtainable forever -- so trading it to the peddler
    (who then LEAVES) reads as harmless.

    Carries the same two inherited conditions `cast_conditions` does, and for the same reasons: a
    body has no path condition of its own when it is a PROCEDURE (it runs because something called
    it) or a `changeState` (it runs because the machine was armed and got that far). It adds a
    third, which `cast_conditions` gets from its caller instead: an object's method only runs when
    the object is IN THE CAST, so a write inside `theHuntersLamp::doVerb` inherits
    `((gInv at: 19) owner:) == gCurRoomNum` -- the fact that the lamp is still lying there. That is
    the difference between "you can always do this" and "you can do this while it exists", and it
    is the whole point for a one-time pickup.

    Values are reported, not filtered: only the caller knows whether it cares about the set or the
    clear (`getLamp`'s own last state writes `local1 := 0`). A `None` guard means unconditional.

    A write whose VALUE we cannot pin to a literal -- a computed assignment, an increment, a
    decrement -- is reported as value `None` rather than dropped. That is the difference between a
    complete answer and a partial one, and a consumer that strengthens a guard from this needs to
    know which it has: locals start at 0 in SCI, so "the local is non-zero" is exactly the union of
    the writes that made it so, and that identity holds only if every write is accounted for. Drop
    the ones we cannot read and the caller silently over-restricts."""
    out = {}

    def leaf_for(seed_owner):
        def leaf(n, pc):
            t = n.get("t")
            if t in ("Increment", "Decrement"):
                d = (n.get("kids") or [None])[0]
                if isinstance(d, dict) and I.is_local_or_temp(d):
                    out.setdefault((d["vtype"][0], d["index"]), []).append((None, _conj(pc)))
                return
            if t != "Assignment":
                return
            dst, src = (n.get("kids") or [None, None])[:2]
            if not (isinstance(dst, dict) and I.is_local_or_temp(dst)):
                return
            out.setdefault((dst["vtype"][0], dst["index"]), []).append((I.as_int(src), _conj(pc)))
        return leaf

    for o in script.objects:
        owner = cast_guard(cast, o.name) if cast else None
        for mn, body in o.methods.items():
            seed = [owner] if owner is not None else []
            if machine_guard and mn == "changeState":
                seed = seed + [machine_guard(o.name)]
            walk_stream(body, seed, leaf_for(owner))
    for pn, body in script.procs.items():
        walk_stream(body, [proc_guard(pn)] if proc_guard else [], leaf_for(None))
    return out


def any_guard(gs):
    """OR a list of alternative path conditions, or None for "always / we did not find out".

    None both when the list is EMPTY and when any member is unconditional. The second is obvious;
    the first is deliberate and narrow -- a thing we found no site for is a thing we did not learn
    about, not a thing that cannot happen, and strengthening a guard on a non-observation is the
    direction that invents softlocks."""
    gs = list(gs or ())
    if not gs or any(g is None for g in gs):
        return None
    return gs[0] if len(gs) == 1 else GOr(gs)


def cast_guard(conds, name):
    """The condition under which `name` is in the cast, or None for "always / do not know".

    See `any_guard` for why "never init'ed" reads as None: plenty of objects join the cast without
    a send we can see -- the room object itself, and the `Actions` handlers a room hands to the ego
    (`(gEgo actions: egoDoVerb init:)`)."""
    return any_guard(conds.get(name))


def _send_atom(n):
    ip = item_prop_read(n)          # `(if ((Inv at: 15) loop:) {Broken Shovel} ...)`
    if ip is not None:
        return Pred("IPROP", var=ip, op="!=", value=0)
    recv, msgs = I.send_pairs(n)
    for sel, params in msgs:
        if sel == "has" and _is_ego(recv):
            it = I.as_int(params[0]) if params else None
            if it is not None:
                return Pred("OWN", var=it)
        if sel in ("said",):
            return Pred("SAID")
        # `(gInv at: X) ownedBy: <where>` -- "item X is currently AT <where>". The SCI idiom for a
        # one-time pickup, used 77 times in LSL2 and previously lost as an opaque. It matters
        # because destroying an item sets its owner to NOWHERE, so the test can never hold again
        # (barfing into the Airsick_Bag).
        #
        # The two games spell <where> differently, as usual: LSL2 writes `gCurRoomNum` (60 sites),
        # KQ4 writes the room number as a LITERAL (`ownedBy: 78` inside Room78, where the Magic
        # Fruit hangs on the tree). Carry the destination through rather than deciding here --
        # only the caller knows which room it is standing in. See missability._loc_required.
        if sel == "ownedBy":
            it = _at_item(recv)
            if it is not None:
                where = "other"
                if params and I.is_global(params[0], _CURROOM):
                    where = "room"
                elif params and I.as_int(params[0]) is not None:
                    where = I.as_int(params[0])
                return Pred("LOC", var=it, op="ownedBy", value=where)
        # `(gEgo inRect: a b c d)` -> a POSITION guard over the ego's (x,y). Coordinates are
        # in the AST, so this is derivable; ONE consistent (x,y) is what makes "cross east =>
        # inRect" unavoidable: one consistent (x,y) per step, not a fresh choice per guard.
        if sel == "inRect" and _is_ego(recv) and len(params) >= 4:
            cs = [I.as_int(p) for p in params[:4]]
            if all(c is not None for c in cs):
                return ("POS", "rect", tuple(cs))
    # onControl (PIC control-map), distanceTo, posn-relative, other sends -> opaque residue
    return Pred("OPAQUE")


# ---- transition system ---------------------------------------------------
@dataclass
class Edge:
    src: int
    dst: int
    guard: object = None       # guard tree; None = free
    via: str = ""              # object whose method emitted it -- see Extractor._inherit_arming


@dataclass
class Acq:
    item: int
    room: int
    guard: object = None
    via: str = ""              # object whose method emitted it -- the same key `Edge.via` uses.
    #   A `get:` inside a `changeState` body is walked BOTH here (with the body's own path
    #   condition, i.e. nothing) and by the machine lift (which knows what it costs to arm the
    #   cutscene at all). Naming the emitter lets `build_maps` recognise the two as one statement.


@dataclass
class TS:
    rooms: set = field(default_factory=set)
    edges: list = field(default_factory=list)
    acqs: list = field(default_factory=list)
    items: set = field(default_factory=set)
    cs_edges: list = field(default_factory=list)   # changeState newRoom exits (room,dst,
    #   guard). The MACHINE owns these; used as a GATED fallback only where the machine
    #   walk can't deliver the exit (control_exits) -- avoids a false dead-end without
    #   reintroducing a free bypass.
    maze_reach: dict = field(default_factory=dict)  # room -> rooms it can WALK to, for a maze
    #   whose grid we recovered (see Extractor._maze_reach). Its DISPATCHER room is spliced out,
    #   but a machine EXIT to that dispatcher is built downstream, so the map is published here
    #   and `missability.build_maps` applies the same substitution to those.
    dispatchers: set = field(default_factory=set)   # rooms that only compute where you come out
    bulk_moves: list = field(default_factory=list)  # (room, dest, guard) -- a transfer of the
    #   WHOLE inventory at once, written as a walk of the Inv list. No item number appears
    #   anywhere, so this is the one case where "no constant" must mean "all of them".
    item_prop_writes: list = field(default_factory=list)  # (room, item, prop, value, guard);
    #   value is an int or "inc". The FOURTH store -- state living in an item's own property.
    #   Breaking the shovel and spending an arrow are written here, and they mean the same thing
    #   as losing the item: its uses stop accepting it.
    item_menus: set = field(default_factory=set)   # {(frozenset(items), dest)} -- transfer sites
    #   that pick the item at run time (a shop counter's `get: (switch slot (0 48) (3 27) ...)`).
    #   One statement moves ONE item, so a menu is an EXCLUSION as well as four sources; see
    #   vocab.item_menus. Carried on TS rather than re-scanned, because the derivation is
    #   IR-global and its consumers are not (script 287 is never attributed to a room).
    placed: dict = field(default_factory=dict)  # item -> {room, ...}: rooms the item's owner is
    #   WRITTEN to (a `put`/`moveTo` to a room, not to the ego). These are the owner STATE's
    #   transitions to a location: an owner-gate `owner == R` is a real item requirement only when R
    #   is a room the item is PLACED at, versus R being its initial resting spot (the pie is thrown
    #   to room 36 -- `put: 2 36` -- so the yeti's `owner == 36` needs the pie; KQ4's fruit is only
    #   ever at owner 78 because it STARTS on the tree, never `put` there, so it is not a placement).


def _conj(pc):
    pc = [g for g in pc if g is not None]
    if not pc:
        return None
    return pc[0] if len(pc) == 1 else GAnd(list(pc))


_ROOM_SPECIES = {}          # ir id -> species number of the Rm/Room base class


def _room_species(ir):
    """Species of the game's Room base class, found by NAME in the class table.

    Room detection used to be `name == f"rm{script.number}"`, which is a decompiler NAMING
    CONVENTION, not a fact about the game. sci-tools emits `rm47` for LSL2 but `Room63` for KQ4,
    so every KQ4 room failed the test and the extractor saw 4 rooms out of 159 scripts -- silently
    analysing almost nothing. Inheritance is the real signal, and it is what the docstring always
    claimed. The name check stays as a fallback."""
    key = id(ir)
    if key in _ROOM_SPECIES:
        return _ROOM_SPECIES[key]
    species = None
    for s in ir.scripts.values():
        for o in s.objects:
            if o.is_class and o.name in ("Rm", "Room"):
                species = o.species
                break
        if species is not None:
            break
    _ROOM_SPECIES[key] = species
    return species


_ROOM_CLOSURE = {}


def _room_species_closure(ir):
    """Every species that IS or DESCENDS FROM the Room base class, transitively.

    A room declared through an INTERMEDIATE base -- QFG2's `Stage of Rm`, `RasPlaza of Stage`,
    `AlleyRoom of Rm`, with instances `cityRoom of Stage` / `alleyRas of AlleyRoom` -- is still a
    room. The old one-level `super == Rm` check dropped all of them (and QFG2's whole Raseir
    endgame with it). Same transitive-closure shape `derive_death` uses for Game subclasses."""
    key = id(ir)
    if key in _ROOM_CLOSURE:
        return _ROOM_CLOSURE[key]
    base = _room_species(ir)
    closure = {base} if base is not None else set()
    changed = bool(closure)
    while changed:
        changed = False
        for s in ir.scripts.values():
            for o in s.objects:
                if o.is_class and o.super in closure and o.species not in closure:
                    closure.add(o.species)
                    changed = True
    _ROOM_CLOSURE[key] = closure
    return closure


_ROOM_NUMS = {}


def _room_numbers(ir):
    """Script numbers that ARE rooms (have a Room instance). Used to validate the destinations of an
    overland-map `newRoom:[array]`: an array slot is a real exit only if a room script exists for
    that number, which also bounds the table (the first non-zero non-room is past its end)."""
    key = id(ir)
    if key not in _ROOM_NUMS:
        _ROOM_NUMS[key] = {s.number for s in ir.scripts.values()
                           if _room_object(s, ir) is not None}
    return _ROOM_NUMS[key]


def _array_room_values(ir, script_num, node):
    """Resolve `newRoom: [localBase][index]` -- overland-map / PIC-control-map travel, where the
    destination is read from a room table indexed by the clicked control region (Camelot rm1:
    `[local9 local7]` over an 18-slot region->room array). The array values are the script's flat
    locals from the base; the source `[localN size]` grouping is NOT in the IR, so scan from the
    base, take non-zero values that are REAL rooms, and stop at the first non-zero value that is not
    (past the table). Only a LOCAL base is handled; a windowed scan caps any over-read."""
    kids = node.get("kids") or []
    base = kids[0] if kids else None
    if not (base and base.get("t") == "Variable" and base.get("vtype") == "Local"):
        return [None]
    s = ir.scripts.get(script_num)
    if s is None:
        return [None]
    vals = {l["index"]: l["value"] for l in s.locals}
    rooms = _room_numbers(ir)
    out, i = [], base["index"]
    while i in vals and i < base["index"] + 64:
        v = vals[i]
        if v == 0:
            i += 1
        elif v in rooms:
            out.append(v)
            i += 1
        else:
            break                                      # first non-zero non-room = past the table
    return out or [None]


def pending_room_global(ir):
    """The global that IS `newRoom:` at the engine level, or None.

    DISCOVERED, not declared. Every SCI0 Game loop contains the same shape --

        (if (!= <pending> <current>) (self newRoom: <pending>))

    -- so the pending-room global is the one that is (a) compared against another global and
    (b) handed to `newRoom:` inside that comparison's body. Both LSL2 and KQ4 land on global13,
    but by derivation rather than coincidence, and the test does not confuse it with a plain
    room-valued global like LSL2's revolving-door `gRmAfter40`: that one is never compared
    against the current-room global."""
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if n.get("t") != "If":
                        continue
                    ks = n.get("kids") or []
                    test = ks[0] if ks else None
                    if not test or test.get("t") != "Ne":
                        continue
                    tk = test.get("kids") or []
                    if len(tk) < 2 or not (I.is_global(tk[0]) and I.is_global(tk[1])):
                        continue
                    pair = {tk[0]["index"], tk[1]["index"]}
                    for m in I.walk(ks[1] if len(ks) > 1 else None):
                        if m.get("t") != "Send":
                            continue
                        _recv, msgs = I.send_pairs(m)
                        for sel, params in msgs:
                            if (sel == "newRoom" and params and I.is_global(params[0])
                                    and params[0]["index"] in pair):
                                return params[0]["index"]
    return None


def current_room_global(ir):
    """The global that holds the CURRENT room number, or None.

    DISCOVERED from the Game loop's `(if (!= pending current) (self newRoom: pending))` shape: the
    current-room global is the member of that comparison that is NOT the one handed to `newRoom:`
    (that one is the pending-room global). Both LSL2 and KQ4 derive global11. This is what the
    scripts compare room numbers against (`(== gCurRoomNum N)`, `ownedBy: gCurRoomNum`)."""
    pending = pending_room_global(ir)
    if pending is None:
        return None
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if n.get("t") != "If":
                        continue
                    ks = n.get("kids") or []
                    test = ks[0] if ks else None
                    if not test or test.get("t") != "Ne":
                        continue
                    tk = test.get("kids") or []
                    if len(tk) < 2 or not (I.is_global(tk[0]) and I.is_global(tk[1])):
                        continue
                    pair = {tk[0]["index"], tk[1]["index"]}
                    if pending not in pair:
                        continue
                    for m in I.walk(ks[1] if len(ks) > 1 else None):
                        if m.get("t") != "Send":
                            continue
                        _recv, msgs = I.send_pairs(m)
                        for sel, params in msgs:
                            if (sel == "newRoom" and params and I.is_global(params[0])
                                    and params[0]["index"] in pair):
                                return (pair - {pending}).pop()
    return None


def prev_room_global(ir):
    """The global that holds the PREVIOUS room, or None.

    DISCOVERED from the same Game-loop shape as `pending_room_global`. The loop saves the current
    room before switching, in the ROOM-SWITCH METHOD and nowhere else:

        (method (newRoom param1 ...)
            ...
            (= <previous> <current>)        ; save where we were
            (= <current>  param1)           ; and go
            (= <pending>  param1))

    so the method is identified by its `<current> := <parameter>` write, and the previous-room
    global is what `<current>` was copied to inside it. `<current>` is `current_room_global`.
    LSL2, KQ4, KQ5 and KQ6 all land on global12 (current global11, pending global13).

    The method restriction is the whole derivation. Without it any `(= X <current>)` anywhere in
    the game matches, and a game that saves the current room for its OWN purposes wins on script
    order: KQ5's `boatRegion` does `(= global361 global11)` to remember which shore you sailed
    from, and prev_room_global returned 361 -- so KQ5's 53 prevRoom-guarded edges measured as 4,
    and "prevRoom is a minor idiom" was concluded from the wrong register.

    It is what a virtual-map room reads to seed its entry cell, so `grid.analyze` gates a grid
    exit on it -- "you can only reach the island if you arrived from the whale" -- and what
    `missability.edge_meta` writes on every edge, since this assignment runs on every transition."""
    current = current_room_global(ir)
    if current is None:
        return None
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                if not _switches_room(body, current):
                    continue
                for n in I.walk(body):
                    if n.get("t") != "Assignment":
                        continue
                    ks = n.get("kids") or []
                    if (len(ks) >= 2 and I.is_global(ks[0]) and I.is_global(ks[1])
                            and ks[1]["index"] == current and ks[0]["index"] != current):
                        return ks[0]["index"]
    return None


def _switches_room(body, current):
    """Is this the Game loop's room-switch method -- does it assign `<current> := <parameter>`?"""
    for n in I.walk(body):
        if n.get("t") != "Assignment":
            continue
        ks = n.get("kids") or []
        if (len(ks) >= 2 and I.is_global(ks[0]) and ks[0]["index"] == current
                and ks[1].get("t") == "Variable" and ks[1].get("vtype") == "Parameter"):
            return True
    return False


def _walks_a_list(loop):
    """Does this Loop iterate a linked list -- `(for ((= v (L first:))) v ((= v (L next: v))))`?

    That control shape is what makes an `owner:` write inside the body a BULK transfer rather than
    a single item's: there is no item number anywhere in

        (for ((= local6 (global9 first:))) local6 ((= local6 (global9 next: local6)))
          (if (and (= local5 (NodeValue local6)) (== (local5 owner:) gEgo))
              (local5 owner: 89)))                            ; KQ4 Room92 -- Lolotte's guards
                                                              ; take EVERYTHING you are carrying
    Only the init and increment are inspected, never the body, so a body that happens to send
    `next:` to something cannot make itself bulk."""
    kids = loop.get("kids") or []
    for k in kids[:3]:                          # init, test, increment -- NOT the body
        for n in I.walk(k):
            if n.get("t") != "Send":
                continue
            _recv, msgs = I.send_pairs(n)
            if any(sel in ("first", "next") for sel, _p in msgs):
                return True
    return False


def _room_object(script, ir=None):
    """The Room instance of a room script: an instance of the Rm/Room class, else named rm<N>."""
    if ir is not None:
        closure = _room_species_closure(ir)
        if closure:
            for o in script.objects:
                if not o.is_class and o.super in closure:
                    return o
    want = f"rm{script.number}"
    for o in script.objects:
        if o.name == want and not o.is_class:
            return o
    return None


class Extractor:
    def __init__(self, ir):
        self.ir = ir
        self.ts = TS()
        self._cur_obj = ""                  # object whose method is being walked
        self._armed = {}                    # room -> {object name: [guard, ...]}
        self._pending = pending_room_global(ir)
        self._list_loop = False             # inside a `for` that walks a linked list
        self._nowalk = None                 # rooms with the walk icon off -- see _no_walk_rooms
        self.procs_by = {}
        for rn, s in ir.scripts.items():
            for name, body in s.procs.items():
                self.procs_by[(rn, name)] = body

    def region_members(self):
        """region-script -> the rooms that activate it, from `(self setRegions: R)` in a room.

        The same map `opmodel` builds. It lives in both because both walk: opmodel picks up a
        region's HANDLER effects, and this walker picks up its edges, acquisitions and item
        properties -- and until now this half simply did not run, so `regUnicorn`'s arrow spend
        was invisible and `resource_exhaustion` reported the bow's direction backwards."""
        out = {}
        for rn, s in self.ir.scripts.items():
            room = _room_object(s, self.ir)
            if room is None:
                continue
            for _mn, a in room.methods.items():
                for n in I.walk(a):
                    if n.get("t") != "Send":
                        continue
                    recv, msgs = I.send_pairs(n)
                    for sel, params in msgs:
                        if sel == "setRegions":
                            for p in params:
                                v = I.as_int(p)
                                if v is not None:
                                    out.setdefault(v, set()).add(rn)
        return out

    def _object_mentions(self, sc):
        """`object name -> the sibling objects its methods name`, from `{"t": "Object"}` nodes.

        This is how one object in a script hands control to another without going through the
        export table: `(= next untieSelfAndStand)`, `(genie setScript: 0)`. Needed because
        `ScriptID` names ONE export but SCI loads the whole script, so the rest of it runs only if
        something inside reaches it."""
        names = {o.name for o in sc.objects}
        out = {}
        for o in sc.objects:
            hit = set()
            for b in o.methods.values():
                for n in I.walk(b):
                    if isinstance(n, dict) and n.get("t") == "Object":
                        nm = n.get("name")
                        if nm in names and nm != o.name:
                            hit.add(nm)
            out[o.name] = hit
        return out

    def _scriptid_scope(self, sc, rows, present):
        """`{object name -> guard}` for the objects of a ScriptID-loaded script that can RUN here.

        Two oracles, deliberately separate, because they fail in opposite directions:

          * `present` -- every export of this script NAMED from this room, from a plain `I.walk`.
            This decides which objects EXIST in the scope, and it must not miss one.
          * `rows` -- `[(export's object or None, that site's guard)]` from `walk_stream`, which
            carries path conditions but does not reach every branch (KQ4's `Main.handleEvent` has
            two `(ScriptID 306 N)` sites and the stream sees only one). This decides CONDITIONS.

        An export in `present` with no row of its own gets the script-wide disjunction -- the
        condition under which the script is loaded here at all -- rather than being dropped or
        being made free. Dropping it would have lost KQ4's `readBook`; making it free would have
        unlocked script 801, the debug menu that hands out every item.

        Then two facts about the mechanism:

          * `ScriptID(N, M)` returns export M, so a site's condition belongs to THAT object, not to
            everything in script N. A site whose export cannot be resolved (a code export, a
            non-literal index, an IR with no export table) falls back to seeding every object --
            the old behaviour, and the permissive direction.
          * SCI loads the script WHOLE, so anything a seeded object mentions can run too, under the
            same condition; propagate to a fixpoint. A script-level PROCEDURE is not walked here,
            but what it mentions is seeded with the script-wide disjunction, because we cannot see
            whether the proc is called.

        Conditions from several sites are OR'd -- a script reached two ways runs if EITHER way was
        taken. Keeping one arbitrary site's condition (what `seen` used to do) is not an
        approximation in either direction: on KQ6 it kept, for script 755 in room 750, the `else`
        branch that arms `noDagger` -- `NOT (dagger owned by 870)` -- and applied it to
        `cassimaHasDagger`, whose state 40 is `newRoom: 180`, the only edge into the winning
        ending. The model then believed you win exactly when Cassima does NOT have the dagger.

        An object that no export names and no sibling mentions is left OUT: for a script that is
        neither a room nor a region there is no other way in. KQ6's `startEndingCartoon` is one --
        a leftover instance nothing in the game references, which used to contribute a phantom
        rm750 -> rm740 edge."""
        FREE = None                       # a condition of None means "unconditional"
        conds = {}                        # name -> None (free) | {repr: guard}
        def as_cond(g):
            return FREE if g is None else {repr(g): g}
        def add(name, c):
            if name not in conds:
                conds[name] = c
                return True
            old = conds[name]
            if old is FREE:
                return False              # already the weakest
            if c is FREE:
                conds[name] = FREE
                return True
            merged = dict(old)
            merged.update(c)
            if len(merged) != len(old):
                conds[name] = merged
                return True
            return False

        script_cond = FREE if not rows else {}
        for _name, g in rows:
            script_cond = FREE if (script_cond is FREE or g is None) else \
                {**script_cond, **as_cond(g)}
        attributed = set()
        for name, g in rows:
            if name is None:              # unresolvable export -- seed the whole script
                for o in sc.objects:
                    add(o.name, as_cond(g))
            elif name in sc.by_name:
                add(name, as_cond(g))
                attributed.add(name)
        for name in present:              # seen by I.walk; may have no condition of its own
            if name is None:
                for o in sc.objects:
                    add(o.name, script_cond)
            elif name in sc.by_name and name not in attributed:
                add(name, script_cond)
        if not conds:
            return {}
        mentions = self._object_mentions(sc)
        # A procedure's body is not walked in this scope, but naming an object there still means
        # the object can be entered once the script is loaded.
        names = set(mentions)
        for b in sc.procs.values():
            for n in I.walk(b):
                if isinstance(n, dict) and n.get("t") == "Object" and n.get("name") in names:
                    add(n["name"], script_cond)
        changed = True
        while changed:
            changed = False
            for p, qs in mentions.items():
                if p not in conds:
                    continue
                for q in qs:
                    if add(q, conds[p]):
                        changed = True
        out = {}
        for name, c in conds.items():
            if c is FREE:
                out[name] = None
            else:
                gs = list(c.values())
                out[name] = gs[0] if len(gs) == 1 else GOr(gs)
        return out

    def scriptid_refs(self):
        """`(target script, room, {object name -> guard})` for every `(ScriptID N M)` -- SCI's
        dynamic script load.

        A fourth scope, after Main / region / room. `Main.sc:1116` answers `Said 'launch'` ANYWHERE
        with `(gEgo setScript: (ScriptID 305 0))`, and script 305 (`shootBow`) is where the arrow is
        actually spent -- so firing into the air costs an arrow and we could not see it. Two deaths
        hide the same way: `timeOut` (the 24-hour deadline) and `openPbox` both write the game-over
        global from scripts that are neither rooms nor regions.

        The reference's PATH CONDITION comes with it, which is what keeps `DebugMenu` (script 801,
        loaded from Main under a debug gate) from handing the player every item. Which OBJECT it
        applies to, and what happens when a script is referenced more than once, is `_scriptid_scope`.

        Measured over the surviving references (`run` skips Main, rooms and regions): LSL2 has ZERO
        `ScriptID` call sites; KQ4 has 8, no two of which disagree and none of which name a second
        export, so neither game can move. KQ6 has 785 sites over 142 (script, room) pairs, 56 of
        them disagreeing on condition and 54 naming more than one export."""
        sites = collections.defaultdict(list)      # (tgt, room) -> [(object name | None, guard)]
        present = collections.defaultdict(set)     # (tgt, room) -> {object name | None}
        for rn, sc in self.ir.scripts.items():
            if _room_object(sc, self.ir):
                rooms = [rn]
            elif rn == 0:
                rooms = [0]            # Main is a SCOPE; consumers widen room 0 to everywhere
            else:
                continue
            bodies = list(sc.procs.values()) + [b for o in sc.objects for b in o.methods.values()]
            for b in bodies:
                def leaf(n, pc, _rooms=rooms):
                    if n.get("t") != "KernelCall" or n.get("name") != "ScriptID":
                        return
                    ks = n.get("kids") or []
                    tgt = I.as_int(ks[0]) if ks else None
                    if tgt is None:
                        return
                    hit = self.ir.script_id_target(n)
                    for room in _rooms:
                        sites[(tgt, room)].append((hit[1] if hit else None, _conj(list(pc))))
                walk_stream(b, [], leaf)
                # EXISTENCE, separately: walk_stream does not reach every branch, and under the
                # export-aware scope a reference it misses is an object we would never walk.
                for n in I.walk(b):
                    if not (isinstance(n, dict) and n.get("t") == "KernelCall"
                            and n.get("name") == "ScriptID"):
                        continue
                    ks = n.get("kids") or []
                    tgt = I.as_int(ks[0]) if ks else None
                    if tgt is None:
                        continue
                    hit = self.ir.script_id_target(n)
                    for room in rooms:
                        present[(tgt, room)].add(hit[1] if hit else None)
        out = []
        for (tgt, room), rows in sites.items():    # first-touch order, as the old `seen` had
            sc = self.ir.scripts.get(tgt)
            if sc is not None:
                out.append((tgt, room, self._scriptid_scope(sc, rows, present[(tgt, room)])))
        return out

    def run(self):
        self.ts.item_menus = set(_MENUS)      # derived per game in install_vocabulary
        # room universe: any script that has an rm<N> Room instance
        room_scripts = {n: s for n, s in self.ir.scripts.items() if _room_object(s, self.ir)}
        for n in room_scripts:
            self.ts.rooms.add(n)
        # A region's scripts run in the rooms that activate it -- SCI's middle dispatch scope.
        # Walked with the DECLARING room as context, so an acquisition or a property write inside
        # a region is attributed where the player actually is.
        regions = self.region_members()
        for rgn, members in sorted(regions.items()):
            rs = self.ir.scripts.get(rgn)
            if rs is None or rgn in room_scripts:
                continue
            for room in sorted(members):
                for o in rs.objects:
                    self._cur_obj = o.name
                    for mname, meth_ast in o.methods.items():
                        self._walk(room, meth_ast, [], rgn, set(),
                                   movement=(mname != "changeState"),
                                   verb_param=(_DOVERB_PARAM if mname == "doVerb" else None))
                self._cur_obj = ""
        # SCRIPTS LOADED BY `ScriptID` -- see scriptid_refs. Walked with the referencing site's
        # path condition, in the scope that loaded them.
        for tgt, room, conds in self.scriptid_refs():
            ts_ = self.ir.scripts.get(tgt)
            # `(ScriptID 0 N)` is how a room reaches MAIN's public procedures -- Main is already
            # its own scope, and walking it into every referencing room attributed its debug
            # cheat block to 25 rooms.
            if ts_ is None or tgt == 0 or tgt in room_scripts or tgt in regions:
                continue
            for o in ts_.objects:
                if o.name not in conds:      # no export named it and no sibling reaches it
                    continue
                g = conds[o.name]
                self._cur_obj = o.name
                for mname, meth_ast in o.methods.items():
                    self._walk(room, meth_ast, [] if g is None else [g], tgt, set(),
                               movement=(mname != "changeState"),
                               verb_param=(_DOVERB_PARAM if mname == "doVerb" else None))
            self._cur_obj = ""
        for n, s in room_scripts.items():
            self._nav_edges(n, s)
            for o in s.objects:
                self._cur_obj = o.name
                for mname, meth_ast in o.methods.items():
                    # changeState newRoom exits belong to the MACHINE (gated); don't
                    # duplicate them as free flat edges. Items still captured. Procedures
                    # are FOLLOWED in-context (below), not walked standalone -- a proc
                    # walked context-free would emit its newRoom as a free bypass.
                    self._walk(n, meth_ast, [], n, set(), movement=(mname != "changeState"),
                               verb_param=(_DOVERB_PARAM if mname == "doVerb" else None))
            self._cur_obj = ""
            self._inherit_arming(n)
        self._nav_hubs()
        # add any newRoom target we saw as a room
        for e in self.ts.edges:
            self.ts.rooms.add(e.dst)
        # AFTER the rooms are known: _coord_tables asks whether the player can be in the
        # dispatcher room, which is only answerable once newRoom targets have been folded in.
        self._coord_tables()
        for e in self.ts.edges:
            self.ts.rooms.add(e.dst)
        return self.ts

    def _nav_hubs(self):
        """Destination-TABLE travel: `newRoom: (<var> <sel>:)` where <sel> is a room-valued property
        on a small set of dedicated objects -- KQ6's magic map does `(global2 newRoom: (local8
        tpRoom:))`, local8 being the map location the player picked and `tpRoom` each island's
        arrival room (crown 200, sacred 300, wonder 450, beast 500, mists 550). The item lets you
        travel between those rooms, so they form a HUB; dropping the read (the destination is not a
        literal) severed every island from the others, collapsing reachability. Modelled as a clique
        among the table's rooms -- the analogue of the Camelot `newRoom:[array]` overland hub, for a
        property table instead of a local array.

        Guarded so it is inert unless the pattern exists: the receiver must be a VARIABLE (a runtime
        choice, not a fixed object), `<sel>` is NOT a per-room direction (n/s/e/w -- those are
        walk-off edges handled by _nav_edges, and every room carries them), and the table must be
        small (<=16 rooms), i.e. a menu and not a pervasive attribute. LSL2/KQ4 have no such site
        (their newRooms are literal/global/array), so nothing is added and they stay byte-identical."""
        rooms = _room_numbers(self.ir)
        table_sels = set()
        for s in self.ir.scripts.values():
            for o in s.objects:
                for body in o.methods.values():
                    for n in I.walk(body):
                        if n.get("t") != "Send":
                            continue
                        _r, msgs = I.send_pairs(n)
                        for sel, params in msgs:
                            if sel != "newRoom" or not params:
                                continue
                            a = params[0]
                            if not (isinstance(a, dict) and a.get("t") == "Send"):
                                continue
                            arecv, amsgs = I.send_pairs(a)
                            if (len(amsgs) == 1 and not amsgs[0][1] and amsgs[0][0]
                                    and amsgs[0][0] not in NAV_SELECTORS
                                    and isinstance(arecv, dict) and arecv.get("t") == "Variable"):
                                table_sels.add(amsgs[0][0])
        for sel in table_sels:
            dests = sorted({o.props.get(sel) for s in self.ir.scripts.values()
                            for o in s.objects if not o.is_class and o.props.get(sel) in rooms})
            if not (2 <= len(dests) <= 16):        # a menu, not a per-room attribute or a singleton
                continue
            for a in dests:
                for b in dests:
                    if a != b:
                        self.ts.edges.append(Edge(a, b))    # hub: item-travel between destinations

    def _coord_tables(self):
        """SIGN-TAGGED destination tables: a room that computes where you go, and marks a real
        room by NEGATING it.

        A coordinate maze does not navigate by room number. KQ6's catacombs keep a grid coordinate
        and derive the destination from it:

            (method (newRoom param1)
                (if (< (= param1 (self calcRoom: labCoords prevEdgeHit)) 0)
                    (super newRoom: (- param1))          ; negative  => a REAL room
                else
                    (self initPseudoRoom: param1 ...)))  ; positive  => same room, redrawn

        and `calcRoom` reads the destination out of a script-local table interleaving rooms with
        the coordinates that reach them. The argument is data-dependent, so the edge is dropped and
        the maze interior is unreachable -- 10 rooms in KQ6, the ones the catacombs softlock lives
        among.

        The SIGN is the game's own tag for "this is a room", and it is load-bearing rather than
        cosmetic: the same table holds coordinate 180, and 180 is also a real room number, so
        reading the table by absolute value invents an edge into the castle. We therefore take only
        NEGATIVE entries, and only in a script that demonstrably uses the convention -- it must
        contain a `newRoom:` whose argument is a NEGATION. That evidence is what keeps this inert
        everywhere else: LSL2 and KQ4 have no negated newRoom at all.

        The result is an over-approximation of the maze -- every table room becomes reachable from
        the dispatcher -- which is the honest direction for a grid the player may walk freely; the
        exact reachable set needs the wall lists (see `labCoords` in the gap census)."""
        rooms = _room_numbers(self.ir)
        for s in self.ir.scripts.values():
            # The dispatcher need not DEFINE a room object: KQ6's script 400 holds the `LBRoom`
            # CLASS its maze rooms inherit, and is itself entered by `newRoom: 400` from them. So
            # the test is "can the player be in this room", i.e. the room graph reached it -- not
            # "does this script declare a room instance", which would drop exactly this case.
            if s.number not in self.ts.rooms:
                continue
            negated = False
            for o in s.objects:
                for body in o.methods.values():
                    for n in I.walk(body):
                        if n.get("t") != "Send":
                            continue
                        _r, msgs = I.send_pairs(n)
                        for sel, params in msgs:
                            if (sel == "newRoom" and params and isinstance(params[0], dict)
                                    and params[0].get("t") == "Neg"):
                                negated = True
            if not negated:
                continue
            dests = set()
            for l in s.locals:
                v = l["value"]
                v = v - 65536 if isinstance(v, int) and v > 32767 else v   # locals are uint16
                if isinstance(v, int) and v < 0 and -v in rooms and -v != s.number:
                    dests.add(-v)
            if len(dests) < 2:                 # a lone negative is a sentinel, not a table
                continue
            cell = {}                          # room -> the grid coordinates it occupies
            locs = sorted(s.locals, key=lambda l: l["index"])
            for a, b in zip(locs, locs[1:]):
                v = a["value"]
                v = v - 65536 if v > 32767 else v
                if v < 0 and -v in dests:
                    cell.setdefault(-v, {b["value"]})
            for r, cs in self._listed_pseudo_rooms(s, rooms).items():
                cell.setdefault(r, set()).update(cs)
                dests.add(r)
            reach = self._maze_reach(s, cell)
            if reach:
                self._splice_dispatcher(s.number, reach, dests)
            else:
                for d in sorted(dests):        # no grid recovered: dispatcher reaches them all
                    self.ts.edges.append(Edge(s.number, d))
                    self.ts.rooms.add(d)

    def _listed_pseudo_rooms(self, script, rooms):
        """`room -> {coords}` for a pseudo-room named for a SET of cells rather than one.

        The (room, coordinate) table pairs each room with a single cell, but a maze can also send a
        whole LIST of coordinates to one room. KQ6's dispatcher does it right after the table walk:

            (if (proc999_5 temp1 65 103 112 130 165 183 230) (return -411))

        Same negative-means-a-room convention, same membership-test idiom the door lists use, so
        nothing new is being recognised -- but rm411 is SEVEN cells, and without them it is a room
        with no coordinate at all. `_splice_dispatcher` then falls back to "reaches every room in
        the table", which is how the maze acquired a free edge into the minotaur's lair."""
        out = {}
        for o in script.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if not (isinstance(n, dict) and n.get("t") in ("PublicCall", "LocalCall")
                            and n.get("name") in _ONEOF):
                        continue
                    vals = [I.as_int(k) for k in (n.get("kids") or [])[1:]]
                    if len(vals) < 2 or any(v is None for v in vals):
                        continue
                    for r in I.walk(body):        # the room this membership test RETURNS
                        if not (isinstance(r, dict) and r.get("t") == "Return" and r.get("kids")):
                            continue
                        v = I.as_int(r["kids"][0])
                        if v is not None and v < 0 and -v in rooms and -v != script.number:
                            out.setdefault(-v, set()).update(vals)
        return out

    def _maze_reach(self, script, cell):
        """room -> the rooms it can WALK to, from the maze's own wall data. `{}` if not recovered.

        The table alone says which rooms exist, not which are mutually reachable, and assuming a
        freely-walkable grid is WRONG: KQ6's catacombs are two levels joined by a one-way drop, so
        a room-to-every-room model asserts you can climb back and would hide any item you must
        carry down. The adjacency is real data -- the room paints a door per direction, each
        guarded by a membership test listing the cells open that way.

        The direction each list means is DERIVED, not read off door names: a door is shared by the
        two cells it joins, so the true pairing is the one under which the relation is symmetric
        (`c open toward +d` iff `c+d` open toward -d). Searching pairs and offsets for the highest
        agreement recovers KQ6's at 0.985 with no name anywhere -- and the grid WIDTH falls out as
        the winning offset rather than being assumed. Only 2 of its 146 edges are asymmetric, which
        is the whole point: symmetrise them and the one-way vanishes, so the walk stays DIRECTED."""
        cand = []
        for o in script.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if n.get("t") == "Not" and n.get("kids"):
                        n = n["kids"][0]
                    if not (isinstance(n, dict) and n.get("t") in ("PublicCall", "LocalCall")
                            and n.get("name") in _ONEOF):
                        continue
                    ks = n.get("kids") or []
                    vals = [I.as_int(k) for k in ks[1:]]
                    if len(vals) >= 8 and all(v is not None for v in vals):
                        cand.append(frozenset(vals))
        cand = list(dict.fromkeys(cand))
        if len(cand) < 4:
            return {}

        def agree(a, b, d):
            return sum(1 for c in a if c + d in b) / len(a) if a else 0.0

        best = {}                              # |offset| -> (score, listA, listB, offset)
        for a in cand:
            for b in cand:
                if a is b:
                    continue
                for d in (1, -1, 16, -16, 8, -8, 32, -32):
                    sc = (agree(a, b, d) + agree(b, a, -d)) / 2
                    key = abs(d)
                    if sc > best.get(key, (0,))[0]:
                        best[key] = (sc, a, b, d)
        pairs = sorted((v for v in best.values() if v[0] >= 0.9), key=lambda v: -v[0])
        # two axes, and their offsets must differ in magnitude (a row step and a column step)
        axes = []
        for p in pairs:
            if all(abs(p[3]) != abs(q[3]) for q in axes):
                axes.append(p)
        if len(axes) < 2:
            return {}
        adj = collections.defaultdict(set)
        for (_sc, a, b, d) in axes:
            for c in a:
                adj[c].add(c + d)
            for c in b:
                adj[c].add(c - d)
        for r, cs in cell.items():                # a named room speaks for its own cells
            for delta in self._repurposed_dirs(script, r):
                for c in cs:
                    adj[c].discard(c + delta)
        room_at = {c: r for r, cs in cell.items() for c in cs}
        out = {}
        for r, cs in cell.items():
            seen, q = set(cs), list(cs)
            while q:
                u = q.pop()
                for v in adj.get(u, ()):
                    if v not in seen:
                        seen.add(v)
                        q.append(v)
            out[r] = {room_at[x] for x in seen if x in room_at} - {r}
        return out

    def _dir_table(self, script):
        """`(key, {direction code: coordinate delta})` -- the maze's own direction table.

        A coordinate maze has to turn "which way did you leave" into a step, and it does it in one
        switch, so both the register and every offset are READ rather than assumed:

            (switch ((ScriptID 30 0) prevEdgeHit:)          ; KQ6 LBRoom::init
                (1 (-= temp0 16)) (3 (+= temp0 16)) (2 (++ temp0)) (4 (-- temp0)))

        Recognised by shape: a switch whose every case adjusts one variable by a constant. The
        direction register has TWO spellings by the time anyone asks -- the property above, and the
        synthetic GLOBAL `lower_obj_props` rewrites it to, since it is exactly the kind of
        written-and-read object property we model as state. `key` says which was found:
        `("sel", name)` or `("glob", index)`. `(None, {})` if the script has no such switch."""
        best = (None, {})
        for o in script.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if not (isinstance(n, dict) and n.get("t") == "Switch" and n.get("kids")):
                        continue
                    head, sel = n["kids"][0], None
                    if isinstance(head, dict) and head.get("t") == "Variable" \
                            and head.get("vtype") == "Global":
                        sel = ("glob", head["index"])
                    else:
                        for h in I.walk(head):
                            if isinstance(h, dict) and h.get("t") == "Selector" and h.get("name"):
                                sel = ("sel", h["name"])
                    if not sel:
                        continue
                    tbl = {}
                    for c in n["kids"][1:]:
                        if not (isinstance(c, dict) and c.get("t") == "Case"):
                            continue
                        k = I.as_int(c["kids"][0])
                        for x in I.walk(c["kids"][1]):
                            if not isinstance(x, dict):
                                continue
                            t, ks = x.get("t"), x.get("kids") or []
                            step = {"Increment": 1, "Decrement": -1}.get(t)
                            if step is None and t in ("AssignmentAdd", "AssignmentSub") and len(ks) > 1:
                                v = I.as_int(ks[1])
                                step = None if v is None else (v if t == "AssignmentAdd" else -v)
                            if step is not None and k is not None:
                                tbl[k] = step
                    if len(tbl) > len(best[1]):
                        best = (sel, tbl)
        return best

    def _repurposed_dirs(self, disp_script, room):
        """Coordinate deltas a NAMED maze room takes back for an exit of its OWN.

        The generic door table is the DISPATCHER's, and it is right about the cells the dispatcher
        draws. A cell that is a real room is drawn by that room's script instead, and a room may
        use a screen edge for something else entirely. KQ6's rm405 is the catacombs entrance:

            (method (init) ... (proc402_2)          ; its own layout, not the table's for cell 117
               ((ScriptID 30 7) addToPic:)          ; topDoor  -> north
               ((ScriptID 30 5) addToPic:))         ; leftDoor -> west ... and no south opening
            (method (doit) (cond ((global2 script:))
               ((== (global0 edgeHit:) 3)           ; the SOUTH edge...
                  ((ScriptID 30 0) prevEdgeHit: 3)
                  (global2 setScript: walkOut))))   ; ...LEAVES the catacombs: newRoom 340

        The table says cell 117's south is open, so we emitted a descent into the LOWER level that
        the game does not have -- and with it a way to reach the minotaur's lair while skipping both
        rooms the player must survive to get there. Deleting it, the trapdoor becomes the only way
        down and the crushing-ceiling room becomes unavoidable, which is what the game does.

        Narrow, because removing movement is the unsafe direction: the direction is dropped only
        when EVERY room the claiming branch can leave to is some other room. A branch that can still
        reach the dispatcher is a maze move and is left alone -- KQ6's rm409 walks out either to the
        dispatcher or through the secret door to the lair, and it keeps both."""
        s = self.ir.scripts.get(room)
        obj = _room_object(s, self.ir) if s else None
        if obj is None or "doit" not in obj.methods:
            return set()
        sel, tbl = self._dir_table(disp_script)
        if not sel or not tbl:
            return set()
        out = set()
        arms = []                    # every branch arm anywhere in `doit` -- the exit cond is
        #   typically wrapped in a seq alongside `(super doit:)`, so the top level is not a branch

        def collect(node):
            if not isinstance(node, dict):
                return                   # an `if` with no else arm hands us a None body
            sh = I.control_shape(node)
            if sh[0] == "branch":
                for _c, body in sh[1]:
                    arms.append(body)
                    collect(body)
                return
            for k in (sh[1] if sh[0] == "seq" else
                      (sh[1:] if sh[0] == "loop" else (node.get("kids", ()) or ()))):
                if isinstance(k, dict):
                    collect(k)

        collect(obj.methods["doit"])
        for body in arms:
            d, dests = None, set()
            for n in I.walk(body):
                if not isinstance(n, dict):
                    continue
                if (sel[0] == "glob" and n.get("t") == "Assignment"
                        and len(n.get("kids") or []) > 1):
                    lhs = n["kids"][0]
                    if (isinstance(lhs, dict) and lhs.get("t") == "Variable"
                            and lhs.get("vtype") == "Global" and lhs.get("index") == sel[1]
                            and I.as_int(n["kids"][1]) is not None):
                        d = I.as_int(n["kids"][1])
                if n.get("t") != "Send":
                    continue
                _r, msgs = I.send_pairs(n)
                for msel, params in msgs:
                    if sel[0] == "sel" and msel == sel[1] and params \
                            and I.as_int(params[0]) is not None:
                        d = I.as_int(params[0])
                    if msel == "setScript" and params:
                        dests |= self._script_newrooms(s, params[0])
                    if msel == "newRoom" and params and I.as_int(params[0]) is not None:
                        dests.add(I.as_int(params[0]))
            if d in tbl and dests and disp_script.number not in dests:
                out.add(tbl[d])
        return out

    def _script_newrooms(self, script, ref):
        """Every literal `newRoom:` destination the Script named by `ref` can reach."""
        tgt = self.ir.script_id_target(ref) if isinstance(ref, dict) else None
        name = tgt[1] if tgt else (ref.get("name") if isinstance(ref, dict) else None)
        holder = self.ir.scripts.get(tgt[0]) if tgt and tgt[0] is not None else script
        obj = next((o for o in holder.objects if o.name == name), None) if holder else None
        if obj is None:
            return set()
        out = set()
        for body in obj.methods.values():
            for n in I.walk(body):
                if not (isinstance(n, dict) and n.get("t") == "Send"):
                    continue
                _r, msgs = I.send_pairs(n)
                for msel, params in msgs:
                    if msel == "newRoom" and params and I.as_int(params[0]) is not None:
                        out.add(I.as_int(params[0]))
        return out

    def _splice_dispatcher(self, disp, reach, dests):
        """Replace `room -> dispatcher -> computed` with the direct walks the grid allows.

        The dispatcher is not somewhere the player stays -- it is the code that works out where
        they came out. Left in the graph it is a hub every maze room enters and leaves, which
        reconnects the levels the grid separates. So route each of its in-edges to that room's own
        reachable set and drop the dispatcher itself. A room with no cell (the pit, reached by
        falling rather than walking) keeps the permissive union: we do not know where it puts you."""
        srcs = {e.src for e in self.ts.edges + self.ts.cs_edges if e.dst == disp}
        kept = [e for e in self.ts.edges if e.src != disp and e.dst != disp]
        for r in sorted(srcs):
            for d in sorted(reach.get(r, set(dests) - {r})):
                kept.append(Edge(r, d))
        self.ts.edges[:] = kept
        self.ts.cs_edges[:] = [e for e in self.ts.cs_edges
                               if e.src != disp and e.dst != disp]
        self.ts.rooms.discard(disp)
        self.ts.dispatchers.add(disp)
        self.ts.maze_reach.update(reach)

    # selectors that make an object animate/move/run, i.e. that end in a `cue` back to it
    # `init` is the most fundamental arming of the lot: an object the room never inits is not in
    # the cast, so it cannot be clicked, cued or animated, and nothing its methods would have done
    # happens. Sierra gates content that way -- Laura Bow 2 removes the taxi from outside the
    # museum once the act advances, `(if (< global123 2) (taxi init: stopUpd:))`, and that single
    # line is what stops you riding back to act 1's city. Inert wherever an object is init'ed
    # unconditionally somewhere, which is nearly everywhere, because one unguarded arming site
    # makes the disjunction below vacuous.
    ARMING = ("setCycle", "setMotion", "setScript", "cue", "setReal", "setTimer", "init")

    def _inherit_arming(self, room):
        """A cue-driven edge inherits the guard of whatever ARMED it.

        SCI's door idiom splits one player action across two objects:

            ((Said 'open/door')                          ; Room22.handleEvent
              (cond ((not global100)                     ; <-- the gate: daytime only
                     (doorSound number: 300 play: door)  ; arms the door (sound cues its client)
                     (door setCycle: End))               ; ...and animates it
                    (else (proc255_0 22 9))))            ; "We're all asleep here!"

            (instance door of Prop                       ; and, separately:
              (method (cue)
                (if (!= (door cel:) (door lastCel:)) (self setCycle: End self)
                  else (global2 newRoom: 54))))          ; <-- the edge

        Walked object-by-object, the edge carries only the cel test -- opaque, so free -- and
        `not global100` is nowhere near it. In KQ4 that is the difference between seeing and not
        seeing that the dwarves' house and the fisherman's shanty LOCK AT NIGHTFALL, with the
        Diamond_Pouch and the Fishing_Pole behind them.

        Same principle as the existing setScript capture: an object that only runs when something
        starts it cannot be freer than its starter. The arming guards are OR-ed, since any of them
        will do, and a single unguarded arming site makes the disjunction vacuous -- which is the
        permissive answer, and the right one.

        Deliberately narrow, because adding a guard REMOVES movement and that is the unsafe
        direction: applied only to objects that emitted an edge, only from arming sends found in
        OTHER objects' methods (an object re-arming itself is the animation loop, not a gate), and
        never when no arming site was found at all."""
        armed = self._armed.get(room)
        if not armed:
            return
        for e in self.ts.edges + self.ts.cs_edges:
            if e.src != room or not e.via:
                continue
            gs = armed.get(e.via)
            if not gs:
                continue
            starter = gs[0] if len(gs) == 1 else GOr(list(gs))
            # via _conj, not a hand-built GAnd. Here a None starter means the arming was
            # UNCONDITIONAL, so dropping it is correct -- which is exactly what _conj does.
            # (Not to be confused with the None `atom()` yields for an operand we cannot model:
            # that one means UNKNOWN and must stay in the tree, which is why the GAnd at the top
            # of this file keeps its null kids. Two different Nones; only this one is droppable.)
            # Latent until edges with a computed destination began arriving here already guarded
            # -- before that this room's edges were all guard-None and took the other branch.
            e.guard = _conj([e.guard, starter])

    def _nav_edges(self, room_num, script):
        obj = _room_object(script, self.ir)
        if obj is not None and room_num not in self._no_walk_rooms():
            for sel in NAV_SELECTORS:
                dst = obj.props.get(sel)
                if dst and dst != 0xffff:
                    self.ts.edges.append(Edge(room_num, dst))   # walk-off exit, free
        # static entranceTo on any object (rooms + Doors): walking it goes to that room
        for o in script.objects:
            et = o.props.get("entranceTo", 0)
            if et and et != 0xffff:
                self.ts.edges.append(Edge(room_num, et))

    def _no_walk_rooms(self):
        """Rooms whose `init` TAKES THE WALK ICON AWAY -- so their declared n/s/e/w exits are not
        exits the player can use, whatever the room object says.

        A declared `south 680` is a walk-off exit: the player walks to the screen edge and the room
        hands them on. If walking is disabled there is no such action. KQ6's rm690 is the room in
        front of the Lord of the Dead:

            (method (init) ... (global69 disable: 0) (self setScript: introScript) ...)

        and it declares `south 680`. The user confirmed in-game that you cannot walk away from that
        confrontation -- the only way out is `holdUpMirror`, which needs the mirror. Without this the
        model strolls south, reaches the escape cutscene having never held up the mirror, and the
        Realm of the Dead's carry-IN items stop being softlocks.

        Note rm690 disables ONLY the walk icon, leaving look/talk/use available, which is the point:
        you are meant to act, just not leave. That is a different idiom from the cutscene shape
        (`enable: disable: 0 1 2 3 4 5 6 height: -100`, which hides the whole bar) -- both mean no
        walking, and both are covered, but only the first has anything to remove.

        Three conditions, because REMOVING movement is the unsafe direction:
          * the disable is in `init` and holds on EVERY path -- descend only `seq` nodes, never a
            branch or a loop. rm580 and rm350 disable the bar under `(if local0 ...)` /
            `(if (not (proc913_0 2)) ...)` and are correctly left alone;
          * it names the walk icon, by index or by object (`IconBar::disable` accepts either), or
            takes no argument at all, which disables every icon;
          * and nothing anywhere in the room's script enables it again.
        Measured over the corpus, exactly one room in one game loses an edge: KQ6's rm690. SCI0 has
        no icon bar, so `derive_walk_icon` returns None and this is inert on LSL2/KQ4/SQ3/Camelot."""
        if self._nowalk is not None:
            return self._nowalk
        self._nowalk = set()
        found = V.derive_walk_icon(self.ir)
        if not found:
            return self._nowalk
        gi, idx, name = found

        def names_walk(params):
            return (not params) or any(
                (I.as_int(p) is not None and I.as_int(p) == idx)
                or (isinstance(p, dict) and p.get("name") == name) for p in params)

        def bar_sends(node):
            for n in I.walk(node):
                if n.get("t") != "Send":
                    continue
                recv, msgs = I.send_pairs(n)
                if I.is_global(recv, gi):
                    yield msgs

        def unconditional(node, out):
            """Sends reached on every path: descend `seq` only."""
            shape = I.control_shape(node)
            if shape[0] == "seq":
                for k in shape[1]:
                    unconditional(k, out)
            elif node is not None and node.get("t") == "Send":
                out.append(node)

        for s in self.ir.scripts.values():
            obj = _room_object(s, self.ir)
            if obj is None or "init" not in obj.methods:
                continue
            stmts = []
            unconditional(obj.methods["init"], stmts)
            off = any(sel == "disable" and names_walk(params)
                      for st in stmts for sel, params in next(bar_sends(st), ()))
            if not off:
                continue
            back = any(sel == "enable" and names_walk(params)
                       for o in s.objects for body in o.methods.values()
                       for msgs in bar_sends(body) for sel, params in msgs)
            if not back:
                self._nowalk.add(s.number)
        return self._nowalk

    def _walk(self, room, node, pc, script, seen, movement=True, verb_param=None):
        """Compose path conditions and record effects (newRoom, item transfers), FOLLOWING calls
        in context. `movement=False` for a changeState body: the MACHINE owns those newRoom exits,
        so a free flat duplicate would bypass the gate. Items are always captured (duplicate
        acquisition is monotone).

        `verb_param` is the Parameter index of a `doVerb` method's verb-or-item arg (SCI1's param1),
        or None. It scopes the doVerb item-use recognition (see _cmp_atom) to the doVerb body itself:
        set on entry, and cleared while FOLLOWING a call, so a followed proc's own param1 is never
        mistaken for the clicked item.

        Control flow comes from `walk_stream` / `ir.control_shape`. This used to re-implement
        If/Cond/Switch/Loop itself, in code all but identical to opmodel's and machine's --
        which is how `Loop` came to be missing from two of the three."""
        global _VERB_PARAM
        saved_verb_param = _VERB_PARAM
        _VERB_PARAM = verb_param

        def enter_loop(n):
            prev = self._list_loop
            self._list_loop = prev or _walks_a_list(n)
            def restore():
                self._list_loop = prev
            return restore

        def leaf(n, p):
            tp = n["t"]
            if tp == "Send":
                self._send_effect(room, n, p, movement, script)
            elif tp == "Assignment" and movement:
                self._nav_assignment(room, n, p)
                self._pending_room_assignment(room, n, p)
            elif tp in ("PublicCall", "LocalCall"):
                tgt = n.get("script", script)
                name = n.get("name")
                body = self.procs_by.get((tgt, name))
                if tgt != 255 and body is not None and name not in seen:
                    # verb_param defaults to None: a followed proc is not a doVerb body, so its own
                    # param1 must not be read as the clicked item.
                    self._walk(room, body, p, tgt, seen | {name}, movement)

        try:
            walk_stream(node, pc, leaf, enter_loop)
        finally:
            _VERB_PARAM = saved_verb_param

    def _pending_room_assignment(self, room, node, pc):
        """`(= gNewRoomNum 57)` -- a room change written at the engine level instead of as
        `newRoom:`.

        SCI's Game loop is literally

            (if (!= global13 global11)          ; Game.sc, in both LSL2 and KQ4
                (self newRoom: global13))

        so assigning that global IS `newRoom:`, one layer down. KQ4 uses it 20 times and LSL2
        never, which is why it went unnoticed -- and it is not a corner case there: rm6 enters the
        witches' cave with `(= global13 57)` on a control-colour test, so rm57 had NO in-edges at
        all. That in turn made rm57 look "sealed" in the day/night analysis and, worse, let start
        discovery anchor on a room nothing can reach.

        Same family as the revolving door (`newRoom: <global>`) we already resolve, approached from
        the other side: there the destination was in a variable, here the whole call is."""
        if self._pending is None:
            return
        kids = node.get("kids") or []
        if len(kids) < 2 or not I.is_global(kids[0], self._pending):
            return
        dst = I.as_int(kids[1])
        if dst is None or dst == 0 or dst == 0xffff:
            return
        self.ts.edges.append(Edge(room, dst, _conj(pc), self._cur_obj))

    def _nav_assignment(self, room, node, pc):
        """`(= north 5)` -- a walk-off exit set by ASSIGNING the room's own property.

        The other idiom, declaring it in the properties block, is handled by `_nav_edges`. Both
        mean the same thing and games pick one: LSL2 uses the properties block 98 times and the
        assignment form NEVER; KQ4 uses the assignment form 162 times. Supporting only the first
        left 35 KQ4 rooms with no extractable exit at all and shattered its map into 64 components,
        so the analysis was reasoning about a game it could not walk across.

        Captured here rather than in `_nav_edges` so the path condition applies: an exit opened
        only under some condition becomes a GUARDED edge, and `(= east 0)` (closing an exit) is
        correctly not an edge at all."""
        kids = node.get("kids") or []
        if len(kids) < 2:
            return
        dest, src = kids[0], kids[1]
        if not (isinstance(dest, dict) and dest.get("t") == "Property"
                and dest.get("name") in NAV_SELECTORS):
            return
        dst = I.as_int(src)
        if not dst or dst == 0xffff:
            return                      # 0 CLOSES the exit; it does not open one
        self.ts.edges.append(Edge(room, dst, _conj(pc)))

    def _record_arming(self, room, node, pc):
        """Note that this send ARMS some object, and under what condition. Two spellings:
        `(door setCycle: End)` -- the object is the receiver -- and `(doorSound play: door)`,
        where the object is handed to something that will cue it when it finishes."""
        recv, msgs = I.send_pairs(node)
        rname = recv.get("name") if isinstance(recv, dict) else None
        targets = set()
        for sel, params in msgs:
            if sel in self.ARMING and rname:
                targets.add(rname)
            for p in params:
                if isinstance(p, dict) and p.get("t") == "Object" and p.get("name"):
                    targets.add(p["name"])
        for t in targets:
            if t and t != self._cur_obj:      # self-arming is the animation loop, not a gate
                self._armed.setdefault(room, {}).setdefault(t, []).append(_conj(pc))

    def _send_effect(self, room, node, pc, movement=True, script=None):
        self._record_arming(room, node, pc)
        recv, msgs = I.send_pairs(node)
        for sel, params in msgs:
            # A WRITE to a tracked item property -- the FOURTH store. `(Inv at: 15) loop: 1`
            # breaks the shovel; `(Inv at: 14) loop: (+ (loop:) 1)` spends an arrow. Both mean
            # the same thing as losing the item, because its uses stop accepting it:
            #   Room16:249  (if (and (gEgo has: 15) (== 0 ((Inv at: 15) loop:))) ... dig ...)
            it = _at_item(recv)
            if params and it is not None and (it, sel) in _IPROPS:
                v = I.as_int(params[0])
                if v is None and any(y.get("t") in ("Add", "Sub") for y in I.walk(params[0])):
                    v = "inc"
                if v is not None:
                    # carry the owning SCRIPT NUMBER: a Main-scope write (KQ4's shootBow spends an
                    # arrow from a ScriptID-loaded script) is attributed to room 0, but its SOURCE
                    # lives in shootBow.sc -- the patcher resolves the number to that file's title
                    # via titles_by_num. (Was the object NAME, which matched shootBow only by
                    # coincidence and was "" for a proc-hosted write -- finding B#7.)
                    self.ts.item_prop_writes.append((room, it, sel, v, _conj(pc), script))
            # The store property written DIRECTLY, bypassing its own accessor -- and inside a
            # list walk, so it means the whole inventory at once: KQ4's Room92 confiscates
            # everything to room 89 and Room89's cupboard hands it all back. The property name
            # comes from the derived vocabulary, not from us; `owner:` is also a Sound property
            # (`(trollMusic owner: self)`), which the destination test excludes.
            if _VOCAB is not None and sel == _VOCAB.prop and params and self._list_loop:
                d = params[0]
                dest = (EGO if _is_ego(d)
                        else I.as_int(d) if I.as_int(d) is not None else None)
                if dest is not None:
                    self.ts.bulk_moves.append((room, dest, _conj(pc)))
            if sel in NAV_SELECTORS and params and self._nav_send_room(recv, room) is not None:
                # `(self north: 340)` -- the SEND spelling of `_nav_assignment`'s `(= north 5)`.
                # Same fact (this room's walk-off exit in that direction), same guard treatment,
                # different syntax, and games mix the two freely: LSL2 5 sites, KQ4 2, KQ6 3,
                # SQ3 4, Dagger 1. Only KQ6 / Dagger / SQ3 gain an edge -- everywhere else the
                # room also declares the exit in its properties block, which is why supporting
                # one spelling looked like it worked.
                #
                # It matters where it does gain one: KQ6's rm300 picks its north exit in `init`
                # (`(if (proc913_0 157) (self north: 340) else (self north: 320))`) and declares
                # none, so the whole Sacred Mountain hung off the START ROOM alone. Nothing could
                # return to it, and every gate that demands a flag set elsewhere became
                # unsatisfiable there -- including the realm of the dead's entry.
                dst = I.as_int(params[0])
                if dst and dst != 0xffff:       # 0 CLOSES the exit; it does not open one
                    self.ts.edges.append(Edge(self._nav_send_room(recv, room), dst,
                                              _conj(pc), self._cur_obj))
            elif sel in ("newRoom", "entranceTo") and params:
                dsts = [I.as_int(params[0])]
                if dsts[0] is None and (I.is_global(params[0])
                                        or I.is_local_or_temp(params[0])):
                    # INDIRECT destination `newRoom: <var>` -- a routing room that COMPUTES
                    # where you go next and keeps it in a variable. Two storage choices, one
                    # idiom:
                    #   GLOBAL  LSL2 rm40's revolving door (gRmAfter40 cycles 42..45). Dropping
                    #           it made rm43 (the Knife) and its cluster unreachable.
                    #   LOCAL   LB2's act break (script 26) picks the next act's start room per
                    #           act, then `newRoom: local0` from another object in the script.
                    #           Dropping it left rm26 a pure SINK with 16 in-edges, which
                    #           anchors.discover then read as a winning terminal.
                    # Resolve either to the room numbers the variable can hold, each with the
                    # condition it was assigned under (see _var_room_values).
                    dsts = self._var_room_values(room, params[0])
                elif dsts[0] is None and params[0].get("t") == "ComplexVariable":
                    # `newRoom: [array][region]` -- overland-map travel keyed by the PIC control
                    # map (Camelot rm1 is the whole world's hub). Dropping it severed the hub and
                    # collapsed every location out of reachability.
                    dsts = _array_room_values(self.ir, script, params[0])
                # Normalise all three shapes to {destination: extra condition}. A literal or an
                # array slot carries none; a computed destination carries the one it was chosen
                # under, and that condition belongs on the EDGE -- it is the difference between
                # "the act break can send you to act 5" and "it does so once you have finished
                # act 4".
                if not isinstance(dsts, dict):
                    dsts = {d: None for d in dsts}
                for dst, extra in dsts.items():
                    if dst is not None:
                        (self.ts.edges if movement else self.ts.cs_edges).append(
                            Edge(room, dst, _conj(list(pc) + [extra]), self._cur_obj))
            else:
                # ACQUISITION -- the last hardcoded `sel == "get"` here is gone too: whether a
                # send hands the player an item is a question for the derived vocabulary, not a
                # selector name we happen to know.
                for tr in item_transfers(recv, sel, params):
                    if tr[1] == EGO:
                        self.ts.items.add(tr[0])
                        self.ts.acqs.append(Acq(tr[0], room, _conj(pc), self._cur_obj))
                    elif isinstance(tr[1], int) and tr[1] > 0:
                        # a transfer to a ROOM (not the ego, not -1/nowhere): the item is PLACED
                        # there. The owner state's transition to a location -- see TS.placed.
                        self.ts.placed.setdefault(tr[0], set()).add(tr[1])

    def _nav_send_room(self, recv, room):
        """Whose exit does `(<recv> north: N)` open -- this room's, or None if not a room's.

        `self`, the current-room global (`(global2 south: 720)`) and the script's own `rm<N>`
        instance are all the room we are extracting. A send to a DIFFERENT room's instance is
        not, and is dropped rather than attributed here -- unlike `newRoom:`, where the receiver
        genuinely does not matter because any object can send it."""
        if not isinstance(recv, dict):
            return None
        if I.is_global(recv) or recv.get("t") in ("Self", "Property"):
            return room
        name = recv.get("name") or ""
        if recv.get("t") == "Object" and name.startswith("rm") and name[2:].isdigit():
            return room if int(name[2:]) == room else None
        return room if recv.get("t") == "Object" and name in ("self", "Self") else None

    def _var_room_values(self, room, var):
        """Room numbers an indirect `newRoom:` destination variable can hold, from
        switch-on-V case labels and `(= V lit)` assignments anywhere in this room's script.
        Filtered to real rooms (an rm<N> Room instance exists), so cycle counters like 0
        are excluded.

        The variable may be a GLOBAL or a script LOCAL/TEMP -- same idiom, different storage,
        so the same scan answers both. Scoping the scan to THIS script is exact for a local
        (that is all a script local can see) and is the deliberate narrowing we already chose
        for the global case.

        Returns {room: guard}, where the guard is the PATH CONDITION UNDER WHICH THE
        DESTINATION WAS ASSIGNED -- `None` meaning unconditional. That is what stops a routing
        room from becoming a free hub between everywhere it can send you: LB2's act break is
        reached from seven rooms and can deliver five, but `(switch global123 (2 (= local0 355)))`
        says rm355 is the destination exactly when the act counter is 2. Without the condition
        the model would let you walk out of act 1 into act 5 -- the same over-merge that hid the
        LSL2 parachute.

        A value assigned at more than one site drops to `None`: we compose conditions with AND
        and the honest reading of two sites is their OR, so the permissive answer is the sound
        one here (we never invent a constraint the game does not have)."""
        s = self.ir.scripts.get(room)
        if s is None:
            return {}
        vtype, vindex = var.get("vtype"), var.get("index")
        seen = {}                              # room -> [guard, ...] one per assignment site

        def is_room(v):
            rs = self.ir.scripts.get(v)
            return rs is not None and _room_object(rs) is not None

        def is_dest(n):
            return (n and n.get("t") == "Variable" and n.get("vtype") == vtype
                    and n.get("index") == vindex)

        def on_leaf(n, pc):
            if n["t"] == "Assignment" and is_dest(n["kids"][0]):
                v = I.as_int(n["kids"][1])
                if v is not None and is_room(v):
                    seen.setdefault(v, []).append(_conj(pc))

        for o in s.objects:
            for _mn, ast in o.methods.items():
                # TWO scans, because the two shapes need different walkers and conflating them
                # cost LSL2 eight softlocks once already. `(switch <dest> ...)` is DATA -- the
                # case labels ARE the values -- but walk_stream reads a Switch as control flow
                # and never hands it to on_leaf, so that harvest has to run on the flat walk.
                # The assignment shape genuinely needs the path condition, so it uses
                # walk_stream. See test_walkers on Switch-as-data.
                for n in I.walk(ast):
                    if n["t"] == "Switch" and is_dest(n["kids"][0]):
                        for c in n["kids"][1:]:
                            if c["t"] == "Case":
                                v = I.as_int(c["kids"][0])
                                if v is not None and is_room(v):
                                    seen.setdefault(v, []).append(None)
                walk_stream(ast, [], on_leaf)
        return {v: (gs[0] if len(gs) == 1 else None) for v, gs in seen.items()}


def extract(ir):
    install_vocabulary(ir)      # derive this game's item-transfer selectors first
    return Extractor(ir).run()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else config.ACTIVE.ir_path
    ir = I.load_ir(path)
    ts = extract(ir)
    print(f"rooms={len(ts.rooms)} edges={len(ts.edges)} acqs={len(ts.acqs)} items={len(ts.items)}")
    free = sum(1 for e in ts.edges if e.guard is None)
    print(f"  free edges={free} gated edges={len(ts.edges)-free}")
    print("  items acquired:", sorted(ts.items))
