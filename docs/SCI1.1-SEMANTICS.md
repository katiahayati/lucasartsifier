# SCI1.1 semantics map — derived from the ScummVM SCI engine

**Provenance.** Read-only study of the ScummVM SCI engine source (`engines/sci/`), pinned at
commit `cd35134` (shallow/sparse clone at `tools/scummvm-ref/`). ScummVM is GPL; this document
records *facts* about how the interpreter behaves (with `file:line` pointers so any claim can be
re-checked) — **no engine code is copied into our tree**, and none is reused. The point is to turn
SCI1.1 extraction from "rediscover each mechanism per game" into "implement the known engine
semantics." Companion detail (this session's scratchpad): `scummvm-analysis/0{1..5}-*.md`.

All `file:line` below are relative to `tools/scummvm-ref/engines/sci/`.

---

## 0. The headline for us

- **The catacombs/maze positional navigation is statically recoverable.** `onControl` returns a
  16-bit *color bitmask*; the color→room map is 100% in the decompiled script, not in a hidden
  engine table. We can emit these edges without any PIC bitmap. **This is the #1 unlock.**
- **Death is 100% game-script — the engine has no concept of "died".** Even ScummVM cannot detect
  death screens (it disables autosave because of it). Our version-aware, script-structural death
  model is not a hack; it is the *only* available approach. Validated.
- **Every level we already model — `newRoom`, the `setScript`/`changeState` machine, `has`/`doVerb`
  requirements, flags as a game-script bit-array — is confirmed game-script convention**, exactly
  where we put it. The engine caches none of those selectors.
- **Object class resolution has a cleaner, engine-faithful rule** than our current `super OR
  species`: *an instance's class is its `super` field; a class is itself (`-info- & 0x8000`).*
  Our rule is functionally correct; this is principled polish.
- **A crisper SCI1.1 predicate exists** (separate heap resource / object-header shape) than our
  0xffff-majority vote — though the vote is empirically sound because SCI1.1 instances genuinely
  carry `species==0xffff`.

---

## 1. Version detection (`is_sci11`)

ScummVM fixes one global `g_sciVersion` at load, entirely from **resource-file format**, in
`ResourceManager::detectSciVersion()` (`resource.cpp:2622-2813`). The `SciVersion` in the
detection tables is only a GUI hint, not the runtime authority. Full enum: `detection.h:136-151`
(SCI0_EARLY/LATE, 01, 1_EGA_ONLY, 1_EARLY/MIDDLE/LATE, 1_1, 2, 2_1_*, 3).

**Authoritative SCI1.1 discriminator: a separate `Heap` resource exists.** `resource.cpp:2731-2736`:
if `testResource((Heap,0))` succeeds → `SCI_VERSION_1_1`. In SCI0/SCI1 the heap is embedded in the
single script resource; SCI1.1 splits `Script` + `Heap` into two resources (`resource.cpp:3044-3056`,
`script.cpp:96-122`). Corroborating axes: 6- vs 5-byte map entries, packed-size +4 volume offset,
`kViewVga11` views.

**`species==0xffff` is not the engine's marker** — it is a per-object "-1 = no parent class"
sentinel used identically in every version (`object.cpp:241-261`). *But* in SCI1.1 every instance
carries it (§2), so our majority-vote heuristic detects a real SCI1.1 property; it is sound, just
indirect.

**KQ5 groups with SCI0, not SCI1.1, on object encoding.** KQ5 is SCI1 middle/late; the encoding
branch is `getSciVersion() <= SCI_VERSION_1_LATE` (`object.cpp:49`). This is *why* mining KQ5 never
surfaced the SCI1.1 idioms — on every divergent axis KQ5 sits on the SCO0 side.

