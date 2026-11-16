# GK1 flag 14 test plan — skip the day-3 newspaper, and is Tulane gone for good?

**The claim (detector row `reg 256`, day 3 → 4).** If you never read the newspaper on day 3:
1. Tulane never appears on the map.
2. Day 4 can then never end.

My source trace (2026-11-16) says this is a **real softlock in the stock game**:
- **Tulane needs flag 14.** Tulane (rooms 330, 331 and 340) is reachable only from its map icon.
  The icon appears only with flag 14 (`rm205.sc:58`).
- **Flag 14 needs the day-3 paper.** It's set only by clicking the newspaper on the bookstore
  counter on day 3 (`bookstore.sc:2130` → `getTheNewsPaper`, set at `:684`). On days 2 and 4 the
  paper runs other scripts, and nothing in the game makes you read it.
- **Day 4 needs Tulane.** Day 4's ending needs flag 227, which is set only by showing the veve
  inside Tulane (`rm340.sc`, `showTheVeve`).
- **Day 3's ending doesn't need the paper.** Day 3 ends at the map once five things are done
  (`theMapPrint.sc:243-252`), and none of them reads flag 14.

**What's uncertain:** I checked what those five requirements read directly, not every step of how
you obtain each one. If one of them can't be done without Tulane, day 3 can't end without the
paper and the row is a false positive. **Part A answers exactly that, and only play can.**

Game: `~/sierra/patched/gk1` or the stock `~/sierra/Games/gk1`; either is fine. v5 patches 455,
490, 720 and 800, and none of them is a day-3 or day-4 script.

Console: Ctrl+Alt+D. The rules from `docs/GK1-TESTPLAN.md` apply, and so does `gameflags_init
127` for `sf`/`cf`/`tf`. **In Part A, use the console for READS only** (`tf`, `vv`, `has`). The
five day-3 tasks are the thing under test, so writing any of them would answer the question for
you.

Legend: ☐ = needs your hands · ✅ = done.

## S — start of day 3, using Sierra's own day jump

GK1 ships the developers' teleporter. Alt+T opens "Where to, Gabriel?" (`debugHandler.sc:526`,
`proc99_1`). It asks for a room and a day, then grants the earlier days' flags and that day's
starting inventory. Normally it's switched on only if a file named `99.scr` sits in the game
folder (`gKInitCode.sc:49-53`). One console write switches it on instead.

1. Start a **new game** and skip the intro until Gabriel can move (day 1, bookstore).
2. Console:
   ```
   vv g 110 1        (Sierra's debug keys on, until you restart)
   ```
   Esc, then move the mouse off the icon bar.
3. Press **Alt+T**. At "Where to, Gabriel?" type `370` and press Enter. At "Which day?" click
   **Day 3**.
4. You get the day-3 card, then the day-3 morning in the bookstore. **Save here.**
5. Console checks:
   ```
   gameflags_init 127
   vv g 123          (must print 3)
   tf 14             (must print 0: the paper is unread)
   tf 72             (must print 1: a day-2 flag, which proves the jump ran)
   ```

If Alt+T does nothing: `vv g 110` must print 1, and the mouse must be off the icon bar.

- **Caveat 1.** This is the developers' idea of "start of day 3". It's close to a real
  playthrough but not guaranteed identical.
- **Caveat 2.** It also marks flag 45 (a Tulane flag) as done on day 2. Nothing in the game reads
  flag 45, so it can't matter.
- **The gold standard** is a save from a real playthrough at the start of day 3, if you have one.

## A — play day 3 without the paper (the real question)

**Rule: never click the newspaper on day 3.** Every so often, open the map: Tulane must never be
on it. If it ever appears, stop and send me `tf 14`.

Day 3 ends at the first use of the map after all five of these are done:

| ✓ | # | requirement | where it comes from (source) | check |
|---|---|---|---|---|
| ☐ | A1 | flag 265 | a cutscene in room 320, the cemetery room next to the Gedde tomb (`rm320.sc` `sCartoon`) | `tf 265` → 1 |
| ☐ | A2 | flag 21 | the interview with Crash (`rm240.sc` `crashInterview`; room 240 is entered from 230) | `tf 21` → 1 |
| ☐ | A3 | flag 256 | give the bracelet mold to Sam at Napoleon House (`napoleon.sc:838-858`). The mold comes from the bracelet scene in room 280, through Madame Cazaunoux's house (room 270). That scene opens only after her conversation topic, flag 44 → 67. | `tf 256` → 1 |
| ☐ | A4 | item 38, the reconstructed veve | the artist in Jackson Square (`neJackson.sc:1275`) | `send GKEgo has 38` → 1 |
| ☐ | A5 | item 8, Wolfgang's phone number | Grace: one of her conversation topics sets flag 55 (`grace.sc:138`), and when you're back in the bookstore she hands you the number (`bookstore.sc:249`) | `send GKEgo has 8` → 1 |
| ☐ | A6 | after all five, use the map | **the day ends**: you're sent home, the Malia scene plays in the bookstore, then the day-4 card. After it: `vv g 123` → 4 and `tf 14` → 0 | |

**If you get stuck on one of A1–A5** and it looks like it needs something from Tulane, the row
is a false positive. Tell me which task and what blocked it.

## B — day 4 without Tulane

| ✓ | # | Do | Expect |
|---|---|---|---|
| ☐ | B1 | open the map | **no Tulane icon** |
| ☐ | B2 | click the newspaper in the bookstore | the day-4 newspaper plays (a different script); `tf 14` still → 0, and still no Tulane |
| ☐ | B3 | day 4's ending check. Console, since this only tests the ending: `sf 447`, `sf 248`, `sf 36`, `send GKEgo get 26` (tattoo tracing), `send GKEgo get 41` (bracelet replica). Leave 227 clear (`tf 227` → 0). Then use the map. | **the day does NOT end.** Day 4 needs all six (`theMapPrint.sc:255-266`, and the bookstore's copy at `bookstore.sc:218-229`), and 227 is the missing one |
| ☐ | B4 | `sf 227`, then use the map | **the day ends** (day-5 phone call or card). That proves 227 alone was holding day 4 |
| ☐ | B5 | *optional control:* restore your B1 state, `sf 14`, open the map | Tulane appears. Go in to the professor (room 340) and show him the veve; `tf 227` → 1. That proves 227 comes from Tulane |

## C — quick form (only if you don't want to play day 3)

After S, run `sf 265`, `sf 21`, `sf 256`, `send GKEgo get 38` and `send GKEgo get 8`, leaving 14
clear. Use the map: day 3 ends. Then do Part B.

**This does NOT answer the question.** It only confirms that day 3's ending check ignores the
paper, which the source already shows. Whether the five can be done without Tulane is exactly
what A tests.

## Verdict

| outcome | ruling |
|---|---|
| A6 reached with `tf 14` = 0, and B1–B4 as expected | **flag 14 is a real softlock in the stock game.** It needs a guard: what and where is a separate decision |
| stuck at one of A1–A5 for want of Tulane | **false positive.** The row goes, and the model has missed a dependency I'll go and find |
| Tulane appears with the paper unread | my trace missed a writer of flag 14. Send `tf 14` and where you were |

Report back: the row IDs with pass or fail, and for A, anything that felt like it needed Tulane.
