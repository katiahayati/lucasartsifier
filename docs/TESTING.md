# Testing

```
python3 tools/run_tests.py              # the whole suite (~21 min with every model cold)
python3 tools/run_tests.py toll scopes  # only files matching these names
```

Each `src/test_*.py` is also a standalone script you can run directly. Files that need no game
at all — `test_walkers`, `test_abstractions`, `test_guards`, `test_patch_text`,
`test_deletion_soundness` — run anywhere; the rest need the IR of the game they are about.

## Some checks are RED on purpose, and the runner is built around that

A test that asserts known-wrong behavior would be worse than no test, so a known limitation is
written as a *failing* check with its reason recorded in `KNOWN_RED` at the top of the runner.
The suite therefore exits 0 only when the failing set is **exactly** the declared one — which
means a red check that starts *passing* is also a failure, reported as "a gap was closed,
promote it". Without that half, closing a modeling gap looks like nothing happening, which is
how a real fix gets landed, forgotten, and later undone by someone who never knew it was there.

Currently **one**: two of KQ6's guard specs have no placement site (`test_sci11_patch.py`) — a
shared-dispatcher seam and a trade-shaped sink, both with their reasons written down.

## Three nets, and they are not the same kind of thing

* `test_golden.py` — the **full** output surface of LSL2 and KQ4, frozen in
  `src/testdata/*.golden.json`. A failure means the change is wrong, not that the baseline needs
  updating. Re-blessing needs sign-off.
* `test_watched_surface.py` — the same surface for KQ6 and LB2, in
  `src/testdata/watched_surfaces.json`. These games are still moving, so a change is allowed —
  but it must be read row by row and then deliberately refreshed:

  ```
  python3 -c "import test_watched_surface as T; T.refresh()"    # from src/
  ```

  Refreshing without reading the diff is the one thing that makes the file worthless.
* `test_kq4_ground_truth.py`, `test_kq6_ground_truth.py`, `test_lb2_ground_truth.py` — per-game
  oracles of user-confirmed verdicts, derived from the games and from hint books rather than
  from our own output. A **drop is a regression**; an **addition is treated with suspicion**.
  Neither column may be edited without sign-off.

The first two answer "did anything move?"; the third answers "is what we emit right?". Both
questions are needed: a surface refreshed from our own output can only tell you that today
agrees with yesterday.

## The full surface, by hand

`src/snapshot.py` writes the same canonical dict the goldens freeze, which is how a change gets
measured before it is committed:

```
cd src
python3 snapshot.py LSL2 > /tmp/lsl2.before     # then make the change
python3 snapshot.py LSL2 > /tmp/lsl2.after
diff /tmp/lsl2.before /tmp/lsl2.after
```

It includes the patch half (placements and their site counts) by default; `--no-placements`
skips it when only the analysis is wanted. "The item list did not change" is **not** the same
as "nothing changed" — guard specs, sink specs and placements move independently of it, which
is the whole reason this file exists.

Note the model cache is keyed on the hash of every non-test source file, so editing `src/`
invalidates it and the next run rebuilds every model. Take the *before* snapshot first.

## Play-testing a build without playing it

The suite checks the *emitted source*; it cannot see what the patched game draws. That gap cost
four wrong cuts at KQ6's in-game guard control, each shipped on a theory because checking one
meant asking someone to play. It does not:

```
python3 -m venv .venv-x && .venv-x/bin/pip install python-xlib pillow
.venv-x/bin/python tools/drive_scummvm.py --game <COPY of the patched game> --id kq6 \
    --script tools/kq6_panel_probe.py          # -> build/kq6_panel_probe/*.png
```

ScummVM opens a real window, XTEST drives the mouse and keyboard, and the window's pixels are
read off the X server. This is the only part of the project that wants third-party Python
packages, and it is optional. Point `--game` at a **copy**, never at the installed game.

What it can and cannot do: it has verified menu clicks and screenshots of KQ6's settings panel.
It has never played a game through. Every end-to-end play result this project claims was a
person at the keyboard.

## Clean-room check of the install instructions

The README's prerequisites were verified from scratch in a container, because a dependency list
written on the machine that already has everything is a guess. The recipe and its timings are in
[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md#clean-room-check).
