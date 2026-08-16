"""Machine layer over the typed IR: lift each room Script's changeState into an explicit
transition system (states -> guarded ops), then simulate/compile it.

The changeState switch is uniform: `(switch (= state param) (K body) ...)`, one Case per
state. Each state body is a sequence of ops, some guarded by if/cond path conditions:
  EXIT r     `(gCurRoom newRoom: r)`              -- leave to room r
  WRITE g v  `(= Global[g] v)`                    -- register write
  DEATH      the death signal write / death proc  -- absorbing sink
  ADVANCE    a cue is armed (`... self` arg, `(= seconds N)`, `(= cycles N)`, `(= ticks N)`,
             `(other changeState: K)`, `(self cue:)`) -> next state = state+1
  JUMP k     `(self changeState: k)`              -- go to state k now
  SETSTATE k `(= state k)`                        -- set state (then a cue advances to k+1)
             ...and `(++ state)` / `(-- state)` in state K's body, which are the SAME op
             relative to K (SETSTATE K+1 / K-1): the game's cue: sends changeState(state+1),
             so a body that bumps `state` moves where that cue lands. Read as a bare
             ADVANCE -- which is what `(++ state)` was until 2026-08-14 -- the model walks
             THROUGH the state the game skips and never reaches the one it lands on; KQ5's
             rm42 hides its death chain (states 8-11) behind exactly this idiom.
  GET i      `(gEgo get: i)`                       -- acquire item
  COUNTER    `(++ c)`/`(-- c)`/`(= c lit)`        -- bounded local counter update
A state that arms NO cue and does not transfer PARKS (waits for the next player action);
it does NOT fall into the next state (segments-per-entry -- the hard lesson of the
DELETED first-generation lifter this file replaced; git history has it).

Effect-timing is exactly the machine's own control flow, so there is no ENTRY/SELF/EXIT
write reconstruction (the seam that lost the parachute).
"""
from __future__ import annotations

import config

from dataclasses import dataclass, field

import ir as I
from guard_ast import GAnd, GOr, Pred
from extract import atom, _conj, item_transfer, EGO
import extract as X


@dataclass
class Op:
    kind: str                 # EXIT WRITE DEATH ADVANCE JUMP SETSTATE GET COUNTER
    guard: object = None      # path condition (guard tree) or None
    a: object = None          # EXIT room / WRITE glob / JUMP-SETSTATE state / GET item / COUNTER name
    b: object = None          # WRITE value / COUNTER (kind,val)


@dataclass
class Machine:
    script: int
    inst: str
    states: dict = field(default_factory=dict)     # k -> [Op] in source order (debug view)
    bodies: dict = field(default_factory=dict)     # k -> state body AST (for path compile)
    entries: list = field(default_factory=list)    # [(state, guard)] how it is entered
    init_entries: list = field(default_factory=list)  # entries from the room's INIT method only.
    #   These run atomically with room init, so they must be bundled onto ROOM ARRIVAL and
    #   evaluated on the pre-entry state -- else an init write to the guard register (rm79:
    #   init sets gIslandStatus:=3, the `changeState 1` cutscene guard is gIslandStatus==2)
    #   makes the standalone one-step-later entry never fire. Player-triggered entries
    #   (handleEvent/doit) stay in `entries` (evaluated in-room, post-init).
    entry_armers: list = field(default_factory=list)   # PARALLEL to entries: the machine whose
    #   changeState body armed us, or None. A cutscene armed by ANOTHER cutscene inherits its
    #   preconditions -- see MachineBuilder._chain_entries.
    entry_locals: list = field(default_factory=list)   # PARALLEL to entries: {(vt,idx): val} the
    #   arming context wrote before setScript'ing us. A machine's internal local branches read
    #   these -- rm214 sets local1:=1 (guarded by using the staff) and knockDoor only reaches
    #   `newRoom: 18` when local1==1, so the coin/bottle inside are reachable ONLY with the staff.
    #   Kept parallel (not a 3-tuple) so every consumer that unpacks `(state, guard)` is untouched.
    init_entry_locals: list = field(default_factory=list)   # PARALLEL to init_entries.
    init_entry_idx: list = field(default_factory=list)   # PARALLEL to init_entries: which
    #   `entries` row each init entry IS. An init entry is the SAME entry, additionally bundled
    #   onto room arrival -- but it used to be stored as a COPY of the (state, guard) pair, and
    #   the passes that strengthen an entry (`_chain_entries`, `_inherit_local_continuations`)
    #   rewrite `entries[i]` only. So the arrival copy kept the WEAKER guard: LSL2's rm26
    #   `birdScript` arrived as `CTR(L3 != 0)` while its entry had grown
    #   `AND(CTR(L3 != 0), own(3), own(10))` -- i.e. the arrival copy asserted the cutscene
    #   fires without owning the items. Keeping the index lets `_resync_init_entries` restate
    #   them from the entries they are, so there is one guard, not two that drift.
    entry_recv: list = field(default_factory=list)      # PARALLEL to entries: the SLOT the arming
    #   `setScript:` wrote -- ("G", 2) for the room's script, ("G", 0) for the ego's, ("O", name)
    #   for an actor's. A Script object occupies one slot, so two machines armed into the SAME slot
    #   are COMPETITORS: whichever is set last is the one that runs. That is how SCI expresses
    #   "the player's action interrupts the timer" -- see missability.death_traps.
    entry_sources: list = field(default_factory=list)   # PARALLEL to entries: the METHOD the
    #   arming was found in ("init", "doit", "cue", a proc, ...). A `cue` is not a way IN -- see
    #   MachineBuilder._drop_continuation_entries.
    restores_control: set = field(default_factory=set)  # states whose body sends a derived
    #   control-restore selector (SCI1.1's handsOn -- vocab.derive_control_selectors): the player
    #   is free to act while this state waits. What lets fatal_uses treat a wait-on-the-clock
    #   state as pre-emptable by arming a competitor into the same slot. Empty on SCI0.
    chase_states: set = field(default_factory=set)  # states whose body arms a `setMotion: Chase`
    #   with a self cue: the state completes only by CATCHING the (moving) player, a race the
    #   player co-determines and can decline by leaving the room. A death behind such a state is
    #   preventable from its own screen, which is the one-rule line: KQ4's rm49 dog and KQ5's
    #   rm36 yeti are this shape (control stays on until the catch), KQ5's yourStuck (pure
    #   timers) and killEgo (scripted MoveTo kill) are not. `Chase` is the SCI system motion
    #   class -- a MoveTo to fixed coordinates completes regardless of the player, so it does
    #   not count.
    glob_dom: dict = field(default_factory=dict)   # glob -> sorted values, for globals this
    #   script uses as a COUNTER (`++`/`--`). compile fans an increment out over these: the new
    #   value depends on the old one, so it is only resolvable against values we know it takes.
    var_dests: dict = field(default_factory=dict)   # (vtype, index) -> {room: assignment guard},
    #   for every variable this machine hands to `newRoom:`. The counterpart of glob_dom for the
    #   OTHER computed thing a state body can do: route. Resolved by extract.var_room_values --
    #   the same function the flat-edge builder uses, so a routing room is read one way, not two.
    local_regs: dict = field(default_factory=dict)  # synthetic-global index -> declared reset
    #   value, for the lowered ROOM LOCALS of this machine's OWN script (vocab.lower_room_locals).
    #   Lowering moved the latch into register-land, but inside this script it is still the
    #   machine-internal state the walks must resolve concretely -- so the walks thread these
    #   registers as counters (keyed by the synthetic index), seeded from the reset, while the
    #   atoms and writes stay registers for every cross-scope consumer. See compile._lreg_test.
    start: int = 0

    def __repr__(self):
        return f"Machine({self.inst}@{self.script}: states {sorted(self.states)})"


