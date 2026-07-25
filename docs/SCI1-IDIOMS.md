# SCI1 idiom audit — 2026-07-24

Purpose: understand the SCI1 control / state / intent surface the way session-A0 understood SCI0's,
and let *measured evidence* — not the previous KQ5 mining — rank the gaps. All numbers below are
raw structural counts over the decompiled IR (`scratchpad/sci1_inventory.py`,
`scratchpad/doverb_probe.py`), no config, no extraction assumptions.

Corpus: **KQ5** (SCI1, has ground truth), **KQ6 / QFG-VGA / Dagger** (SCI1.1, decompiled here for
the first time), against the frozen SCI0 refs **LSL2 / KQ4**.

## The reframe (the thing we got wrong)

**We learned SCI1 from KQ5, and KQ5 is the least representative SCI1 game.** On every idiom where
SCI1.1 diverges from SCI0, KQ5 sits *closer to SCI0* than its SCI1.1 siblings do:

| idiom | LSL2 | KQ4 | **KQ5** | KQ6 | QFGvga | Dagger |
|---|---|---|---|---|---|---|
| `Said` (SCI0 parser intent) | 1010 | 2023 | **0** | 0 | 0 | 0 |
| `doVerb` param dispatch (SCI1 intent) — *effect-bearing* branches | 0 | 0 | **0** | 74 | 78 | 1 |
| `curInvIcon` item-use (the KQ5 spelling) | 0 | 0 | **98** | 20 | 21 | 14 |
| flag-manager store (`tstFlag`/test-set-clear) | none | none | **none** | ✓ g137 | ✓ g290 | ✓ g186 |
| `global <- global` writes (prevRoom style) | 3 | 29 | **5** | 9 | 27 | 3 |

So the pieces the previous sessions built — `curInvIcon` → `OWN`, individual-global gates — are
exactly the KQ5-shaped ones. The **dominant SCI1.1 idioms barely appear in KQ5**, so mining KQ5
mole-by-mole could never surface them. This is the concrete content of "we don't understand SCI1
the way we understood SCI0."

## The idiom surface, measured

### Intent — the channel that moved the most
SCI0 expresses player intent through the **parser** (`Said`, 1000–2000 sites) plus `has:` item
gates. In SCI1 the parser is **gone entirely** (0 `Said` in all four). Intent moved to the
point-and-click **`doVerb`** dispatch:

- A feature's `(method (doVerb param1) ...)` switches on `param1` — the verb-or-item the player
  clicked. Invoked as `(feature doVerb: (event message:))`; `message` is the icon-bar verb number,
  **or, when an inventory item is used, that item's number**.
- Guards are `(== param1 N)` and `(proc99x param1 A B C…)` (a variadic "verb is one of" test).
- `param1` has IR vtype **`Parameter`**, which `extract._cmp_atom` does not recognize (it handles
  Global / Local / Temp), so **every `doVerb` intent guard becomes `OPAQUE`**. The `proc99x`
  membership form is a `PublicCall`, which `atom()` doesn't handle at all → also opaque.
