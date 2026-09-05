# GK1 §1.34 fan probes (2026-09-05)

The measurements behind docs/GK1-SOFTLOCK-CANDIDATES.md §1.56–§1.57. ⛔ None of this is on the
live path; it is kept so the next round starts from numbers instead of from prose.

Set up the worktree these expect (they hard-code `<this dir>/wt134`, so copy them to a
scratchpad next to it, or edit the `WT` line):

    git worktree add /tmp/wt134 <commit> --detach
    mkdir -p /tmp/wt134/build && ln -s "$PWD/build" /tmp/wt134/build   # or just build/sweep
    python3 apply_134.py          # run from inside the worktree; patches its machine.py
    # GK1 model rebuild under §1.34 is ~115 s (NOT the ~55 min §1.55 claimed)

| probe | asks |
|---|---|
| `probe_fwd.py` | is `producible_seal`'s `fwd` the blocker? (§1.55's proposal, measured a NO-OP) |
| `probe_leak2.py` | with the cures in and `flag15 := 0` forced back, which write still leaks? |
| `probe_era.py` | which edges reach rm510/rm490 — the era question |
| `probe_510.py` | how the day-3 closure gets into Germany (prevRoom bootstrap) |
| `sim_previmport2.py` | the prev-import rule + room-bounded writes, end to end |