def _is_cue_send(recv, msgs):
    """A send that ARMS a cue (completes later -> advance to state+1)."""
    for sel, params in msgs:
        # `self` as an argument is the universal cue callback -- ANY position, not just last.
        # SCI1.1's Messager puts it mid-list (`say: noun verb cond seq self room`), so a
        # last-argument test read those states as PARKing and truncated every cutscene that
        # speaks: KQ6's minotaur fight stalls at state 1 and never reaches the state where the
        # red scarf decides it.
        if any(isinstance(p, dict) and p.get("t") == "Self" for p in params):
            return True
        if sel in ("cue", "setCycle", "setMotion", "setScript") and params and \
                any(p.get("t") == "Self" for p in params):
            return True
        # `(self cue:)` -- an IMMEDIATE self-cue, the way a state says "nothing to wait for,
        # carry on". No arguments, so the callback tests above cannot see it, and the state
        # read as PARKing: KQ6's minotaur fight takes this branch whenever it is not the
        # talking variant, and stalled one state before the scarf decides the outcome.
        if sel == "cue" and not params and recv.get("t") == "Self":
            return True
        # `(otherInstance changeState: K)` starts another script that cues back here
        if sel == "changeState" and recv.get("t") != "Self":
            return True
    return False


def _setscript_target(param, ir=None):
    """The Script a `setScript:` param refers to, as `(script_or_None, name)`.

    FOUR spellings: `henchScript` (an Object ref in the same script), `(henchScript new:)`
    (a Send whose receiver is the Object), `(ScriptID 344 3)` -- SCI's CROSS-SCRIPT reference --
    and a bare SCRIPT NUMBER. The last two need the export table to resolve and so are only
    available when an `ir` is supplied. A `None` script means "this same script", which is all the
    first two can mean.

    KQ6 arms 231 scripts this way and we resolved none of them, so every cutscene armed from
    another script -- the realm-of-the-dead entry among them -- lost its guard.

    THE NUMBER SPELLING, and it is derived from the game's own class table rather than assumed --
    `KQ6Room::setScript` spells out what the interpreter does with a non-object argument:

        (method (setScript param1 &tmp temp0)
          (cond ((IsObject param1) (super setScript: param1 &rest))
                ...
                (else (super setScript: (ScriptID param1) &rest))))

    so `setScript: N` IS `setScript: (ScriptID N)`, i.e. export 0 of script N. **Zero is not a
    target**: `Actor::setScript` guards the delegation with `(if param1 ...)`, so `setScript: 0`
    disposes the running script and arms nothing. That distinction is the whole safety story here --
    all 77 of KQ4's integer `setScript:`s are `setScript: 0`, and LSL2 has none, so neither golden
    can move. KQ6 has ~34 real targets, QFG-VGA 184, Dagger 33.

    What it costs to miss: KQ6's `mixPaintScr` is script 915, armed `(gCurRoom setScript: 915)`
    from the inventory under `(and flag68 flag58 (not flag22))`. Unresolved it has no entry at all,
    so the magic paint reads as free -- and flag 58 is the Styx water, which you can only draw
    during the Realm of the Dead's single visit."""
    if isinstance(param, dict) and ir is not None:
        n = I.as_int(param)
        if n:                          # 0 = clear the slot, not a script number
            got = ir.export_target(n)
            if got:
                return got
    if not isinstance(param, dict):
        return None
    if param.get("t") == "Object":
        return (None, param.get("name"))
    if ir is not None:
        got = ir.script_id_target(param)
        if got:
            return got
    if param.get("t") == "Send" and param.get("kids"):
        recv = param["kids"][0]
        if isinstance(recv, dict) and recv.get("t") == "Object":
            return (None, recv.get("name"))
        got = ir.script_id_target(recv) if ir is not None else None
        if got:
            return got
    return None


def _local_conjuncts(guard, zero_lregs=()):
    """Room-LOCAL keys this guard requires to be non-zero, along its top-level AND spine.

    `atom()` renders a bare `(if local1 ...)` as the tuple `('CTR', ('L', 1), '!=', 0)`, which is
    the SCI spelling of "the player set this latch". Only the AND spine, and only locals: a test
    under a negation or inside an OR is not required, and a TEMP is scratch within a single call so
    it can never carry a latch from one handler to a later arming.

    `zero_lregs`: the script's own LOWERED room locals whose declared reset is 0 -- the same test
    in its post-lowering spelling, `Pred CMP gi != 0`. Restricted to reset-0 registers because the
    strengthening rests on "non-zero means some non-zero write ran", and a local that RESETS to a
    non-zero value is non-zero by default."""
    out = set()

    def walk(g):
        if isinstance(g, list):
            for k in g:
                walk(k)
        elif isinstance(g, GAnd):
            for k in g.kids:
                walk(k)
        elif (isinstance(g, tuple) and len(g) == 4 and g[0] == "CTR"
              and isinstance(g[1], tuple) and g[1][0] == "L" and g[2] == "!=" and g[3] == 0):
            out.add(g[1])
        elif (isinstance(g, Pred) and g.kind == "CMP" and g.var in zero_lregs
              and g.op == "!=" and str(g.value) == "0"):
            out.add(g.var)
    walk(guard)
    return out


def _pc_covers(wpc, apc):
    """The write's path condition is a PREFIX of the arm's -- so whenever the arm fires, the write
    has already run and its value holds at machine start. Sibling leaves in one branch share the
    same atom OBJECTS (walk_stream passes one `pc + ext` list per branch), so identity comparison
    is exact and cheap; a shallower unconditional write also covers a deeper guarded arm."""
    return len(wpc) <= len(apc) and all(wpc[i] is apc[i] for i in range(len(wpc)))


