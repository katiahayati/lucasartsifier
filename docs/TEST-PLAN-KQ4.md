# KQ4 — open questions for a play-test

Not a patch test plan yet; KQ4 has never been patched or played. This is the list of things the
STATIC analysis could not settle, written down while the reasoning was fresh so a play session can
answer them cheaply. Add to it as more turn up.

## Getting around

`overtime nosleep` sets the debug flag (`global215`, `Main.sc:1846`). The debug menu then toggles
it with `^=`. With it on, the copy-protection screen accepts a room number and warps you there
(`copyProtect.sc:687`) — the fastest way to reach a specific room.

Useful item numbers (`newInvItem` declaration order in `Main.sc`, 0-indexed):

| # | item | # | item | # | item |
|---|---|---|---|---|---|
| 1 | Diamond_Pouch | 15 | **Shovel** | 25 | **Magic_Fruit** |
| 2 | Talisman | 17 | Fishing_Pole | 33 | Magic_Hen |
| 4 | Pandora's_Box | 19 | Worm | 34 | Rose |
| 7 | **Obsidian_Scarab** | 21 | Golden_Bridle | | |
| 14 | **Cupid's_Bow** | 24 | Dead_Fish | | |

---

## 1. Can Cupid's arrows actually be WASTED?  ← the open one

**Why it matters.** The user's original claim was *"you can waste Cupid's arrows before needing the
last one for Lolotte."* Source confirms a two-arrow budget with two consumers and no visible slack,
so the claim is plausible but the wasting mechanism is not in the code we can find.

What the source says:

```lisp
regUnicorn.sc:123   (if (and (gEgo has: 14) (< ((Inv at: 14) loop:) 2))   ; fewer than 2 used
                        ... (uniActions changeState: 10) ...
                        ((Inv at: 14) loop: (+ ((Inv at: 14) loop:) 1)))   ; spends one
Room82.sc:387       ((>= ((Inv at: 14) loop:) 2)  (proc255_0 82 33))       ; refuses to shoot Lolotte
Room82.sc:625       ((Inv at: 14) loop: (+ ((Inv at: 14) loop:) 1))        ; spends one
```

So: **2 arrows, the unicorn takes one, Lolotte needs one.** Exactly enough.

What we could NOT find: a site that consumes an arrow for nothing. A MISS does not — the increment
sits inside the `(global125 inRect: 0 0 319 189)` hit branch, and the `else` is just a message. And
after the first hit `uniActions changeState: 10` runs, which looks like it ends the encounter.

**To check in play:**
- [ ] Shoot at the unicorn and MISS (fire while it is off-screen). Does the arrow count go up?
      Check by trying to shoot Lolotte afterwards, or `showSelf` on the bow.
- [ ] After hitting the unicorn once, can you shoot it AGAIN? If yes, that is the waste.
- [ ] Is there any third thing you can shoot? (`Said 'launch/arrow...'` handlers elsewhere.)
- [ ] Fire twice at anything, then reach Lolotte: does `Room82` message 33 appear?

**What the answer changes.** If arrows can be wasted, `resource_exhaustion` is right to flag the bow
and the patch should refuse the wasting shot. If they cannot, the two-arrow budget is exact-fit by
design and the bow row is a false positive to be removed.

---

## 2. Is the bow row's DIRECTION right?

`resource_exhaustion` currently reports *"Cupid's_Bow one-way at rm82, still needed at
[20, 26, 27]"* — spend it at Lolotte, still needed at the unicorn. That is backwards in plot terms:
the unicorn comes first.

**Known cause, not a mystery:** `extract.Extractor.run()` walks room scripts only, so
`regUnicorn`'s arrow spend (a REGION script) is invisible and only Lolotte's was recorded. Fixing
region scope in `extract` should flip the direction to unicorn → Lolotte.

- [ ] After that fix, confirm the reported direction is unicorn → Lolotte.

---

## 2b. Is the fishing pole REALLY re-baitable?  ← and our reason for saying so is weak

The pole is EXCLUDED from `resource_exhaustion` because its `loop` property is written to both 0
and 1, which the one-way test reads as "restorable". That test is SYNTACTIC -- it asks whether the
good value is ever written, not whether that write is still REACHABLE.

```lisp
Main.sc:1205-6   ((Inv at: 19) moveTo: 666)   ((Inv at: 17) loop: 1)   ; worm on hook, pole baited
Room95.sc:652    ((Inv at: 17) loop: 0)                                 ; unbaited
Room95.sc:675    ((Inv at: 19) moveTo: 777)                             ; the worm is consumed
```