**For us.** The 0xffff-majority `is_sci11` is fine to keep. If we ever want a crisper signal and the
decompiler exposes it: (a) *does the game have a separate heap segment?* (exact analog of the engine
test), or (b) object-header shape — SCI1.1 puts the magic word at object offset 0 and `-info-` at
byte 14, vs SCI0/1 magic at −8 and `-info-` at byte 4 (§2). Low priority; only if the vote misfires.

---

## 2. Object / heap model

`Object::_offset = (version < SCI_VERSION_1_1) ? 0 : 5` (`object.h:73`) shifts where the four
"special" selectors live. Field order is **species, super, -info-, name** in both regimes:

- **SCI0/SCI1** (`_offset=0`): magic at obj−8; species `+0`, super `+2`, `-info-` `+4`, name `+6`
  (`object.h:63-64`). `-info-` byte offset = 4.
- **SCI1.1** (`_offset=5`, heap object): 5-word header (magic/count/propDict/methods/classScript),
  then species `+10`, super `+12`, `-info-` `+14`, name `+16` (`object.h:65-66`, `script.cpp:1077-1080`).

**Class vs instance = the `-info-` bit `kInfoFlagClass = 0x8000`** (`object.h:53,266`), all versions.
Classes set it; instances/clones clear it. `kClone` clears class + sets `kInfoFlagClone`
(`kscripts.cpp:231-232`).

**Species vs super, by version:**
- SCI0/SCI1 instance: class-number is in **species** *and* in **super** (either resolves).
- SCI1.1 instance: **species = 0xffff** (genuine sentinel → `getClassAddress(0xffff)=NULL_REG`,
  `seg_manager.cpp:1064`); class-number is in **super** (`script.cpp:1087-1088`).
- A *class* (any version): super = the **parent** class, not itself.

**The engine's own class resolver uses `super` only, every version** — `Object::getClass`
(`object.cpp:173-175`) = `isClass() ? this : getObject(super)`; runtime method dispatch walks the
super chain (`selector.cpp:326-364`). Species is consulted only in SCI0 load to copy the selector
layout, and is `self` for clones — so species is the *fragile* field.

Class table: species number is a **global class ID** (index into vocab-996 table,
`seg_manager.cpp:1046-1086`); every instance references its class by that index.

**For us.** Replace `super OR species` with the engine-faithful rule:

```
resolve_class(obj):
    if obj.info & 0x8000:   # kInfoFlagClass → obj is a class
        return obj
    else:                   # instance/clone
        return class_by_number(obj.super)   # super holds the class number
```

Functionally identical on SCI0/KQ5 (where super==species==class for an instance) and correct on
SCI1.1. **Must stay LSL2/KQ4/KQ5 byte-identical** — verify before/after. Polish, not urgent.

---

## 3. Movement & control map — the positional-nav unlock (#1 priority)

**`kOnControl` returns a 16-bit bitmask of control colors** under a point or rect
(`kgraphics.cpp:540-562` arg forms; `compare.cpp:46-67`: `result |= 1 << getControl(x,y)`).
Control colors are 0–15 (`picture.cpp:476`, `& 0x0F`), so `1<<color` fits a `uint16`. Point form
(2 args) samples one pixel → result is exactly `1<<color`; rect form ORs an area.

So the game-script idioms decode directly from the **comparison constant**:
- `(== (ego onControl: ...) K)` where `K` is a power of two ⇒ "ego stands on control color
  `log2(K)`". KQ6's `(== (gEgo onControl: 1) 16)` = **color 4** (16 = 1<<4).
- `(& (ego onControl: ...) M)` ⇒ "ego touches any color in the set `M`".

**The color→room and edge→room maps are entirely in the decompiled script — there is no hidden
engine table.** The engine supplies only the pure color-mask function plus a per-cycle position
update. Two distinct uses of the control map, in different places:
- **Blocking movement**: engine `kCanBeHere`/`kCantBeHere`, but the illegal-color set is the
  *actor's* game-supplied `illegalBits` selector (`compare.cpp:145-147`), not engine-fixed.
