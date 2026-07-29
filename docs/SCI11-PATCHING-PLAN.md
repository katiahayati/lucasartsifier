# SCI1.1 gate generation + patching — the plan to a patched KQ6

Written 2026-07-28, after `v1.0-kq6` (detection: 14 of 14, `KNOWN_GAPS` empty). Everything below
that says MEASURED was run today; the commands are in the last section.

**Scope.** SCI1.1 titles we hold: **KQ6** and **The Dagger of Amon Ra (LB2)**. QFG-VGA is excluded
for tractability (it does not finish a missability run). The emission matrix falls out of the
resource map and therefore also covers **KQ5** (SCI1, one resource per script) for free — see §2.1.

**Standing constraint.** LSL2 and KQ4 must stay byte-identical on the full snapshot surface,
**placements included**, through every commit here. That is the whole point of the goldens.

---

## 1. Where we actually are — MEASURED today, not remembered

### 1.1 The detector is done; the two halves after it are not

| stage | LSL2 | KQ4 | KQ6 | Dagger |
|---|---|---|---|---|
| findings | 15 + group | 9 | **14 of 14** | 5 |
| specs derived | yes | yes | 14 edge + 3 sink | 3 edge + 2 sink |
| **placed in source** | 13/15 | most | **5 of 17** | **2 of 4** |
| compiles | 117/118 | 156/159 | **331/341** (with a version fix) | untried |
| emitted + played | **yes** | not yet | no | no |

### 1.2 KQ6 placement, item by item (MEASURED)

```
[ok  ] Main          sink: peppermint      <- but Main.sc does not compile (§2.5)
[ok  ] Main          sink: mint            <- same
[SKIP] lampTradeScr  sink: huntersLamp     "expected exactly one `put: 19 -1`, found 0"
[ok  ] rm220         setscript             castle short entrance, 7-item guard
[ok  ] rm230         setscript             castle long entrance, same 7-item guard
[ok  ] rm340         setscript             -> rm440
[SKIP] rm340->rm155  not-found             the realm entry
[SKIP] rm340->rm370  not-found
[SKIP] rm340->rm405  no-trigger            the catacombs entrance
[SKIP] rm{405,408,410,411,415,425,430,435}->rm420   not-found  (x8, all the brick)
```

Dagger: `rm26->rm750` **not-found** (the act break), `Main` sink **not found**, and the two that
*did* apply are **24-item guards** placed as `arm-event`, i.e. events that would simply never fire.
That is a bad patch, and it is the first thing §5 exists to stop.

### 1.3 The SCI1.1 back end is much closer than it looked — MEASURED

I probed `scicompile` with a throwaway `--sci11` flag (the patch is saved at
`scratchpad/scicompile-sci11-probe.patch`; the repo is clean and the binary was rebuilt from
committed source):

* Pinning `sciVersion1_1` instead of `sciVersion0` is **the only change needed to make SCI1.1
  compile at all**. Today `main.cpp` calls `SkipNextVersionSniff()` + `SetVersion(sciVersion0)`,
  so the SCI1.1 resource map never parses and every selector is unknown
  (`Failed to load selector names from vocab resource` → 793 bogus errors).
* With the version right: SCI1.1 template `Main.sc` → 5466 bytes. **KQ6: `--sco` writes 340/341,
  `--all` compiles 331/341**, converged in 2 passes.
* Adding ~12 lines to also write `results.GetHeapResource()` gives real script+heap pairs, and the
  **heaps are byte-length identical to Sierra's own** for all three patch-site rooms:

  | script | Sierra scr / hep | ours scr / hep |
  |---|---|---|
  | 220 | 7716 / **1762** | 7502 / **1762** |
  | 230 | 5336 / **1542** | 5240 / **1542** |
  | 340 | 5434 / **1622** | 5354 / **1622** |

  Same result as LSL2: every *data* structure reproduces exactly, only the *code* block differs
  (Sierra's compiler vs SCICompanion's). The heap bytes that differ are pointers into the code.
* The loose-patch **header is unchanged**: KQ6's own shipped patches are `82 00` for `420.SCR` and
  `91 00` for `420.HEP` — exactly the `[0x80|type][0x00]` the patcher already writes. Only the
  **filename scheme** and the **extra heap resource** are new.

