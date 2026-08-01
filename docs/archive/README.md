# Archived plans and findings

**These documents are SUPERSEDED. Do not read a number out of one and act on it.**

Every file here records how some conclusion was reached — the measurements, the wrong turns, the
things that were tried and refuted. That is worth keeping, and it is the only reason they were
not deleted: several of them are the sole record of a negative result, and a negative result you
cannot find is one you pay for twice.

What they are **not** is current. Each was written as a live plan, states a score or a status as
of the day it was written, and stopped being updated when the work moved on. Where one of them
disagrees with the live docs, the live docs win:

| for | read |
|---|---|
| KQ6 status, verdicts, what is caught and what is not | `../KQ6-STATUS.md` |
| the KQ6 goal derivation | `../KQ6-GOAL.md` |
| the KQ6 item oracle and candidate list | `../KQ6-ITEM-ORACLE.md`, `../KQ6-SOFTLOCK-CANDIDATES.md` |
| what is still open on SCI1.1 patching | `../SCI11-PATCHING-PLAN.md` |
| how the pipeline works | `../HOW-IT-WORKS.md`, `../ARCHITECTURE.md` |

Known-stale numbers, called out because they are the ones most likely to mislead:

* `KQ6-LAST-FOUR-PLAN.md` — "11 caught of 15", oracle "6/6". Now 18 units, oracle 16/16.
* `KQ6-TEACUP-PLAN.md` — "the 14 stay caught", oracle "13/13". Also §5/§8 recommend making the
  ENDING first-class to catch the teacup; that was **measured and refuted** (flag 15 is raised on
  realm entry, not by the paint). The teacup is caught as a one-visit-pocket carry-in instead.
* `KQ6-CATACOMBS-PLAN.md` — self-declares closed at the top; kept for the mechanism write-up.
* `one-shot-sources.WIP.patch` — an attempted fix that was parked, not applied. It is a `.patch`
  file, not something in effect.

Archived 2026-07-31.