- **Triggering a room change**: 100% game script — it reads `onControl`, tests a color, calls
  `newRoom`.

**`edgeHit` (screen-edge nav) is a game-script selector the engine never writes** — it appears only
in `script_patches.cpp` (patches *to* game code). The engine updates `ego.x/y` via `kDoBresen` and
sets `kSignalHitObstacle` only on control-map collision (`kmovement.cpp:369-370`), never on a screen
edge. So the direction→room table lives in the room object and is statically parseable.

**Movers:** `setMotion`/`mover`/`moveDone` are game-level selectors, not kernels
(`selector.cpp:112,141,170`). Chain for a positional room change:
`setMotion: MoveTo <x> <y> <cue>` → engine steps via `kDoBresen` → on arrival `mover:moveDone`
(`kmovement.cpp:386-387`) → cues the caller → script `changeState`/handler → `newRoom`. The
arrival→newRoom link is in the script, keyed off the cue — **the same cue-carry we already model**.

**For us — the recipe to connect the catacombs:**
1. Stop rendering `onControl` opaque. Read `(== (x onControl: ...) 1<<n)` as "on color n" and
   `(& ... M)` as "on any color in M".
2. Treat the control-color predicate as an **always-satisfiable positional choice** (the player can
   walk onto the region), i.e. a *free* edge — unless that branch *also* carries an item/flag gate,
   which we keep. Pair it with the branch's `newRoom`/cue and emit a traversable edge.
3. Handle `edgeHit` / direction-property nav the same way (pure script; direction→room table in the
   room object).
4. Mover `moveDone`→cue→`newRoom` needs no new machinery — it is another cue source into the machine
   lift.

**Not statically recoverable:** only the screen *geometry* (which pixels carry which color; polygon
obstacles for `kAvoidPath`). Reachability does **not** need it — we need whether an edge *exists*,
not where the feet are. Geometry matters only to prove a painted region is physically walled off (a
rare, defensive case; the PIC control layer is decodable offline if ever needed — cf. our
`tools/pic-oracle`).

Soundness note: emitting an `onControl` edge as *free* only **adds** connectivity. Missing a real
edge → false-positive strandings; a spurious free edge (color region actually unreachable) → could
hide a real stranding. Maze control regions are walkable by design, so emitting them is the correct
direction; the residual risk is the same geometry case above.

---

## 4. Death & restart — validated, no engine signal exists

Death is **100% game-script**. The engine offers only:
- `kRestartGame` (SCI16) — merely sets `abortScriptProcessing = kAbortRestartGame` and returns
  (`kmisc.cpp:53-58`); the actual reset (wipe segments, reload script 0, re-`play`) is mechanical in
  `runGame()` (`sci.cpp:683-698`). The abort enum has None/Load/Restart/Quit — **no "death"**
  (`state.h:52-57`). In SCI32 RestartGame is a no-op (`kernel_tables.h:796`).
- `kRestoreGame` (`kfile.cpp:1231`) and a `gameIsRestarting` status flag (restart=1/restore=2,
  `state.h:66-70`).

`restart`/`save`/`restore` are ordinary **Game-class selectors** (`static_selectors.cpp:54,65,92`).
A death-dialog Restart button and a SCI1.1 icon-bar Restart button both call `restart:` → same
`kRestartGame` → identical engine signal. **The engine cannot see call-site provenance** — this is
exactly why our SCO0 "reachable Restart ⟹ death" heuristic breaks on SCI1.1, where Restart lives in
an always-available control panel. There is **no** `Death` class, `die`/`dieScript` selector, or
death palette effect to key on. ScummVM documents it *cannot* detect death screens and disables
autosave for that reason (`sci.h:157-182`).

**For us.** No change; strong validation. The version-aware model stands:
- SCO0/SCI1: any reachable Restart offer = death.
- SCI1.1: death = a death *dialog* at the hazard (non-Game object offering both `restart:`+`restore:`)
  or a proc that `newRoom`s into a death room. This is the only viable signal — even the reference
  interpreter has nothing better.

