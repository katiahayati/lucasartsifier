"""Does the LIVE INTERPRETER instantiate our SCI2 scripts? (GK1, the first SCI32 patch)

Compiling is not loading. `emit_patches` writes ten files a Python program believes in; loading
them means ScummVM parsing the script header, applying the HEAP's relocation table and building
every object's property and method table. A script whose heap disagrees with its code compiles
cleanly and dies exactly there.

⛔ THE OBVIOUS COMMAND DOES NOT DO THIS. `scro N` answers "Script N is currently not
loaded/available" for anything the game has not already entered -- and the first draft of this
probe read that as a pass for all five. It only showed up because Sierra's own scripts and two
never-patched stock ones were asked the SAME question and gave the SAME answer
([[instruments-lie-run-the-control]]).

`find_callk` is the command that actually does it: `printKernelCallsFound` walks EVERY script in
the game, `instantiateScript`s it, disassembles it and uninstantiates it (console.cpp:3840). So
one call loads all 213 -- ours among them -- through the real engine path. A malformed pair is an
`error()`, which takes the process down; that is the failure this probe is looking for.

STATE ONLY -- every command here is a query ([[sci-console-is-a-text-loop]]).
"""

OURS = [455, 490, 720, 800, 899]


def run(c, log=print):
    log("=== verify_scripts: every script resource + its heap loads, none over 64KB ===")
    for ln in (c.cmd("verify_scripts", timeout=180) or "").splitlines():
        if ln.strip():
            log("  " + ln)

    # `Graph` is present in every SCI kernel; the point is the WALK, not the hits.
    log("=== find_callk: instantiate + disassemble EVERY script through the engine ===")
    out = c.cmd("find_callk Graph", timeout=600) or ""
    lines = out.splitlines()
    scanned = [ln for ln in lines if "disassembling" in ln]
    hits = [ln for ln in lines if "Script " in ln and ":" in ln]
    errs = [ln for ln in lines if "rror" in ln or "arning" in ln or "Invalid" in ln]
    for ln in scanned:
        log("  " + ln.strip())
    log("  %d line(s) of output, %d look like call sites" % (len(lines), len(hits)))
    for ln in errs[:20]:
        log("  ⛔ " + ln.strip())

    # The engine is still alive afterwards -- ask it something only a live VM can answer.
    alive = c.cmd("version", timeout=30) or ""
    log("=== after the walk, the VM still answers ===")
    for ln in alive.splitlines():
        if ln.strip():
            log("  " + ln.strip())
    log("VERDICT: walk completed with %d error/warning line(s); VM alive: %s"
        % (len(errs), bool(alive.strip())))


run(c)                                                            # noqa: F821 -- injected
