# KQ4 softlock patch — play-test plan

Apply: copy `build/patch/script.{000,016,018,031,043,045,305}` into a **COPY** of the KQ4 folder
(ScummVM reads loose `script.NNN` patches over the RESOURCE volumes). Delete them to revert.

For each softlock: **(A)** reproduce the trap on the UNPATCHED game to confirm it, then **(B)** confirm
the patch prevents it, and **(C)** confirm the game is still WINNABLE (the required action still works).

Item numbers are KQ4 inventory indices; room numbers are `rmNN`.

---

## The whale funnel — rm31 ocean → rm44 whale interior → rm43 bridle island

The island is reachable ONLY by being swallowed by the whale (random while swimming in rm31), then
sneezing out. Once you leave the island you cannot return. Three items ride on this.

| # | item | patch (script) | test |
|---|------|----------------|------|
| **8** | **Peacock_Feather** | Room31 (`script.031`) | A: swim in rm31 without the feather until the whale swallows you → in rm44 you cannot `tickle` it → the deadTimer kills you. B: without the feather you are **never swallowed**. C: WITH the feather you still get swallowed and `tickle` still sneezes you out. |
| **24** | **Dead_Fish** | Room31 (`script.031`) | A: get swallowed without the fish → sneezed to rm43, nothing to throw the pelican. B: the swallow now also requires the fish — no fish, no swallow. C: with feather **and** fish you get swallowed and can feed the pelican on the island. |
| **21** | **Golden_Bridle** | Room43 (`script.043`) | A: reach rm43, leave WITHOUT taking the bridle → you cannot return (whale is one-time) → the unicorn (rm20/26/27) is untameable. B: on rm43 the four walk-off exits are **closed** until you hold the bridle. C: pick up the bridle → exits open → leave normally. |

Note: the whale swallow is a random roll; the guard is on its *arming* (`Room31::init`), so you simply
won't be swallowed until you carry feather **and** fish. Expect to need both before the ocean matters.

---

## Nightfall — the two day-only doors

Night falls on a wall clock (`global100`). Two doors lock at night and only reopen at dawn, and dawn
comes only when Lolotte dies — which needs the very items behind those doors. Patch holds the sunset
(`global100:=1` in `KQ4::newRoom`, `script.000`) until you hold both items.

| # | item | door | test |
|---|------|------|------|
| **1** | **Diamond_Pouch** | rm22 → rm54 (dwarves' house) | A: dawdle until night, then try rm22 → rm54 → "come back tomorrow", and there is no tomorrow. B: night does not fall until you hold the pouch **and** pole; the door stays open. C: get the pouch in daytime as normal. |
| **17** | **Fishing_Pole** | rm7 → rm42 (fisherman's shanty) | A: at night rm7 → rm42 → "GO AWAY!!". B/C: same as above — night is held; get the pole. |

Watch: after you have **both** the pouch (1) and pole (17), night is allowed to fall again — confirm
the game still progresses into night/endgame normally (the plot nightfall needs scarab+fruit+task-3,
which come later, so it should be unaffected).

---

## The endgame point of no return — rm45 → rm690 → rm693/694

Handing Genesta the amulet at rm45 commits you to the ending; you cannot go back. Three items must be
in hand. Patch gates the handover (`Room45`, `script.045`).

| # | item | note |
|---|------|------|
| **7** | **Obsidian_Scarab** | also protects vs the crypt/graveyard zombies+mummy (rm16/18) |
| **25** | **Magic_Fruit** | cures your father at rm694 = the WIN; also **not eaten** — see below |
| **33** | **Magic_Hen** | delivered to Genesta at the end |

A: enter the endgame missing any of the three → unwinnable. B: rm45 handover refuses until you hold
scarab **and** fruit **and** hen. C: with all three, the handover proceeds and rm694 shows the cure.

**Magic_Fruit sink (Main, `script.000`):** A: `eat fruit` → it is consumed (`put: 25 999`) and gone.
B: the consumption is removed and replaced with a "just kidding" line — you keep the fruit.

---

## Resource exhaustion — the fourth store

| # | item | patch | test |
|---|------|-------|------|
| **14** | **Cupid_s_Bow** (arrows) | shootBow (`script.305`) | A: `launch arrow` into the air twice → out of arrows → cannot shoot Lolotte at rm82. B: shooting into the air no longer spends an arrow (a "just kidding" line). C: the **unicorn** shots (rm20/26/27) and the **Lolotte** shot (rm82) still cost their arrows — the 2-arrow puzzle is intact, you just cannot WASTE them. |
| **15** | **Shovel** | Room16 + Room18 (`script.016/018`) | A: dig 5 holes total across the graveyard (rm16) and crypt (rm18) → "Oh, Oh! You've broken your shovel!" → cannot dig the spot you needed. B: the shovel never breaks (a "just kidding" line after the "broke" message). C: keep digging freely; find the buried items. |

---

## Regression watch (the game must still be winnable)
- You can still reach and complete the whale/island loop (with feather+fish), tame the unicorn, kill
  Lolotte, and finish at rm694.
- Night still eventually falls once the day-list items are held (nothing that *needs* night is blocked).
- No new "wall": every guard is satisfiable — each item is obtainable before its gate.

Report anything that reads wrong (a message that lies, a door that won't open when it should, a gate
that blocks a legitimate path). Those are the bugs only play-testing can find.