---

## 5. Selectors, kernels, flags — modeling level confirmed

The engine caches only the selectors it reads from C++ (`SelectorCache`, `selector.h:33-204`;
mapped `selector.cpp:48-245`): graphics (`view/loop/cel/signal/x/y/priority`), motion
(`client/moveSpeed/moveDone/setMotion/setStep/cantBeHere`), the Animate heartbeat `doit`, events
(`message/modifiers/type/claimed`). **Absent from the cache — therefore pure game-script
convention:** `newRoom, has, owner, setScript, changeState, cue, caller, curInvIcon, doVerb,
approachVerbs, edgeHit, register, script`. Exactly the level we model at.

- **Room change is not a kernel.** Convention: `kGlobalVarNewRoomNo = 13` (`vm.h:153`); a
  `(theGame newRoom: N)` game method sets **global 13**, which the engine only *reads*
  (`state.cpp:184-190`). The literal `NewRoom` kernel symbol is a no-op debug hook
  (`kernel_tables.h:1006`). → *Idea:* a uniform nav signal is "any write to global 13", which would
  cover `newRoom:` literal / `<global>` / `(obj sel:)` forms **and** direct `(= global13 N)` writes
  in one rule. Worth checking whether we already cover all forms.
- **`changeState` is a method of the `Script` class (script 999)** (`static_selectors.cpp:150-152`)
  — validates the machine-lift level. `client/caller/register` are the `Script`'s wiring selectors.
- **Flags: no engine flag kernel.** Flags are a game-script bit-array (packed 16-per-global-word);
  the only bit primitive is `kMemory` PEEK/POKE (`kmisc.cpp:360-365`). Confirms `vocab.derive_flags`
  (proc913 test/set/clear over a base global) is correctly game-level.
- **doVerb item-use model — confirmed.** `kGetEvent` fills `event.message` with the input payload
  (`kevent.cpp:195`); the item number rides in as the verb param (from `curInvIcon`), so
  `(== param1 item#)` ⟺ `OWN(item#)` — *you can only select a verb-item you own*. `kMessage` keys
  text by `MessageTuple{noun,verb,cond,seq}` (`message.cpp:78,105`).
- **Version kernel diffs that matter.** Kernels dispatch by name (vocab.999 number→name→fn,
  version/platform-filtered, `kernel.cpp:588-641`). SCI1.1 disables the parser
  (`kSetSynonyms→Empty`, `kernel.cpp:763-765`) → `Said`/`Parse` go dead, intent moves to
  `doVerb`/`Message` (matches our audit's 0 `Said` across all SCI1 games). `kGetMessage→kMessage`
  around SCI1→1.1. The control map is read via the `kOnControl` kernel (SCI32 uses `kIsOnMe`).

---

## 6. Action items, ranked by leverage

1. **Positional `onControl` → real edges (build).** Decode the color-mask guard from the script
   constant; emit the branch's `newRoom` as a free positional edge; do the same for `edgeHit` /
   direction-property nav. Connects the KQ6 catacombs (where the real softlocks live). §3 is the
   recipe. *Feasible and statically complete — the big result of this study.*
2. **Land the flag-toll pocket detector** (already prototyped + validated: sacredWater one-way,
   user-confirmed) — the general "one-way entry" model. Parked next to `toll_strandings`.
3. **Engine-faithful class resolution** (`class = super` for non-class objects; `info & 0x8000` =
   class). Byte-identical polish over the current `super OR species`. §2.
4. **Death model — no change; validated.** §4.
5. **(Optional) Crisper `is_sci11`** via heap-segment presence or object-header shape, only if the
   0xffff vote ever misfires. §1.
6. **(Idea) Uniform room-change signal = writes to global 13** (`kGlobalVarNewRoomNo`); may catch
   `newRoom` forms we miss. §5. Measure before adopting.
