# Guard modes: full / lite / stock

The player toggles, in-game and at any moment, how a placed guard behaves. Detection,
spec derivation and placement are untouched — the mode is pure EMISSION (patcher/trigger)
plus a small per-dialect UI patch. Shipped first in LSL2/KQ4 mode builds and KQ6 v26.

## The three modes

| mode | value | behavior |
|---|---|---|
| **full** | 0 | every guard refuses, exactly as before this feature (the default — uninitialized globals and stale saves read 0) |
| **lite** | 1 | each guard SITE refuses once; from then on it prints "You have been warned!" and lets the original behavior run |
| **stock** | 2 | every guard lets the stock behavior through silently |

Silent guard kinds (arm-event, nav-assign, edge-exit closes, award gates) and the
register/flag holds (KQ4 nightfall, KQ6 wedding fuse) have no refusal to warn with, so
lite behaves as full there [user ruling at plan time]; stock bypasses them too.

## Storage (per game, derived)

- **Mode global** = the first index past everything the assembled game declares OR
  references (`patcher._init_mode`): LSL2 `global481` (stock rm63 already reads
  `global480` out of bounds), KQ4 `global401`, KQ6 `global171`.
- **Warned bits** = one bit per guard site in trailing bitmask words after the mode
  global (`global482+` / `global402+` / `global172+`), allocated in emission order; a
  multi-clause placement shares one bit ("every guard fires once" is per guard).
- All are ordinary globals: declared by the existing `_declare_missing_globals` pass
  (re-run inside `install_mode_ui`, after every apply pass, because the globals exist
  only in emitted text), persisted through save/restore by the whole-heap SaveGame
  kernel, and reset to full/unwarned on Restart (script 0 reloads).

## The emitted dispatch

Refusal-bearing wraps (`trigger.guarded_wrap`, one builder for every kind that says no):

```
(if <guard>
    <body>
else
    (if (or (== gMode 2) (and (== gMode 1) (& gWarnWord $mask)))
        (if (== gMode 1) (<proc> {You have been warned!}))
        <body>                                  ; proceed
    else
        <mechanical deny lines, e.g. edgeHit resets>
        <refusal>
        (if (== gMode 1) (|= gWarnWord $mask))  ; mark warned
    )
)
```

The body is duplicated once so the guard condition stays verbatim at the site (nothing
hoisted into helpers — the patched source stays reviewable, and test_sci11_patch's
substring pins stay meaningful). Silent kinds and holds get only the stock bypass:
`(or (== gMode 2) <guard>)`.

Sink remedies no longer DELETE the disposal: the `put:` (and its adjacent negative
`changeScore:`) runs under the same allow test, the retraction speaks only when the
disposal was withheld — inline behind `(not <allow>)` on the appended path, via the
cue-object's `register` property on the rides-the-say path (an EXISTING selector on
Script, deliberately: a novel property name would need a vocab-997 entry the patch set
does not ship). Full mode is behaviorally identical to the deletion era: mode 0 never
takes the disposal branch.

## The in-game UI (`patcher.install_mode_ui`, derived by shape)

- **SCI0** (LSL2/KQ4): a `Guards...` item APPENDED to the last menu of the menu bar (the
  file with the most literal `AddMenu` declarations; appending cannot shift any existing
  menu code, including KQ4's runtime Debug menu). Its handler case (before the
  handleEvent switch's own `else`, reusing the switch's temp) runs a 3-button chooser on
  the derived display proc. LSL2 = Sound menu code 1283, KQ4 = 1284 (computed, not
  declared).
- **SCI1.1** (KQ6): an `iconGuards` ControlIcon added to the `of GameControls` panel,
  cloned from iconTextSwitch's working shape (signal $0183 = panel stays open,
  `theObj: self selector: #doit`), one row below the deepest existing row (the view-947
  window interior leaves ~38px, measured), face reusing the first ControlIcon's loop
  (currently the Save face — cosmetic, revisit if it bothers). Its doit runs a 3-button
  `Print` chooser.
- Both choosers use button values 1/2/3 and store `value - 1` only when nonzero, so
  dismissing the dialog keeps the current mode.

## What is pinned

`src/test_mode.py`: wrapper structure per mode (guard verbatim, body duplicated, mark in
deny only, classic v25 shape when unconfigured), allocator word rollover, UI installers
against the real game files (codes 1283/1284, balance), surface neutrality (guards.py /
missability.py never touch the mode machinery), and the mini-project declaration flow.
Full-surface gates at the introduction: LSL2 golden green; KQ4/Dagger/KQ6 snapshots
byte-identical to the pre-feature worktree baseline; KQ6 v26 compiled 341/341 with
verify "fixed 10 + 1 group(s), NEW: none"; LSL2/KQ4 mode builds compiled and emitted.

## Play-verification checklist (pending)

On any game: full refuses at a known guard; lite refuses once, then warns and proceeds;
stock passes silently; mode persists across save/restore; restart resets to full; the
chooser is reachable (SCI0 Sound menu / KQ6 control panel) and ESC keeps the mode.
KQ6-specific: the mists trail (rm550) and the catacombs entrance are convenient sites;
the sacredWater pour in lite should retract once then waste for real after the warning.