- The dispatch space splits by number: low values are verbs (look/do/talk — a free player choice,
  the SCI1 analogue of `Said`), high values are **inventory-item uses** (`param1 == item#` ⟺
  `OWN(item#)`, the exact requirement `curInvIcon == N` already yields). KQ6: 11 verb-like vs **52
  item-like** distinct values; QFGvga: 10 vs **61**. The split point is the derived inventory-item
  number set (`vocab.item_names`), per game — not a magic threshold (Dagger's item numbers are 500+).

`curInvIcon` (modeled) and `doVerb param==item` (not modeled) are **the same requirement in two
spellings**. KQ5 happens to use the first; KQ6/QFG-VGA use the second. Capturing `curInvIcon` took
KQ5 "from ~0 to ~30 requirements"; the analogous `doVerb` capture is worth **74 + 78 effect-bearing
branches** on KQ6 + QFG-VGA that are currently invisible.

### State
- **Object encoding (SCI1 vs SCI1.1 — a foundational divergence found while building the above).**
  SCI1.1 (the `.SCR`/`.HEP` heap games: KQ6/QFG-VGA/Dagger) encodes an INSTANCE with
  `species = 0xffff` and its class species in `super`; SCO0 **and SCI1 (KQ5)** put the class species
  in `species`. So *every species-based instance→class membership test* silently matched **nothing**
  on SCI1.1 (100% of instances have the sentinel). Room detection survived on a name-convention
  fallback (KQ6 86 rooms), but `item_names` returned 0 items — so the inventory was invisible and no
  requirement could resolve. Fixed by resolving an instance's class via `super` OR `species`
  (`vocab.item_names`, `vocab.doverb_item_messages`); LSL2/KQ4/KQ5 byte-identical (there the two
  agree), KQ6/QFG-VGA/Dagger now yield 52/50/36 items. **This is the deepest "we don't model SCI1.1"
  fact: our object model didn't identify SCI1.1 objects at all.**
- **Flag manager** — a `test/set/clear` proc trio over a base global (KQ6 g137, QFGvga g290, Dagger
  g186). **Derived correctly** by `vocab.derive_flags`; the flag half of a `doVerb` branch
  (`(proc913_0 21)` = `tstFlag 21`) is captured. KQ5 has no flag array (plain globals). ✓ modeled.
- **Item owner / location** (`(item owner:) == room`) → `LOC`. ✓ modeled.
- **Room-locals** — tracked as `CTR` only inside a lifted machine; not first-class scoped gates.
  This is the KQ5 basement (`local36`) case — real, but a KQ5-specific and high-risk build.
- **prevRoom / `global <- global`** — 5 sites in KQ5, low everywhere. **Confirmed minor**, not a
  lever (this settles the earlier hypothesis).
- **own-vs-worn** — only Dagger has `wear/worn` selectors (32); KQ5's amulet is a one-off, not a
  general idiom.

### Navigation
- `newRoom: <literal>` / `<global>` → ✓ modeled. `newRoom: []array` → 0 in all SCI1 (was a Camelot
  SCO0 thing).
- **`newRoom: (obj north:)`** direction-property travel — Dagger 30, KQ6 10 (nav-props: Dagger 79).
  **Not modeled**; drops real edges. Same idiom as the open QFG2 SCO0 desert-nav gap.

### Cutscene / machine
- The lift is built around `changeState` switches. SCI1 leans instead on **`setScript` +
  proc-call cues** (KQ5: 19 changeState vs 1274 setScript, 435 `(..self)` cues). `setScript` arming
  and proc-cues are ✓ modeled; the low changeState count is fewer multi-state cutscenes, not a
  missed form. Worth a coverage check but not obviously a gap.

### Death
- Imperative / proc-call death → ✓ modeled (`derive_death_proc`, landed 2026-07-23).

### Positional
- `onControl` (PIC control-map hit) is KQ5-heavy (171 vs LSL2 6) and goes opaque; `onMe`/
  `setOnMeCheck` is the SCI1.1 mouse-hit model. Mostly gates deaths/positional events; lower
  requirement-relevance than `doVerb`.

## Gaps, ranked by measured leverage

1. **`doVerb` param dispatch (intent capture).** The general SCI1.1 requirement channel; ~150
   effect-bearing branches opaque across KQ6+QFGvga; fully derivable (verb/item split from the
   item-number set). Without it, SCI1.1 requirement capture is near-zero and no SCI1.1 softlock can
   surface. **Highest leverage; it is the "understand SCI1 controls" item.**
2. **Direction-property navigation** (`newRoom: (obj north:)`). Drops real edges on Dagger/KQ6 (and
   QFG2). Medium; self-contained.
3. **Room-locals as first-class scoped gates** (KQ5 basement). Real, but KQ5-specific and touches
   the reachability core (high regression risk). The memories' focus; deprioritized by this audit
   relative to #1.
4. **`onControl` positional intent.** KQ5-heavy but mostly death/positional, not item requirements.
5. **prevRoom.** Confirmed minor — parked.

## Not yet done (validation follow-ups)
- Full extraction-coverage run (opaque-atom %) on KQ6/QFGvga/Dagger — blocked behind the same
  death-derivation + OpEmitter memory wall the SCO0 sweep hit on 247+ script games; the structural
  counts above are sufficient to rank, the % is a nice-to-have.
- No SCI1.1 ground truth yet (KQ6/QFG-VGA/Dagger). KQ5 remains the only validated SCI1 title.
