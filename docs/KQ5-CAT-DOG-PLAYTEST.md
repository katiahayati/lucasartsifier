# KQ5 play-test sheet — the throwable pool: can the Fish go to the dog?

> ## ✅ ANSWERED 2026-08-16 — T1 CONFIRMED, stock game, USER
> **No.** The dog refuses the Fish: *"that wouldn't divert the dog's attention"* — message 280,
> the `else` arm of `rm012.sc:672`, exactly as predicted. The pool is **asymmetric**; the Fish
> belongs to the cat and the bear only. Ruling recorded in `docs/KQ5-ORACLE.md` §1. The rest of
> this sheet is kept as the derivation and for T3/T4, which are still unrun.

Derived from source 2026-08-15 (`rm006.sc`, `rm011.sc`, `rm012.sc`, `Main.sc`). Everything
below is a PREDICTION from the scripts; the point of the test is to confirm or refute it in
play. Console syntax is carried over from `docs/KQ6-RETEST-V22-CONSOLE-SHEET.md` — the
`send`/`room` forms are verified there, the KQ5 flag commands are NOT (see §4).

## 1. The question and why it matters

One pool of throwables feeds three scenes. If the pool is **asymmetric** — the Fish accepted
by the cat but refused by the dog — then "spending the Fish at the cat costs you the bear at
rm11" is a real, single-item claim rather than a disjunction the tool is blind to. If the dog
DOES take the Fish, the two scenes share a wider pool and the sink rows on both sides are
disjunction-blind in the same way, which changes what the detector should say.

**Source prediction: the dog REFUSES the Fish.** `rm012.sc:672` dispatches
`(switch (gInv indexOf: (gIconBar curInvIcon:)))` over exactly `16`, `8`, `19` — anything
else falls to `else → (proc0_29 280)`, a refusal line, with no `put:`.

| scene | room | accepts | source |
|---|---|---|---|
| the dog | **12** | Stick 16, Shoe 8, Leg_of_Lamb 19 | `rm012.sc:672` |
| the cat (click the CAT) | **6** | Shoe 8, Stick 16, Leg_of_Lamb 19, **Fish 5** | `rm006.sc:832` |
| the cat (click the FLOOR strip) | 6 | Shoe 8, Stick 16, **Fish 5** — no lamb | `rm006.sc:905` |
| the bear/bees | **11** | holding Fish 5 spawns the bear | `rm011.sc` |

## 2. Numbers

**Items** — `send ?ego get <N>` / `send ?ego has <N>` / `send ?ego put <N> 0`

| # | name | note |
|---|---|---|
| 5 | **Fish** | the pool item under test |
| 8 | **Shoe** | also the scene ARMER — see §3 |
| 16 | **Stick** | the other armer |
| 19 | **Leg_of_Lamb** | third throwable |
| 37 | Cat_Fish | ⚠️ **NOT this one.** Mordack's island fish, a different item and a different cat |

**Rooms** — 12 dog + anthill · 6 cat & mouse · 11 anthill + beehive (the bear)

**Flags** — 106 dog scene spent · 83 cat scene armed/spent · 36 the bees' flag (bear chain)

## 3. ⚠️ The setup gotcha that would waste the run

**The dog does not exist unless you walk in already holding the Shoe or the Stick.**

```
rm012.sc:83   (if (and (or (gEgo has: 8) (gEgo has: 16)) (not (proc0_12 106)))
                  ... (dog init: setScript: dogScript) ...
```

So carrying only the Fish gives you an empty screen and an inconclusive test. Arrive with
**Fish 5 AND Shoe 8**, flag 106 clear. The cat scene at rm6 has the identical shape — arming
is `(or (has 8) (has 16)) ∧ ¬flag83`, `rm006.sc:112` — and note the arming set (8, 16) is
NARROWER than the accepted-throw set (8, 16, 19, 5). That asymmetry is the mechanism this
whole thread is about.

Also: flag 83 is set the moment the chase STARTS (`rm006.sc:152`, in `doit`), win or lose —
so at rm6 you get exactly one attempt per save.

## 4. Console

Ctrl-Alt-D. `room <N>` does not act until you press Esc and let the room draw; reopen the
console afterwards.

```
room 12                 (Esc, wait for the draw, reopen)
send ?ego get 5         # Fish
send ?ego get 8         # Shoe -- REQUIRED, or there is no dog
send ?ego has 5         # expect 1
```

**Flags — untested on KQ5.** Try ScummVM's table first: `tf 106` reads, `cf 106` clears,
`sf 106` sets. If it does not know KQ5's flag table, use the raw store. `Main.sc:719` keeps
the flags as a word array based at **`global129`**: flag *N* lives at
**`global(129 + N/16)`, bit `1 << (N mod 16)`**.

| flag | global | mask | clear with |
|---|---|---|---|
| 83 (cat) | **global134** | 8 | `vmvars g 134 0` (or AND off bit 3) |
| 106 (dog) | **global135** | 1024 | `vmvars g 135 0` |
| 36 (bees) | **global131** | 16 | — |

(`vmvars g <idx> [<value>]` is the ScummVM SCI form; unverified for this game. Read first,
write second, and re-read to confirm the write landed.)

## 5. The tests

**T1 — the question.** In rm12, holding Fish 5 + Shoe 8, flag 106 clear, dog visible on
screen. Select the **Fish**, click the **dog**.
*Predicted:* a refusal line (message 280), no animation, `send ?ego has 5` still **1**.
*Record:* the message text, and whether `has 5` changed.

**T2 — control, same screen.** Select the **Shoe**, click the **dog**.
*Predicted:* throw animation, `send ?ego has 8` → **0**, flag 106 now set.
This proves the click target and the dispatch are live, so a T1 refusal means "refused",
not "I clicked the wrong pixel".

**T3 — the mirror, and the one that decides the pool.** `room 6`, holding Fish 5 + Shoe 8,
flag 83 clear. Walk right past x≈290 to trigger the chase, then throw the **Fish** at the
**cat itself** (not the floor).
*Predicted:* accepted — `put: 5 6`, the shoe-fly animation, mouse saved, `has 5` → **0**.

**T4 — optional, the lamb quirk.** Same as T3 with Leg_of_Lamb 19: predicted accepted when
clicked on the **cat**, refused when clicked on the **floor strip**. Only worth doing if T1
and T3 come out as predicted and you want the dispatch-site split confirmed.

## 6. What each outcome means for the tool

- **T1 refuses (predicted):** the pool is asymmetric, the Fish belongs to cat+bear only, and
  the emitted `Fish@rm6 → still needed at rm11` row is a clean single-item catch. Pin it.
- **T1 succeeds (refutes the source read):** I have mis-read the dispatch and the sink rows
  on both sides are the same disjunction-blind shape; the detector needs the
  exchange-slot treatment before either framing is pinnable.