class MachineBuilder:
    def __init__(self, ir, game_death):
        self.ir = ir
        self.is_death = game_death        # (glob_index, value) -> bool
        import vocab as _V
        self._restore_sels = frozenset(
            sel for sel, kind in _V.derive_control_selectors(ir).items() if kind == "restore")
        #   the Game hierarchy's own "player control comes back" selectors (SCI1.1's handsOn),
        #   derived from the class table; empty on SCI0. Marks states for `restores_control`.
        _script_cls = ir.find_class("Script")
        _timers = set()
        for n in I.walk((_script_cls.methods.get("doit") or {}) if _script_cls else {}):
            if n.get("t") in ("Decrement", "Assignment", "Eq", "Ne", "Lt", "Gt", "Le", "Ge"):
                for k in (n.get("kids") or []):
                    if isinstance(k, dict) and k.get("t") == "Property":
                        _timers.add(k.get("name"))
        self._timer_props = frozenset(_timers)
        #   the cue CLOCK: whatever properties the engine Script class's own doit counts down
        #   and compares (seconds/ticks/cycles and their lastX shadows -- read off the class,
        #   not listed). A state that writes one of these is scheduling its own future.
        self.procs_by = {}                # (script, proc-name) -> body, for call-following
        self._cast_cache = {}             # script number -> extract.cast_conditions(script)
        self._local_cache = {}            # script number -> extract.local_write_conditions(script)
        self._lreg_cache = {}             # script number -> {lowered-local gi: reset value}
        self._vdest_cache = {}            # script number -> {(vtype,idx): {room: guard}}
        self._entry_guard = {}            # (script, inst) -> the machine's entry disjunction, from
        #   the PREVIOUS pass. Empty until `prime` runs, which is the permissive answer. See prime.
        for rn, s in ir.scripts.items():
            for name, body in s.procs.items():
                self.procs_by[(rn, name)] = body
        # CROSS-SCRIPT arming index: (target script, target instance) -> [(arming script, method,
        # body)]. A `setScript:` naming an Object can only mean an object of the SAME script, so
        # the per-script scan in _build covers it; a `(ScriptID s n)` target can live anywhere, so
        # the arming code has to be found by looking outward from the machine. Built once here
        # rather than re-scanned per machine, which would be quadratic over 341 scripts.
        # CALL-SITE index for procedures. A machine armed inside a procedure has no way in of its
        # own -- the procedure runs because someone CALLED it, so the conditions on the call are
        # the machine's preconditions. KQ6 hangs the hole-in-the-wall chain off exactly that:
        #
        #     n404.sc:25   (procedure (proc404_0 param1) (global0 setScript: holeOnWall 0 param1))
        #     rm409.sc:232 (method (doVerb param1) (switch param1 (25 (proc404_0 2)) ...))
        #
        # Scanned standalone, `holeOnWall` gets an UNCONDITIONAL entry, and since entries are
        # alternatives that erases the `own(holeInTheWall)` the call site carries -- so putting the
        # hole on the wall, watching the minotaur through it, and thus finding the secret door to
        # his lair all become free. Same principle as `scriptid_refs`, which already carries a
        # cross-script reference's path condition; ORed over call sites, and permissive (None) if
        # any call site is unconditional or none was found.
        self.proc_calls = {}
        from extract import walk_stream, verb_param_scope

        def scan_calls(body, source):
            def leaf(n, pc):
                if n.get("t") in ("PublicCall", "LocalCall") and n.get("name"):
                    self.proc_calls.setdefault(n["name"], []).append(_conj(pc))
            with verb_param_scope(source):
                walk_stream(body, [], leaf)

        for rn, s in ir.scripts.items():
            for o in s.objects:
                for mn, body in o.methods.items():
                    scan_calls(body, mn)
            for pn, body in s.procs.items():
                scan_calls(body, pn)
        self.arms = {}
        for rn, s in ir.scripts.items():
            bodies = [(o.name, mn, b) for o in s.objects for mn, b in o.methods.items()]
            bodies += [(nm, "proc", b) for nm, b in s.procs.items()]
            for _oname, mn, body in bodies:
                for n in I.walk(body):
                    if n.get("t") != "Send":
                        continue
                    _r, msgs = I.send_pairs(n)
                    for sel, params in msgs:
                        if sel != "setScript" or not params:
                            continue
                        tgt = _setscript_target(params[0], ir)
                        if tgt and tgt[0] is not None and tgt[0] != rn:
                            self.arms.setdefault(tgt, []).append((rn, _oname, mn, body))
        # ...AND AN OBJECT IS OFTEN PUT ON SCREEN BY A SCRIPT THAT DOES NOT DECLARE IT:
        # `((ScriptID 550 3) init:)`, SCI's dynamic load addressed by EXPORT INDEX.
        # `cast_conditions` collects only the init sites written in the object's own script, so
        # such an object has no presence condition at all -- `any_guard` reads "no site found"
        # as "always", and its methods are then attributed to every room its script serves.
        #
        # KQ5's Mordack henchman is the case, and he is the reason the pea bag was demanded in
        # the wedding cutscene: `theHenchMan` lives in `castle.sc` (the region, live in all 16
        # castle rooms) but is init'ed only by rm54, 58, 59, 60, 61 and 67, so "throw the peas
        # at him" read as an act available anywhere in the castle. Mordack (`theWizard`,
        # 9 rooms), `theAura`, `theMagicDoor` and `theRings` are all the same shape.
        #
        # The site's own path condition comes with it, conjoined with the CALLING SCRIPT'S ROOM
        # -- an unconditional init in rm58 means "present in 58", not "present". A caller that
        # is not a room (Main, another region) contributes None, i.e. the permissive answer this
        # already gives everywhere else: a scope with no room cannot say where you are.
        self.foreign_inits = {}
        for rn, s in ir.scripts.items():
            room = X._room_object(s, ir)
            here = (Pred("CMP", var=X._CURROOM, op="==", value=str(rn))
                    if room is not None else None)
            bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
            for body in bodies:
                def leaf(n, pc, _here=here):
                    if n.get("t") != "Send":
                        return
                    recv, msgs = I.send_pairs(n)
                    if (not isinstance(recv, dict) or recv.get("t") != "KernelCall"
                            or recv.get("name") != "ScriptID"):
                        return
                    hit = ir.script_id_target(recv)
                    if not hit or hit[0] is None or hit[1] is None:
                        return
                    for sel, _params in msgs:
                        g = None if _here is None else _conj(list(pc) + [_here])
                        self.foreign_inits.setdefault(hit[0], []).append((hit[1], sel, g))
                walk_stream(body, [], leaf)

    def machines(self, script):
        out = []
        for o in script.objects:
            if "changeState" in o.methods and o.methods["changeState"]:
                m = self._build(script, o)
                if m.states:
                    out.append(m)
        self._chain_entries(out)
        for m in out:
            self._resync_init_entries(m)
        return out

    @staticmethod
    def _resync_init_entries(m):
        """Restate the ROOM-ARRIVAL copies from the entries they are.

        `init_entries` is not a second, weaker way in -- it is the same entry, additionally
        bundled onto arrival because it runs atomically with room init. Every pass that
        STRENGTHENS an entry (`_chain_entries` conjoining the armer's preconditions,
        `_inherit_local_continuations` conjoining the local writes that must have happened)
        rewrites `entries[i]`, so a copy taken at append time goes stale the moment either
        fires. Measured drift before this: LSL2 1 machine, KQ6 4.

        The arrival copy is the one bundled onto every room entry, so drift here is the
        permissive direction -- the model believes a cutscene can fire on arrival under a
        guard the game would not accept."""
        for j, i in enumerate(m.init_entry_idx):
            if 0 <= i < len(m.entries) and j < len(m.init_entries):
                m.init_entries[j] = m.entries[i]

    def _chain_entries(self, ms):
        """A cutscene armed by ANOTHER cutscene inherits its preconditions.

        KQ6's catacombs exit hinges on this: `freeCeleste` walks you out to the surface with an
        empty guard, because it is armed deep inside `minotaurCharging` -- which is itself only
        armed once the minotaur has seen you. Read alone, the escape looks free and the catacombs
        never become the sealed pocket they are.

        The armer's entries are alternatives, so they contribute a DISJUNCTION; conjoined with the
        path condition at the arming site. Bounded: only when the armer has a small entry set (a
        big one says little and would blow the guard up), and only one level, since the chains that
        matter are short and a fixpoint over mutually-arming scripts is not worth the risk."""
        by_name = {m.inst: m for m in ms}
        for m in ms:
            for i, armer in enumerate(m.entry_armers):
                a = by_name.get(armer[0]) if armer else None
                if a is None or a is m or not a.entries or len(a.entries) > 3:
                    continue
                alts = [g for _k, g in a.entries if g is not None]
                if not alts or len(alts) != len(a.entries):
                    continue                    # some arming of the armer is unconditional
                pre = alts[0] if len(alts) == 1 else GOr(list(alts))
                K, g = m.entries[i]
                m.entries[i] = (K, GAnd([pre, g]) if g is not None else pre)

    def _var_dests(self, script):
        """{(vtype, index): {room: guard}} for every variable this script gives to `newRoom:`.

        Scanned once per script and cached, because the resolution walks the whole script and a
        script can hold several machines. The values come from `extract.var_room_values`, which
        the flat-edge builder has used since LSL2's revolving door -- shared rather than
        reimplemented, since having this rule in only one of the two places is what left LB2's
        act break emitting PARK and orphaned the act advance from its own edge."""
        got = self._vdest_cache.get(script.number)
        if got is None:
            got = self._vdest_cache[script.number] = {}
            for o in script.objects:
                for _mn, ast in o.methods.items():
                    for n in I.walk(ast):
                        if n.get("t") != "Send":
                            continue
                        _recv, msgs = I.send_pairs(n)
                        for sel, params in msgs:
                            if sel != "newRoom" or not params:
                                continue
                            p = params[0]
                            if I.as_int(p) is not None:
                                continue
                            if not (I.is_global(p) or I.is_local_or_temp(p)):
                                continue
                            key = (p.get("vtype"), p.get("index"))
                            if key not in got:
                                got[key] = X.var_room_values(self.ir, script.number, p)
        return got

    def _restores(self, body):
        """Restore-of-control AND a clock: the state opens a WINDOW the player acts in.

        The restore send alone is not the fact -- every SCI1.1 cutscene ends with a `handsOn:`,
        and marking those made EVERY doomed machine on the corpus pre-emptable (measured: KQ6's
        fatal_uses went from three play-validated rows to zero). What distinguishes LB2's trunk
        state -- the one the rule exists for -- is that it hands control back AND starts the
        Script class's own timer in the same body: `(global1 handsOn:)` + `(= seconds ...)` is
        "you are free, and something is coming". The timing properties come from the engine's
        Script class table (`seconds`/`ticks`/... are whatever it declares), not from a list
        here; the value written is deliberately ignored, because LB2 writes it as
        `(if (HaveMouse) 6 else 12)` and the window's LENGTH is not the question."""
        restore = timer = False
        for n in I.walk(body):
            t = n.get("t")
            if t == "Send":
                try:
                    _recv, msgs = I.send_pairs(n)
                except Exception:                      # noqa: BLE001
                    continue
                restore = restore or any(sel in self._restore_sels for sel, _p in msgs)
            elif t == "Assignment":
                k = (n.get("kids") or [None])[0]
                if isinstance(k, dict) and k.get("t") == "Property" \
                        and k.get("name") in self._timer_props:
                    timer = True
            if restore and timer:
                return True
        return False

    @staticmethod
    def _chases(body):
        """Does this state body arm a `setMotion: Chase ... self` -- a pursuit of the moving
        player whose completion cue IS the catch? See the `chase_states` field for why that
        state is a race the player can decline, and `missability.ownedby_death_folds` for the
        consumer. The Self param is required: a Chase without a cue never advances this
        machine, so no death of ours sits behind it."""
        for n in I.walk(body):
            if n.get("t") != "Send":
                continue
            try:
                _recv, msgs = I.send_pairs(n)
            except Exception:                          # noqa: BLE001
                continue
            for sel, params in msgs:
                if (sel == "setMotion" and params
                        and params[0].get("t") == "Class"
                        and params[0].get("name") == "Chase"
                        and any(p.get("t") == "Self" for p in params)):
                    return True
        return False

    def _local_regs(self, script_number):
        """{synthetic gi: reset value} for `script_number`'s own lowered room locals."""
        got = self._lreg_cache.get(script_number)
        if got is None:
            idx = getattr(self.ir, "_room_local_index", None) or {}
            resets = (getattr(self.ir, "_room_local_resets", None) or {}).get(script_number, {})
            got = self._lreg_cache[script_number] = \
                {gi: resets.get(gi, 0) for gi, (sn, _i) in idx.items() if sn == script_number}
        return got

    def _build(self, script, obj):
        m = Machine(script.number, obj.name, start=obj.props.get("start", 0))
        m.glob_dom = _glob_domains(script)
        m.var_dests = self._var_dests(script)
        m.local_regs = self._local_regs(script.number)
        cs = obj.methods["changeState"]
        sw = self._top_switch(cs)
        if sw:
            for c in sw["kids"][1:]:
                if c["t"] == "Case":
                    k = I.as_int(c["kids"][0])
                    if k is not None:
                        m.bodies[k] = c["kids"][1]
                        ops = []
                        self._ops(c["kids"][1], [], ops, script.number, state_k=k)
                        m.states[k] = ops
                        if self._chases(c["kids"][1]):
                            m.chase_states.add(k)
                        # A state that HANDS CONTROL BACK (the derived handsOn) is one the
                        # player lives through with the verbs available -- which is what lets
                        # `fatal_uses` see a wait-on-the-clock state as pre-emptable. Recorded
                        # on the state, not the path: the send is unconditional room dressing
                        # in every observed case, and a guarded restore would only over-mark
                        # in the PERMISSIVE direction for the one consumer this feeds.
                        if self._restore_sels and self._restores(c["kids"][1]):
                            m.restores_control.add(k)
        # entries: ANY object's init/handleEvent/doit that does `(<inst> changeState: K)`
        # (guarded) -- the machine is often started/redirected by the ROOM object, not by
        # itself (rm65.init -> rm65Script changeState: survive-or-die on gCurrentStatus).
        #
        # ...UNDER THE ARMING OBJECT'S PRESENCE CONDITION, exactly as the `setScript:` scan
        # below has always done (`owner=`). This path did not, and an object's methods went
        # through the two paths with DIFFERENT conditions -- which broke the invariant
        # `_clause_key` rests on ("a clause and the state it arms necessarily share" their
        # positive item preconditions, missability.py). KQ5 rm12 is the specimen: the dog's
        # throw handler does `(gRoom setScript: throwStick)`, so the machine entry carried the
        # dog's cast `(or (has 8) (has 16))` while the handler's own `put: <item> 12` did not,
        # the two keys diverged, and the throw -- which plainly arms a machine -- was classified
        # by `pure_sinks` as a consumption that ACCOMPLISHES NOTHING.
        cast = self._cast(script)
        for other in script.objects:
            is_self = (other.name == m.inst)   # `self` in other's method means `other`,
            #   so a `(self changeState:K)` is an entry to THIS machine ONLY when other IS it.
            #   Cross-object starts must name the instance: `(<m.inst> changeState:K)`.
            og = X.cast_guard(cast, other.name)
            for mn in ("init", "handleEvent", "doit"):
                if mn in other.methods:
                    self._entries(other.methods[mn], [] if og is None else [og], m,
                                  script.number, set(), source=mn, is_self_obj=is_self)
        # setScript entries: `(actor setScript: <m or (m new:)>)` in ANY method (incl a
        # changeState body -- hench1Script state1 -> henchScript). These START m at state 0.
        # The extractor dropped them, so setScript-driven machines (the henchmen chasers, the
        # bottle) never ran -- which is WHY the absent-start fall-through hack was needed.
        for other in script.objects:
            owner = X.cast_guard(cast, other.name)   # in the cast only when...? see cast_conditions
            for mn, body in other.methods.items():
                # If the arming site is inside ANOTHER machine's changeState, remember whose AND
                # at which state: that machine's preconditions up to that point are ours too, and
                # a cutscene decides its outcome long before the state that pays it off (KQ6's
                # minotaur fight branches at 8 and arms the walk-out at 14). Scanned per CASE so
                # the state is known; the whole body otherwise loses it.
                if (mn == "changeState" and other.name != m.inst
                        and "changeState" in other.methods):
                    sw = self._top_switch(body)
                    for c in (sw["kids"][1:] if sw else []):
                        if c.get("t") != "Case":
                            continue
                        k = I.as_int(c["kids"][0])
                        if k is None:
                            continue
                        self._scan_setscript(c["kids"][1], [], m, source=mn,
                                             armer=(other.name, k), owner=owner,
                                             selfobj=other.name)
                    continue
                # An arming inside another MACHINE's doit/cue is a continuation of that machine
                # exactly as a changeState-case arming is, so it carries the same armer link and
                # `_chain_entries` conjoins that machine's own preconditions. KQ6's mists shore
                # ambush is the instance this was deaf to: `waitForCapture` (armed by rm550::init
                # only under flag 25 & !14) arms `captured` from its `doit`, and without the link
                # the seizure that delivers the player to the cage sorter read as free-standing.
                # `_chain_entries`' own bounds still apply: an armer that is not a built machine,
                # has no entries, or has any unconditional entry changes nothing.
                armer = ((other.name, None)
                         if other.name != m.inst and "changeState" in other.methods else None)
                self._scan_setscript(body, [], m, source=("init" if mn == "init" else mn),
                                     owner=owner, armer=armer, selfobj=other.name)
        # ...and this script's own PROCEDURES, which were never scanned at all. A machine armed
        # from a proc in its own script had no entry whatever: KQ6's realm cutscene is armed by
        # `proc344_1`, and the item-state test guarding it went with it.
        for pname, pbody in script.procs.items():
            self._scan_setscript(pbody, [], m, source="proc",
                                 owner=X.any_guard(self.proc_calls.get(pname)))
        # ...and the same scan over the OTHER scripts that arm this machine by `(ScriptID s n)`.
        # Deduplicated per body: one method can arm the same machine on several branches, and
        # _scan_setscript already records one entry per arming site within a body.
        seen = set()
        for (arm_script, oname, mn, body) in self.arms.get((script.number, m.inst), ()):
            key = (arm_script, mn, id(body))
            if key in seen:
                continue
            seen.add(key)
            s2 = self.ir.scripts.get(arm_script)
            self._scan_setscript(body, [], m, source=("init" if mn == "init" else mn),
                                 owner=(X.cast_guard(self._cast(s2), oname) if s2 else None),
                                 selfobj=oname)
        self._drop_continuation_entries(m)
        self._inherit_local_continuations(m, script)
        return m

    def _inherit_local_continuations(self, m, script):
        """An entry gated on a room LOCAL inherits the condition of whoever SETS that local.

        The sibling of `_drop_continuation_entries`, and the same insight from the other side. That
        one recognises a `cue` arming as the continuation of something already running and drops it;
        this one recognises the LATCHED form -- one handler records what the player asked for, and a
        later arming replays it -- and supplies the condition instead of discarding the entry.

        SCI writes an interrupted action that way whenever walking to a thing can be pre-empted.
        KQ6's rm520 is the specimen:

            theHuntersLamp::doVerb 5   (= local1 1) (gEgo setScript: getLamp)  ; you clicked the lamp
            rm520::doit                ... (self setScript: bravePond)         ; the pond pre-empts
            bravePond::changeState 5   (cond (local1 (gEgo setScript: getLamp)) ...)  ; and resumes

        Read standalone, that third arming is gated on nothing an item model can see, so `getLamp`
        offers an alternative with no `LOC(19 ownedBy room)` in it -- and a destruction is permanent
        only if EVERY way of re-acquiring demands the object still be lying there. One vacuous
        alternative is enough to make trading the lamp away read as harmless, which is the whole
        finding (the peddler leaves; there is no second trade).

        Locals start at 0 in SCI, so "this local is non-zero" is EXACTLY the union of the writes
        that made it so -- an identity, not an approximation. That is what makes strengthening an
        entry legitimate here, and it is also what makes the bail-outs mandatory, because the
        identity only holds if every write is accounted for. Strengthening an entry is the direction
        that deletes real movement (it cost the scarf twice), so it stands down whenever the picture
        is incomplete:
          * only conjuncts on the top-level AND spine, where the test really is required;
          * a write we cannot pin to a literal value (computed, incremented, decremented) is
            reported by `local_write_conditions` as `None` and makes us stand down for that local;
          * no non-zero writer found at all -> stand down (we learned nothing, which is not the
            same as "it cannot happen");
          * `any_guard` already yields None if any writer is unconditional, and None changes
            nothing.
        Temps are excluded: a temp is scratch within one call and cannot carry a latch between the
        handler that sets it and the arming that reads it."""
        loc = self._locals(script)
        zero_lregs = frozenset(gi for gi, v in m.local_regs.items() if v == 0)
        for i, (K, g) in enumerate(m.entries):
            if g is None:
                continue
            extra = []
            for key in _local_conjuncts(g, zero_lregs):
                writes = loc.get(key)
                if not writes or any(v is None for v, _pc in writes):
                    continue
                pre = X.any_guard([pc for v, pc in writes if v != 0])
                if pre is not None:
                    extra.append(pre)
            if extra:
                m.entries[i] = (K, GAnd([g] + extra))

    def _locals(self, script):
        """`local_write_conditions` for a script, computed once -- `_build` runs per machine."""
        c = self._local_cache.get(script.number)
        if c is None:
            c = self._local_cache[script.number] = X.local_write_conditions(
                script, cast=self._cast(script),
                proc_guard=lambda pn: X.any_guard(self.proc_calls.get(pn)),
                machine_guard=lambda on: self._entry_guard.get((script.number, on)),
                lregs=frozenset(self._local_regs(script.number)))
        return c

    @staticmethod
    def _drop_continuation_entries(m):
        """An UNCONDITIONAL arming found in a `cue` method is not a way IN; drop it.

        A room's `cue` runs only because a script the room was already running finished, so a
        `setScript:` there CONTINUES that script rather than offering the player a fresh way to
        start this one. Its real precondition is whatever armed the previous script -- upstream,
        in the arming chain, which we do not follow. Recorded as an unconditional entry it says
        "this machine can start at any time", and since entries are ALTERNATIVES that single
        vacuous member erases every real precondition the other armings carry.

        KQ6's rm407 is the case. `emptyHandedDeath` is armed four ways; one of them is

            (method (cue) (global1 handsOff:) (global2 setScript: emptyHandedDeath))

        and another is the real gate, `... (not (has: 18)) ...` -- you die in the hole-in-the-wall
        room without the hole. With the `cue` arming counted, the death looks unconditional, the
        item requirement vanishes, and the labyrinth stops being a trap for a player who walked in
        without it.

        Narrow on purpose, because dropping an alternative STRENGTHENS a guard and that is the
        direction that invents softlocks:
          * only when the cue arming is UNCONDITIONAL -- a conditional one carries real information
            and is kept, even though the same argument would apply;
          * only when some other entry survives, so a machine armed solely from `cue` is untouched
            and keeps its (permissive) unconditional entry.
        Measured over six games: LSL2, KQ4 and SQ3 contain NO cue armings at all, Dagger's 28 are
        all either cue-only or already conditional, and exactly three machines change -- KQ6's
        `emptyHandedDeath` and `queensLeave`, and KQ5's `faceMove`."""
        drop = {i for i, src in enumerate(m.entry_sources)
                if src == "cue" and m.entries[i][1] is None}
        if not drop or len(drop) == len(m.entries):
            return
        keep = [i for i in range(len(m.entries)) if i not in drop]
        m.entries = [m.entries[i] for i in keep]
        m.entry_locals = [m.entry_locals[i] for i in keep]
        m.entry_armers = [m.entry_armers[i] for i in keep]
        m.entry_sources = [m.entry_sources[i] for i in keep]
        m.entry_recv = [m.entry_recv[i] for i in keep]
        # `init_entry_idx` points INTO `entries`, so re-index it here or the arrival copies
        # would later be restated from whatever entry slid into the dropped row's place. A
        # dropped row is always a `cue` arming and an init entry never is, so nothing an init
        # entry points at can vanish -- but the positions still move.
        remap = {old: new for new, old in enumerate(keep)}
        m.init_entry_idx = [remap.get(i, -1) for i in m.init_entry_idx]

    def _targets(self, param, m):
        """Does this `setScript:` argument name machine `m`? An Object reference is scoped to the
        script it appears in, so only the name is compared; a `(ScriptID s n)` carries its own
        script and must match m's too, or two same-named Scripts in different scripts would be
        conflated."""
        tgt = _setscript_target(param, self.ir)
        if not tgt:
            return False
        s, name = tgt
        return name == m.inst and (s is None or s == m.script)

    def prime(self):
        """Resolve the casts/entries mutual recursion by iterating it, twice.

        A machine's ENTRY is built from the casts (an arming that sits in the method of an object
        the room only sometimes `init:`s only fires under that condition), and a cast is built from
        the entries (an `init:` inside a `changeState` runs only when that machine was armed and
        got that far). Neither can be computed first, so compute both from the permissive answer
        and feed the result back: pass 0 sees `_entry_guard = {}` and reproduces exactly what this
        builder did before, pass 1 rebuilds the casts from pass 0's entries, and a pass that
        changes nothing stops.

        Iterated rather than shortcut on purpose. The shortcut -- a flat scan of every `setScript:`
        naming the machine, used as if it were the entry -- was tried twice and reverted twice: it
        has not been through `_drop_continuation_entries` or `_chain_entries`, so it can be
        STRONGER than the real entry, and gating a cast on a too-strong guard deletes movement the
        game allows. Convergence is not assumed either: `_entry_guard` only ever appears inside a
        conjunction, so a round can only narrow, and the loop is bounded regardless.

        Optional -- a caller that never primes gets the previous behaviour. `opmodel` primes."""
        for _round in range(2):
            eg = {}
            for rn, s in self.ir.scripts.items():
                for m in self.machines(s):
                    # Alternatives, and permissive (None) if any of them is unconditional -- the
                    # same reading `any_guard` gives everywhere else.
                    eg[(rn, m.inst)] = X.any_guard([g for _k, g in m.entries]) if m.entries else None
            if eg == self._entry_guard:
                break
            self._entry_guard = eg
            self._cast_cache.clear()
            self._local_cache.clear()     # derived from the casts, so it goes stale with them
        return self

    def _cast(self, script):
        """`cast_conditions` for a script, computed once -- `_build` runs per machine."""
        c = self._cast_cache.get(script.number)
        if c is None:
            c = self._cast_cache[script.number] = X.cast_conditions(
                script, proc_guard=lambda pn: X.any_guard(self.proc_calls.get(pn)),
                machine_guard=lambda on: self._entry_guard.get((script.number, on)),
                init_sels=X.init_selectors(self.ir),
                delegate_sels=X.delegate_slots(self.ir),
                foreign_inits=self.foreign_inits.get(script.number))
        return c

    def _scan_setscript(self, node, pc, m, source, armer=None, owner=None, selfobj=None):
        """Find `(x setScript: <ref>)` where <ref> is m, record an entry to m at state 0 with the
        path condition, AND carry the LOCAL WRITES the arming context made before the setScript. A
        machine reads its own script's locals, so a local the arming branch set gates the machine's
        internal flow -- rm214 sets `local1:=1` in the same branch that arms knockDoor, and knockDoor
        only reaches `newRoom: 18` while local1==1. Control flow is shared (walk_stream)."""
        from extract import walk_stream, verb_param_scope
        events = []                               # ordered: ("w",(vt,idx),val,pc) | ("a",pc)
        def leaf(n, p):
            t = n.get("t")
            if t == "Assignment":
                ks = n.get("kids") or []
                d = ks[0] if ks else None
                if (d and d.get("t") == "Variable" and d.get("vtype") in ("Local", "Temp")
                        and len(ks) > 1 and I.as_int(ks[1]) is not None):
                    events.append(("w", (d["vtype"][0], d["index"]), I.as_int(ks[1]), list(p)))
                elif (d and d.get("t") == "Variable" and d.get("vtype") == "Global"
                        and d.get("index") in m.local_regs
                        and len(ks) > 1 and I.as_int(ks[1]) is not None):
                    # A lowered room local IS a local of this script: the arming context's write
                    # to it gates the machine's internal flow exactly as a raw local write did
                    # before lowering. Carried under the synthetic-global index (an int key, so
                    # it can never collide with the (vt,idx) tuples or REG_KEY).
                    events.append(("w", d["index"], I.as_int(ks[1]), list(p)))
            elif t == "Send":
                _r, msgs = I.send_pairs(n)
                slot = None
                if isinstance(_r, dict):
                    if _r.get("t") == "Variable" and _r.get("vtype") == "Global":
                        slot = ("G", _r["index"])
                    elif _r.get("name"):
                        slot = ("O", _r["name"])
                    elif _r.get("t") == "Self" and selfobj:
                        # `(self setScript: X)` IS a slot arming -- `self` is the object whose
                        # method we are standing in, and it holds the one Script slot exactly as a
                        # named receiver does. Recorded as ("O", <that object>), the same key the
                        # named spelling produces, so the two spellings compete correctly.
                        #
                        # It read as NO SLOT, and `death_traps` bails on `if not slots` -- so a
                        # room that kills you by arming its own death script was not a trap at all.
                        # LB2's act-5 walls are precisely that: `rm350`/`rm500`'s `init` do
                        # `(self setScript: sLauraDies)` under `global12 == 420 AND global123 == 5`,
                        # a fully-modelled arming whose negation is exactly "do not arrive from the
                        # pursuit region during act 5" -- and it was discarded for want of a
                        # receiver name.
                        slot = ("O", selfobj)
                for sel, params in msgs:
                    if sel != "setScript" or not params or not self._targets(params[0], m):
                        continue
                    # `setScript: <script> <caller> <register>` -- the third argument tells the
                    # Script WHICH job it is doing, and its body branches on it. Carried like a
                    # local write so the entry only reaches the arm it selected: without it,
                    # KQ6's `walkOut 0 1` (flag-gated, out to the surface) and `walkOut 0 0`
                    # (back into the maze) merge, and the gated escape reads as free.
                    reg = X.REG_KEY if len(params) > 2 and I.as_int(params[2]) is not None else None
                    events.append(("a", list(p), I.as_int(params[2]) if reg else None, slot))
        # A doVerb that arms this machine with `setScript:` gates it on the item the player used --
        # `(== param1 <item.message>)` -> OWN. verb_param_scope makes `atom` see that inside the
        # arming path condition (the machine lift shares extract.atom but does not set the context).
        with verb_param_scope(source):
            walk_stream(node, pc, leaf)
        for i, ev in enumerate(events):
            if ev[0] != "a":
                continue
            apc = ev[1]
            loc = {}
            for e in events[:i]:                  # writes that RAN before this arm, on its path
                if e[0] == "w" and _pc_covers(e[3], apc):
                    loc[e[1]] = e[2]
            if len(ev) > 2 and ev[2] is not None:
                loc[X.REG_KEY] = ev[2]            # the `register` this arming selected
            # ...and the arming cannot be freer than the object whose method it sits in: a method
            # of an object the room only conditionally `init:`s only runs under that condition.
            self._add_entry(m, 0, _conj(apc + [owner]), loc, source == "init", armer, source,
                            recv=(ev[3] if len(ev) > 3 else None))
            #   are ADDITIONALLY bundled onto room arrival, not instead -- still normal entries too

    def _add_entry(self, m, state, guard, locals_, is_init, armer=None, source=None, recv=None):
        """Append an entry AND its carried locals, keeping the parallel lists in lockstep."""
        m.entries.append((state, guard))
        m.entry_locals.append(dict(locals_))
        m.entry_armers.append(armer)
        m.entry_sources.append(source)
        m.entry_recv.append(recv)
        if is_init:
            m.init_entries.append((state, guard))
            m.init_entry_locals.append(dict(locals_))
            m.init_entry_idx.append(len(m.entries) - 1)

    def _top_switch(self, cs):
        """The `(switch (= state param1) ...)` that IS the machine -- identified by its head
        assigning the `state` property, not by position."""
        for n in I.walk(cs):
            if n["t"] == "Switch":
                head = n["kids"][0]
                if head["t"] == "Assignment":
                    dst = head["kids"][0]
                    if dst.get("t") == "Property" and dst.get("name") == "state":
                        return n
        return None

    def _entries(self, node, pc, m, script, seen, source=None, is_self_obj=False):
        """Find player-triggered `(<me> changeState: K)` entries and the FULL path condition that
        gates them, FOLLOWING PublicCall/LocalCall (the changeState often lives inside a proc,
        with the guard -- e.g. `has: Passport` -- on a Cond case above the call).

        Control flow is shared (walk_stream); this used to hand-roll If and Cond, in a third copy
        of the same code."""
        from extract import walk_stream
        walk_stream(node, pc,
                    lambda n, p: self._entry_leaf(n, p, m, script, seen, source, is_self_obj))

    def _entry_leaf(self, node, pc, m, script, seen, source, is_self_obj):
        tp = node["t"]
        if tp == "Send":
            recv, msgs = I.send_pairs(node)
            # `(self changeState:K)` only when scanning THIS machine's own object; OR
            # `(theMachineInstance changeState:K)` from ANOTHER object -- rm65.init does
            # `(rm65Script changeState: 4)` gated on gCurrentStatus to start the survive
            # segment. Matching bare Self across objects mis-attributed rm34Script's
            # `changeState: 9/15` to henchScript (the disguise), etc.
            targets_me = ((recv.get("t") == "Self" and is_self_obj)
                          or (recv.get("t") == "Object" and recv.get("name") == m.inst))
            if not targets_me:
                return
            for sel, params in msgs:
                if sel == "changeState" and params:
                    k = I.as_int(params[0])
                    if k is not None:
                        self._add_entry(m, k, _conj(pc), {}, source == "init")
        elif tp in ("PublicCall", "LocalCall"):
            tgt, name = I.proc_ref(self.ir, node, script)
            body = self.procs_by.get((tgt, name))
            if tgt != 255 and body is not None and name not in seen:
                self._entries(body, pc, m, tgt, seen | {name}, source, is_self_obj)

    def _ops(self, node, pc, out, room=None, state_k=None):
        """Walk a state body, composing path conditions, appending guarded ops.

        Control flow comes from `extract.walk_stream` / `ir.control_shape`; this used to
        re-implement If/Cond/Switch itself, in code identical to extract's and opmodel's.

        `room` is the script the body lives in, threaded only so an indirect `newRoom:` can be
        resolved against that script's own assignments -- see `_send_op`. `state_k` is which
        state's body this is, threaded only so `(++ state)` / `(-- state)` can be resolved to
        the SETSTATE they are (relative to K, see the module docstring)."""
        from extract import walk_stream
        walk_stream(node, pc, lambda n, p: self._op_leaf(n, _conj(p), out, room, state_k))

    def _op_leaf(self, node, g, out, room=None, state_k=None):
        """What one statement means to the machine model -- the part that is ours, not shared."""
        tp = node["t"]
        if tp == "Send":
            self._send_op(node, g, out, room)
        elif tp == "Assignment":
            self._assign_op(node, g, out)
        elif tp in ("Increment", "Decrement"):
            dst = node["kids"][0]
            if dst.get("t") == "Property" and dst.get("name") == "state" \
                    and state_k is not None:
                # `(++ state)` in state K: the pending cue's changeState(state+1) now lands
                # one further on -- identical in effect to `(= state K+1)`. Two bumps on one
                # path would need composing; no corpus spells it, and one bump is the idiom.
                out.append(Op("SETSTATE", g, state_k + (1 if tp == "Increment" else -1)))
            else:
                self._counter_op(dst, "inc" if tp == "Increment" else "dec", None, g, out)

    def _send_op(self, node, g, out, room=None):
        recv, msgs = I.send_pairs(node)
        for sel, params in msgs:
            if sel == "newRoom" and params:
                r = I.as_int(params[0])
                if r is not None:
                    out.append(Op("EXIT", g, r))
                elif room is not None and (I.is_global(params[0])
                                           or I.is_local_or_temp(params[0])):
                    # INDIRECT destination inside a state body -- `(newRoom: <var>)`. The flat
                    # edge builder has resolved this since LSL2's revolving door; the machine
                    # lift never did, and that costs more than an edge, because a state's
                    # REGISTER WRITES only reach `edge_meta` when the state EXITS. LB2's act
                    # break is one state -- `(++ global123)` then `(newRoom: local0)` -- so the
                    # act advance was orphaned from the crossing that performs it and the model
                    # read rm26 as a room where any act may be selected. One resolver, shared,
                    # for exactly the reason it keeps being two ([[same-rule-two-places]]).
                    #
                    # Each destination carries the condition it was ASSIGNED under, which is what
                    # keeps a routing room from becoming a free hub between everywhere it can
                    # send you. ANDed with the state's own path condition -- both held.
                    for dst, extra in X.var_room_values(self.ir, room, params[0]).items():
                        out.append(Op("EXIT", _conj([g, extra]), dst))
            elif sel == "changeState" and recv.get("t") == "Self" and params:
                k = I.as_int(params[0])
                if k is not None:
                    out.append(Op("JUMP", g, k))
            else:
                # Same recogniser compile uses -- these two walkers must not drift.
                for tr in X.item_transfers(recv, sel, params):
                    if tr[1] == EGO:
                        out.append(Op("GET", g, tr[0]))
        if _is_cue_send(recv, msgs):
            out.append(Op("ADVANCE", g))

    def _assign_op(self, node, g, out):
        dst, src = node["kids"][0], node["kids"][1]
        if dst.get("t") == "Variable" and dst["vtype"] == "Global":
            gi, v = dst["index"], I.as_int(src)
            if v is not None:
                if self.is_death(gi, v):
                    out.append(Op("DEATH", g))
                else:
                    out.append(Op("WRITE", g, gi, v))
        elif dst.get("t") == "Property" and dst.get("name") in ("seconds", "cycles", "ticks"):
            out.append(Op("ADVANCE", g))            # timing set -> cue will fire
        elif dst.get("t") == "Property" and dst.get("name") == "state":
            k = I.as_int(src)
            if k is not None:
                out.append(Op("SETSTATE", g, k))
        elif dst.get("t") in ("Variable",) and dst["vtype"] in ("Local", "Temp"):
            v = I.as_int(src)
            self._counter_op(dst, "set", v, g, out)

    def _counter_op(self, dst, kind, val, g, out):
        if dst.get("t") == "Variable" and dst["vtype"] in ("Local", "Temp"):
            out.append(Op("COUNTER", g, ("L" if dst["vtype"] == "Local" else "T", dst["index"]),
                          (kind, val)))