Re-baiting needs a worm. The robin only appears while the worm is `ownedBy: 206` (`Room23.sc:144`,
`Room29.sc:84`, 50% per room entry), and **no site anywhere moves item 19 back to 206 from 777**.
So after one cast there is no second worm, and the pole cannot be re-baited.

Whether that is a SOFTLOCK depends on whether a baited pole is ever needed twice -- you only need
one Dead_Fish, so probably not. But the reason we excluded it is wrong either way, and if the cast
can fail (worm consumed, no fish) it becomes a real one.

- [ ] Cast and MISS, if missing is possible. Is the worm gone? Can you get another?
- [ ] After catching the fish, check the pole: does it still say baited? Try `put worm on hook`.
- [ ] Confirm the robin never returns once the worm has been used.

**What the answer changes.** If a cast can consume the worm without producing the fish, the Worm
belongs in `resource_exhaustion` and the pole's exclusion is a false negative. See TODO A0m:
the one-way test needs to ask whether the restoring write is REACHABLE, not merely present.

---

## 2c. The Gold Ball -- is rm21 a real second source?

`drops[5] = [15]` (throwing it in the pond) and `sources[5] = [15, 21]`. The second source is why
it is NOT flagged as a softlock: the model thinks you can get another. The user's recollection is
that you cannot -- *"if you throw the ball in the pond and don't get the crown from the frog you
can't try again. There's definitely ways to lose that gold ball."*

- [ ] Throw the ball in the pond (rm15) and DO NOT take the crown from the frog. Can you retrieve
      the ball, at rm15 or anywhere else?
- [ ] What is rm21's ball source -- the initial pickup, or a genuine second chance?

**What the answer changes.** If rm21 is only the initial placement, then losing the ball at rm15 is
a true stranding we are missing, and the same one-time-pickup question applies as to the fishing
pole in 2b -- a source that exists syntactically but is unreachable once used.

---

## 3. The Shovel — confirm the mechanism end to end

Believed solid; source and the user agree. Recorded so a play-test can close it.

```lisp
Room16.sc:611  (= local5 (* (- (++ global113) 1) 3))   ; ++ per hole dug
Room16.sc:589  (if (>= global113 5) ((Inv at: 15) loop: 1))   ; five holes and it snaps
Room16.sc:249  (if (and (gEgo has: 15) (== 0 ((Inv at: 15) loop:))) ... dig ...)
```

`global113` is a GLOBAL, so holes dug in the graveyard (rm16) count against the crypt (rm18).

- [ ] Dig 5 wrong holes in rm16, then try to dig in rm18. Refused?
- [ ] Confirm the shovel's name changes to "Broken Shovel" (`Main.sc:2008`).

---

## 4. The endgame confiscation

- [ ] Get captured (rm92) and confirm the whole inventory moves to the cupboard (rm89), not just
      the hen and box.
- [ ] Leave the castle WITHOUT emptying the cupboard, then walk back to rm89 and retrieve. The
      model says this works right up until you hand Genesta the amulet at rm45.
- [ ] Hand Genesta the amulet, then try to return. Should be impossible (rm45 → rm690 is the only
      point of no return in the endgame).

---

## 5. Day/night

- [ ] Let the clock run to hour 21 without finishing the day tasks. Confirm nightfall
      (`Main.sc:924`, "Like a heavy blanket, darkness enfolds you").
- [ ] At night, try the dwarves' door (rm22) and the fisherman's shanty (rm7). Both should refuse —
      *"We're all asleep here! Come back tomorrow!"* and *"D'ya know what TIME it is?! GO AWAY!!"*
- [ ] Shoot Lolotte, get the dawn (`Room82.sc:599` sets `global100` back to 0), then walk back and
      try those doors again. The model says they reopen; confirm.
- [ ] Confirm the 24-hour deadline exists at all (`timeOut`, script 302, at clock 31:59).
      ~6 real hours from the start, so this one is a patience test, not a quick check.

---

## 6. Obsidian Scarab

The user has confirmed the graveyard and crypt hold required items, so the scarab is a true
stranding. Worth one confirmation that it is not merely death-avoidance:

- [ ] Enter rm16/rm17/rm18 at night WITHOUT the scarab. Death expected (`Room17.sc:67`).
- [ ] Confirm you cannot obtain the required graveyard/crypt items without surviving those rooms.
