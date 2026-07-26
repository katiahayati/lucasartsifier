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
    global _VOCAB, _IPROPS, _EGO, _CURROOM, _ITEM_MSG, _ONEOF
    _VOCAB = V.Vocabulary.from_ir(ir)
    _IPROPS = (V.item_property_registers(ir, _VOCAB.store_class, _VOCAB.prop, _at_item)
               if _VOCAB else {})
    _ITEM_MSG = V.doverb_item_messages(ir)
    _ONEOF = frozenset(V.derive_oneof(ir))
    holders = frozenset().union(*_VOCAB.holders.values()) if _VOCAB and _VOCAB.holders else frozenset()
    _EGO = holders or frozenset({0})
    _CURROOM = current_room_global(ir)
    if _CURROOM is None:
        _CURROOM = 11
    return _VOCAB


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
    bulk_moves: list = field(default_factory=list)  # (room, dest, guard) -- a transfer of the
    #   WHOLE inventory at once, written as a walk of the Inv list. No item number appears
    #   anywhere, so this is the one case where "no constant" must mean "all of them".
    item_prop_writes: list = field(default_factory=list)  # (room, item, prop, value, guard);
    #   value is an int or "inc". The FOURTH store -- state living in an item's own property.
    #   Breaking the shovel and spending an arrow are written here, and they mean the same thing
    #   as losing the item: its uses stop accepting it.
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
    room before switching -- `(= <previous> <current>)` -- where `<current>` is `current_room_global`.
    Both LSL2 and KQ4 land on global12 (current global11, pending global13), by derivation. It is
    what a virtual-map room reads to seed its entry cell, so `grid.analyze` gates a grid exit on it
    -- "you can only reach the island if you arrived from the whale"."""
    current = current_room_global(ir)
    if current is None:
        return None
    # previous = the global assigned FROM the current-room global (saved before the update)
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if n.get("t") != "Assignment":
                        continue
                    ks = n.get("kids") or []
                    if (len(ks) >= 2 and I.is_global(ks[0]) and I.is_global(ks[1])
                            and ks[1]["index"] == current and ks[0]["index"] != current):
                        return ks[0]["index"]
    return None


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

    def scriptid_refs(self):
        """`(target script, room, guard)` for every `(ScriptID N)` -- SCI's dynamic script load.

        A fourth scope, after Main / region / room. `Main.sc:1116` answers `Said 'launch'` ANYWHERE
        with `(gEgo setScript: (ScriptID 305 0))`, and script 305 (`shootBow`) is where the arrow is
        actually spent -- so firing into the air costs an arrow and we could not see it. Two deaths
        hide the same way: `timeOut` (the 24-hour deadline) and `openPbox` both write the game-over
        global from scripts that are neither rooms nor regions.

        The reference's PATH CONDITION comes with it, which is what keeps `DebugMenu` (script 801,
        loaded from Main under a debug gate) from handing the player every item.

        KQ4 has 8 such scripts; LSL2 has ZERO `ScriptID` call sites, so this cannot move it."""
        out, seen = [], set()
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
                    for room in _rooms:
                        key = (tgt, room)
                        if key not in seen:
                            seen.add(key)
                            out.append((tgt, room, list(pc)))
                walk_stream(b, [], leaf)
        return out

    def run(self):
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
        for tgt, room, pc in self.scriptid_refs():
            ts_ = self.ir.scripts.get(tgt)
            # `(ScriptID 0 N)` is how a room reaches MAIN's public procedures -- Main is already
            # its own scope, and walking it into every referencing room attributed its debug
            # cheat block to 25 rooms.
            if ts_ is None or tgt == 0 or tgt in room_scripts or tgt in regions:
                continue
            for o in ts_.objects:
                self._cur_obj = o.name
                for mname, meth_ast in o.methods.items():
                    self._walk(room, meth_ast, list(pc), tgt, set(),
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
            for d in sorted(dests):
                self.ts.edges.append(Edge(s.number, d))
                self.ts.rooms.add(d)

    # selectors that make an object animate/move/run, i.e. that end in a `cue` back to it
    ARMING = ("setCycle", "setMotion", "setScript", "cue", "setReal", "setTimer")

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
            e.guard = starter if e.guard is None else GAnd([e.guard, starter])

    def _nav_edges(self, room_num, script):
        obj = _room_object(script, self.ir)
        if obj is not None:
            for sel in NAV_SELECTORS:
                dst = obj.props.get(sel)
                if dst and dst != 0xffff:
                    self.ts.edges.append(Edge(room_num, dst))   # walk-off exit, free
        # static entranceTo on any object (rooms + Doors): walking it goes to that room
        for o in script.objects:
            et = o.props.get("entranceTo", 0)
            if et and et != 0xffff:
                self.ts.edges.append(Edge(room_num, et))

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
            if sel in ("newRoom", "entranceTo") and params:
                dsts = [I.as_int(params[0])]
                if dsts[0] is None and I.is_global(params[0]):
                    # INDIRECT destination `newRoom: <global>` -- a routing room whose next
                    # room is held in a global (rm40's revolving door: gRmAfter40 cycles
                    # 42..45). Resolve to the room numbers that global can hold; dropping it
                    # made rm43 (the Knife) and its cluster unreachable -> endgame sealed.
                    dsts = self._global_room_values(room, params[0]["index"])
                elif dsts[0] is None and params[0].get("t") == "ComplexVariable":
                    # `newRoom: [array][region]` -- overland-map travel keyed by the PIC control
                    # map (Camelot rm1 is the whole world's hub). Dropping it severed the hub and
                    # collapsed every location out of reachability.
                    dsts = _array_room_values(self.ir, script, params[0])
                for dst in dsts:
                    if dst is not None:
                        (self.ts.edges if movement else self.ts.cs_edges).append(
                            Edge(room, dst, _conj(pc), self._cur_obj))
            else:
                # ACQUISITION -- the last hardcoded `sel == "get"` here is gone too: whether a
                # send hands the player an item is a question for the derived vocabulary, not a
                # selector name we happen to know.
                tr = item_transfer(recv, sel, params)
                if tr is not None and tr[1] == EGO:
                    self.ts.items.add(tr[0])
                    self.ts.acqs.append(Acq(tr[0], room, _conj(pc)))
                elif tr is not None and isinstance(tr[1], int) and tr[1] > 0:
                    # a transfer to a ROOM (not the ego, not -1/nowhere): the item is PLACED there.
                    # This is the owner state's transition to a location -- see TS.placed.
                    self.ts.placed.setdefault(tr[0], set()).add(tr[1])

    def _global_room_values(self, room, gi):
        """Room numbers a `newRoom:` global can hold, from switch-on-G case labels and
        `(= G lit)` assignments anywhere in this room's script. Filtered to real rooms
        (an rm<N> Room instance exists), so cycle counters like 0 are excluded."""
        vals = set()
        s = self.ir.scripts.get(room)
        if s is None:
            return vals

        def is_room(v):
            rs = self.ir.scripts.get(v)
            return rs is not None and _room_object(rs) is not None

        for o in s.objects:
            for _mn, ast in o.methods.items():
                for n in I.walk(ast):
                    if n["t"] == "Switch":
                        head = n["kids"][0]
                        if head.get("t") == "Variable" and head.get("vtype") == "Global" \
                                and head.get("index") == gi:
                            for c in n["kids"][1:]:
                                if c["t"] == "Case":
                                    v = I.as_int(c["kids"][0])
                                    if v is not None and is_room(v):
                                        vals.add(v)
                    elif n["t"] == "Assignment" and I.is_global(n["kids"][0]) \
                            and n["kids"][0].get("index") == gi:
                        v = I.as_int(n["kids"][1])
                        if v is not None and is_room(v):
                            vals.add(v)
        return vals


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