**So the toolchain is not the wall.** The wall is (a) four SCI1.1-shaped hardcodes, (b) placement
that only looks in one script, and (c) guard quality.

---

## 2. Seam A — the SCI1.1 back end

### 2.1 A1: the SCI version, and the emission matrix, are DERIVED from the map

We already derive the map format by shape (`sci_resource.Sci0Game._sci1_sections`: "recognised by
that shape rather than declared"). Extend that one derivation to answer three questions at once:

```
SCI0 map                     -> patch file `script.NNN`,      script resource only
SCI1 map, no type-17 entries -> patch file `NNN.SCR`,         script resource only     (KQ5)
SCI1 map, type-17 == scripts -> patch files `NNN.SCR`+`NNN.HEP`, script + heap         (KQ6, Dagger)
```

MEASURED: KQ5 `n_script=207 n_heap=0`; KQ6 `341/341`; Dagger `255/255`; LSL2 has no type 17.
ScummVM accepts *both* naming schemes regardless of version (`readResourcePatches`), so this is a
correctness-and-convention choice, not a compatibility one — use the scheme the game itself uses.

`scicompile` gains `--version {sci0|sci1|sci11}`, supplied by the patcher from that derivation. Do
**not** port `VersionDetectionHelper.cpp`: I tried, and it needs ~8 more MSVC rvalue-binding fixes
for 900 lines of view/pic/audio sniffing we would never exercise. We already know the answer from
the map we read ourselves; asking a second oracle is over-purity.

### 2.2 A2: emit the heap

`RunSingle` writes only `results.GetScriptResource()`. When `version.SeparateHeapResources`, also
write `GetHeapResource()`. `emit_patches` then writes the pair. A script patch without its heap is
not a partial patch — it is a **crash**, because the interpreter reads objects out of the heap at
offsets the new code assumes.

### 2.3 A3: `assemble()` must copy the game's own loose patches

`assemble()` copies `resource.*` only. KQ6 ships `420/425/460/470 .SCR/.HEP` and `65535.MAP`;
Dagger ships `100/450`. Those are Sierra's own late bug-fix patches, and **sci-tools decompiled the
patched versions** — so today the compile project's `--sco` step pairs our patched source against
the *unpatched* mapped resource. Copy every loose patch file alongside the volumes. This is the
two-tree seam in a new costume: one decompilation, one set of resources, or nothing is provable.

### 2.4 A4: kernel names come from OUR OWN decompiler

`--all` fails on 5 scripts with `Unknown procedure 'Portrait'`. `Portrait` is kernel **0x26** in
KQ6 (it displaces `SetSynonyms`; ScummVM's table records exactly that, "Portrait (KQ6 hires)").
SCICompanion falls back to a hardcoded SCI0/SCI1 list when the game has no `vocab.999`.

The derived fix is a **round-trip property**: *the compiler must speak the kernel vocabulary the
decompiler spoke.* Our JSON IR already carries it — every `KernelCall` node has both `name` and
`func` (the index). MEASURED: 106 distinct kernels in KQ6, `Portrait` among them.

So `assemble()` synthesises a `vocab.999` name table from `{func: name}` and drops it in the
project as a loose patch (`999.VOC`); `KernelTable::Load` reads it in preference to the hardcoded
list. No per-game data, no C++ change, and it *cannot* drift from the analysis.

### 2.5 A5: two decompiler-dialect seams (small, but they block real files)

* `rm710.sc:48` — `dungeon# 0`, a selector name containing `#`. SCICompanion's parser rejects `#`
  there. One script; fix in our sci-tools fork's emitter (or teach the parser). rm710 is the long
  ending's castle interior, so it matters eventually.
* `boringBook`, `rm430`, `rm880` — *"`&rest` cannot be used if the send target itself contains
  nested procedure calls or sends"*. A compiler restriction on a form our decompiler emits; the
  mechanical cure is to hoist the target into a temp, in the emitter.
* `speedRoom` — `Unknown procedure 'proc911_1'` (script 911's export). Probably closes with A4.

None of these is on the critical path to the first patched KQ6; all four should be logged as a
tracked red test rather than fixed opportunistically.

**Gate A (the null-patch gate).** Recompile an **unmodified** KQ6 room, wrap it as `NNN.SCR` +
`NNN.HEP`, drop both into a *copy* of the game, and play that room in ScummVM. This proves the
whole back end with the guard held out. Nothing downstream is trustworthy until this passes; the
LSL2 history is unambiguous that structural validity is not runtime validity.

---

## 3. Seam B — the refusal primitive, which is currently a silent landmine

`patcher.REFUSE` is `(proc255_0 {Not yet!})` and `_JUST_KIDDING` is the same call. That is LSL2's
and KQ4's print procedure, hardcoded.

**KQ6 has a `proc255_0` too, and it is a different, unrelated procedure** — `Dialog.sc:199` calls
it with no arguments as a boolean. MEASURED: the guard the patcher already places in `rm220`
compiles to
`Error: Unknown procedure 'proc255_0'. Did you forget to use "Interface"?`
Here we get lucky and it fails loudly; in a game that *does* export a `proc255_0` we would emit a
call to something arbitrary with a wrong signature and never know.

**Derivation.** "How does this game display a literal line?" is answerable from the game's own
scripts: find the call form that takes a `{literal}` and shows it, and reuse *that exact form*.
KQ6's is `(Print addText: {…} init:)` — used by the game itself (`WriteFeature.sc`), alongside the
message-resource form `(Print addText: <mod> <noun> <cond> <seq> …)` used in rooms. LSL2/KQ4's is
`(proc255_0 {…})`, which the same derivation reproduces.

Rules:
* Derive per game; **never** assume by name.
* If no literal-string display form can be derived, **refuse to emit any refusal-bearing guard**
  (an `arm-event` gate, which has no `else`, is still emittable). Silence is not an option:
  a guard that refuses without saying anything is the "the game lied to the player" class that
  only play-testing caught last time.
* Pin the derived form per game in a test, so a change in the derivation is visible.

---

## 4. Seam C — locate edits by the IR node we analysed, not by re-finding them

Three failures today are one bug:

| game | spec | patcher looked for | the source says |
|---|---|---|---|
| LSL2 | sink | `put: X -1` | `put: X -1` ✓ |
| KQ4 | sink | `put: X -1` | `put: X 999` (fixed once, by threading `dest`) |
| KQ6 | sink | `put: 19 -1` | `(global0 put: 19)` — **no destination at all** (SCI NOWHERE) |
| Dagger | sink | `put: 6 -1` | same shape |

The cheap fix is to let the matcher accept an absent destination (`dest` is already carried on the
spec). **The real fix is architectural and is the recommendation:** the analysis already knows the
exact site — script, object, method, state, and the AST node — because that is how it decided the
clause was a sink. Carry that provenance onto the spec and have the patcher resolve it to a source
span, instead of regenerating a regex and hoping the spelling matches. Every dialect difference in
this table then costs nothing, in this game and the next one.

The same argument applies to §5's `find_trigger`, which is a *second, independent* re-derivation of
something the detector already computed. This is [[same-rule-two-places]] at the level of a module.

---

## 5. Seam D — placement, which is SCI0-shaped in four separate ways

MEASURED causes behind the 12 KQ6 skips and the Dagger skip:

1. **`trigger.py` searches only the FROM room's own file.** `rm340->rm155` (the Realm entry, which
   lives in `nightMare.sc`, script 344) and `rm340->rm370` are `not-found` for that reason alone.
   Dagger's `rm26->rm750` is the act break — `actBreak.sc` does `(newRoom: local0)`, an **indirect**
   newRoom. Both problems were solved on the detection side long ago (the four script scopes; the
   revolving-door indirect-newRoom resolution). Placement needs the same reach — ideally by
   *sharing* it, per §4, not by copying it. KQ4's open TODO ("region-sourced edges, rm20/26/27→333")
   is the same rule, so this fix pays for three games at once.
2. **Controllability is spelled for SCI0.** `CONTROLLABLE_METHODS = {handleEvent, doVerb}` and the
   `recv == "self"` test. SCI1.1 arms with `(global2 setScript: X)` where `global2` **is** the room
   object, and commits through `doit` reacting to `onControl`/approach. Derive: a `setScript:`
   whose receiver resolves to the current room or the ego is a self-arming, not a cross-instance
   decoy. `rm340->rm405` (`no-trigger`) is exactly this.
3. **`guard_edge_exit` hardcodes `of Rm`.** KQ6 rooms are `of KQ6Room`, Dagger's are `of LBRoom`.
   We already derive the room-class family in `vocab`/`extract`; use it. Today the room-property
   fallback can never fire on any SCI1.1 title, which is why every `not-found` is also a total miss.
4. **The catacombs eight have no call site by construction.** `rm*->rm420` is pseudo-room movement
   through `LBRoom::makeDoors`' coordinate table — there is no `newRoom: 420` anywhere in the game.
   **Do not invent a placement for these.** §6 argues they are the wrong edges to guard in the
   first place, and after §6 they disappear.

---

## 6. Seam E — guard QUALITY, and why it must gate emission

Three distinct defects, all measured, all general:

### 6.1 The guard demands "still needed past this edge", not "required to win"

Dagger asks for **24 items** to cross `rm440->rm435`; KQ6 asks for **7** at each castle entrance.
KQ4 already showed this (`rm20/26/27->333` wanted ~32). The frontier is computed from `s.required`,
which counts *uses* on the path — a superset of what winning needs.

The detector already owns the right predicate: an item is a softlock only if pinning it off makes
the goal unreachable. **A guard should demand exactly the items whose absence at that edge makes
the goal unreachable — no more.** Same predicate, applied one layer later. This shrinks all three
of the bad guards without a new concept.

### 6.2 Satisfiability is tested from START, not from where the player is

`guards.unsatisfiable()` asks "with edge a→b deleted, is a source of x still reachable **from
`start_room`**?" It must ask "…still reachable **from `a`**". They differ exactly when the player
is already past a one-way — which is every interesting case.

This is what puts the brick guard on eight edges *inside* the catacombs. From `rm405` you cannot go
back for a brick, so those guards would convert a softlock into a **permanent wall** — the failure
mode this project treats as strictly worse than the bug. The global test hides it because the
catacombs are re-enterable *from the surface*.

The cure is already half-built: prohibitions relocate themselves via `droppability_frontier` ("the
last edge where the item can still be got rid of"). **Requirements need the mirror —
`obtainability_frontier`: the last edge where the item can still be got.** For the brick that is
`rm340->rm405`, the catacombs entrance, which is where the user's own ruling puts it. Eight bad
guards collapse into one right one, derived, with no room named.

### 6.3 ✅ LANDED (part): a guard must not demand what it cannot hold

**The KQ6 castle, resolved as far as it is derivable.** Both doors are one-way into the same
19-room terminal castle (`rooms_after(730) == rooms_after(710)`, and neither door room is in it),
so both are genuine commitment points and the placement was already right — only the condition was
wrong. Two things landed:

1. **The arming floor** (`missability.entry_alts`) — `wearClothingScr`'s `newRoom: 730` sits one
   state past a `(secondGuardDoorScr cue:)` handoff, so the entry-reach walk stopped short and
   `own(clothes)` had vanished from the short door. See the commit "You cannot be executing a
   machine you never armed".
2. **`guards.incompatible_with_the_edge`** — an item may not be demanded at an edge when getting it
   costs something the crossing itself requires. The Realm of the Dead is gated on flag 14; the
   **only** room that writes flag 14 is rm580 (the Druids); rm580's escape burns Beauty's clothes;
   the short door requires them. So `handkerchief` and `skeletonKey` — Realm-only items — are
   dropped from the short door's guard, with the reason recorded on the spec.

| door | demands now |
|---|---|
| rm220 -> rm730 (dress, short) | dagger, mint, mirror, nightingale, peppermint |
| rm230 -> rm710 (paint, long) | + handkerchief, skeletonKey |

This mattered more than "over-strict": demanding a Realm item at the short door **walls** that
route, since the short path never visits the Realm.

**The exchange-counter discriminator** is what keeps the rule honest: a room that both SOURCES and
DROPS an item is a counter, not a loss (`sources[brush] == drops[brush] == 280`, the pawn shop), so
it is not pruned. Without it the rule got the right answer on the long door for the wrong reason.

**⚠️ THE REMAINING HALF, pinned as a KNOWN LIMIT in `test_kq6_ground_truth.py`.** The long door
still demands `mint` and `nightingale`, which the walkthroughs put on the SHORT route (the guard-dog
distraction; the lower-score alternative to the lamp for Shamir). Nothing about the long route makes
them *unobtainable* — they are merely *not needed* — and "not needed on this route" is a per-ENDING
question. That needs 6.4.

### 6.4 Per-ending requirements — the goal is a set of ROOMS, and both endings end at rm94

`goal_rooms = {94, 205}`; rm94 is the credits and both endings reach it, so "can you still win" is
true on both routes and no per-route requirement can exist. The discriminator is known and already
modelled: **`alexWedding.sc` branches on `proc913_0 15` eleven times**, flag 15 is "you entered the
Realm" (= the King and Queen were revived), and **register = flag + 172**, so flag 15 is register
**187**, already promoted. The two endings are therefore distinct PRODUCT states `(94, 187=1)` and
`(94, 187=0)`.

Making the goal a set of product states rather than rooms gives per-ending `required` for free, and
dissolves the `teaCup` `LONG_ENDING_ONLY` column at the same time. The known obstacle is that
`_need_rooms` is room-granular, so a use that is only reachable on one route still counts on both —
that is the piece to design.

### 6.5 Path-forcing: a guard must not demand one arm of a disjunction

Both KQ6 castle entrances get the **same 7-item** guard. But the castle has two entrances —
`rm220->rm730` (disguise, short ending) and `rm230->rm710` (magic paint, long ending) — and the
`teaCup` ruling already settled the principle: *a long-ending-only item does not make the game
unwinnable, so it is not a requirement.* Demanding the union at both doors forces a route the game
does not force. Same rule as [[path-forcing-guards]], now with a concrete site.

6.1 subsumes this: an item that only gates one arm survives pinning, so it is not "required to
win", so it leaves the guard. Worth stating separately because it is the rule the user has already
ruled on twice, and because it is the check to run *by hand* on the castle guard before emitting.

**Gate E.** No spec is emitted unless: every literal is required-to-win (6.1), satisfiable from the
edge's own source room (6.2), and the guard does not exceed the items the detector actually
flagged for that finding. A refusal here is a success, not a failure.

---

## 7. Seam F — two detector classes produce no spec at all

`guard_specs` consumes edge strandings, joint strandings, survival gates and register flips. It
does **not** consume:

* **`toll_strandings`** — KQ6 has 4. Two of them are the Realm of the Dead carry-outs
  (`handkerchief`, `skeletonKey`: obtained inside a flag-15 one-visit pocket, needed outside).
  The remedy shape is already implied by the finding's own fields (`pocket`, `source_rooms`,
  still-needed-at): **gate the pocket's EXIT on the items obtained inside and needed outside.**
  The user has already said this in as many words about the teacup: *"we should not let you leave
  the realm of the dead without it."*
* **`fatal_uses`** — KQ6 has 1, the `skull` thrown into the gears at rm420: a move the game invites,
  that looks like the solution, that costs a required item and kills you. User: *"that's exactly
  the kind of bad use we need to prevent."* The remedy is to refuse the ACTION (guard the arming of
  `throwSkull`), which needs a new spec site kind — `action` — but reuses the existing `setscript` /
  `arm-event` placement machinery.
  Note the one known FP in this class (`holeInTheWall @rm407 via putHoleOnWall`) costs a wrong
  *reason*, not a wrong item; it must not reach emission, so `fatal_uses` specs need the same
  Gate E treatment.

---

## 8. Sequencing

Each phase ends in a gate; nothing proceeds past a red gate.

**Phase 0 — the harness, before any behaviour changes.**
Extend `snapshot.py --placements` to KQ6 and Dagger and commit goldens for all four games. Add
`test_sci11_patch.py` as a red test listing §2.5's four dialect failures and §7's two missing
remedy classes. *Gate: LSL2 + KQ4 byte-identical; 12 test files green.*

**Phase 1 — the back end (§2).** A1–A4, plus heap emission and the filename matrix.
*Gate A: the null-patch runtime gate — an unmodified KQ6 room recompiled, wrapped, installed, and
played in ScummVM.*

**Phase 2 — the thinnest real slice: one patched KQ6 finding, end to end.**
Target the **`huntersLamp` sink in `lampTradeScr` (script 11)**. It needs only §2 (back end), §3
(refusal/retraction primitive) and §4 (the `put: 19` spelling) — **no placement work at all** —
and script 11 is in the 331 that already compile. The finding is user-confirmed real (*"you cannot
trade it again because the peddler leaves"*).
*Gate: trade the lamp in ScummVM, keep it, and `rm580`'s `makeRain` branch still fires.*

**Phase 3 — guard quality (§6), before anything wide is emitted.**
6.1, then 6.2's `obtainability_frontier`, then re-measure all four games' specs.
*Gate: Dagger's 24-item guards and KQ6's 8 brick guards are gone or relocated; LSL2 and KQ4 specs
unchanged; the castle guard is inspected by hand against the short/long ending split.*

**Phase 4 — placement generality (§5).** Share the analysis's site provenance (§4) rather than
re-deriving; then the room-class derivation and the SCI1.1 arming receivers.
*Gate: KQ6 placement ≥ 12/14 remaining sites; Dagger's act break places; KQ4's `rm20/26/27→333`
places as a side effect.*

**Phase 5 — the missing remedy classes (§7).** Toll-pocket exits, then fatal uses.
*Gate: `handkerchief`, `skeletonKey` and `skull` each carry a spec that survives Gate E.*

**Phase 6 — emit and PLAY.** Full KQ6 patch set, then Dagger. Write the play-test plan in the shape
of `docs/PATCH-TEST-PLAN-KQ4.md`: for each finding, (A) reproduce the trap unpatched, (B) confirm
prevention, (C) confirm the game is still winnable.
*Gate: KQ6 completed end to end on the patched build, as LSL2 was.*

KQ4 gets carried along free by Phases 3–5 (its `rm45->690` guard already compiles); finishing its
play-test is a natural Phase 6 companion and a second data point that none of this is KQ6-shaped.

---

## 9. What needs a user ruling (none of these blocks Phases 0–2)

1. **The castle guard and the two endings.** Should `rm220->rm730` (short) demand long-ending
   items? §6.1 says no and derives it; the user has ruled adjacent to this twice (teaCup →
   `LONG_ENDING_ONLY`). Confirm before emitting.
2. **The catacombs entrance guard is a plot capture, not a player action.** Relocating the
   carry-ins to `rm340->rm405` means gating the *arming* of the capture cutscene: you are simply
   not thrown into the catacombs until you carry brick + tinderbox + hole + scarf. That is the
   correct prevention but it changes the game's plot pacing. Same shape as KQ4's whale swallow,
   which the user accepted.
3. **`Main.sc` case 63 — `(global0 put: 23 280)`, the mint.** The destination is room 280, the
   **pawn shop** — that is a *trade*, not a destruction. Deleting it leaves the player holding the
   mint *and* whatever they traded for. Check this one against the item oracle before emitting;
   the `peppermint` sibling (`put: 31 0`) has no such smell.
4. **KQ6's shipped Sierra patches (`420/425/460/470`).** rm420 is the crusher room — one of ours.
   Once §2.3 lands we will be recompiling *on top of* Sierra's own bug fix. Worth a look before we
   overwrite it.

---

## 10. Reproduce

```sh
# specs + placements for any game (writes <game>_specs.json + _placements.json).
# A name config.py knows, or any build/sweep/<dir> -- so a title needs no config entry.
MEASURE_OUT=/tmp/m python3 tools/measure_specs.py KQ6
MEASURE_OUT=/tmp/m python3 tools/measure_specs.py dagger

# the SCI1.1 compile probe (throwaway; the repo is clean and the binary is built from
# committed source -- apply, build, measure, then `git checkout -- tools/scicompile/main.cpp`)
git apply tools/scicompile/sci11-probe.patch
cmake --build tools/scicompile/build -j8
scicompile --sci11 --sco  <project>           # 340/341 on KQ6
scicompile --sci11 --all  <project>           # 331/341 on KQ6
scicompile --sci11 <project> <project>/src/rm220.sc /tmp/rm220.bin   # + /tmp/rm220.bin.hep

# what the game itself does (the format we must match)
python3 -c "d=open('420.SCR','rb').read(); print(d[:2].hex())"   # 8200
python3 -c "d=open('420.HEP','rb').read(); print(d[:2].hex())"   # 9100
```