if __name__ == "__main__":
    import os
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else config.ACTIVE.ir_path
    ir = I.load_ir(path)

    def is_death(gi, v):
        return gi == 101 and v == 1001      # LSL2 death_signal gCurrentStatus==1001

    mb = MachineBuilder(ir, is_death)
    for rn in (64, 138):
        s = ir.script(rn)
        for m in mb.machines(s):
            print(m, " start=", m.start, " entries=", [(k, g is not None) for k, g in m.entries])
            for k in sorted(m.states):
                ops = m.states[k]
                if ops:
                    desc = ", ".join(f"{o.kind}{'' if o.a is None else o.a}{'' if o.b is None else '='+str(o.b)}"
                                     f"{'[g]' if o.guard is not None else ''}" for o in ops)
                    print(f"   state {k:2d}: {desc}")


def _glob_domains(script):
    """{global: sorted values} for globals this script uses as a COUNTER.

    Scoped two ways on purpose. Only globals the script actually `++`/`--` are included, so
    nothing changes for a game that never counts in a global; and the values come from the
    literals THIS SCRIPT tests the global against -- `(switch G (0 ...) (5 ...))`, `(== G 3)` --
    which is the same "read the literals the code compares against" rule extract uses to resolve
    a computed room destination.

    LB2's act break is the motivating case: script 26 switches on global123 over 0..5 and is the
    only place that advances it, so the domain and the increment sit in the same script. A game
    that increments a score it never compares yields {} and the increment is dropped.
    """
    incs, vals = set(), {}
    bodies = [a for o in script.objects for a in o.methods.values()]
    bodies += list((getattr(script, "procs", None) or {}).values())
    for ast in bodies:
        for n in I.walk(ast):
            tp = n["t"]
            if tp in ("Increment", "Decrement") and I.is_global(n["kids"][0]):
                incs.add(n["kids"][0]["index"])
            elif tp == "Switch" and I.is_global(n["kids"][0]):
                gi = n["kids"][0]["index"]
                for c in n["kids"][1:]:
                    if c["t"] == "Case":
                        v = I.as_int(c["kids"][0])
                        if v is not None:
                            vals.setdefault(gi, set()).add(v)
            # EQUALITY tests only. `(> G 3)` describes a RANGE, not a value the counter takes,
            # and harvesting it would put 500 in the domain of any score compared against 500.
            # A switch case label and an `==`/`!=` both name one concrete value; that is the
            # evidence we want.
            elif tp in ("Eq", "Ne") and len(n["kids"]) == 2:
                a, b = n["kids"]
                for x, y in ((a, b), (b, a)):
                    if I.is_global(x) and I.as_int(y) is not None:
                        vals.setdefault(x["index"], set()).add(I.as_int(y))
    return {gi: sorted(vs) for gi, vs in vals.items() if gi in incs}
