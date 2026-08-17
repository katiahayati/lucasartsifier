"""Emit a patched game from the guard specs -- the 'prevent' half, made real.

Pipeline, all on ONE decompilation (ours):

    build/ir/src/*.sc            our sluicebox decompilation (regenerate: tools/sci-tools-fork/build.sh)
      -> assemble()              a compilable project: sources + game.ini + the game's resources
      -> apply_*()               the edits guards.py derived
      -> scicompile --sco/--all  interface files, then compile
      -> emit_patches()          script.NNN loose patch files ScummVM reads in preference

Nothing here decides WHAT to patch: `guards.py` owns that, and every edit carries the spec that
justified it. This module only turns specs into bytes.

The loose-patch format (SCI0), per SCICompanion's own writer and ScummVM's reader:

    byte 0 : 0x80 | ResourceType   -> 0x80 | 2 (Script) = 0x82
    byte 1 : 0x00                  -> SCI0 has no extra resource header
    byte 2+: the raw compiled script

Dropping `script.NNN` into the game folder overrides the mapped resource, so the original
RESOURCE.MAP/volumes are never touched and the patch is trivially reversible: delete the files.
"""
from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import sys
from collections import defaultdict

import config
import guards as G
import ir as I
import missability as M
from sexpr import read_file
import trigger as T
from trigger import (find_trigger, find_arming, find_all_armings, find_cue_chain_armings,
                     find_nav_assign, find_proc_calls, exports_of,
                     reaching_procs, reaching_owners, wrap_trigger_in_source,
                     wrap_all_armings_in_source, wrap_forbidden_case, guarded_wrap, stock_or,
                     _ModeSite,
                     _block_span,
                     _enclosing_clause_body, enclosing_clause_head, _find_region)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
SCICOMPILE = os.path.join(_ROOT, "tools", "scicompile", "build", "scicompile")
RES_TYPE_SCRIPT = 2
RES_TYPE_HEAP = 17

# How this game stores a replaced script as a loose patch -- DERIVED from its own resource map by
# assemble() (see sci_resource.Sci0Game.patch_scheme), never declared. SCI0's `script.NNN` is the
# default so an un-assembled caller behaves exactly as before.
_SCHEME = {"name": "sci0", "script": "script.%03d", "heap": None}

# The SCI object globals the emitted patches reference, DERIVED per game by configure():
#   ego  -- the get/put/has receiver (the store wrapper's holder global)
#   game -- the changeScore receiver (the score object; drops a penalty)
#   room -- the newRoom receiver (the current room object; closes a property exit)
# LSL2 and KQ4 both use 0 / 1 / 2 -- the SCI template layout, kept as the defaults below -- but a
# game that laid its object globals out differently would still get correct patches.
_EGO, _GAME, _ROOM = 0, 1, 2
_IR = None                     # the analysed IR, stashed by configure() for assemble()


def configure(ir):
    """Derive this game's object-global layout so the patcher emits its real indices, not the
    template's 0/1/2. Call once before apply_*()."""
    global _EGO, _GAME, _ROOM, _IR, REFUSE, _JUST_KIDDING, _SEL_NAMES, _WARNED_LINE, _MODE_DEST
    _IR = ir
    _SEL_NAMES = None              # per-game: the selector table is the game's own
    _MODE_DEST = None              # a new game invalidates the mode-global derivation
    T.MODE = None
    form = refusal_form(ir)
    # No derivable way to show a line -> emit NO refusal text at all. A guard that refuses
    # silently is the "the game lied to the player" class that only play-testing caught last time,
    # so `apply_guards` treats an empty refusal as a reason not to place a refusal-bearing guard.
    REFUSE = (form % "Not yet!") if form else None
    _JUST_KIDDING = (form % "Just kidding! You still need it.") if form else None
    # Lite mode's repeat-firing line, same derived display form as every other wording.
    _WARNED_LINE = (form % "You have been warned!") if form else None
    globals()["_RETRACTION_FORM"] = form or "%s"
    import extract as X
    X.install_vocabulary(ir)                       # sets X._EGO = the ego holder global(s)
    _EGO = min(X._EGO) if X._EGO else 0
    _GAME = _dominant_receiver(ir, "changeScore", 1)
    _ROOM = _dominant_receiver(ir, "newRoom", 2)


def ego_spellings(ir):
    """Every way this game's source WRITES the ego as a send receiver: `globalN`, plus the names
    of the objects assigned to it.

    The analysis reads the IR, where a receiver is a node and the ego is whatever the vocabulary
    says holds items. The patcher has to find the same statement in TEXT, and text has more than
    one spelling of it: LSL2 and KQ6 write `(global0 put: 23 280)`, while LB2's Main writes
    `(ego put: 6 0 …)` -- and a pattern hardcoded to `global0` matched zero lines there, so the
    press-pass sink had no remedy and was reported as an unplaceable spec.

    Derived from the game's own `(= global<EGO> <object>)`, which is how every SCI game installs
    its ego. Not a name list: `ego` is LB2's identifier, not a convention we may assume."""
    out = {"global%d" % _EGO}
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if n.get("t") != "Assignment":
                    continue
                ks = n.get("kids") or []
                if len(ks) < 2 or not I.is_global(ks[0], _EGO):
                    continue
                nm = ks[1].get("name") if isinstance(ks[1], dict) else None
                if nm:
                    out.add(nm)
    return out


def _dominant_receiver(ir, selector, default):
    """The global most often used as the RECEIVER of `selector` -- e.g. `changeScore:` identifies
    the score object, `newRoom:` the room object. Falls back to the SCI template index."""
    from collections import Counter
    c = Counter()
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if n.get("t") != "Send":
                    continue
                try:
                    recv, msgs = I.send_pairs(n)
                except Exception:                  # noqa: BLE001 -- malformed send
                    continue
                if I.is_global(recv):
                    for sel, _ in msgs:
                        if sel == selector:
                            c[recv["index"]] += 1
    return c.most_common(1)[0][0] if c else default


def _script_numbers(src_dir):
    """title -> script number, read from each source's own `(script# N)` declaration."""
    out = {}
    for fn in sorted(os.listdir(src_dir)):
        if not fn.endswith(".sc"):
            continue
        m = re.search(r"\(script#\s*(\d+)\)", open(os.path.join(src_dir, fn), errors="replace").read())
        if m:
            out[fn[:-3]] = int(m.group(1))
    return out


def assemble(dest, cfg=None):
    """Build a compilable project directory from our decompilation + the pristine resources."""
    global _SCHEME
    cfg = cfg or config.ACTIVE
    src = cfg.src_dir
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(os.path.join(dest, "src"))
    for fn in os.listdir(src):
        if fn.endswith(".sc"):
            shutil.copy(os.path.join(src, fn), os.path.join(dest, "src", fn))
    # the compiler reads vocab.997/996/000 out of the game's own volumes...
    for fn in os.listdir(cfg.resource_dir):
        if fn.lower().startswith("resource."):
            shutil.copy(os.path.join(cfg.resource_dir, fn), os.path.join(dest, fn))
    # ...and the game's OWN loose patches, which override those volumes. KQ6 ships Sierra's late
    # bug fixes for 420/425/460/470 (+65535.MAP) and sci-tools decompiled the PATCHED versions, so
    # without these we would pair our patched source against the unpatched mapped resource. One
    # decompilation, one set of resources, or nothing is provable.
    for fn in os.listdir(cfg.resource_dir):
        if _is_loose_patch(fn):
            shutil.copy(os.path.join(cfg.resource_dir, fn), os.path.join(dest, fn))
    _SCHEME = _patch_scheme(cfg)
    globals()["_PRISTINE_DIR"] = src      # stage extraction must read UNEDITED source: an
    #   earlier wrap in the same file shifts the clause and the extracted "test" can be our
    #   own guard text (the rm390 compile break, 2026-08-04)
    _write_kernel_vocab(dest, cfg)

    nums = _script_numbers(os.path.join(dest, "src"))
    with open(os.path.join(dest, "game.ini"), "w") as f:
        f.write("[Game]\nLanguage=sci\nName=%s\n[Script]\n" % cfg.name)
        for title, n in sorted(nums.items(), key=lambda kv: kv[1]):
            f.write("n%03d=%s\n" % (n, title))
    _declare_missing_globals(os.path.join(dest, "src"))
    return nums


def _is_loose_patch(fn):
    """A file in the game folder that the interpreter reads INSTEAD of the mapped resource.

    Both naming schemes, because a game may ship either: SCI0's `script.042` / `view.001`, and
    SCI1's `420.SCR` / `420.HEP` / `65535.MAP`. Recognised by shape -- a resource-type extension
    with a numeric stem -- so no game's patch list is written down."""
    stem, _, ext = fn.rpartition(".")
    if stem and ext.isdigit():                     # script.042, view.001
        return stem.lower() in _TYPE_EXT
    return stem.isdigit() and ext.lower() in _TYPE_EXT   # 420.SCR, 65535.MAP


_TYPE_EXT = {"script", "view", "pic", "text", "sound", "vocab", "font", "cursor", "patch",
             "scr", "hep", "v56", "p56", "snd", "voc", "fon", "cur", "pat", "msg", "map"}


def _patch_scheme(cfg):
    """This game's loose-patch naming, derived from its resource map. Falls back to SCI0's
    `script.NNN` if the map cannot be read -- the shape every existing golden was built with."""
    try:
        import sci_resource as R
        return R.Sci0Game(cfg.resource_dir).patch_scheme()
    except Exception:                              # noqa: BLE001 -- no map, or an unreadable one
        return {"name": "sci0", "script": "script.%03d", "heap": None}


def _write_kernel_vocab(dest, cfg):
    """Give the compiler the kernel vocabulary OUR DECOMPILER SPOKE, as a `999.VOC` loose patch.

    A ROUND-TRIP PROPERTY, not a per-game table: every `KernelCall` node in the IR carries both a
    `func` index and a `name`, so the set of kernel names the source can possibly mention is
    exactly the set the analysis already read out of the game. Synthesising the table from that
    cannot drift from the analysis, and needs no data written down anywhere.

    Why it is needed: SCICompanion falls back to a hardcoded SCI0/SCI1 name list when the game
    ships no vocab.999, and KQ6 displaces `SetSynonyms` (kernel 0x26) with `Portrait` -- so five
    scripts fail to compile with `Unknown procedure 'Portrait'`. LSL2 and KQ4 both ship their own
    vocab.999, so this writes nothing for them: the condition is the absence of the resource, not
    the version.

    Format, READ OFF SIERRA'S OWN `vocab.999` (LSL2's, decoded with `sci_resource`) rather than
    guessed: uint16 count, then `count` x uint16 offset into the resource data, then at each
    offset a uint16 LENGTH followed by that many raw characters -- no terminator. LSL2's first
    offset is 226 == 2 + 2*112, and 226 -> `04 00 'Load'`, 232 -> `06 00 'UnLoad'`, so the entries
    pack end to end. Wrapped in the same `[0x80|type][0x00]` patch header as any other loose
    patch. (Writing NUL-terminated names instead puts every name two bytes out and the compiler
    reports `Unknown procedure 'ScriptID'` -- which is how this format was found.)"""
    if _IR is None:
        return None
    try:
        import sci_resource as R
        if 999 in R.Sci0Game(cfg.resource_dir).list_type(R.VOCAB):
            return None                            # the game has its own table; do not shadow it
    except Exception:                              # noqa: BLE001 -- unreadable map: leave it alone
        return None
    names = {}
    for s in _IR.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if I.t(n) == "KernelCall" and isinstance(n.get("func"), int) and n.get("name"):
                    names[n["func"]] = n["name"]
    if not names:
        return None
    # Dense 0..max: the reader indexes by position, and an index the game never calls can never be
    # named in the source either -- so a placeholder there is unreachable by construction.
    table = [names.get(i, "Unused%d" % i) for i in range(max(names) + 1)]
    head = 2 + 2 * len(table)
    offsets, blob, at = [], bytearray(), head
    for nm in table:
        raw = nm.encode("ascii", "replace")
        offsets.append(at)
        blob += struct.pack("<H", len(raw)) + raw
        at += 2 + len(raw)
    data = struct.pack("<H", len(table)) + b"".join(struct.pack("<H", o) for o in offsets) + blob
    path = os.path.join(dest, "999.VOC")
    with open(path, "wb") as f:
        f.write(bytes([0x80 | 6, 0x00]))           # 6 = ResourceType::Vocab
        f.write(data)
    return path


def _ensure_refusal_use(text, titles_by_num):
    """Make sure a file that now CALLS the refusal procedure declares the script it comes from.

    SCI resolves `procNNN_M` as export M of script NNN, and the caller must say `(use <that
    script>)` or the compiler reports `Unknown procedure 'proc921_0'. Did you forget to use
    "Print"?`. LSL2's rooms happen to `(use Interface)` already, which is why this never came up;
    KQ6's rooms do not all `(use Print)`. The owning script number is read off the derived form
    itself, so nothing is named here either."""
    m = re.search(r"proc(\d+)_\d+", _RETRACTION_FORM or "")
    if not m:
        return text
    owner = titles_by_num.get(int(m.group(1)))
    if not owner or re.search(r"\(use\s+%s\s*\)" % re.escape(owner), text):
        return text
    uses = list(re.finditer(r"^\(use\s+\w+\s*\)\s*$", text, re.M))
    if uses:
        at = uses[-1].end()
    else:
        inc = re.search(r"^\(include\s+[^)]*\)\s*$", text, re.M)
        if not inc:
            return text
        at = inc.end()
    return text[:at] + "\n(use %s)" % owner + text[at:]


_CLASS_OWNER = {}


def _class_owner_title(dest, class_name):
    """The TITLE of the script that DEFINES `class_name` in this project -- what a file that
    references the class must `(use ...)`. Derived by scanning the project's own sources: KQ6
    defines `Script` in System.sc, not in a file named Script.sc, so ensuring `(use Script)`
    by class name manufactures an unresolvable dependency (measured: it was the whole of
    Main's v23 compile failure)."""
    key = (dest, class_name)
    if key not in _CLASS_OWNER:
        _CLASS_OWNER[key] = None
        pat = re.compile(r"^\(class\s+%s\b" % re.escape(class_name), re.M)
        src = os.path.join(dest, "src")
        for f in sorted(os.listdir(src)) if os.path.isdir(src) else ():
            if f.endswith(".sc") and pat.search(open(os.path.join(src, f),
                                                     errors="replace").read()):
                _CLASS_OWNER[key] = f[:-3]
                break
    return _CLASS_OWNER[key]


def _ensure_use(text, name):
    """Add `(use <name>)` when the file lacks it -- the class-script twin of
    `_ensure_refusal_use`, for wraps that introduce a class reference (MoveTo needs Motion)."""
    if re.search(r"\(use\s+%s\s*\)" % re.escape(name), text):
        return text
    uses = list(re.finditer(r"^\(use\s+\w+\s*\)\s*$", text, re.M))
    if not uses:
        return text
    at = uses[-1].end()
    return text[:at] + "\n(use %s)" % name + text[at:]


def _version_args():
    """`--version` for scicompile, from the same derivation. SCI1.1 must be pinned or the map
    never parses and every selector comes out unknown (793 bogus errors on KQ6)."""
    return ["--version", _SCHEME["name"]]


def _declare_missing_globals(src_dir):
    """Extend script 0's local block to cover every global the game actually reads.

    Globals ARE script 0's locals. LSL2 reads `global480` while the block declares 0..479, so the
    compiler rejects rm63 -- a patch site. The decompilation is faithful; the declaration is just
    short. Compile-time only: a room compiles to an absolute global index that the interpreter
    resolves against its own array, which the shipped game already indexes this far."""
    main = os.path.join(src_dir, "Main.sc")
    if not os.path.exists(main):
        return 0
    txt = open(main, errors="replace").read()
    highest = max((int(m) for m in re.findall(r"\bglobal(\d+)\b", _all_sources(src_dir))), default=-1)
    declared = set(int(m) for m in re.findall(r"^\s*global(\d+)\s*$", txt, re.M))
    missing = [g for g in range(highest + 1) if g not in declared and g > max(declared or {0})]
    if not missing:
        return 0
    lines = txt.splitlines(True)
    start = next(i for i, l in enumerate(lines) if l.startswith("(local"))
    depth = 0
    end = start
    for i in range(start, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        if depth == 0:
            end = i
            break
    for g in reversed(missing):
        lines.insert(end, "\tglobal%d\n" % g)
    open(main, "w").write("".join(lines))
    return len(missing)


def _all_sources(src_dir):
    parts = []
    for fn in sorted(os.listdir(src_dir)):
        if fn.endswith(".sc"):
            parts.append(open(os.path.join(src_dir, fn), errors="replace").read())
    return "\n".join(parts)


_MODE_DEST = None                  # the dest _init_mode last derived for (cache key)


def _init_mode(dest):
    """Derive the guard-mode storage for this project and hand it to the emitters.

    The mode global is the first index past everything the game declares OR references --
    computed from the assembled sources exactly as `_declare_missing_globals` computes its
    ceiling, so the two can never claim the same word (LSL2's stock rm63 already reads
    global480 out of bounds; the mode lands at 481 there for the same reason the declaration
    pass ends at 480). Warned-bit words follow it, allocated 16 bits at a time as sites ask.
    All of them become ordinary declared globals when `_declare_missing_globals` re-runs at
    compile time, because by then the guard text REFERENCES them -- nothing is registered
    anywhere by hand.

    A game with no derivable display form gets no mode at all (T.MODE stays None -> classic
    always-refuse emission): there is no way to print the warned line, and no way to build
    the chooser UI either."""
    global _MODE_DEST
    if _WARNED_LINE is None or _MODE_DEST == dest:
        return
    _MODE_DEST = dest
    src_dir = os.path.join(dest, "src")
    txt = _all_sources(src_dir)
    highest = max((int(m) for m in re.findall(r"\bglobal(\d+)\b", txt)), default=-1)
    base = highest + 1
    counter = [0]

    def alloc():
        b = counter[0]
        counter[0] += 1
        return base + 1 + b // 16, "$%04x" % (1 << (b % 16))
    T.MODE = {"g": base, "warned": _WARNED_LINE, "alloc": alloc}


_HANDS_CACHE = {}


def _hands_forms(dest):
    """The input-lock pair the turn-back script may speak, IN THIS GAME'S OWN SPELLING.

    Scanned once over the assembled sources: `handsOff:`/`handsOn:` where the game sends them
    (LSL2, KQ4 -- their emissions stay byte-identical); `(User canControl: 0/1)` where THAT is
    the game's idiom (KQ5 -- rm012's lamb throw locks input exactly this way); None when
    neither is spoken, because a selector the game never sends does not compile and a brief
    uncontrolled walk-back beats an uncompilable guard."""
    if dest in _HANDS_CACHE:
        return _HANDS_CACHE[dest]
    src = os.path.join(dest, "src")
    spoken = set()
    for fn in os.listdir(src):
        if not fn.endswith(".sc"):
            continue
        t = open(os.path.join(src, fn), errors="replace").read()
        if "handsOff:" in t:
            spoken.add("hands")
        if "canControl:" in t:
            spoken.add("cancontrol")
        if "hands" in spoken:
            break
    if "hands" in spoken:
        got = ("(global%d handsOff:)" % _GAME, "(global%d handsOn:)" % _GAME)
    elif "cancontrol" in spoken:
        got = ("(User canControl: 0)", "(User canControl: 1)")
    else:
        got = None
    _HANDS_CACHE[dest] = got
    return got


def apply_sink_remedies(dest, sinks, titles_by_num):
    """Withhold the item consumption in each dangerous PURE SINK.

    Safe by construction: a pure sink is a clause that does nothing EXCEPT destroy the item (it
    arms no machine state and writes no register any guard reads), so withholding its one effect
    cannot perturb anything else. The joke stays; the player keeps the item.

    Mode-aware since the lite-mode feature: the `put:` is no longer DELETED but wrapped in the
    run-time mode dispatch -- full mode withholds it exactly as v25's deletion did (the branch
    never runs under mode 0), stock lets the stock disposal through, and lite withholds once
    then lets a warned player waste the item for real. The adjacent negative `changeScore:`
    rides the disposal branch: the penalty is the price of the destruction, charged exactly
    when it happens. The retraction only speaks when the disposal was actually withheld --
    inline behind `(not <allow>)` on the appended path, and via the cue-object's `armed`
    property on the rides-the-say path (armed by the withhold branch, cleared by the cue), so
    full-mode timing is unchanged. A MODE-less run (no derivable display form) keeps the
    original deletion shape."""
    _init_mode(dest)
    edits = []
    seen = set()
    for sk in sinks:
        if sk["refused"]:
            continue
        # One CLAUSE can be reported at several rooms: the airsick-bag sink is script 600, a
        # REGION covering rm61/62/63, so the same `put: 27 -1` shows up three times. Edit once.
        key = (sk["script"], sk["item"])
        if key in seen:
            continue
        seen.add(key)
        title = titles_by_num.get(sk["script"])
        if title is None:
            continue
        path = os.path.join(dest, "src", title + ".sc")
        lines = open(path, errors="replace").read().splitlines(True)
        # The disposal DESTINATION is derived per game (LSL2 -1, KQ4 999), carried on the sink
        # spec -- and it may be ABSENT: SCI's `(gEgo put: 19)` with no second argument means
        # NOWHERE, which is how KQ6 destroys the hunter's lamp. Accept either spelling of the same
        # disposal rather than only the one the first game happened to use.
        disposal = sk.get("dest", -1)
        # RECEIVER: every spelling the game uses for the ego (see `ego_spellings`), not just
        # `globalN`. LB2's Main writes `(ego put: …)` and the globalN-only pattern found nothing.
        #
        # ARGUMENTS: the disposal, then ANYTHING ELSE on the line. SCI's `put:` is declared
        # `(method (put param1 param2))` and reads exactly two arguments, so trailing ones are
        # pushed and ignored -- and LB2's Main really does carry nine of them:
        # `(ego put: 6 0 1 3 4 5 8 9 18 23 32)`, which the engine executes as "item 6 to room 0"
        # and the rest as dead numbers. The analysis reads it that way already (vocab.transfer
        # takes the item and dest args by position); this makes the text pattern agree instead of
        # refusing the line for having extra tokens.
        recv = "|".join(re.escape(e) for e in sorted(ego_spellings(_IR)))
        pat = re.compile(r"^\s*\((?:%s)\s+put:\s*%d\b\s*(?:%d\b)?[^)]*\)\s*$"
                         % (recv, sk["item"], disposal))
        hits = [i for i, l in enumerate(lines) if pat.match(l)]
        if len(hits) != 1:
            edits.append({**sk, "applied": False,
                          "why": "expected exactly one `put: %d %d` (or with no destination) in "
                                 "%s, found %d" % (sk["item"], disposal, title, len(hits))})
            continue
        i = hits[0]
        # ⚠️ VERIFY THE PURITY CLAIM AT THE EDIT SITE. "A pure sink does nothing except destroy the
        # item" is what makes deleting the `put:` provably safe -- but `pure_sinks` keys a clause by
        # (room, positive-owns), and in a big dispatch script a sibling `cond` arm gets a different
        # key, so a TRADE can reach here looking pure. KQ6's lamp peddler is exactly that: the same
        # doVerb hands over `(get: 25)` and sets the flag that makes the peddler leave, so deleting
        # the `put:` left the player keeping the old lamp AND taking the new one -- reported from
        # live play. Read the clause we are about to edit and refuse if it moves any other item.
        cbody = _enclosing_form("".join(lines), sum(len(l) for l in lines[:i]))
        if cbody:
            clause = "".join(lines)[cbody[0]:cbody[1]]
            others = [m for m in re.finditer(r"\b(get|put):\s*(\d+)", clause)
                      if int(m.group(2)) != sk["item"]]
            if others:
                edits.append({**sk, "applied": False,
                              "why": "not a pure sink: the same clause also moves item(s) %s -- "
                                     "this is a TRADE, and deleting the disposal would hand the "
                                     "player both sides of it"
                                     % sorted({int(m.group(2)) for m in others})})
                continue
        # Replace the consumption with a LINE OF TEXT, not silence. The clause has just announced
        # an IRREVERSIBLE act -- "You carefully pour your bottle ... on the padlock", "You dump the
        # bottle ... on the ice", "You do so and immediately discard the now-soiled airsick bag" --
        # so deleting only the `put:` leaves the game insisting you lost something you are still
        # holding. Reported from live play, twice. A retraction cannot be "you thought better of
        # it" either: you cannot un-pour a bottle. It has to be an explicit joke, which is well
        # within this game's register. Wording is the user's.
        # No apostrophes: a single quote opens a Said spec.
        indent = re.match(r"[ \t]*", lines[i]).group(0)
        if _JUST_KIDDING is None:
            edits.append({**sk, "applied": False,
                          "why": "no literal-display form derives for this game"})
            continue
        # Spelled with the game's OWN display form (see `refusal_form`) -- this line used to
        # hardcode LSL2's `proc255_0` a second time, which is the same defect in two places.
        #
        # AND IT GOES LAST IN THE CLAUSE, not where the `put:` stood. The retraction only makes
        # sense after the game has said the thing it is retracting, and SCI1.1 puts the disposal
        # FIRST: KQ6's `(63 (gEgo put: 23 280) (say: ...))` printed "Just kidding!" before the joke
        # it was answering. LSL2 happened to order them the other way, which is why this shipped.
        #
        # LAST IN TEXT IS NOT LAST ON SCREEN (finding #18, user play 2026-08-05, "a huge mess"):
        # a Messager `say:` is ASYNC -- it queues a talker box for later cycles -- while our
        # retraction is a MODAL Print, so a sibling statement opens ON TOP of the still-queued
        # joke and the two fight for input claiming; neither dismisses. When the surviving
        # clause speaks through a `say:` whose CALLER slot is free, the retraction rides the
        # messager's COMPLETION instead: the caller argument is pointed at an injected
        # cue-object that prints when the joke's box is dismissed. The sibling-append remains
        # the fallback (and the path LSL2's synchronous Print clauses always used, unchanged).
        wording = "Just kidding! You hold on to it because you still need it."
        say_pat = re.compile(r"(\(\s*global\d+\s+say:(?:\s+\S+){4}\s+)0(\s+\S+\s*\))")
        forms = _ModeSite().forms() if T.MODE is not None else None
        if forms is None:
            # No mode (no derivable display form): the original deletion shape, unchanged.
            retraction = "%s%s\n" % (indent, _RETRACTION_FORM % wording)
            del lines[i]
            end = _clause_end_line(lines, i)
            say_at = next((j for j in range(i, end)
                           if say_pat.search(lines[j]) and "softlock" not in lines[j]), None)
            if say_at is not None:
                inst = "sgRetract%d" % sk["item"]
                lines[say_at] = say_pat.sub(r"\1%s\2" % inst, lines[say_at], count=1)
                lines[say_at] = lines[say_at].rstrip("\n") + "  ; softlock-guard: retraction rides the say\n"
                lines.append("\n(instance %s of Script\n\t(properties)\n\n"
                             "\t(method (cue)\n\t\t%s\n\t)\n)\n"
                             % (inst, _RETRACTION_FORM % wording))
            else:
                lines.insert(end, retraction)
            # Drop the penalty too. It was the price of DESTROYING the item, and the destruction
            # is gone -- charging for something that did not happen also caps the reachable score
            # permanently, a small unwinnable state of its own in a scored game. Only ever a
            # NEGATIVE score adjacent to the consumption; a positive one rewards something real.
            dropped_score = None
            if i + 1 < len(lines):
                sm = re.match(r"\s*\(global%d\s+changeScore:\s*(-\d+)\)\s*$" % _GAME, lines[i + 1])
                if sm:
                    dropped_score = int(sm.group(1))
                    del lines[i + 1]
        else:
            # Mode dispatch. The put line becomes the conditional block IN PLACE (indices below
            # stay stable); the penalty joins the disposal branch; the retraction speaks only
            # when the disposal was withheld.
            allow, warn, mark = forms
            put_src = lines[i].strip()
            dropped_score = None
            score_src = ""
            if i + 1 < len(lines):
                sm = re.match(r"\s*\(global%d\s+changeScore:\s*(-\d+)\)\s*$" % _GAME, lines[i + 1])
                if sm:
                    dropped_score = int(sm.group(1))
                    score_src = "%s\t%s\n" % (indent, lines[i + 1].strip())
                    del lines[i + 1]
            end = _clause_end_line(lines, i)
            say_at = next((j for j in range(i + 1, end)
                           if say_pat.search(lines[j]) and "softlock" not in lines[j]), None)
            if say_at is not None:
                # The withheld-this-time latch is the Script class's own `register` property --
                # an EXISTING selector, deliberately: a novel property name would need a new
                # entry in the selector vocab (997), which the patch set does not ship.
                inst = "sgRetract%d" % sk["item"]
                lines[say_at] = say_pat.sub(r"\1%s\2" % inst, lines[say_at], count=1)
                lines[say_at] = lines[say_at].rstrip("\n") + "  ; softlock-guard: retraction rides the say\n"
                lines[i] = ("%s(if %s\n"
                            "%s\t%s\n"
                            "%s\t%s\n"
                            "%s"
                            "%selse\n"
                            "%s\t(%s register: 1)\n"
                            "%s\t%s\n"
                            "%s)  ; softlock-guard: mode-conditional disposal\n"
                            % (indent, allow, indent, warn, indent, put_src, score_src,
                               indent, indent, inst, indent, mark, indent))
                lines.append("\n(instance %s of Script\n\t(properties)\n\n"
                             "\t(method (cue)\n\t\t(if register\n\t\t\t(= register 0)\n\t\t\t%s\n"
                             "\t\t)\n\t)\n)\n"
                             % (inst, _RETRACTION_FORM % wording))
            else:
                lines[i] = ("%s(if %s\n"
                            "%s\t%s\n"
                            "%s\t%s\n"
                            "%s"
                            "%s)  ; softlock-guard: mode-conditional disposal\n"
                            % (indent, allow, indent, warn, indent, put_src, score_src, indent))
                # Retraction LAST in the clause, after the announcement it answers -- and the
                # warned mark rides it: nothing between here and the block writes the warned
                # word, so `allow` reads the same both times.
                end = _clause_end_line(lines, i)
                lines.insert(end, "%s(if (not %s)\n%s\t%s\n%s\t%s\n%s)  ; softlock-guard: retraction\n"
                             % (indent, allow, indent, _RETRACTION_FORM % wording,
                                indent, mark, indent))
        new_txt = _ensure_refusal_use("".join(lines), titles_by_num)
        if say_at is not None:
            owner = _class_owner_title(dest, "Script")  # the injected cue-object's base class
            if owner:
                new_txt = _ensure_use(new_txt, owner)
        open(path, "w").write(new_txt)
        edits.append({**sk, "applied": True, "title": title, "line": i + 1,
                      "score_removed": dropped_score,
                      "retraction": "rides-the-say" if say_at is not None else "appended"})
    return edits


def _enclosing_form(text, pos):
    """(start, end) of the innermost balanced form that CONTAINS `pos`.

    `trigger._enclosing_clause_body` only understands `cond`, and SCI1.1's item verbs are a
    `switch` -- KQ6's lamp trade is `(5 (put: 19) ... (get: 25))`, a switch case -- so asking it
    about them silently answered "no clause", which is how a trade got read as a pure sink."""
    stack = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "{":
            j = text.find("}", i)
            i = n if j < 0 else j + 1
            continue
        if c == "'":
            j = text.find("'", i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == ";":
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if i == pos:
            return _block_span(text, stack[-1]) if stack else None
        if c == "(":
            stack.append(i)
        elif c == ")" and stack:
            stack.pop()
        i += 1
    return None


def _clause_end_line(lines, i):
    """The line index just past the statement list `lines[i]` belongs to.

    Walks forward tracking parenthesis depth relative to the line's position: the list ends
    where depth would go negative (its own closing paren) -- or at a bare `else`, which ends
    the arm without closing anything. Used to put a retraction AFTER the text it retracts.

    THE `else` STOP IS LOAD-BEARING (found by review, 2026-08-06). Without it the walk runs
    straight through into the sibling arm, and the retraction is emitted in the branch the
    disposal is NOT in: KQ4's `((Said 'eat/fruit') (if (has: 25) <eat+destroy> else <you do
    not have it>))` printed "Just kidding! You hold on to it" to a player who never had the
    fruit. Harmless noise until lite mode, where that stray print also SPENDS the guard's one
    warning -- so the first real fruit-eating destroys it with only "You have been warned!"."""
    depth = 0
    for j in range(i, len(lines)):
        stripped = _strip_literals(lines[j])
        if depth == 0 and re.match(r"\s*else\b", stripped):
            return j
        for ch in stripped:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    return j
    return len(lines)


def _strip_literals(line):
    """`line` with {…} strings, 'said' specs and ; comments removed, so paren counting is honest."""
    out, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c == "{":
            i = line.find("}", i)
            i = n if i < 0 else i + 1
            continue
        if c == "'":
            i = line.find("'", i + 1)
            i = n if i < 0 else i + 1
            continue
        if c == ";":
            break
        out.append(c)
        i += 1
    return "".join(out)


def refusal_form(ir):
    """The call form THIS GAME uses to display a literal line -- `"(procN_M {%s})"`, or None.

    `REFUSE` used to be LSL2's print procedure spelled out. **KQ6 has a `proc255_0` too and it is
    an unrelated procedure** (`Dialog.sc:199` calls it with no arguments, as a boolean), so the
    hardcode emits a call to something arbitrary. Here we get lucky and it fails loudly at compile
    time; in a game that exports a compatible `proc255_0` it would fail silently.

    DERIVATION, from the game's own code and in the SCI vocabulary the rest of this codebase
    already speaks: a candidate is a GLOBAL procedure whose body DISPLAYS TEXT -- it sends an
    `addText`-family or `text` selector, or calls the `Display`/`GetFarText`/`Format` kernels.
    Of those, take the one the game CALLS MOST; a literal first argument breaks ties.

    Call sites alone are not enough, which is why the body is what is read: LSL2's own code never
    passes `proc255_0` a bare literal (it passes a module/number pair), yet a literal works,
    because the procedure branches on `[param1 0] < 1000` and treats anything above that as a text
    pointer. Ranking by literal call sites instead picks `proc255_3` -- the PROMPT, whose result is
    assigned and tested.

    MEASURED, whole corpus: LSL2 `proc255_0` (2400 calls) over `proc255_3` (14); KQ4 `proc255_0`
    (2782); KQ6 and the Dagger of Amon Ra both `proc921_0`, which is
    `(procedure (proc921_0 &tmp temp0) (= temp0 (Print new:)) (temp0 addText: &rest init:))`.
    So LSL2 and KQ4 keep the exact text they have always emitted, and the two SCI1.1 titles stop
    emitting a call to a procedure that in KQ6 is an unrelated boolean."""
    from collections import Counter
    _SEL = ("addText", "addTextF", "text")
    _KERN = ("Display", "GetFarText", "Format")
    calls, lit = Counter(), Counter()
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if I.t(n) not in ("LocalCall", "PublicCall"):
                    continue
                name = n.get("name") or ""
                if not name.startswith("proc"):     # script-local: not callable from elsewhere
                    continue
                calls[name] += 1
                args = n.get("kids") or []
                if args and I.t(args[0]) == "String":
                    lit[name] += 1
    cands = set()
    for s in ir.scripts.values():
        for name, body in s.procs.items():
            if not name.startswith("proc"):
                continue
            for n in I.walk(body):
                if I.t(n) == "KernelCall" and n.get("name") in _KERN:
                    cands.add(name)
                elif I.t(n) == "Send":
                    try:
                        _recv, msgs = I.send_pairs(n)
                    except Exception:               # noqa: BLE001 -- malformed send
                        continue
                    if any(sel in _SEL for sel, _ in msgs):
                        cands.add(name)
    if not cands:
        return None
    best = max(cands, key=lambda nm: (calls[nm], lit[nm], nm))
    return "(%s {%%s})" % best


REFUSE = "(proc255_0 {Not yet!})"
# Retraction for a resource remedy, printed after the game's own "you broke/spent it" line so the
# announcement is not left lying. Generic on PURPOSE -- it must fit any wasted item, counter or
# flag, so it says nothing about what the item does. No apostrophes -- a single quote opens a Said.
_JUST_KIDDING = "(proc255_0 {Just kidding! You still need it.})"
# Lite mode's repeat-firing line (see trigger.guarded_wrap); derived by configure() like the rest.
_WARNED_LINE = "(proc255_0 {You have been warned!})"
_RETRACTION_FORM = "(proc255_0 {%s})"   # the same form, un-worded; set by configure()
# NOT the stock refusals. proc0_20 ("You don't have it.") LIES -- reported from live play at rm26,
# where the player was holding the very item they had just used; what they lacked was something
# else, needed later. proc0_15 ("Not now!") is honest but misleads in a different way: it reads as
# "the game is busy", when the real meaning is "you are missing something you will need". "Not
# yet!" says that. Literal {..} strings compile in this dialect (rm5.sc: `proc255_3 {Teleport to:}`)
# and proc255_0 takes a string pointer -- it is called that way with Format. No apostrophes: a
# single quote opens a Said spec.

def to_source_syntax(cond):
    """Our specs say `gEgo`; this decompilation names the ego by its global index (derived)."""
    return cond.replace("(gEgo has:", "(global%d has:" % _EGO)


DIRECTIONS = ("north", "south", "east", "west")


EDGEHIT = {"north": 1, "east": 2, "south": 3, "west": 4}   # Game.sc Rm.doit switch

# Placements find_trigger can actually wrap in a controllable handler: a direct newRoom, a
# changeState cutscene, or a setScript-started Script. Anything else falls back to the exit idiom.
_PLACED_KINDS = ("trigger", "direct", "setscript", "arm-event", "arm-clause",
                 "proc-call", "proc-arm")


def guard_edgehit_clause(text, direction, cond):
    """Guard a room script's own `edgeHit` reaction, which is the real trigger for a
    room-property exit.

    `Rm.doit` runs `(script doit:)` BEFORE it reads the direction property, so a room whose script
    reacts to the edge (rm47 awards 12 points and prints "You made it!") will fire that reaction
    even when the exit is closed -- and since nothing moves the ego off the edge, `edgeHit` stays
    set and it repeats forever. That is a real loop, found by play-testing, and it is why closing
    the property alone is NOT enough here.

    So: wrap the clause body, and on refusal clear `edgeHit` (exactly as `Rm.init` does) and step
    the ego back from the boundary so the flag cannot immediately re-arm."""
    n = EDGEHIT.get(direction)
    if n is None:
        return text, 0
    m = re.search(r"\(\(==\s*%d\s*\(global%d\s+edgeHit:\)\)" % (n, _EGO), text)
    if not m:
        return text, 0
    # body = everything between the clause condition and the clause's closing paren
    depth, i = 1, m.end()
    while i < len(text) and depth:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
        i += 1
    body = text[m.end():i - 1]
    ego = "global%d" % _EGO
    # The motion/flag resets ride EVERY refusal (deny_extra): without them the clause re-fires
    # each cycle. In lite-once-warned and stock the body runs instead, and the crossing itself
    # moves the ego off the edge, so the resets are refusal-only by construction.
    wrapped = ("\n\t\t\t\t"
               + guarded_wrap(cond, body, REFUSE, site=_ModeSite(), indent="\t\t\t\t",
                              deny_extra=("(%s setMotion: 0)" % ego,
                                          "(%s x: (- (%s x:) 12))" % (ego, ego),
                                          "(%s edgeHit: 0)   ; else the clause re-fires every cycle"
                                          % ego))
               + "\n\t\t\t")
    return text[:m.end()] + wrapped + text[i - 1:], 1


def _recycle_counter_break(text, write_start, msg, forms=None):
    """Neutralize a COUNTER-GATED break whose counter also indexes a bounded store.

    Some degradations are not a standalone write but a break clause `(if (>= C L) <then> else <E>)`
    where <then> degrades the item AND aborts the action, and <E> is the productive continuation.
    Deleting only the write (KQ4 shovel: `(Inv at:15) loop:1`) leaves the abort, so once the counter
    C latches at the limit the action is permanently blocked (the shovel "breaks" on every later dig).
    But C here also indexes a bounded store -- global113 counts holes AND indexes the global138 hole
    array (consecutive globals, 3 per hole), and the >=5 cap is what stops the 6th hole overrunning
    global153+ -- so simply lifting the cap corrupts memory.

    Recycle instead: when C hits the limit, pin it one under (reuse the last slot, no overflow) and
    always run the productive branch, so the tool never degrades and the store stays bounded:
        (if (>= C L) <then: msg + degrade + abort> else <E>)  ->  (if (>= C L) <msgs> <retract> (= C L-1)) <E>
    Returns (new_text, True) on success; (text, False) if the write is not in this shape (e.g. the
    bow's standalone increment, which the caller then simply deletes)."""
    best = None
    for m in re.finditer(r"\(if\b", text):
        if m.start() > write_start:
            break
        s, e = _block_span(text, m.start())
        if not (s <= write_start < e):
            continue
        depth, elp, i = 0, None, s
        while i < e:                                  # first `else` at the if's own top level
            ch = text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif (depth == 1 and text.startswith("else", i)
                  and not (text[i - 1].isalnum() or text[i - 1] in "_-")):
                elp = i
                break
            i += 1
        if elp is not None and s < write_start < elp and (best is None or s > best[0]):
            best = (s, e, elp)                        # innermost if whose THEN holds the write
    if best is None:
        return text, False
    s, e, elp = best
    cs = s + re.match(r"\(if\s+", text[s:]).end()
    if text[cs] != "(":                               # need a parenthesized comparison condition
        return text, False
    cond_s, cond_e = _block_span(text, cs)
    cond = text[cond_s:cond_e]
    cmp = re.match(r"\(\s*[<>]=?\s+(global\d+)\s+(\d+)\s*\)\s*$", cond)
    if not cmp:                                       # only a `(>= counter limit)` gate is recyclable
        return text, False
    counter, limit = cmp.group(1), int(cmp.group(2))
    anns = re.findall(r"\(proc255_0[^()]*\)", text[cond_e:elp])   # keep the clause's own announcements
    else_body = text[elp + 4:e - 1].strip()
    ind = text[text.rfind("\n", 0, s) + 1:s]
    recycle = "".join("\n%s\t\t%s" % (ind, a) for a in anns)
    recycle += "\n%s\t\t%s  ; softlock-guard: retract the break" % (ind, msg)
    if forms is not None:
        # MODE DISPATCH, and the exclusion matters. The recycle lifts `<E>` out of the `else`
        # and runs it unconditionally -- correct when the break never happens, which is what
        # full mode does. But stock must be STOCK: the break fires and `<E>` does NOT run, or
        # the player both breaks the tool and completes the dig, and the clamp that keeps the
        # counter inside its array never runs either (measured on KQ4's shovel: state 6 wrote
        # three globals past the 5-slot store). So the allow branch keeps the original
        # then/else exclusion and only the deny branch recycles.
        allow, warn, mark = forms
        # keep the stock body readable at its new depth: it moves one level in
        then_body = ("\n%s\t\t" % ind).join(
            ln.strip() for ln in text[cond_e:elp].strip().splitlines() if ln.strip())
        recycle += "\n%s\t\t%s" % (ind, mark)
        recycle += ("\n%s\t\t(= %s %d)"
                    "  ; softlock-guard: recycle the bounded store, never exhaust"
                    % (ind, counter, limit - 1))
        rebuilt = ("(if %s\n%s\t(if %s\n%s\t\t%s\n%s\t\t%s\n%s\telse%s\n%s\t\t%s\n%s\t)\n"
                   "%selse\n%s\t%s\n%s)"
                   % (cond, ind, allow, ind, warn, ind, then_body, ind, recycle,
                      ind, else_body, ind, ind, ind, else_body, ind))
        return text[:s] + rebuilt + text[e:], True
    body = "".join("\n%s\t%s" % (ind, a) for a in anns)
    body += "\n%s\t%s  ; softlock-guard: retract the break" % (ind, msg)
    body += ("\n%s\t(= %s %d)  ; softlock-guard: recycle the bounded store, never exhaust"
             % (ind, counter, limit - 1))
    rebuilt = "(if %s%s\n%s)\n%s%s" % (cond, body, ind, ind, else_body)
    return text[:s] + rebuilt + text[e:], True


def apply_resource_remedies(dest, remedies, titles_by_num):
    """Delete the WASTEFUL degradation write -- the fourth-store analogue of apply_sink_remedies.

    The write is a standalone statement, so the line is replaced with a comment (structure kept). A
    counter increment (the bow shot into the air) or a single 'dead' write (the shovel break) stops
    firing on that use, so the item no longer depletes/breaks there. The file is the write's room,
    except a Main-scope write (room 0) whose source lives in its OWN file -- carried on `object`.

    NOTE for play-test: the shovel's break CLAUSE also prints a 'broke' line and plays a break
    animation; removing only the `loop: 1` leaves those cosmetics saying it broke when it did not.
    Harmless (no softlock), flagged for a later polish pass."""
    _init_mode(dest)
    out, seen = [], set()
    for r in remedies:
        it, prop, room = r["item"], r["property"], r["room"]
        # The write's OWNING script names the file to edit (its source lives there even when the
        # write is attributed to room 0 -- KQ4's shootBow). Resolve the number to a title; fall
        # back to the room only if no script was carried (finding B#7).
        title = titles_by_num.get(r.get("script")) or (titles_by_num.get(room) if room else None)
        key = (title, it, prop, r["value"])
        if title is None or key in seen:
            continue
        seen.add(key)
        path = os.path.join(dest, "src", title + ".sc")
        try:
            lines = open(path, errors="replace").read().splitlines(True)
        except Exception as e:
            out.append({**r, "applied": False, "why": "no file %s: %s" % (title, e)})
            continue
        if _JUST_KIDDING is None:
            # The retraction is printed after the game's own "you spent it" line; with no derived
            # way to print, leaving the announcement standing would be a lie about the fix.
            out.append({**r, "applied": False,
                        "why": "no literal-display form derives for this game"})
            continue
        forms = _ModeSite().forms() if T.MODE is not None else None
        valpat = r"\(\+" if r["counter"] else r"%d\b" % r["value"]     # increment vs literal dead value
        pat = re.compile(r"\(\([^()]*\bat:\s*%d\s*\)\s*%s:\s*%s" % (it, re.escape(prop), valpat))
        hits = [i for i, l in enumerate(lines) if pat.search(l)]
        if not hits:
            out.append({**r, "applied": False, "why": "write not found in %s" % title})
            continue
        # Shape split: a COUNTER-GATED break (the write in the THEN of `(if (>= C L) ... else <E>)`,
        # C indexing a bounded store) is recycled -- deleting the write alone leaves the abort and
        # would need the cap lifted, overrunning the store (the KQ4 shovel). A standalone wasteful
        # write (the bow's shot bump) has no such clause and falls through to the delete below.
        text = "".join(lines)
        recycled = 0
        for m in reversed(list(pat.finditer(text))):
            nt, ok = _recycle_counter_break(text, m.start(), _JUST_KIDDING, forms)
            if ok:
                text, recycled = nt, recycled + 1
        if recycled:
            open(path, "w").write(text)
            out.append({**r, "applied": True, "title": title, "sites": recycled,
                        "why": "counter-gated break recycled (tool never breaks, store bounded)"})
            continue
        msg = _JUST_KIDDING
        for i in hits:
            indent = re.match(r"[ \t]*", lines[i]).group(0)
            if forms is None:
                lines[i] = "%s; [softlock-guard] %s no longer wasted here\n" % (indent, r["item_name"])
            else:
                # Mode dispatch: stock (and lite-once-warned) wastes the resource as stock does;
                # full withholds the write exactly as the comment-out always did.
                allow, warn, _mark = forms
                lines[i] = ("%s(if %s\n%s\t%s\n%s\t%s\n"
                            "%s)  ; softlock-guard: mode-conditional degradation\n"
                            % (indent, allow, indent, warn, indent, lines[i].strip(), indent))
            # Print a JUST-KIDDING line right after the clause's OWN announcement (the "you broke
            # it" / "you shot it away" message), like the airsick-bag sink, so the game does not
            # claim a loss that no longer happens. Embed the new line in the target string so the
            # list indices do not shift.
            # Search the write's OWN state clause -- from its `(N` label to the next one -- not a
            # fixed +/-8-line window, which can reach into a neighbour clause and retract the wrong
            # message (finding B#6). Fall back to the window only if the write is not inside a case.
            cstart = next((j for j in range(i, -1, -1) if re.match(r"\s*\(\d+\s*$", lines[j])), None)
            lo = cstart if cstart is not None else max(0, i - 8)
            hi = (next((j for j in range(i + 1, len(lines)) if re.match(r"\s*\(\d+\s*$", lines[j])),
                       len(lines)) if cstart is not None else min(len(lines), i + 9))
            ann = min((j for j in range(lo, hi)
                       if j != i and "proc255_0" in lines[j] and "softlock-guard" not in lines[j]),
                      key=lambda j: abs(j - i), default=None)
            tgt = i if ann is None else ann
            # If the announcement's state ENDS with an animation-wait self-cue (the bow's shot balloon
            # then `(Timer setReal: self 4)`), a retraction printed here pops mid-animation -- clunky.
            # Defer it to the start of the NEXT state clause, so it fires after the animation settles.
            # A clause with no such delay (the shovel's break) keeps the retraction after its message.
            if ann is not None:
                for j in range(ann + 1, min(len(lines), ann + 6)):
                    if re.search(r"(Timer|setReal:|setCycle:|setMotion:).*\bself\b", lines[j]):
                        nxt = next((k for k in range(j + 1, min(len(lines), j + 6))
                                    if re.match(r"\s*\(\d+\s*$", lines[k])), None)
                        if nxt is not None:
                            # Anchor AFTER the deferred state's OWN message send, not at its start.
                            # The animation state left a PERSISTENT balloon up (a proc255_0 carrying
                            # the keep-on-screen code, stashed in a global); the deferred state
                            # disposes it partway through, and a modal retraction printed BEFORE that
                            # disposal cannot take focus -- it flashes and never shows. The state's
                            # last proc255_0 runs after the balloon is gone, so put it there; else
                            # just before the script teardown; else the state start.
                            sind = len(re.match(r"[ \t]*", lines[nxt]).group(0))
                            end = len(lines)
                            for k in range(nxt + 1, len(lines)):
                                if re.match(r"\s*\(\d+\s*$", lines[k]):
                                    end = k; break
                                if (lines[k].strip() == ")"
                                        and len(re.match(r"[ \t]*", lines[k]).group(0)) <= sind):
                                    end = k; break
                            cand = [k for k in range(nxt + 1, end)
                                    if "proc255_0" in lines[k] and "softlock-guard" not in lines[k]]
                            if cand:
                                tgt = cand[-1]
                            else:
                                tear = next((k for k in range(nxt + 1, end)
                                             if re.search(r"\b(DisposeScript|dispose:)", lines[k])),
                                            None)
                                tgt = tear - 1 if tear is not None else nxt
                        break
            aind = re.match(r"[ \t]*", lines[tgt]).group(0)
            if forms is None:
                lines[tgt] = lines[tgt].rstrip("\n") + "\n%s%s  ; [softlock-guard]\n" % (aind, msg)
            else:
                # The retraction only speaks when the write was withheld, and the warned mark
                # rides it (nothing between the write and here touches the warned word).
                allow, _warn, mark = forms
                lines[tgt] = (lines[tgt].rstrip("\n")
                              + "\n%s(if (not %s) %s %s)  ; [softlock-guard]\n"
                              % (aind, allow, msg, mark))
        open(path, "w").write("".join(lines))
        out.append({**r, "applied": True, "title": title, "sites": len(hits)})
    return out


# ⭐ THE THREE MODES AS THE PLAYER SEES THEM, indexed by the mode value (0 full / 1 lite /
# 2 stock). The INTERNAL name of mode 2 stays "stock" -- it is the stock game, and that is what
# `trigger.stock_or` and every doc call it -- but "Stock" means nothing to somebody mid-game,
# where the question is only whether the guards are on: **"Off"** [user, 2026-08-08].
#
# It is one tuple because the label was written out SIX times across the two dialects (a button,
# a "now:" line and a face label on each), and a rename that reaches five of them is worse than
# no rename at all -- the UI would then disagree with itself about what the mode is called.
MODE_NAMES = ("Full", "Lite", "Off")
_CHOOSER_TEXT = ("Softlock guards: %s refuses dangerous moves. "
                 "%s warns once then allows. %s is the original game."
                 % tuple(n.upper() for n in MODE_NAMES))
_CHOOSER_TITLE = "Softlock guards"      # short form, for a prompt that names the current mode


def _mode_button(i):
    """The button label for mode `i`, padded so the three read as one row of controls.

    Both choosers place their buttons at fixed x positions, so the box each one draws is sized
    by its own text: centring every name in the widest name's width keeps them even when the
    names are not (`Off` is two characters shorter than `Stock` was)."""
    return "  %s  " % MODE_NAMES[i].center(max(len(n) for n in MODE_NAMES))


def install_mode_chooser(dest, titles_by_num):
    """The CHOOSER half of the mode feature -- run BEFORE any wrap is emitted, because it is
    also the mode's own FEASIBILITY GATE: a mode nobody can switch is not a mode. If neither
    dialect shape hosts a chooser (SCI0 menu bar / SCI1.1 control panel), the mode is
    RETRACTED (`T.MODE = None`, `_MODE_DEST` left pinned so `_init_mode` cannot re-arm) and
    every later emitter takes the classic always-refuse path: no mode conjunct in any wrap, no
    mode/warned globals, and -- on a game whose stock declarations already cover its reads --
    no Main in the patch at all.

    LB2 is the case that forced the gate (docs/LB2-ORACLE.md §7ak): its GameControls panel has
    no `(= nsTop (.. X else Y ..))` row ladder to clone, so v1 shipped mode plumbing with no
    picker -- and shipping the plumbing meant shipping a recompiled Main, whose `WrapMusic`
    class (a game class declared in script 0, stock species 134) came back numbered 46,
    colliding with `Actions` (46, script 950): `LB2::init`'s `(WrapMusic add:)` resolved to a
    class with no `add` and the game crashed at boot. The species drift is a real compiler gap
    (scicompile numbers classes by its own enumeration, not the game's table) -- but the mode
    plumbing was the only reason Main shipped, and a chooser-less mode was dead weight anyway.
    The gate removes the exposure for every game whose script 0 declares a class; the species
    gap itself stays open and documented for the day a patch NEEDS to edit such a script."""
    _init_mode(dest)
    if T.MODE is None:
        return []
    src_dir = os.path.join(dest, "src")
    row = _install_menu_chooser(src_dir, T.MODE["g"])
    if row is None:
        row = _install_panel_chooser(src_dir, T.MODE["g"])
    if row is None or not row.get("applied"):
        T.MODE = None
        row = row if row is not None else {"applied": False, "ui": None, "why": ""}
        row["why"] = ((row.get("why") or "no menu bar or control panel shape found to host "
                       "the chooser") + " -- MODE RETRACTED, wraps emit modeless")
        return [row]
    return [row]


def declare_mode_globals(dest):
    """The DECLARATION half: `_declare_missing_globals` re-run AFTER every apply pass, because
    the mode/warned globals exist only in emitted text -- `assemble()`'s early run cannot see
    them. Nothing to do on a modeless run (the wraps then reference no new global)."""
    if T.MODE is None:
        return []
    if _declare_missing_globals(os.path.join(dest, "src")):
        return [{"applied": True, "title": "Main", "ui": "globals",
                 "why": "mode/warned globals declared"}]
    return []


def install_mode_ui(dest, titles_by_num):
    """Install the in-game guard-mode chooser and declare the mode/warned globals.

    ⚠️ LEGACY COMPOSITION -- both halves at once, which is only correct when called BEFORE any
    wrap emission or on a game whose chooser lands. The pipeline calls the halves separately
    (`install_mode_chooser` right after `assemble`, `declare_mode_globals` after the applies);
    a late composed call on a chooser-less game retracts the mode after wraps already
    referenced it, and the compile then fails loudly on the undeclared mode global.

    The player-facing half of the mode feature: an entry in each game's own settings surface
    that sets the mode global (0 full / 1 lite / 2 stock). The SURFACE is derived by shape,
    the same way `refusal_form` derives the display proc:

      * SCI0's settings live on the MENU BAR -- the file with the most literal `(AddMenu {..}
        {..})` declarations (Menu.sc on LSL2/KQ4; KQ4's DebugMenu has one and Interface's
        `(AddMenu &rest)` forwarder has none). A `Guards...` item is APPENDED to the last
        declared menu -- appending is the one placement that cannot shift any existing menu
        code, including KQ4's runtime DebugMenu (menu 6) -- and its handler case is inserted
        before the handleEvent switch's own top-level `else`, reusing the switch's `temp0`.
        The chooser is the game's own button dialog (`81 <text> <value>` pairs on the derived
        display proc, values 1/2/3 so 0 = dismissed = keep).
      * SCI1.1's settings are the CONTROL PANEL -- the file holding the `of GameControls`
        instance. A ControlIcon is added below the deepest existing icon row (nsTop expression
        copied from the host file with its row offsets +20; view 947's window interior leaves
        ~38px below the last row, measured), cloned from iconTextSwitch's working shape
        (signal $0183: the panel stays open, `theObj: self selector: #doit`), face reusing an
        existing button loop. Its doit runs a 3-button `Print` chooser (the font spelled as
        the host file spells it).

    Returns edit rows (never merged into the apply_* returns -- those are a frozen snapshot
    surface); `title`s must join the emission set, `Main` included when the declaration pass
    touched it."""
    return install_mode_chooser(dest, titles_by_num) + declare_mode_globals(dest)


def _install_menu_chooser(src_dir, g):
    """The SCI0 half of `install_mode_ui`. Returns an edit row, or None if no menu bar."""
    addmenu = re.compile(r"\(AddMenu\s+\{[^}]*\}\s+\{([^}]*)\}\s*\)", re.S)
    best, best_n = None, 0
    for fn in sorted(os.listdir(src_dir)):
        if fn.endswith(".sc"):
            txt = open(os.path.join(src_dir, fn), errors="replace").read()
            n = len(addmenu.findall(txt))
            if n > best_n:
                best, best_n, text = fn, n, txt
    if best is None or best_n < 2:     # one AddMenu is a runtime extension, not the bar
        return None
    menus = list(addmenu.finditer(text))
    # WHICH MENU. Not simply the last one: that is the SOUND menu on both SCI0 games, and a
    # softlock-guard setting does not belong beside the volume control [user, play,
    # 2026-08-06: "it shouldn't be under Sound"]. The menus that own DEVICE and SESSION
    # settings identify themselves by what their handler cases DO -- audio menus call the
    # sound kernel, speed menus send `setSpeed:`, the file menu sends save/restore/restart/
    # quit -- so they are excluded by the game's own vocabulary rather than by reading their
    # English titles. What remains is the gameplay menu; take the last of those (LSL2 and KQ4
    # both land on `Action`, beside Pause and Inventory).
    hm0 = re.search(r"\(method\s+\(handleEvent\b", text)
    sw_text = text[_block_span(text, hm0.start())[0]:_block_span(text, hm0.start())[1]] \
        if hm0 else ""
    _DEVICE = ("DoSound", "setSpeed:", "save:", "restore:", "restart:", "quitGame:",
               "restartGame", "RestartGame")

    def _is_device_menu(mi, m):
        """Does menu `mi`'s own handler code only touch the sound/speed/session machinery?"""
        n_items = m.group(1).count(":") + 1
        bodies = []
        for item in range(1, n_items + 1):
            cm = re.search(r"\(\s*%d\b" % ((mi << 8) | item), sw_text)
            if cm:
                bodies.append(sw_text[cm.start():_balanced_span(sw_text, cm.start())])
        return bool(bodies) and all(any(d in b for d in _DEVICE) for b in bodies)

    eligible = [i for i, m in enumerate(menus, 1) if not _is_device_menu(i, m)]
    menu_idx = eligible[-1] if eligible else len(menus)
    host_menu = menus[menu_idx - 1]
    item_idx = host_menu.group(1).count(":") + 2      # separators count; ours appends after all
    code = (menu_idx << 8) | item_idx
    text = text[:host_menu.end(1)] + ":Guards..." + text[host_menu.end(1):]
    # the handler case, before the switch's own top-level else (same file, same method)
    hm = re.search(r"\(method\s+\(handleEvent\b", text)
    if not hm:
        return {"applied": False, "ui": "menu", "title": best[:-3],
                "why": "menu bar has no handleEvent to extend"}
    ms, me = _block_span(text, hm.start())
    sw = re.search(r"\(switch\s+\(=\s+(\w+)\s+\(super handleEvent:", text[ms:me])
    if not sw:
        return {"applied": False, "ui": "menu", "title": best[:-3],
                "why": "menu handleEvent has no `(switch (= tN (super handleEvent:` head"}
    tmp = sw.group(1)
    ss, se = _block_span(text, ms + sw.start())
    # top-level clauses of the switch: depth-1 forms after the head expression
    head_end = _block_span(text, text.index("(", ms + sw.start() + 1))[1]   # the head expr
    at, depth, i = None, 0, head_end
    while i < se:
        ch = text[i]
        if ch == "(":
            if depth == 0 and re.match(r"\(\s*else\b", text[i:]):
                at = i
                break
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                break
        i += 1
    if at is None:
        at = se - 1                                   # no else: before the switch's close
    indent = re.search(r"[ \t]*$", text[:at]).group(0)
    proc = re.search(r"\(proc\d+_\d+", _RETRACTION_FORM).group(0)[1:]
    # A SCRATCH TEMP FOR THE PROMPT, taken from the method's own `&tmp` list (never invented:
    # a name the method does not declare will not compile). The prompt names the CURRENT mode,
    # as the SCI1.1 chooser does [user, 2026-08-06: "it should give you the currently selected
    # level, same as kq6"] -- built by picking one of three literals, because this display proc
    # takes a single text argument and `Format` would need a game-specific buffer global.
    decl = re.search(r"\(method\s+\(handleEvent[^)]*&tmp([^)]*)\)", text)
    temps = [t for t in re.findall(r"\b(\w+)\b", decl.group(1) or "") if t != tmp] if decl else []
    label = temps[0] if temps else None
    if label is None:
        prompt = "{%s}" % _CHOOSER_TEXT
        pre = ""
    else:
        prompt = label
        pre = ("%s\t(= %s {%s -- now: %s})\n"
               "%s\t(if (== global%d 1)\n"
               "%s\t\t(= %s {%s -- now: %s})\n"
               "%s\telse\n"
               "%s\t\t(if (== global%d 2) (= %s {%s -- now: %s}))\n"
               "%s\t)\n"
               % (indent, label, _CHOOSER_TITLE, MODE_NAMES[0].upper(),
                  indent, g, indent, label, _CHOOSER_TITLE, MODE_NAMES[1].upper(),
                  indent, indent, g, label, _CHOOSER_TITLE, MODE_NAMES[2].upper(), indent))
    case = ("(%d\n"
            "%s"
            "%s\t(= %s\n"
            "%s\t\t(%s\n"
            "%s\t\t\t%s\n"
            "%s\t\t\t81 {%s} 1\n"
            "%s\t\t\t81 {%s} 2\n"
            "%s\t\t\t81 {%s} 3\n"
            "%s\t\t)\n"
            "%s\t)\n"
            "%s\t(if %s (= global%d (- %s 1)))\n"
            "%s)  ; softlock-guard: mode chooser\n%s"
            % (code, pre, indent, tmp, indent, proc, indent, prompt,
               indent, _mode_button(0), indent, _mode_button(1), indent, _mode_button(2),
               indent, indent, indent, tmp, g, tmp, indent, indent))
    text = text[:at] + case + text[at:]
    open(os.path.join(src_dir, best), "w").write(text)
    return {"applied": True, "ui": "menu", "title": best[:-3], "menu_code": code,
            "menu_index": menu_idx, "shows_current": label is not None}


def _icon_press_bit(src_dir):
    """The signal bit that makes a control icon ANIMATE ITS PRESS, read out of the icon class.

    `IconI::select` draws cel 1 of the icon's own loop while the button is held and cel 0 when it
    is released -- the SCI convention that a control's loop is a two-cel pair {0: up, 1: down}.
    An icon whose face is NOT such a pair must not ask for that animation, or the press paints
    whatever else happens to live in the loop (see `_install_panel_chooser`). The bit is a class
    constant, so read it off the condition that guards that first DrawCel rather than naming it.
    """
    m = re.search(r"\(&\s*signal\s*\$([0-9a-fA-F]+)\s*\)[^\n]*\n\s*"
                  r"\(DrawCel\s+view\s+loop\s+\(=\s*\w+\s+1\)", _all_sources(src_dir))
    return int(m.group(1), 16) if m else 1


def _dialog_icon(text):
    """The panel's OWN control that opens a dialog: a `select` that hides the panel, then prints.

    Returns (name, signal). That signal is the one to clone for a chooser, because opening a
    dialog from inside the panel is not a free-standing act: the panel is a modal running its own
    event loop, and only an icon whose signal carries the "dismiss" bit makes that loop exit
    (`IconBar::dispatchEvent` sets its exit flag from `(& signal $0040)`). Cloning the icon that
    already does it correctly takes that bit, and the panel's own "I position myself" and "the
    arrow keys reach me" bits, without this code having to know which is which.
    """
    found = None
    for m in re.finditer(r"\(instance\s+(\w+)\s+of\s+\w+", text):
        body = text[m.start():_balanced_span(text, m.start())]
        sm = re.search(r"\(method\s+\(select\b", body)
        if not sm:
            continue
        sel = body[sm.start():_balanced_span(body, sm.start())]
        if "hide:" not in sel or "Print" not in sel:
            continue
        g = re.search(r"\bsignal\s+(\d+)", body)
        if g:
            found = (m.group(1), int(g.group(1)))
    return found


def _install_panel_chooser(src_dir, g):
    """The SCI1.1 half of `install_mode_ui`. Returns an edit row, or None if no panel."""
    host, text, panel = None, None, None
    for fn in sorted(os.listdir(src_dir)):
        if fn.endswith(".sc"):
            t = open(os.path.join(src_dir, fn), errors="replace").read()
            m = re.search(r"\(instance\s+(\w+)\s+of\s+GameControls\b", t)
            if m:
                host, text, panel = fn, t, m.group(1)
                break
    if host is None:
        return None
    # THE GLOBAL THAT HOLDS THE PANEL, read from its own `(= globalN self)` -- the panel has to
    # be hidden before a chooser opens over it (see the instance below), and `iconAbout` does
    # that through this global rather than by naming the instance. Derived, not assumed: a game
    # that keeps its panel somewhere else still gets the right receiver, and one that keeps it
    # nowhere falls back to the instance name, which is in scope in the same file anyway.
    pg = re.search(r"\(=\s*(global\d+)\s+self\)", text)
    panel_global = pg.group(1) if pg else panel
    # THE NEW ROW. The panel's rows are a ladder: each icon's `nsTop` is the same expression
    # with one constant per row, and the PITCH is the gap between consecutive rungs (20 on
    # KQ6). Derive the pitch from the ladder rather than assuming it, then hang the new row
    # one pitch below the deepest one -- and grow the window by the same amount, or the icon
    # lands outside the window and is clipped (the v26 bug, user screenshot 2026-08-06).
    tops = re.findall(r"\(=\s+nsTop\s+(\(.*?\))\s*\)", text)
    rows = [(int(m.group(1)), int(m.group(2)), t)
            for t in tops
            for m in [re.search(r"\(if [^)]*\)\s*(\d+)\s+else\s+(\d+)", t.replace("\n", " "))]
            if m]
    if not rows:
        return {"applied": False, "ui": "panel", "title": host[:-3],
                "why": "no `(= nsTop (.. X else Y ..))` row idiom to clone"}
    ladder = sorted({r[0] for r in rows})
    pitch = min((b - a for a, b in zip(ladder, ladder[1:])), default=20)
    x, y, tmpl = max(rows)
    ns_top = tmpl.replace(" %d " % x, " %d " % (x + pitch), 1)
    ns_top = re.sub(r"else\s+%d\b" % y, "else %d" % (y + pitch), ns_top, count=1)
    fm = re.search(r"font:\s*(global\d+|\d+)", text)
    font = fm.group(1) if fm else "0"
    # THE FACE, and why it is not a button cel. Every button face in a panel like this is a
    # WORD baked into the art (KQ6's view 947: SAVE/RESTORE/RESTART/QUIT/ABOUT/PLAY/SPEECH/
    # TEXT), so borrowing one ships a control that lies about what it does -- the v26 build
    # grew a second "SAVE". What the window DOES have is blank art: the inset plates its own
    # `open` draws behind its controls. Take that cel as the face and write the label with
    # `Display`, the same kernel the game uses for every other run-time string. Zero new art,
    # and the label says what the control is.
    #
    # The plate is found by its y-expression carrying the DEEPEST row's constant (KQ6: the
    # 58x22 inset under the text/speech switch); its own DrawCel arguments give view/loop/cel
    # and x. Spans come from `_balanced_span`, not a nesting-depth regex: the y argument is
    # three forms deep (`(+ 0 (if (== g 256) A else B) 7)`) and a hand-rolled pattern misses it.
    plate = None
    deep = re.compile(r"\b%d\b\s+else\s+\b%d\b" % (x, y))
    for dm in re.finditer(r"\(\s*DrawCel\b", text):
        d = text[dm.start():_balanced_span(text, dm.start())]
        args = re.match(r"\(\s*DrawCel\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(\(|-?\d)", d)
        if not args or not deep.search(re.sub(r"\s+", " ", d)):
            continue
        ym = re.search(r"\(\s*DrawCel\s+\d+\s+\d+\s+\d+\s+-?\d+\s+", d)
        yexpr = d[ym.end():_balanced_span(d, ym.end())] if d[ym.end()] == "(" else None
        if yexpr is None:
            continue
        plate = {"view": args.group(1), "loop": args.group(2), "cel": args.group(3),
                 "x": int(args.group(4)),
                 "y": deep.sub("%d else %d" % (x + pitch, y + pitch), yexpr, count=1)}
        break
    if plate is None:
        return {"applied": False, "ui": "panel", "title": host[:-3],
                "why": "no blank inset cel is drawn behind the deepest control row, so there "
                       "is no unlabelled face to host the chooser (every button face in the "
                       "panel art carries a baked-in word)"}
    view, loop, cel = plate["view"], plate["loop"], plate["cel"]
    deep_left, ns_top = plate["x"], plate["y"]
    # the label's colour: the panel's own highlight colour, as it sets it on every element
    hm = re.search(r"eachElementDo:\s*#highlightColor\s+(\d+)", text)
    ink = hm.group(1) if hm else "0"
    # MEASURE the plate and the font, rather than assume they fit. Two UI defects came out of
    # assuming: v26 put a long sentence in a dialog and the wrap drew the buttons over the text,
    # and the single-line label was sized by eye. A font is a resource like any other
    # (`sci_gfx.decode_font`), so the label layout below is derived from real metrics --
    # measured on KQ6: plate 58x22, font 4 is 9px tall, "GUARDS" 31px, "STOCK" 27px.
    plate_w, plate_h, font_h = 58, 22, 9
    # Is the face a BUTTON PAIR -- loop = {cel 0: up, cel 1: down}, the shape `IconI::select`
    # assumes when it animates a press? Ours never is (see the signal below), but prove it from
    # the art instead of asserting it, and default to "no" when the art cannot be read: the
    # safe answer is the one that draws nothing extra.
    face_is_button_pair = False
    try:
        import sci_gfx as _gfx
        import sci_resource as _res
        game = _res.Sci0Game(config.ACTIVE.resource_dir)
        cels = _gfx.decode_view(game, int(view))[int(loop)]["cels"]
        c = cels[int(cel)]
        plate_w, plate_h = c.width, c.height
        face_is_button_pair = (int(cel) == 0 and len(cels) > 1
                               and (cels[0].width, cels[0].height)
                                   == (cels[1].width, cels[1].height))
        # the panel names its font as a GLOBAL (KQ6: `font: global22`); resolve it to the
        # number the game assigns, since only a number can be looked up as a resource
        fnum = font
        if str(font).startswith("global"):
            am = re.search(r"\(=\s*%s\s+(\d+)\)" % re.escape(str(font)), _all_sources(src_dir))
            fnum = am.group(1) if am else None
        if fnum is not None:
            font_h = _gfx.decode_font(game, int(fnum))["height"] or font_h
    except Exception:                                  # noqa: BLE001 -- unreadable art/font
        pass
    # Two lines -- what the control IS, and what it is SET TO -- when the plate can hold them.
    two_line = 2 * font_h <= plate_h
    top1 = max(0, (plate_h - (2 * font_h if two_line else font_h)) // 2)
    top2 = top1 + font_h
    # ⭐ THE SIGNAL, AND THE ONE BIT THAT BROKE THREE BUILDS.
    #
    # `IconI::select` animates a press by drawing cel 1 of the icon's own loop while the mouse is
    # held and cel 0 when it is released -- the SCI convention that a control's loop is a two-cel
    # pair {0: up, 1: down}. Every real button in this panel obeys it (KQ6 loops 2..9 are each
    # exactly two 50x15 cels). OUR FACE DELIBERATELY DOES NOT: it is a blank plate taken from the
    # window's decorative loop, because every button loop has a word baked into its art. On KQ6
    # that loop is [0: a 12x43 slider arrow strip, 1: the 58x122 left-hand inset, 2: the plate],
    # so asking for the animation painted the arrow strip and the big inset at the control's
    # position. Three play reports, one mechanism -- and the artifact was MEASURED off the
    # screenshot back to those two cels at nsLeft/nsTop, not inferred:
    #   v29 "a + - slider artifact"  -- cel 0 IS the strip; its top rows are a +, its bottom a -.
    #   v30 "looks weird on click"   -- cel 1, clipped by the window edge, plus cel 0 on release.
    #   v31 "same behavior"          -- nothing in v31 touched this bit, so nothing changed.
    # (The nesting theory and the window-growth theory were both wrong: v29 grows the window too
    # and is clean at rest, and v31 hid the panel before printing to no effect.)
    #
    # So: clone the signal of the panel's own dialog-opening control -- which is where `select`,
    # the hide, and the dismiss bit that lets the icon bar's modal loop exit all come from -- and
    # clear the press bit unless the face really is a button pair. Both the bit and the template
    # are read out of the game.
    tmpl = _dialog_icon(text)
    if tmpl is None:
        return {"applied": False, "ui": "panel", "title": host[:-3],
                "why": "the panel has no control of its own that opens a dialog (a `select` that "
                       "hides the panel and then prints), so there is no working shape to clone "
                       "for a chooser -- and an icon that opens one without the panel's dismiss "
                       "bit leaves the modal loop running over a disposed window"}
    press_bit = _icon_press_bit(src_dir)
    signal = tmpl[1] if face_is_button_pair else tmpl[1] & ~press_bit
    # join the panel's add: list right before its first eachElementDo:
    ee = re.search(r"\n([ \t]*)eachElementDo:", text)
    if not ee:
        return {"applied": False, "ui": "panel", "title": host[:-3],
                "why": "GameControls add: list has no eachElementDo: anchor"}
    # THREE SPLICES, ONE TEXT. All spans are measured on the same pristine text, so they are
    # applied BACK TO FRONT -- splicing front to back shifts every later span and lands the
    # next edit mid-form (measured: it chopped the plaque draw in half).
    edits = []
    ind = ee.group(1)
    # `init:` and `selector: #doit`, exactly as `iconAbout` joins the list -- an icon that opens
    # a dialog is initialised like the game's own do, and positions itself in `init` as well as
    # `show`. (iconTextSwitch, which only toggles, skips both; we are the About shape now.)
    edits.append((ee.start(), ee.start(),
                  "\n%s(iconGuards init: selector: #doit yourself:)" % ind))
    # GROW THE WINDOW by one pitch, or the new row is drawn outside it and clipped (the v26
    # bug). The window's own `bottom:` expression is WRAPPED, never rewritten, so whatever
    # the game computed still decides where the panel sits and how tall its art is.
    grew = False
    bset = re.search(r"\n\s*bottom:\s*", text)
    if bset:
        rest = text[bset.end():]
        if rest.lstrip()[:1] == "(":
            off = bset.end() + (len(rest) - len(rest.lstrip()))
            bend = _balanced_span(text, off)
            edits.append((off, bend, "(+ " + text[off:bend] + " %d)" % pitch))
            grew = True
    for (s0, s1, rep) in sorted(edits, reverse=True):
        text = text[:s0] + rep + text[s1:]
    # ⭐ THE CHOOSER IS A DIALOG, OPENED THE WAY THIS PANEL ALREADY OPENS ONE. Four play reports
    # shaped it:
    #   1. v26: the chooser drew its buttons over its own wrapped text  -> short lines.
    #   2. v29: a "+ - slider" artifact, and THE PANEL NEVER CLOSING    -> a broken game.
    #   3. v30: cycling in place fixed the closing, but it "looks weird on click", and the user
    #      preferred the dialog: "I liked the previous UI better honestly."
    #   4. v31: the dialog restored, panel hidden first -- "same behavior".
    # The artifact common to (2), (3) and (4) is the press animation, and it is dealt with by the
    # signal above, not here. What (2) needed was this: its `doit` ended with `(<panel> show:)`,
    # which re-enters `GameControls::show` and runs the panel's whole modal event loop a second
    # time from inside itself -- so dismissing the inner loop only ever returned to the outer one
    # and the panel never went away. The panel is not re-shown; it is DISMISSED, and the dismiss
    # bit in the cloned signal is what makes the icon bar's loop stop.
    #
    # `iconAbout`, in this same file, is the shape:
    #
    #     (method (select)
    #         (super select: &rest)
    #         (global63 hide:)          ; the panel goes away FIRST
    #         (KQ6Print ... init:))
    #
    # so: `select` (not `doit`), the panel hidden before the chooser opens, and `(return 1)` at
    # the end -- `IconBar::dispatchEvent` only reaches its exit flag inside `(if (self select:
    # ...))`, so a `select` that returns 0 when the chooser is dismissed would leave the modal
    # loop spinning over a window it had just disposed. `global63` is the panel itself,
    # `(= global63 self)` in its own init, so it is read from the game and not assumed.
    inst = (
        "\n(instance iconGuards of ControlIcon\n"
        "\t(properties\n\t\tview %s\n\t\tloop %s\n\t\tcel %s\n\t\tsignal %d\n\t)\n\n"
        # The label is written AFTER `super show:` -- the plate is the icon's own face, so a
        # label drawn before it would be painted over. dsBACKGROUND -1 keeps the plate visible
        # behind the text; dsALIGN 1 centres it in the plate's own width, and the vertical
        # offsets are the font's real height in the plate's real height, not a guessed 6. Two
        # lines when they fit -- what the control IS over what it is SET TO -- so the mode is
        # legible without opening anything, which is also the only way to read it back after the
        # chooser has closed the panel behind itself.
        "\t(method (show%s)\n"
        "%s"
        "\t\t(= nsLeft %d)\n"
        "\t\t(= nsTop %s)\n"
        "\t\t(super show: &rest)\n"
        "\t\t(Display {GUARDS}\n"
        "\t\t\t100 nsLeft (+ nsTop %d)\n"
        "\t\t\t105 %s\n\t\t\t102 %s\n\t\t\t103 -1\n\t\t\t106 %d\n\t\t\t101 1\n"
        "\t\t)\n"
        "%s"
        "\t)\n\n"
        # About defines `init` as well as `show`, because it is init:-ed from the add: list.
        "\t(method (init)\n"
        "\t\t(= nsLeft %d)\n"
        "\t\t(= nsTop %s)\n"
        "\t\t(super init: &rest)\n"
        "\t)\n\n"
        # Short lines only: a long unpositioned sentence WRAPS, and buttons placed on the
        # wrapped line are drawn over the text (the v26 defect).
        "\t(method (select &tmp temp0 temp1)\n"
        "\t\t(super select: &rest)\n"
        "\t\t(%s hide:)\n"
        "\t\t(= temp1 {now: %s})\n"
        "\t\t(if (== global%d 0)\n"
        "\t\t\t(= temp1 {now: %s})\n"
        "\t\telse\n"
        "\t\t\t(if (== global%d 1) (= temp1 {now: %s}))\n"
        "\t\t)\n"
        "\t\t(= temp0\n"
        "\t\t\t(Print\n"
        "\t\t\t\tfont: %s\n"
        "\t\t\t\taddText: {Softlock guards:}\n"
        "\t\t\t\taddText: temp1 0 14\n"
        "\t\t\t\taddButton: 1 {%s} 0 34\n"
        "\t\t\t\taddButton: 2 {%s} 48 34\n"
        "\t\t\t\taddButton: 3 {%s} 96 34\n"
        "\t\t\t\tinit:\n"
        "\t\t\t)\n"
        "\t\t)\n"
        # dismissing the chooser (temp0 == 0) keeps the current mode
        "\t\t(if temp0 (= global%d (- temp0 1)))\n"
        # ...and the icon bar's loop only reads its exit flag on a TRUE select (see above)
        "\t\t(return 1)\n"
        "\t)\n)\n" % (view, loop, cel, signal,
                      " &tmp temp0" if two_line else "",
                      ("\t\t(= temp0 {%s})\n"
                       "\t\t(if (== global%d 0)\n"
                       "\t\t\t(= temp0 {%s})\n"
                       "\t\telse\n"
                       "\t\t\t(if (== global%d 1) (= temp0 {%s}))\n"
                       "\t\t)\n" % (MODE_NAMES[2].upper(), g, MODE_NAMES[0].upper(),
                                    g, MODE_NAMES[1].upper())) if two_line else "",
                      deep_left, ns_top, top1, font, ink, plate_w,
                      ("\t\t(Display temp0\n"
                       "\t\t\t100 nsLeft (+ nsTop %d)\n"
                       "\t\t\t105 %s\n\t\t\t102 %s\n\t\t\t103 -1\n\t\t\t106 %d\n\t\t\t101 1\n"
                       "\t\t)\n" % (top2, font, ink, plate_w)) if two_line else "",
                      deep_left, ns_top, panel_global,
                      MODE_NAMES[2].lower(), g, MODE_NAMES[0].lower(),
                      g, MODE_NAMES[1].lower(), font,
                      _mode_button(0), _mode_button(1), _mode_button(2), g))
    text = text + inst
    open(os.path.join(src_dir, host), "w").write(text)
    return {"applied": True, "ui": "panel", "title": host[:-3], "row_pitch": pitch,
            "window_grown": grew, "face": "%s/%s/%s (blank plate + Display label)"
                                          % (view, loop, cel),
            # say the signal out loud: it is the whole of the v29..v31 defect, and a build log
            # that prints "cloned iconAbout 449 -> 448 (no press animation)" is reviewable
            "signal": signal, "cloned_from": "%s %d" % tmpl,
            "press_animation": bool(signal & press_bit)}


def guard_board_commit(text, cond):
    """Gate the controllable action that BOARDS the scripted vehicle leaving a property-exit room.

    Some rooms have no `newRoom` and no edgeHit reaction: leaving is a scripted vehicle that `MoveTo`s
    the ego off-screen, and the engine reads the direction property at the boundary (KQ4 rm43: mount
    the dolphin -> it rides you off the right edge -> the `east 31` property). Zeroing that property
    HANGS -- the vehicle loops against the closed edge. The real commit is the player action that
    boards the vehicle, and it surrenders control (`(User canControl: 0)`) inside a handleEvent Said
    clause. Wrap that whole clause so it refuses without the item: the ride never starts, no hang.
    Distinct from guard_edgehit_clause, which guards an edge REACTION; here nothing reacts, the
    vehicle drives into the edge."""
    if not re.search(r"\(method\s+\(handleEvent\b", text):
        return text, 0
    m = re.search(r"\(User\s+canControl:\s*0\b", text)
    if not m:
        return text, 0
    clause = _enclosing_clause_body(text, m.start())
    if not clause:
        return text, 0
    bs, be = clause
    wrapped = guarded_wrap(cond, text[bs:be], REFUSE, site=_ModeSite(),
                           marker="; softlock-guard: cannot board without it")
    return text[:bs] + wrapped + text[be:], 1


def guard_edge_exit(text, inst_name, to_room, cond):
    """Guard a ROOM-PROPERTY exit (`east 48`), which no `newRoom:` call can be wrapped around.

    Walking off-screen is engine-handled: the Rm instance names the neighbour in a property, so
    there is no call site for `trigger.find_trigger` to find. The game's own idiom for closing such
    an exit is `(global2 <dir>: 0)` -- used in rm15, rm42, rm74 and rm77 -- so we re-evaluate the
    guard on every room entry and close the exit when it fails.

    Silent by nature: a disabled edge behaves as a wall, with no refusal text. That is how the game
    already does it, and it is the only lever available for this kind of exit."""
    # ANY room class: LSL2/KQ4 rooms are `of Rm`, KQ6's are `of KQ6Room`, the Dagger's `of LBRoom`.
    # Nothing needs deriving -- the instance NAME is the script's own room object, so the class it
    # inherits from is not what identifies it, and hardcoding `Rm` meant this fallback could never
    # fire on any SCI1.1 title.
    m = re.search(r"\(instance\s+%s\s+of\s+\w+" % re.escape(inst_name), text)
    if not m:
        return text, 0, None
    props = re.search(r"\(properties(.*?)\)", text[m.start():], re.S)
    if not props:
        return text, 0, None
    directions = [d for d in DIRECTIONS
                  if (pm := re.search(r"\b%s\s+(\d+)\b" % d, props.group(1)))
                  and int(pm.group(1)) == to_room]
    if not directions:
        # KQ4 idiom: exits set by ASSIGNMENT in init, e.g. (= south (= north (= west (= east 31)))).
        # A direction's resolved value is the innermost literal of its (chained) assignment, so all
        # four directions in that chain lead to rm31 and all must be closed. LSL2 declares exits in
        # the properties block instead (handled above); each game uses exactly one idiom.
        body = text[m.start():]
        for d in DIRECTIONS:
            am = re.search(r"\(=\s+%s\b" % d, body)
            if not am:
                continue
            bs, be = _block_span(body, am.start())
            nums = re.findall(r"\b(\d+)\b", body[bs:be])
            if nums and int(nums[-1]) == to_room:
                directions.append(d)
    if not directions:
        return text, 0, None
    # If the room's script reacts to this edge, guard THAT clause instead: closing the property
    # would let the reaction fire on a loop (see guard_edgehit_clause).
    for d in directions:
        new_text, n = guard_edgehit_clause(text, d, cond)
        if n:
            return new_text, n, d + " (edgeHit clause)"
    # A room that leaves via a scripted VEHICLE (KQ4's rm43 dolphin `MoveTo`s the ego off-screen and
    # the engine reads the direction property at the boundary) has no `newRoom` and no edgeHit
    # reaction. Zeroing the property then HANGS -- the vehicle loops at the closed edge (reported in
    # play-test, the same shape as LSL2 rm47 but a different cause). Gate the board-the-vehicle commit
    # instead, so the ride never starts.
    bt, bn = guard_board_commit(text, cond)
    if bn:
        return bt, bn, "board-commit"
    init = re.search(r"\(method\s+\(init\)", text[m.start():])
    if not init:
        return text, 0, None
    # `(super init:)` in SCI0; SCI1.1 rooms write `(super init: &rest)` -- same anchor.
    sup = re.search(r"\n(\s*)\(super init:[^()]*\)", text[m.start() + init.start():])
    if not sup:
        return text, 0, None
    at = m.start() + init.start() + sup.end()
    indent = sup.group(1)
    closes = "".join("\n%s\t(global%d %s: 0)" % (indent, _ROOM, d) for d in directions)
    ins = ("\n%s; [softlock-guard] close this exit until the player can survive past it\n"
           "%s(if (not %s)%s\n%s)"
           % (indent, indent, stock_or(cond), closes, indent))
    return text[:at] + ins + text[at:], 1, "+".join(directions)


def guard_register_write(text, register, trap, cond):
    """Hold a free-running TRAP register's flip until the player is safe.

    The pervasive write lives in the game class's ALWAYS-LIVE dispatch (KQ4::newRoom writes
    global100:=1 -- nightfall, on every qualifying room change); wrap that one so it only fires when
    the guard holds -- the sunset waits for the day-list items. The copy in handleEvent (a scripted
    or debug event, not free-running) is deliberately left alone: only the newRoom/doit write is the
    adversary the player cannot refuse."""
    for meth in ("newRoom", "doit"):
        for mm in re.finditer(r"\(method\s+\(%s\b" % meth, text):
            bs, be = _block_span(text, mm.start())
            region = text[bs:be]
            wm = re.search(r"\(=\s+global%d\s+%d\s*\)" % (register, trap), region)
            if not wm:
                continue
            # Wrap the enclosing `(if ...)` whose CONDITION names the trap register -- that IS the
            # clock clause that sets the flag AND stashes the destination AND diverts to the darkness
            # room; holding only the flag write would divert you into night with the doors still open.
            # Gate the entire clause atomically. (Was: the INNERMOST enclosing if, which under a nested
            # nightfall would be a sub-branch and leak the divert/stash -- finding B#2.) If nothing
            # names the register, fall back to the OUTERMOST enclosing if.
            encls = []
            for im in re.finditer(r"\(if\b", region):
                es, ee = _block_span(region, im.start())
                if es <= wm.start() < ee:
                    encls.append((es, ee))
            if not encls:
                continue

            def _cond_names_reg(es):
                cs = es + re.match(r"\(if\s+", region[es:]).end()
                cond = (region[cs:_block_span(region, cs)[1]] if region[cs] == "("
                        else re.match(r"\S+", region[cs:]).group(0))
                return bool(re.search(r"\bglobal%d\b" % register, cond))

            named = [e for e in encls if _cond_names_reg(e[0])]
            es, ee = named[0] if named else min(encls, key=lambda e: e[0])
            wrapped = ("(if %s\n\t\t\t%s\n\t\t)  ; softlock-guard: hold the flip until survivable"
                       % (stock_or(cond), region[es:ee]))
            return text[:bs] + region[:es] + wrapped + region[ee:] + text[be:], 1
    return text, 0


_INV_CACHE = {}


def _inv_form(dest):
    """The inventory-list global, IN THIS GAME'S OWN SPELLING, or None.

    A window guard's bank test reads an item's owner -- `(== ((gInv at: 8) owner:) 6)` -- and
    the spelling of `gInv` is the game's, not ours. Scanned once from the owner-test idiom the
    game already speaks (`((globalN at: <item>) owner:)` -- KQ5's rm086 kidnap fork reads the
    bank exactly this way), same discipline as `_hands_forms`: derive the idiom from the
    assembled sources, refuse when the game never speaks it."""
    if dest in _INV_CACHE:
        return _INV_CACHE[dest]
    src = os.path.join(dest, "src")
    counts = defaultdict(int)
    for fn in os.listdir(src):
        if not fn.endswith(".sc"):
            continue
        t = open(os.path.join(src, fn), errors="replace").read()
        for m in re.finditer(r"\(\(global(\d+)\s+at:\s+\d+\)\s+owner:\)", t):
            counts[int(m.group(1))] += 1
    got = max(counts, key=counts.get) if counts else None
    _INV_CACHE[dest] = got
    return got


def guard_flag_proc_write(text, set_proc, flag, cond):
    """Hold a boolean-flag RAISE spelled as a set-proc call -- `(proc0_9 83)` -- until `cond`.

    The third flag-store spelling's write side (the first two: a global assignment,
    `guard_register_write`; a property-word setFlag:, `guard_prop_flag_write`). The window
    remedy's clause 1: the closer flag stops going up when the chase starts and goes up only
    once the demand it would seal is banked -- so losing the race closes nothing and the
    player can walk out and try again. Stock mode lets the stock raise through (`stock_or`);
    the hold is silent, so lite behaves as full.

    A multi-flag raise (`(proc0_9 82 83)`) is SPLIT, not wrapped whole: the sibling flags keep
    their unconditional raise and only the held flag moves under the guard -- wrapping the
    whole call would hold state this spec knows nothing about, the same discipline as
    `guard_prop_flag_write`'s exact-mask rule."""
    edits = []
    for m in re.finditer(r"\(%s((?:\s+\d+)+)\s*\)" % re.escape(set_proc), text):
        args = [int(x) for x in m.group(1).split()]
        if flag not in args:
            continue
        rest = [a for a in args if a != flag]
        guarded = ("(if %s (%s %d))  ; softlock-guard: hold the closer until banked"
                   % (stock_or(cond), set_proc, flag))
        if rest:
            indent = re.search(r"[ \t]*$", text[:m.start()]).group(0)
            guarded = "(%s %s)\n%s%s" % (set_proc, " ".join(str(a) for a in rest),
                                         indent, guarded)
        edits.append((m.start(), m.end(), guarded))
    for bs, be, rep in sorted(edits, reverse=True):
        text = text[:bs] + rep + text[be:]
    return text, len(edits)


def strengthen_flag_reads(text, test_proc, flag, cond):
    """Rewrite every READ of a flag -- `(proc0_12 83)` -- into `(or (proc0_12 83) <cond>)`.

    The window remedy's clause 2, and the half that carries the meaning correction: with the
    raise held (`guard_flag_proc_write`), "the flag is up" becomes "the flag is up OR the bank
    is filled", i.e. the closer stops meaning "the chase started" and starts meaning "the
    business is settled". At the arming that tests it negatively this is exactly
    `(and (not <test>) (not <cond>))` -- a banked scene never re-arms, which is the standing
    rule a patched chase must obey. The added disjunct is withdrawn in stock mode
    (`stock_and`); no comment is emitted because a read sits mid-expression."""
    pat = r"\(%s\s+%d\s*\)" % (re.escape(test_proc), flag)
    wrapped = lambda m: "(or %s %s)" % (m.group(0), T.stock_and(cond))   # noqa: E731
    new, n = re.subn(pat, wrapped, text)
    return new, n


def guard_prop_flag_write(text, sel, word, bit, recv_src, cond):
    """Hold a property-word flag SET (`(<recv> setFlag: <word> <mask>)`) until `cond` holds.

    The write commonly rides a CHAINED send -- KQ6's rm880 guards-return cutscene writes the
    "wedding has started" flag as `((ScriptID 80 0) clrFlag: 710 1 setFlag: 709 2)` -- so the
    flag message is SPLIT out of its chain and re-issued alone under the guard, in original
    order, and the siblings still run: the scene plays, the seal waits. The same "hold the flip"
    semantics as `guard_register_write` (KQ4's nightfall), in the second flag store's spelling.

    Only an exact single-bit mask on the RIGHT RECEIVER is edited: the flag's identity is
    (receiver, word, bit), and KQ6 has `(ScriptID 81 0)` writing the same `709 2` word/mask for a
    different region's flags two rooms over -- matching the numbers alone would both guard a
    stranger's flag and re-spell its receiver. A multi-bit mask carrying other flags too is left
    alone (guarding it would hold state this spec knows nothing about). All matching sites in
    `text` are edited -- every writer waits."""
    mask = 1 << bit
    want_recv = re.sub(r"\s+", " ", recv_src.strip("() ")).strip()
    guarded = "(if %s (%s %s: %d %d))  ; softlock-guard: hold the flip until obtainable" % (
        stock_or(cond), recv_src, sel, word, mask)
    edits = []                      # (send_start, send_end, replacement)
    for m in re.finditer(r"%s:\s+%d\s+%d\b" % (re.escape(sel), word, mask), text):
        # the innermost balanced form containing the message IS the send (its args are literals)
        send = None
        for om in re.finditer(r"\(", text[:m.start()]):
            bs, be = _block_span(text, om.start())
            if bs <= m.start() < be and (send is None or bs > send[0]):
                send = (bs, be)
        if send is None:
            continue
        bs, be = send
        body = text[bs:be]
        rm_ = re.match(r"\(\s*(\([^()]*\)|\S+)", body)
        recv_here = re.sub(r"\s+", " ", (rm_.group(1) if rm_ else "").strip("() ")).strip()
        if recv_here != want_recv:
            continue
        frag = re.search(r"\s*%s:\s+%d\s+%d\b" % (re.escape(sel), word, mask), body)
        remainder = body[:frag.start()] + body[frag.end():]
        indent = re.search(r"[ \t]*$", text[:bs]).group(0)
        # a send whose ONLY message was the flag write leaves no selector behind -- drop the husk
        keep = remainder if re.search(r"\w+:", remainder) else ""
        sepa = ("\n" + indent) if keep else ""
        edits.append((bs, be, keep + sepa + guarded))
    for bs, be, rep in sorted(edits, reverse=True):
        text = text[:bs] + rep + text[be:]
    return text, len(edits)


_SEL_NAMES = None


def _selector_name(value):
    """The source NAME of a selector number, from the analysed IR's own Selector nodes.

    The prop-flag store's identity is numeric -- ((script, export), selector, bit) -- but the
    owner class's DIRECT writes are spelled with the property's name (`(|= rFlag1 $0002)`), so a
    text-level edit needs the number resolved back. The lowering stashes the map it built
    (`ir._sel_names`) because the Selector nodes carrying name+number together are consumed by
    the rewrite -- a walk of the analysed IR comes back empty. The walk stays as the fallback
    for an IR that predates the stash."""
    global _SEL_NAMES
    if _SEL_NAMES is None:
        _SEL_NAMES = dict(getattr(_IR, "_sel_names", None) or {})
        if not _SEL_NAMES:
            for s in (_IR.scripts.values() if _IR is not None else ()):
                bodies = [m for o in s.objects for m in o.methods.values()] \
                    + list(s.procs.values())
                for body in bodies:
                    for n in I.walk(body):
                        if n.get("t") == "Selector" and isinstance(n.get("value"), int) \
                                and n.get("name"):
                            _SEL_NAMES.setdefault(n["value"], n["name"])
    return _SEL_NAMES.get(value)


def guard_prop_flag_owner_write(text, prop_name, mask, cond):
    """Hold a property-word flag's ARITHMETIC set -- `(|= rFlag1 $0002)` in the OWNER's own
    always-live method -- until `cond` holds.

    The third spelling of the same store (`vocab.lower_prop_flags`' second pass): the owning
    region class writes its own word directly, and because the region's `doit` runs in every
    room it attaches, the write is region-homed -- the adversary can fire anywhere in its scope,
    driven by a countdown the same method decrements (KQ6's wedding fuse, `weddingRemind`).

    Same doctrine as `guard_register_write` (KQ4's nightfall, the play-validated precedent):
    wrap the ENCLOSING `(if ...)` clause ATOMICALLY -- preferring one whose condition names the
    property, else the outermost -- rather than the bare write. Here that clause is the
    countdown-expiry test itself, so the hold FREEZES the decrement while the demand is unmet:
    nothing is consumed, the fuse stays armed, and the game's own clock resumes the moment the
    demand is satisfied. (Wrapping the write alone would let the expiry spend the countdown with
    the flag unwritten -- a one-shot fire that never retries -- and would leak the write's
    siblings, finding B#2's lesson.)"""
    pat = re.compile(r"\(\|=\s+%s\s+(?:\$0*%x|%d)\s*\)" % (re.escape(prop_name), mask, mask))
    for meth in ("newRoom", "doit"):
        for mm in re.finditer(r"\(method\s+\(%s\b" % meth, text):
            bs, be = _block_span(text, mm.start())
            region = text[bs:be]
            wm = pat.search(region)
            if not wm:
                continue
            encls = []
            for im in re.finditer(r"\(if\b", region):
                es, ee = _block_span(region, im.start())
                if es <= wm.start() < ee:
                    encls.append((es, ee))
            if not encls:
                continue

            def _cond_names_prop(es):
                cs = es + re.match(r"\(if\s+", region[es:]).end()
                cnd = (region[cs:_block_span(region, cs)[1]] if region[cs] == "("
                       else re.match(r"\S+", region[cs:]).group(0))
                return bool(re.search(r"\b%s\b" % re.escape(prop_name), cnd))

            named = [e for e in encls if _cond_names_prop(e[0])]
            es, ee = named[0] if named else min(encls, key=lambda e: e[0])
            wrapped = ("(if %s\n\t\t\t%s\n\t\t)  ; softlock-guard: hold the flip until obtainable"
                       % (stock_or(cond), region[es:ee]))
            return text[:bs] + region[:es] + wrapped + region[ee:] + text[be:], 1
    return text, 0


def _forward_demand_to_hold(dest, dsp, fwd, stage, out):
    """Conjoin a refused-everywhere demand into the placed interceptor hold of its sole
    producing flip, or report it covered when the host already demands everything.

    The demand half of the deferral principle the prohibition side has had all along: a
    demand with NO survivable site at its own crossing rides the last controllable commit
    on the only path there. The model's proof obligations (sole producer, one host edge,
    satisfiable at the host) were discharged by `guards.defer_to_entry`; here the host row
    must actually carry a `flip-interceptor-hold` site, the delta items must all spell as
    plain `has:` predicates of this spec's own rendered condition, and the re-wrap must
    land -- any miss returns None and the refusal stands unchanged."""
    hx, hy = fwd["host"]
    host = next((r for r in out if r.get("from_room") == hx and r.get("to_room") == hy
                 and r.get("applied")
                 and any(e.get("kind") == "flip-interceptor-hold"
                         for e in r.get("entry_sites") or ())), None)
    if host is None:
        return None
    hitems = set(host.get("items") or ())
    delta = sorted(set(dsp.get("items") or ()) - hitems)
    # a demand GROUP (any-of) is covered when the host already demands SOME member;
    # an uncovered group forwards as its own (or ...) clause
    dgroups = [sorted(g) for g in (dsp.get("groups") or ()) if not (set(g) & hitems)]
    base = {**dsp, "applied": True,
            "placement": {"kind": "demand-forwarded-to-hold", "stage": stage,
                          "host": "rm%d->rm%d" % (hx, hy), "forwarded": delta}}
    base["placement"]["forwarded_groups"] = dgroups
    if not delta and not dgroups:
        base["placement"]["kind"] = "covered-by-host-hold"
        base["sites"] = 0
        return base
    preds = {}
    for m in re.finditer(r"\(\S+\s+has:\s*(\d+)\)", to_source_syntax(dsp["condition"])):
        preds[int(m.group(1))] = m.group(0)
    if not all(i in preds for i in delta) \
            or not all(i in preds for g in dgroups for i in g):
        return None
    clauses = [preds[i] for i in delta] \
        + ["(or %s)" % " ".join(preds[i] for i in g) for g in dgroups]
    delta_cond = clauses[0] if len(clauses) == 1 else "(and %s)" % " ".join(clauses)
    title = next(e["title"] for e in host["entry_sites"]
                 if e.get("kind") == "flip-interceptor-hold")
    p = os.path.join(dest, "src", title + ".sc")
    try:
        text = open(p, errors="replace").read()
    except Exception:                                  # noqa: BLE001
        return None
    nt, n = guard_flip_interceptor(text, dsp["from_room"], fwd["host_stage"], delta_cond)
    if not n:
        return None
    open(p, "w").write(nt)
    base["sites"] = n
    base["placement"]["title"] = title
    return base


def guard_flip_interceptor(text, pocket, stage_src, cond):
    """Hold a player-committed register flip at its EXIT-INTERCEPTOR commit clause -- the
    night-guard shape for a flip whose write lives in a sole-exit pocket room.

    KQ4's nightfall holds a free-running writer's clock clause (`guard_register_write`); a
    player-committed flip has no free-running writer to hold, but a game may spell the commit
    as a clause in an always-retested method that ROUTES into the pocket -- LB2's
    rm520::newRoom: `((and (== global123 4) (global0 has: 31)) (= param1 26) ...)` diverts
    every exit into the act-break card. Conjoining the demand into that arm gives the KQ4
    semantics exactly: a held exit falls through to the arm below it (the stock plain exit,
    hands on), the demand is read at exit time (no state-born heads, no cross-file spelling),
    nothing inside the arm is consumed while held (the retracted-consumption rule satisfied
    by construction), and retry is free because the interceptor re-tests on every exit.

    The arm must PIN the spec's own stage test -- the flip this demand scopes to; an arm that
    does not pin the stage is somebody else's crossing -- and its body must route into the
    pocket (`(= param<N> <pocket>)` or `newRoom: <pocket>`). Only the retested methods
    `newRoom`/`doit` are searched: the same pair as `guard_register_write`, for the same
    reason (a `cue` fires once when cued -- refusing there would never retry; rm520's own
    `cue` performs the post-commit delivery and must not be touched).

    EVERY MATCHING ARM, NOT THE FIRST. A commitment reached through N doors and guarded at one
    of them is not guarded: the player takes another door and the surface, which freezes the
    site count, reports the same `sites=1` it would have reported for a single-door commit.
    That is finding #4 and finding #8 in this project's own history, and the count returned
    here is what makes the difference visible from outside. Two arms of one `cond`, two `cond`s,
    a `doit` twin of the `newRoom` commit -- all of them get the demand. Edits are applied
    right-to-left so earlier spans stay valid as later text grows.

    PINNING IS STRUCTURAL, NOT SUBSTRING. `want_stage in norm(head)` accepted any head the
    stage's TEXT appeared in, which is two different mistakes: `(or (== global123 4) (== global123
    9))` runs at act 9 as well, so conjoining the demand there refuses a crossing the spec never
    scoped (the wall-shaped failure, the one this project holds to be worse than the bug), and
    `(not (== global123 4))` means every act EXCEPT the one being scoped. So the head is parsed:
    the stage must appear as a TOP-LEVEL CONJUNCT -- the head is the stage test itself, or an
    `(and ...)` one of whose direct kids is. Anything else, including a stage buried under an
    `or` or a `not`, is refused, and the demand falls back to whatever placement would have
    happened without an interceptor."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip()          # noqa: E731
    want_stage = norm(stage_src)
    route = re.compile(r"\(=\s*param\d+\s+%d\s*\)|newRoom:\s*%d\b" % (pocket, pocket))

    def _pins_stage(head):
        """Is `want_stage` a conjunct of this head -- at any depth of nested `and`s?

        THROUGH the `and` nesting, because conjunction is associative and one of the heads this
        has to recognise is OUR OWN previous rewrite. When a second demand forwards onto a hold
        that is already wrapped, the arm reads `(and (and <stage> <game test>) <first demand>)`:
        the stage sits one level down, and it is pinned exactly as hard as it was before we
        touched it. Rejecting that spelling silently dropped LB2's forwarded act-5 demand from
        the patch -- caught by the surface diff, not by reasoning, which is the argument for
        diffing the surface at all. `or` and `not` are NOT walked through: those are the two
        shapes that make an arm run when the stage does not hold."""
        h = norm(head)
        if h == want_stage:
            return True
        if not h.startswith("(and "):
            return False                      # (or ...) / (not ...) / a call: not a pinning
        i = len("(and")                       # walk the direct kids of the `and`
        while i < len(h) - 1:
            while i < len(h) - 1 and h[i] == " ":
                i += 1
            if i >= len(h) - 1:
                break
            if h[i] != "(":                   # a bare atom kid (a variable): skip the token
                j = i
                while j < len(h) - 1 and h[j] not in " )":
                    j += 1
                i = j
                continue
            ks, ke = _block_span(h, i)
            if _pins_stage(h[ks:ke]):
                return True
            i = ke
        return False

    edits, n = [], 0
    for meth in ("newRoom", "doit"):
        for mm in re.finditer(r"\(method\s+\(%s\b" % meth, text):
            ms, me = _block_span(text, mm.start())
            region = text[ms:me]
            for cm in re.finditer(r"\(cond\b", region):
                cs, ce = _block_span(region, cm.start())
                i = cs + len("(cond")
                while i < ce:
                    while i < ce and region[i] in " \t\r\n":
                        i += 1
                    if i >= ce or region[i] != "(":
                        break
                    as_, ae = _block_span(region, i)
                    j = as_ + 1
                    while j < ae and region[j] in " \t\r\n":
                        j += 1
                    if j < ae and region[j] == "(":
                        hs, he = _block_span(region, j)
                        head = region[hs:he]
                        if _pins_stage(head) and route.search(region[he:ae]):
                            new_head = ("(and %s %s)  ; softlock-guard: hold the act flip "
                                        "until its carries are obtainable"
                                        % (head, stock_or(cond)))
                            edits.append((ms + hs, ms + he, new_head))
                            n += 1
                    i = ae
    for s, e, rep in sorted(edits, reverse=True):
        text = text[:s] + rep + text[e:]
    return text, n


_SOURCE_CACHE = {}


def _edit_candidates(dest, titles_by_num, sp, rooms):
    """Files that could hold the `newRoom: <to>` this spec guards, best first.

    The FROM room's own script always comes first -- that is where the edit belongs when it is
    there at all. After it come scripts that perform the same `newRoom` and are NOT another room's
    script: helper scripts a room arms (KQ6's `nightMare.sc`, script 344, delivers the Realm
    entry attributed to rm340). Another ROOM's script is excluded because a room sends you
    somewhere on its own account, and guarding its exit would guard a different crossing."""
    own = titles_by_num.get(sp["from_room"])
    out = [own] if own else []
    pat = re.compile(r"newRoom:\s*%d\b" % sp["to_room"])
    for num, title in sorted(titles_by_num.items()):
        if title in out or (rooms and num in rooms and num != sp["from_room"]):
            continue
        path = os.path.join(dest, "src", title + ".sc")
        if path not in _SOURCE_CACHE:
            try:
                _SOURCE_CACHE[path] = open(path, errors="replace").read()
            except Exception:                      # noqa: BLE001 -- missing source
                _SOURCE_CACHE[path] = ""
        if pat.search(_SOURCE_CACHE[path]):
            out.append(title)
    return out


def _balanced_span(text, i):
    """End index (exclusive) of the balanced parenthesis group starting at text[i] == '('."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(text)


def _guard_travel_dispatch(dest, sp, titles_by_num, seen_dispatch):
    """Place an edge guard on an INDIRECT travel dispatch, the spelling `_edit_candidates`
    cannot see: `(<room> newRoom: (<x> <prop>:))` fanned out by INSTANCES that each declare
    `<prop> <destination>`.

    KQ6's magic map is the instance that forced this. Every landing on a beach room is
    `pullOutMapScr.sc`'s `(global2 newRoom: (local8 tpRoom:))`; the mists carry `tpRoom 550`;
    and the CONTROLLABLE moment is the island click -- the dispatch class's `doVerb` arm
    `((== param1 5) ...)`, which highlights the island and rides an uncontrollable cutscene
    into the teleport. The beach rooms the spec names never perform the crossing, which is why
    the ordinary candidate search reports not-found for all four.

    The edit: wrap that commit arm's body in the guard, discriminated by the instance property
    (`(or (not (== <prop> <to>)) <cond>)`), refusing with the derived line otherwise. One edit
    covers every crossing the dispatch fans to that destination, so sibling rows report shared.
    Discrimination keeps every other island's click byte-for-byte on its stock path.

    Refuses (returns None) rather than guessing when: no file performs a property-read
    `newRoom:` whose property some instance pins to this destination; the file has no doVerb
    cond arm testing the verb parameter against a literal alone (the 'already here' arm also
    compares the current-room global and is deliberately not matched -- clicking the island
    you stand on never travels); or no refusal line derives for the game."""
    if REFUSE is None:
        return None
    src_dir = os.path.join(dest, "src")
    for fn in sorted(os.listdir(src_dir)):
        if not fn.endswith(".sc"):
            continue
        path = os.path.join(src_dir, fn)
        text = open(path, errors="replace").read()
        m = re.search(r"newRoom:\s*\(\s*\w+\s+(\w+):\s*\)", text)
        if not m:
            continue
        prop = m.group(1)
        if not re.search(r"\(properties[^()]*\b%s\s+%d\b" % (re.escape(prop), sp["to_room"]),
                         text):
            continue
        key = (fn, sp["to_room"], sp["condition"])
        if key in seen_dispatch:
            return {"applied": True, "sites": 0, "title": fn[:-3], "shared": True,
                    "placement": {"kind": "travel-dispatch", "instance": fn[:-3],
                                  "property": prop}}
        # the commit arm: a doVerb cond clause whose test is exactly `(== param1 <lit>)`
        dv = re.search(r"\(method\s+\(doVerb\s+(\w+)[^)]*\)", text)
        if not dv:
            continue
        pname = dv.group(1)
        mend = _balanced_span(text, text.rfind("(", 0, dv.start() + 1))
        edits = []
        for cm in re.finditer(r"\(cond\b", text[dv.start():mend]):
            ci = dv.start() + cm.start()
            cend = _balanced_span(text, ci)
            j = ci + len("(cond")
            while j < cend:
                while j < cend and text[j] != "(":
                    j += 1
                if j >= cend - 1:
                    break
                aend = _balanced_span(text, j)
                arm = text[j:aend]
                tm = re.match(r"\(\s*\(\s*==\s+%s\s+\d+\s*\)" % re.escape(pname), arm)
                if tm and prop not in arm[:tm.end()]:
                    tend = _balanced_span(arm, arm.index("(", 1))
                    body = arm[tend:-1]
                    edits.append((j + tend, j + len(arm) - 1, body))
                j = aend
        if not edits:
            continue
        guard = "(or (not (== %s %d)) %s)" % (prop, sp["to_room"],
                                              to_source_syntax(sp["condition"]))
        site = _ModeSite()             # one dispatch guard, one warned bit across its arms
        for (bs, be, body) in reversed(edits):
            # the marker comment must be followed by a newline BEFORE the arm's own closing
            # paren resumes at text[be:], or the `;` swallows that paren and the file no
            # longer balances (guarded_wrap keeps that property)
            text = (text[:bs]
                    + "\n\t\t\t\t"
                    + guarded_wrap(guard, body, REFUSE, site=site, indent="\t\t\t\t",
                                   marker="; softlock-guard: the landing")
                    + "\n\t\t\t"
                    + text[be:])
        open(path, "w").write(_ensure_refusal_use(text, titles_by_num))
        seen_dispatch.add(key)
        return {"applied": True, "sites": len(edits), "title": fn[:-3],
                "placement": {"kind": "travel-dispatch", "instance": fn[:-3],
                              "property": prop, "guard": guard}}
    return None


def apply_guards(dest, specs, titles_by_num, nums, s_drops=lambda it: set(), rooms=None,
                 entry_frontier=None, defer_info=None):
    """Place each EDGE guard at its CONTROLLABLE TRIGGER.

    A frontier `newRoom: N` usually sits at the last state of a changeState cutscene -- an
    UNCONTROLLABLE transition that has already consumed resources and started animating. Guarding
    it there hangs the game. `trigger.find_trigger` walks back to the player-facing handler that
    STARTS the cutscene and we guard that instead, so the refusal happens before anything runs.
    `wrap_trigger_in_source` wraps the whole enclosing cond-clause, not just the changeState, so
    side-effecting siblings (score, sounds, flag sets) cannot fire ahead of the refusal.

    `entry_frontier(room)` -- MODEL knowledge for the arrival-commit re-site: the rooms that
    cross INTO `room` from outside its pocket (`guards.commit_entry_frontier`). Without it an
    arrival commit stays honestly unplaced, exactly as before this parameter existed.

    `defer_info(sp)` -- MODEL knowledge for the SOLE-EXIT deferral (`guards.defer_to_entry`):
    the register stage that discriminates the spec's crossing and the predecessor rooms where
    it is presentable and satisfiable. A demand whose trigger resolves to sole-exit (LB2's act-break card: the one
    `newRoom:` lives inside the cutscene the wrap would refuse to arm, so refusing in place
    strands the player on the card) is re-sited to the pocket's entry frontier as
    `(or (not <stage>) <demand>)` -- the demand deferral that prohibitions have had since the
    Spinach_Dip raft, extended to demands. Without it a sole-exit row stays honestly unplaced."""
    _init_mode(dest)               # runtime stock/lite/full dispatch for everything placed below
    # OWNER-VALUED conditions arrive in the neutral `(gInv at: N)` spelling (window remedies,
    # fold carry-ins); translate them into this game's own inventory-list global once, up
    # front, so every wrap form downstream sees compilable source. A game that never speaks
    # the owner-test idiom cannot compile such a guard -- refuse those specs rather than emit
    # a guard that does not build.
    for sp in specs:
        c = sp.get("condition")
        if c and "(gInv at:" in c:
            inv = _inv_form(dest)
            if inv is None:
                sp.setdefault("refused", []).append(
                    "no inventory-store spelling derives for this game")
            else:
                sp["condition"] = c.replace("(gInv at:", "(global%d at:" % inv)
    out_unplaced = []
    pending_fwd = []               # (index of the refusal row, spec, fwd, stage) -- see below
    by_title = {}
    for sp in specs:
        if sp["site"] != "edge" or sp["refused"] or not sp.get("condition"):
            continue
        by_title.setdefault(titles_by_num.get(sp["from_room"]), []).append(sp)

    # A prohibition's droppability frontier may be UNCONTROLLABLE. rm131 -> rm138 is: the ship
    # sequence is `setScript:` at room init and runs itself to `newRoom: 138`, so there is no
    # player action to refuse and refusing an automatic cutscene would hang the game. Fall back to
    # the nearest EARLIER commit that is both controllable and still lets the player comply --
    # rm38 -> rm131, whose source room is itself a drop site for the dip.
    deferred = []
    for title, group in list(by_title.items()):
        keep = []
        for sp in group:
            if sp.get("forbid") and title:
                forms = read_file(os.path.join(dest, "src", title + ".sc"))
                k = find_trigger(forms, sp["to_room"], ego=_EGO)["kind"]
                # arm-event gates an uncontrollable event on HAVING a survival item; a PROHIBITION
                # enforced by refusing to arm an automatic cutscene would hang the game (the
                # Spinach_Dip -> rm138 raft). So a forbid spec that resolves to arm-event is deferred
                # to a droppability-frontier commit, exactly as when there is no trigger at all.
                if k not in _PLACED_KINDS or k == "arm-event":
                    deferred.append(sp)
                    continue
            keep.append(sp)
        by_title[title] = keep
    for sp in deferred:
        item = sp["forbid"][0]
        host = None
        for cand in specs:
            if (cand["site"] == "edge" and not cand.get("forbid") and not cand["refused"]
                    and cand["from_room"] in s_drops(item)):
                host = cand
                break
        if host is None:
            out_unplaced.append({**sp, "applied": False,
                                 "why": "no controllable commit where the item is still droppable"})
            continue
        host["condition"] = "(and %s %s)" % (host["condition"], sp["condition"])
        host.setdefault("merged", []).append(sp["condition"])

    out = out_unplaced
    seen_entry = set()             # (title, from_room, guard) -- entry-commit dedup across rows
    seen_dispatch = set()          # (file, to_room, condition) -- one travel-dispatch edit
    #   covers every crossing the dispatch fans to that destination; siblings report shared
    # FATAL USES -- refuse the ACTION. The site is the arming of the machine that kills you, in the
    # room that offers the move: KQ6's rm420 `(gCurRoom setScript: throwSkull)`. `find_arming`
    # already locates an arming by name, so this reuses the Realm-entry path rather than adding a
    # third way to find a setScript.
    for sp in specs:
        if sp["site"] != "action" or sp["refused"]:
            continue
        title = titles_by_num.get(sp["room"])
        path = os.path.join(dest, "src", title + ".sc") if title else None
        if not path or not os.path.exists(path):
            out.append({**sp, "applied": False, "why": "no source for rm%s" % sp["room"]})
            continue
        arm = find_arming(read_file(path), {sp["machine"]})
        if not arm:
            out.append({**sp, "applied": False,
                        "why": "no arming of %s found in %s" % (sp["machine"], title)})
            continue
        if _RETRACTION_FORM is None or REFUSE is None:
            out.append({**sp, "applied": False,
                        "why": "no literal-display form derives for this game"})
            continue
        # Always a REFUSAL, never a silent arm-event gate: the player chose this move, so they are
        # owed a reason. `find_arming` reports `arm-event` when the arming sits outside a handler,
        # and that shape has no `else` -- force the refusing form here.
        arm = {**arm, "kind": "setscript", "target_room": None}
        text = open(path, errors="replace").read()
        # A FATAL USE gets its own wording. "Not yet!" is the edge-guard line and it means "come
        # back with the missing thing" -- but there is no later moment at which throwing the skull
        # into the gears is a good idea, so that line would be a lie. Say what is true instead.
        refuse = _RETRACTION_FORM % "Better not. You are going to need that."
        new_text, n = wrap_trigger_in_source(text, arm, to_source_syntax(sp["condition"]), refuse)
        if not n:
            out.append({**sp, "applied": False, "why": "arming found but no site rewritten",
                        "placement": arm})
            continue
        open(path, "w").write(_ensure_refusal_use(new_text, titles_by_num))
        out.append({**sp, "applied": True, "title": title, "sites": n, "placement": arm})
    # MARKET SQUEEZES -- refuse the fatal PAYMENT. The site is the condemned token's own
    # dispatch case (KQ5's shops switch on the offered item, so every payment has one), located
    # by its case-head literal and its committed act -- the purchase cutscene's `setScript:` or
    # the handler's own `put:` -- and the whole case is held, siblings included. The refusing
    # line says why, because the player is being told no about a move the game invites; the
    # gypsy and the princess are never in this list by construction (the detector's rows are
    # spends at slots that merely tolerate the token while a tight consumer starves).
    for sp in specs:
        if sp["site"] != "market" or sp["refused"]:
            continue
        title = titles_by_num.get(sp["script"])
        path = os.path.join(dest, "src", title + ".sc") if title else None
        if not path or not os.path.exists(path):
            out.append({**sp, "applied": False, "why": "no source for script %s" % sp["script"]})
            continue
        if _RETRACTION_FORM is None or REFUSE is None:
            out.append({**sp, "applied": False,
                        "why": "no literal-display form derives for this game"})
            continue
        text = open(path, errors="replace").read()
        refuse = _RETRACTION_FORM % "Better not. You are going to need that."
        new_text, n = wrap_forbidden_case(text, sp["anchor"], sp["item"],
                                          to_source_syntax(sp["condition"]), refuse)
        if not n:
            out.append({**sp, "applied": False,
                        "why": "no switch case headed %d anchors `%s` in %s"
                               % (sp["item"], sp["anchor"], title)})
            continue
        open(path, "w").write(_ensure_refusal_use(new_text, titles_by_num))
        out.append({**sp, "applied": True, "title": title, "sites": n,
                    "placement": {"kind": "market-case", "instance": sp.get("machine"),
                                  "case": sp["item"]}})
    # register-flip guards edit the game class's always-live method (script 0 = Main), not a room.
    for sp in specs:
        if sp["site"] != "register-write" or sp["refused"]:
            continue
        title = titles_by_num.get(0, "Main")
        path = os.path.join(dest, "src", title + ".sc")
        text = open(path, errors="replace").read()
        new_text, n = guard_register_write(text, sp["register"], sp["trap"],
                                           to_source_syntax(sp["condition"]))
        if n:
            open(path, "w").write(new_text)
            out.append({**sp, "applied": True, "title": title, "sites": n,
                        "placement": {"kind": "register-write", "instance": title}})
            continue
        # ...or the flip is a PROPERTY-WORD flag set in a room's cutscene, the second flag
        # store's spelling (KQ6's letter: flag 166 -- "the wedding has started" -- is
        # `((ScriptID 80 0) ... setFlag: 709 2)` in rm880's guards-return scene). Every SET
        # site is held: each writer waits for the condition, the scene around it still runs.
        pf = (getattr(_IR, "_prop_flag_index", None) or {}).get(sp["register"]) \
            if _IR is not None else None
        ssel = (getattr(_IR, "_prop_flag_sels", None) or {}).get("set") \
            if _IR is not None else None
        placed = 0
        if pf and ssel and sp["trap"] == 1:
            (sfn, ex), word, bit = pf
            recv_src = "(ScriptID %d %d)" % (sfn, ex)
            for t2 in sorted(set(titles_by_num.values())):
                p2 = os.path.join(dest, "src", t2 + ".sc")
                if not os.path.exists(p2):
                    continue
                tx = open(p2, errors="replace").read()
                nt, n2 = guard_prop_flag_write(tx, ssel, word, bit, recv_src,
                                               to_source_syntax(sp["condition"]))
                if n2:
                    open(p2, "w").write(nt)
                    out.append({**sp, "applied": True, "title": t2, "sites": n2,
                                "placement": {"kind": "flag-write", "instance": t2}})
                    placed += n2
        # ...and the THIRD spelling: the OWNER writes its own word arithmetically inside an
        # always-live method -- KQ6's `(|= rFlag1 $0002)` in rgCastle::doit, the region-homed
        # writer every attached room inherits (it is where `register_strandings`' flip_rooms
        # come from). Until 2026-08-05 this site was deliberately skipped as "allowing the
        # defeat"; MEASURED WRONG: on the long route the fuse is only ever armed by the
        # 800->720 return, which requires the ghost-boy bit, which keeps the hallway to the
        # letter open while the hold refuses -- the letterless player is never stalled, and
        # the win (rm180) stays obtainable, which is the thing guards exist to protect.
        if pf and ssel and sp["trap"] == 1:
            (sfn, _ex), word, bit = pf
            owner = titles_by_num.get(sfn)
            pname = _selector_name(word)
            if owner and pname:
                p2 = os.path.join(dest, "src", owner + ".sc")
                if os.path.exists(p2):
                    tx = open(p2, errors="replace").read()
                    nt, n2 = guard_prop_flag_owner_write(tx, pname, 1 << bit,
                                                         to_source_syntax(sp["condition"]))
                    if n2:
                        open(p2, "w").write(nt)
                        out.append({**sp, "applied": True, "title": owner, "sites": n2,
                                    "placement": {"kind": "flag-write-owner",
                                                  "instance": owner}})
                        placed += n2
        if not placed:
            out.append({**sp, "applied": False, "why": "no free-running trap write found",
                        "from_room": None, "to_room": None})
    # ONE-SHOT WINDOWS (`guards.window_remedies`) -- hold the durable closer's raise until the
    # demand it seals is banked, and strengthen its reads so a banked scene never re-arms. The
    # two halves are applied ATOMICALLY: the hold alone leaves the closer permanently down, so
    # the chase would replay after success (the exact shape the standing rule forbids); the
    # read strengthen alone cures nothing (losing the race still raises the closer). Either
    # both land or neither, and a partial landing is reported, not shipped.
    for sp in specs:
        if sp["site"] != "window" or sp["refused"]:
            continue
        inv = _inv_form(dest)
        if inv is None:
            out.append({**sp, "applied": False,
                        "why": "no owner-test spelling derives for this game"})
            continue
        cond = to_source_syntax(sp["condition"]).replace("(gInv at:", "(global%d at:" % inv)
        edits = {}                     # path -> rewritten text, flushed only when both halves land
        held = reads = 0
        for t2 in sorted(set(titles_by_num.values())):
            p2 = os.path.join(dest, "src", t2 + ".sc")
            if not os.path.exists(p2):
                continue
            tx = edits.get(p2)
            if tx is None:
                tx = open(p2, errors="replace").read()
            changed = False
            for h in sp["holds"]:
                tx2, n2 = guard_flag_proc_write(tx, h["set_proc"], h["flag"], cond)
                if n2:
                    tx, held, changed = tx2, held + n2, True
                tx2, n3 = strengthen_flag_reads(tx, h["test_proc"], h["flag"], cond)
                if n3:
                    tx, reads, changed = tx2, reads + n3, True
            if changed:
                edits[p2] = tx
        if held and reads:
            for p2, tx in sorted(edits.items()):
                open(p2, "w").write(tx)
            titles = sorted(os.path.basename(p)[:-3] for p in edits)
            out.append({**sp, "applied": True, "sites": held + reads,
                        "title": ", ".join(titles),
                        "placement": {"kind": "window", "instance": ", ".join(titles),
                                      "holds": held, "reads_strengthened": reads}})
        else:
            out.append({**sp, "applied": False, "title": "window@rm%d" % sp["need_room"],
                        "why": "window halves incomplete (holds=%d, reads=%d) -- one half "
                               "alone replays the chase after success or cures nothing"
                               % (held, reads)})
    for title, group in sorted((k, v) for k, v in by_title.items() if k):
        for sp in group:
            # ONE WARNED BIT PER SPEC ROW. A row is wrapped at more sites than one -- extra
            # armings of the same script, cue-chain arms, every room on an entry frontier --
            # and they are all the SAME guard saying the same no. Minting the bit inside each
            # wrapper call (as the first cut did) charges the player a fresh warning at each
            # one, so lite refuses a single demand two, four, six times.
            row_site = _ModeSite()
            # The edit does not always live in the FROM room's own file. KQ6's Realm entry
            # `rm340 -> rm155` is delivered by `nightMare.sc` (script 344), a helper the room
            # arms, and looking only at rm340.sc reports `not-found` for that reason alone. Try
            # the room's own file first, then any OTHER script that performs this `newRoom` and
            # is not itself some other room's script -- a room that sends you somewhere is a
            # source of its own edge, never of this one.
            title_used, path, forms, placement = None, None, None, None
            for cand in _edit_candidates(dest, titles_by_num, sp, rooms):
                cpath = os.path.join(dest, "src", cand + ".sc")
                try:
                    cforms = read_file(cpath)
                except Exception as e:
                    out.append({**sp, "applied": False, "why": "parse failed: %s" % e})
                    break
                p = find_trigger(cforms, sp["to_room"], ego=_EGO)
                # Best first: a placeable trigger, else a file that at least CONTAINS the newRoom
                # (its instance is what the cross-file arming search below needs), else nothing.
                def rank(q):
                    return (2 if q["kind"] in _PLACED_KINDS else (1 if q.get("instance") else 0))
                if placement is None or rank(p) > rank(placement):
                    title_used, path, forms, placement = cand, cpath, cforms, p
                if p["kind"] in _PLACED_KINDS:
                    break
            if placement is None:
                continue                            # parse failure, already reported
            title = title_used
            # A COMPUTED destination serves several rooms from one statement, so the guard has to
            # say WHICH crossing it is about or it refuses them all. `(or (not (== <var> N)) …)`:
            # every other destination passes untouched, and only the frontier is demanded. Applied
            # once, here, where the placement is settled -- every kind below reads `sp["condition"]`
            # and threading it through each of them would be the same rule in nine places.
            # ...but keep the PRE-dest_test condition for the sole-exit deferral below: the
            # dest_test names the pocket's OWN dispatch variable (LB2: script 26's `local0`),
            # which does not exist at the entry rooms the demand is re-sited to -- there the
            # model-derived stage does the same discriminating through a register that is in
            # scope everywhere.
            raw_cond = sp["condition"]
            if placement.get("dest_test"):
                sp = {**sp, "condition": "(or (not %s) %s)"
                                         % (placement["dest_test"], sp["condition"])}
            if placement["kind"] not in _PLACED_KINDS and placement.get("instance"):
                # The cutscene that performs the `newRoom` is in one file and the ARMING that
                # starts it is in another: KQ6's rm340 arms script 344's cutscenes, and script
                # 344's `catchNiteMare` does the `newRoom: 155`. WHO arms the crossing is READ
                # off the helper's own arming graph (`reaching_owners`/`reaching_procs`: who
                # performs the newRoom, who arms them, and so on), never assumed from the export
                # table. The old form of this block took ANY export of the helper as the way in,
                # and wrapped rm340's arming of `(ScriptID 344 3)` -- `blowinIt`, flute flavor
                # that hands off to script 85 and never crosses -- while the cast's chain (skull
                # verb 28 -> openBook 190 -> `handsOn:` -> `(global2 notify:)` -> `proc344_1` ->
                # `catchNiteMare`) rode to the Realm unguarded. Play-found 2026-08-05: "she
                # comes over and takes you as soon as you cast the spell."
                snum, exps = exports_of(forms)
                owners = reaching_owners(forms, sp["to_room"])
                armers = sorted(reaching_procs(forms, sp["to_room"]))
                insts = {o for o in owners if not re.fullmatch(r"proc\d+_\d+", o)}
                # A helper-internal arming whose call sites all sit OUTSIDE `init` is
                # refusal-safe in place, and in place is tightest: every caller funnels through
                # the one arming form, and its else-sibling stays the game's own. An `init`
                # call site is an ARRIVAL COMMIT -- refusing there is finding #5's hang -- so
                # those keep routing through the proc-call path into the entry-frontier
                # re-site. Call sites are collected from EVERY source file, not just the edit
                # candidates: a helper proc called from one room's init and another's doVerb
                # must still count as an arrival commit.
                call_methods = set()
                if armers:
                    mention = re.compile(r"\((?:%s)\b" % "|".join(map(re.escape, armers)))
                    for fn in sorted(os.listdir(os.path.join(dest, "src"))):
                        if not fn.endswith(".sc") or fn == os.path.basename(path):
                            continue
                        p3 = os.path.join(dest, "src", fn)
                        if p3 not in _SOURCE_CACHE:
                            try:
                                _SOURCE_CACHE[p3] = open(p3, errors="replace").read()
                            except Exception:      # noqa: BLE001 -- missing source
                                _SOURCE_CACHE[p3] = ""
                        if not mention.search(_SOURCE_CACHE[p3]):
                            continue
                        try:
                            cforms2 = read_file(p3)
                        except Exception:          # noqa: BLE001 -- unparseable candidate
                            continue
                        call_methods |= {c["trigger_method"]
                                         for c in find_proc_calls(cforms2, set(armers),
                                                                  methods=None)}
                if call_methods and "init" not in call_methods:
                    placement = {"kind": "proc-arm", "target_procs": armers,
                                 "target_script": placement["instance"],
                                 "arm_targets": sorted(insts),
                                 "target_room": sp["to_room"]}
                else:
                    targets = set(insts)
                    if snum is not None:
                        targets |= {("ScriptID", snum, idx)
                                    for idx, nm in exps.items() if nm in insts}
                        targets |= {("proc", nm) for nm in armers}
                    for cand in _edit_candidates(dest, titles_by_num, sp, rooms):
                        if cand == title:
                            continue
                        cpath = os.path.join(dest, "src", cand + ".sc")
                        try:
                            arm = find_arming(read_file(cpath), targets)
                        except Exception:           # noqa: BLE001 -- unparseable candidate
                            continue
                        if arm:
                            arm["target_room"] = sp["to_room"]
                            title, path, placement = cand, cpath, arm
                            break
            if placement["kind"] not in _PLACED_KINDS:
                # fall back to the room-property exit idiom before giving up
                text = open(path, errors="replace").read()
                new_text, n, direction = guard_edge_exit(
                    text, title, sp["to_room"], to_source_syntax(sp["condition"]))
                if n:
                    open(path, "w").write(new_text)
                    out.append({**sp, "applied": True, "title": title, "sites": n,
                                "placement": {"kind": "edge-exit", "instance": title,
                                              "trigger_method": "init", "trigger_state": direction}})
                    continue
                # ...then the indirect travel dispatch (the magic-map class), whose crossing no
                # from-room file performs at all
                got = _guard_travel_dispatch(dest, sp, titles_by_num, seen_dispatch)
                if got:
                    out.append({**sp, **got})
                    continue
                # THE SOLE-EXIT DEFERRAL. Refusing in place is a wall (the pocket's one
                # `newRoom:` is inside the cutscene being refused), so the demand moves to the
                # controllable crossings INTO the pocket, scoped by the model-derived stage --
                # without which the row stays honestly unplaced, exactly as before.
                if placement["kind"] == "sole-exit" and defer_info is not None:
                    dsp = {**sp, "condition": raw_cond}
                    info = defer_info(dsp)
                    if info:
                        # MODEL knowledge for the arrival-commit triage: the stage's register
                        # alternatives (vacuity), the positional registers (head stripping),
                        # the predecessor map (chain hops), and the per-site filters the
                        # deferral itself applies (a re-sited room owes the same presentability
                        # and compliance the original site owed).
                        dctx = {"alts": info.get("alts") or [],
                                "positional": set(info.get("positional") or ()),
                                "prev_g": info.get("prev_g"),
                                "preds": info.get("preds") or (lambda r: []),
                                "site_ok": info.get("site_ok") or (lambda X, r: None),
                                "depth": 0, "visited": set()}
                        placed, _stg, unwrapped = _guard_arrival_entries(
                            dest, dsp, titles_by_num, rooms, path, placement, seen_entry,
                            info["rooms"], site=row_site, stage_override=info["stage"],
                            defer_ctx=dctx)
                        if not placed and unwrapped and info.get("fwd"):
                            # DEMAND FORWARDING: every site refused, but the model proved a
                            # sole producing flip one stage earlier (guards.defer_to_entry
                            # "fwd"). If THAT crossing carries a placed interceptor hold, the
                            # part of this demand it does not already carry is conjoined into
                            # the same arm -- the player meets the whole later demand at the
                            # last controllable moment on its only path.
                            #
                            # DEFERRED TO A SECOND PASS, because the host is found by scanning
                            # the rows placed SO FAR: run inline, whether a demand forwards
                            # depends on whether its host's spec happened to come first, and
                            # nothing pins the order specs arrive in. The refusal row goes in
                            # now and the pass below replaces it if the forward lands, so the
                            # outcome is the same for every ordering.
                            pending_fwd.append((len(out), dsp, info["fwd"], info["stage"]))
                        if not placed and unwrapped:
                            # every deferral site refused -- the row stays unplaced, but the
                            # PER-SITE reasons are the measurement (a wrap that would have been
                            # vacuous or mid-commit is not coverage lost; it is a wall or a
                            # strand not shipped). Losing them to the generic SKIP line made
                            # the honest outcome unreadable.
                            out.append({**dsp, "applied": False,
                                        "why": "entry-deferral refused at every site",
                                        "placement": {"kind": "entry-deferral-REFUSED",
                                                      "commit": placement,
                                                      "stage": info["stage"]},
                                        "frontier_unwrapped": unwrapped})
                            continue
                        if placed:
                            kind = ("entry-deferral" if not unwrapped
                                    else "entry-deferral-PARTIAL")
                            # NO "title": the wraps span several files, and a single title would
                            # make sibling rows (same pocket, different stages) freeze as
                            # identical strings -- a set-diff collapses duplicates, so one of
                            # them dropping would be invisible. Keyed by the edge instead.
                            row = {**dsp, "applied": True,
                                   "sites": sum(p["sites"] for p in placed),
                                   "placement": {"kind": kind, "commit": placement,
                                                 "stage": info["stage"]},
                                   "entry_sites": placed}
                            if unwrapped:
                                row["frontier_unwrapped"] = unwrapped
                            out.append(row)
                            continue
                out.append({**sp, "applied": False,
                            "why": "no controllable trigger (%s) and no room-property exit"
                                   % placement["kind"],
                            "placement": placement})
                continue
            if placement["kind"] == "proc-call" and placement.get("trigger_method") == "init":
                # An arrival commit: refusing inside `init` HANGS (finding #5, play-found), so
                # the demand is RE-SITED to the controllable crossings INTO the room. The two
                # text-level attempts that failed in play are both answered structurally: the
                # stage test comes from the PRISTINE source (`_PRISTINE_DIR`), and the site list
                # comes from the MODEL (`entry_frontier` = `guards.commit_entry_frontier`), so an
                # interior return can never be wrapped. Without model knowledge the row stays
                # honestly unplaced, exactly as v11 shipped it.
                frontier = sorted(entry_frontier(sp["from_room"])) if entry_frontier else []
                placed, stage, unwrapped = (
                    _guard_arrival_entries(dest, sp, titles_by_num, rooms, path,
                                           placement, seen_entry, frontier, site=row_site)
                    if frontier else ([], None, []))
                if placed:
                    # A frontier crossing without a wrap is a BYPASS, not a detail: v12 shipped
                    # with rm320 gated and rm300's solved-puzzles shortcut open, and the play
                    # pass walked straight through it. Coverage is part of the placement KIND,
                    # so the golden surface goes loud when it slips.
                    kind = "entry-frontier" if not unwrapped else "entry-frontier-PARTIAL"
                    row = {**sp, "applied": True, "title": placed[0]["title"],
                           "sites": sum(p["sites"] for p in placed),
                           "placement": {"kind": kind, "commit": placement, "stage": stage},
                           "entry_sites": placed}
                    if unwrapped:
                        row["frontier_unwrapped"] = unwrapped
                    out.append(row)
                elif frontier and any((titles_by_num.get(r), sp["from_room"], sp["condition"])
                                      in seen_entry for r in frontier):
                    # the sibling row that shares this commit already wrapped the frontier; this
                    # row's demand is the same conjunction, enforced at the same site.
                    out.append({**sp, "applied": True, "sites": 0,
                                "placement": {"kind": "entry-frontier", "commit": placement},
                                "shared": True})
                else:
                    out.append({**sp, "applied": False, "placement": placement,
                                "why": "arrival commit (init proc-call): refusing in place hangs "
                                       "(finding #5) and no controllable entry-frontier site "
                                       "took the re-sited demand"})
                continue
            if REFUSE is None and placement["kind"] not in ("arm-event", "arm-clause"):
                # An `arm-event` gate has no `else` branch and so says nothing either way; every
                # other placement REFUSES the player's command, and refusing without a word is the
                # "the game lied to the player" failure only play-testing catches.
                out.append({**sp, "applied": False, "placement": placement,
                            "why": "no literal-display form derives for this game, so a refusal "
                                   "would be silent"})
                continue
            text = open(path, errors="replace").read()
            if placement["kind"] == "arm-clause":
                # the turn-back variant speaks and moves the ego; give the wrapper the game's
                # own object-global spellings, and the file the class scripts it will need.
                # The INPUT-LOCK pair rides along in the game's own tongue -- see the template
                # in trigger.py for why an unspoken selector must never be emitted.
                placement = {**placement,
                             "obj_globals": {"ego": "global%d" % _EGO,
                                             "room": "global%d" % _ROOM,
                                             "game": "global%d" % _GAME,
                                             "hands": _hands_forms(dest)}}
            new_text, n = wrap_trigger_in_source(
                text, placement, to_source_syntax(sp["condition"]), REFUSE, site=row_site)
            if n == 0:
                out.append({**sp, "applied": False, "why": "trigger found but no site rewritten",
                            "placement": placement})
                continue
            if placement["kind"] == "arm-clause" and "sgTurnBack" in new_text:
                new_text = _ensure_refusal_use(new_text, titles_by_num)
                new_text = _ensure_use(new_text, "Motion")
                if "(User canControl:" in new_text:
                    new_text = _ensure_use(new_text, "User")   # the derived input-lock's class
            elif placement["kind"] not in ("arm-event", "arm-clause"):
                new_text = _ensure_refusal_use(new_text, titles_by_num)
            open(path, "w").write(new_text)
            row = {**sp, "applied": True, "title": title, "sites": n, "placement": placement}
            # A machine with N controllable armings needs N wraps -- play-found on KQ6's short
            # door: `wearClothingScr` arms from egoDoVerbCode::doVerb AND guardHut::doVerb, and
            # wrapping the first alone left the hut a bypass. Each extra site gets the same
            # guard, reported on the row so no second edit happens silently.
            if placement["kind"] == "setscript":
                for extra in find_all_armings(forms, placement["target_script"]):
                    if (extra["trigger_instance"], extra["trigger_method"]) == \
                            (placement["trigger_instance"], placement["trigger_method"]):
                        continue
                    t2 = open(path, errors="replace").read()
                    nt2, n2 = wrap_trigger_in_source(
                        t2, extra, to_source_syntax(sp["condition"]), REFUSE, site=row_site)
                    if n2:
                        open(path, "w").write(_ensure_refusal_use(nt2, titles_by_num))
                        row["sites"] = row.get("sites", 1) + n2
                        row.setdefault("also_wrapped", []).append(
                            {"instance": extra["trigger_instance"],
                             "method": extra["trigger_method"]})
            if placement["kind"] == "proc-arm":
                gated = _gate_notify_awards(dest, to_source_syntax(sp["condition"]))
                if gated:
                    row["award_gated"] = gated
            also = _also_place_capture(dest, sp, titles_by_num, rooms, placement)
            if also:
                row["also_placed"] = also
            out.append(row)
    # SECOND PASS -- every host row is placed by now, so a forward lands or refuses on the
    # model's proof rather than on the order the specs arrived in. Each entry replaces its own
    # refusal row in place (the index recorded when that row was appended), so a forward that
    # still cannot find its host leaves the honest refusal exactly as it was.
    for idx, dsp, fwd, stage in pending_fwd:
        frow = _forward_demand_to_hold(dest, dsp, fwd, stage, out)
        if frow is not None:
            out[idx] = frow
    return out


def _gate_notify_awards(dest, cond):
    """A notify-delivered commit's scene may pay its award BEFORE the notify; a `proc-arm`
    refusal downstream then splits what stock wrote as one atom. KQ6's spell cast
    (openBook.sc, script 190): `(global1 givePoints: 3)` and then `(global2 notify:)`, and a
    hot cast in stock ALWAYS rides to rm155 -- points and ride are atomic, the award can fire
    once. With the arming refused, every rejected cast farmed +3 (play-found 2026-08-05).

    So: in any clause that reaches the current-room `notify:`, an award paid before it gets
    the commit's own demand. NO else -- a suppressed award is not a player action owed a
    refusal line, it is simply not yet earned; the successful cast still pays it. Every edit
    is reported on the placement row -- a second edit made silently is how a patch stops
    being reviewable."""
    if _ROOM is None:
        return []
    notify_pat = re.compile(r"\(global%d\s+notify:\s*\)" % _ROOM)
    award_pat = re.compile(r"\([^()]*givePoints:[^()]*\)")
    out = []
    for fn in sorted(os.listdir(os.path.join(dest, "src"))):
        if not fn.endswith(".sc"):
            continue
        path = os.path.join(dest, "src", fn)
        try:
            text = open(path, errors="replace").read()
        except Exception:                          # noqa: BLE001 -- unreadable candidate
            continue
        if "givePoints" not in text or not notify_pat.search(text):
            continue
        n = 0
        for nm in list(notify_pat.finditer(text))[::-1]:    # back-to-front: offsets stay valid
            clause = _enclosing_clause_body(text, nm.start())
            if not clause:
                continue
            bs = clause[0]
            region = text[bs:nm.start()]
            for am in list(award_pat.finditer(region))[::-1]:
                a0, a1 = bs + am.start(), bs + am.end()
                wrapped = ("(if %s\n\t\t\t\t\t%s\n\t\t\t\t)"
                           "  ; softlock-guard: the award belongs to the ride"
                           % (stock_or(cond), text[a0:a1]))
                text = text[:a0] + wrapped + text[a1:]
                n += 1
        if n:
            open(path, "w").write(text)
            out.append({"title": fn[:-3], "sites": n})
    return out


def _pristine_room_text(dest, ttl):
    """The UNEDITED source for `ttl` -- context classification must read what the game wrote,
    not what a sibling row's wrap already rewrote (the same rule the stage extraction states)."""
    pris = globals().get("_PRISTINE_DIR")
    for base in ([os.path.join(pris, ttl + ".sc")] if pris else []) + \
            [os.path.join(dest, "src", ttl + ".sc")]:
        if os.path.exists(base):
            try:
                return open(base, errors="replace").read()
            except Exception:                      # noqa: BLE001
                return None
    return None


_REG_EQ_HEAD = re.compile(r"\(==\s+global(\d+)\s+(-?\d+)\s*\)$")


def _head_conjuncts(head):
    t = head.strip()
    if t.startswith("(and"):
        return [t[a:b] for (k, a, b) in T._immediate_children(t, 1, len(t) - 1) if k == "form"]
    return [t]


def _ctx_pins(ctx):
    """Registers this arming's own path PINS to a value: exact `(== globalN V)` heads (or
    top-level conjuncts of an `(and ...)`), plus switch cases whose discriminator is a bare
    global. Disjuncts pin nothing -- an `(or ...)` alternative is not a commitment."""
    pins = {}
    for h in ctx["heads"]:
        for c in _head_conjuncts(h):
            m = _REG_EQ_HEAD.match(c.strip())
            if m:
                pins[int(m.group(1))] = int(m.group(2))
    for (expr, v) in ctx["cases"]:
        m = re.fullmatch(r"global(\d+)", expr.strip())
        if m:
            pins[int(m.group(1))] = v
    return pins


def _stage_vacuous(pins, alts):
    """The arming's own path CONTRADICTS every stage alternative -- the game's own condition
    says this site never crosses at the spec's stage, so it carries no wrap at all. (LB2's
    rm620: `sFoundDagger` arms under `(== global123 3)`; a stage-1/4/5 demand there is a guard
    on a crossing that cannot happen.)"""
    return bool(alts) and all(any(R in pins and pins[R] != v for R, v in musts.items())
                              for musts in alts)


_PORTABLE_TOK = re.compile(r"global\d+|proc\d+_\d+|-?\d+|\$[0-9a-fA-F]+")
_HEAD_OPS = {"and", "or", "not", "==", "!=", "<", ">", "<=", ">=", "&", "|", "+", "-", "*",
             "/", "u<", "u>", "mod"}


def _portable_head(h):
    """May this head text cross into ANOTHER room's file? Only spellings that resolve game-wide:
    globals, public procedures, selectors, literals. `local0` compiles in the file that declares
    it and means garbage anywhere else -- a chain hop that would carry one refuses instead."""
    for tok in re.findall(r"[^\s()]+", re.sub(r"\{[^}]*\}", " ", h)):
        if tok.endswith(":") or tok in _HEAD_OPS or _PORTABLE_TOK.fullmatch(tok):
            continue
        return False
    return True


def _strip_positional_head(head, positional, alts=()):
    """`head` with its positional-register conjuncts removed -> (text-or-empty, ok). At the
    re-sited frontier a previous/current-room test names where the player is standing NOW --
    keeping it would make the carried guard vacuously true (the same rule the stage extraction
    applies to clause heads). A positional register in a shape that is not a strippable
    conjunct (inside an `or`) refuses the whole head.

    Conjuncts the STAGE already implies are dropped too (`(== global123 4)` under a stage that
    pins 123=4): they are redundant at the landing, and dropping them is what lets a
    state-conditioned arming whose only condition IS the stage ride upstream at all."""
    keep = []
    for c in _head_conjuncts(head):
        c = c.strip()
        m = _REG_EQ_HEAD.match(c)
        if m and int(m.group(1)) in positional:
            continue
        if m and alts and all(musts.get(int(m.group(1))) == int(m.group(2))
                              for musts in alts):
            continue
        if any(re.search(r"\bglobal%d\b" % g, c) for g in positional):
            return None, False
        keep.append(c)
    if not keep:
        return "", True
    return (keep[0] if len(keep) == 1 else "(and %s)" % " ".join(keep)), True


def _cutscene_delivers(dest, titles_by_num, from_room, to_room):
    """Does `from_room` perform its crossing into `to_room` from inside a changeState -- a
    cutscene ride, arriving with the game in control of the ego? (rm300 -> rm250 is `sHailCab`
    state 10; the ego is hidden by state 9.)

    THREE ANSWERS, not two: True, False, and None for "the performer could not be read". The
    difference matters because False is not a neutral place to land -- it classifies the arming
    as benign and keeps the IN-PLACE GATE, which is the shape the user's play test caught
    sitting inside a commit (LB2's rm250: the cab ride had already hidden the ego when the gate
    declined to arm). Answering that from a file we failed to parse is asserting the very thing
    we could not check. None makes the caller refuse the site and say why, which costs a
    placement and cannot hang a game."""
    ttl = titles_by_num.get(from_room)
    if not ttl:
        return None                                # no file to read: not an answer
    pris = globals().get("_PRISTINE_DIR")
    path = os.path.join(pris, ttl + ".sc") if pris else os.path.join(dest, "src", ttl + ".sc")
    if not os.path.exists(path):
        path = os.path.join(dest, "src", ttl + ".sc")
    try:
        forms = read_file(path)
        nr, _cs, _ss, _pc = T.analyze_room(forms)
    except Exception:                              # noqa: BLE001
        return None
    # the same destination spellings find_trigger resolves: a literal, a nav-property read
    # (`newRoom: (self north:)` -- rm740's sGoTRex exits north into rm480), or a variable
    nav = T.nav_props(forms)
    assigned = T._var_assigned_rooms(forms)

    def hits(dst):
        if dst == to_room:
            return True
        if isinstance(dst, tuple) and dst[0] == "nav":
            return nav.get(dst[1]) == to_room
        if isinstance(dst, tuple) and dst[0] == "var":
            return to_room in assigned.get(dst[1], ())
        return False
    return any(meth == "changeState" and hits(dst)
               for (_inst, meth, _state, dst, _pos) in nr)


def _defer_triage_site(dest, num, ttl, sp, trig, cond, stage_override, titles_by_num,
                       rooms, own_path, placement, seen, site, dctx):
    """The ARRIVAL-COMMIT TRIAGE for a sole-exit deferral site whose trigger is an arm-event.

    Play-found (LB2 2026-08-11, the user's own test of the shipped guard): the deferral placed
    its arm-gate on `rm250::init`'s arming of `sACTBREAK` -- but the arrival that satisfies that
    arming's own head (`prevRoom == 300`) is delivered by rm300's `sHailCab`, a hands-off cab
    ride that hides the ego before `newRoom:`. The gate refused AFTER the commit: hidden ego,
    nothing armed, the §7i strand. The act guard must sit OUTSIDE the act commit.

    Per arming of the trigger's target script, classified from the game's own context
    (`trigger.arming_contexts`):

      * STAGE-VACUOUS -- the path pins a register against every stage alternative: no wrap;
        recorded. A guard that cannot fire is not worth a mis-siting.
      * COMMITTED -- mid-changeState, or the game takes the controls (`handsOff:`/ego `hide:`)
        before the arming, or an `init` arrival delivered by a cutscene: not a refusal point.
        The demand is RE-SITED up the chain: in-file to the enclosing Script's own armings, and
        across files to the delivering rooms (`_guard_arrival_entries`, rebased on this room),
        with the arming path's own non-positional heads conjoined into the stage so the carried
        guard scopes to exactly the committed chain. Heads that cannot cross files (`local0`)
        refuse the hop -- honestly unplaced beats a wrap built on garbage.
      * BENIGN -- a hands-on arming (walk-in `init`, `cue`/`doit`/`notify` without a preceding
        handsOff): the in-place silent gate stays exactly as before.

    Returns (handled, placed, unwrapped). handled=False only when no arming context could be
    read at all (no pristine text, or the armings are spelled in a form `arming_contexts`
    cannot see) -- the caller's legacy flow then proceeds unchanged. Once contexts exist the
    triage owns the whole site, INCLUDING the benign armings: a target with a controllable
    arming and an uncontrollable sibling (rm300's `sHailCab`: `taxiSign::doVerb` and
    `frontDoor::cue`) needs both covered, and the legacy single-trigger wrap takes only the
    first -- wrapping one door of an N-door commitment is a bypass (the KQ6 finding #4 rule,
    applied here because the play-tested walkthrough path was the CUE one)."""
    text = _pristine_room_text(dest, ttl)
    if text is None:
        return False, [], []
    ego = "global%d" % _EGO
    ctxs = T.arming_contexts(text, trig["target_script"], ego=ego)
    if not ctxs:
        return False, [], []
    placed, unwrapped = [], []
    benign = []                                    # (ctx, heads_carried, land_controllable)
    # NOTE: once `ctxs` is non-empty the triage owns this site unconditionally -- the two early
    # returns above are the only `handled=False` exits. There used to be a `handled` flag and an
    # `if not handled: return False, [], []` down below; the flag was never reassigned, so the
    # branch could not run. Removed rather than left as a hedge that reads like a live path.
    prev_g = dctx.get("prev_g")
    frontier = [(c, [], trig["target_script"]) for c in ctxs]
    for _depth in range(6):
        nxt = []
        for (c, hs, tgt) in frontier:
            where = "%s::%s" % (c["instance"], c["method"])
            pins = _ctx_pins(c)
            if _stage_vacuous(pins, dctx["alts"]):
                unwrapped.append({"room": num, "why": "stage-vacuous arming at %s: the game's "
                                  "own path pins %s" % (where, pins)})
                continue
            if c["method"] in T.CONTROLLABLE_METHODS:
                benign.append((c, hs, tgt, True))
                continue
            committed = (c["method"] == "changeState" or c["handsoff_branch"])
            deliverers = []
            if not committed and c["method"] == "init":
                pinned = [pins[prev_g]] if prev_g in pins else []
                deliverers = pinned or dctx["preds"](num)
                says = [_cutscene_delivers(dest, titles_by_num, X, num) for X in deliverers]
                committed = any(d is True for d in says)
                if not committed and any(d is None for d in says):
                    # A deliverer we could not read is not a deliverer we cleared. Falling
                    # through to `benign` would place the in-place gate on an arrival that may
                    # well be a commit -- the play-caught shape -- so refuse and say so.
                    unwrapped.append({"room": num, "why": "arrival-commit arming at %s: a "
                                      "delivering room could not be read, so the arrival is "
                                      "unclassified" % where})
                    continue
            if not committed:
                benign.append((c, hs, tgt, False))
                continue
            if c["poisoned"]:
                unwrapped.append({"room": num, "why": "arrival-commit arming at %s behind an "
                                  "else arm: path underivable" % where})
                continue
            # heads carried out of a changeState are STATE-BORN: their value at the landing's
            # earlier moment is not the value the game tests at the arming (rm480's `local0`
            # is 0 through all of init and only means something by state 13). One survives the
            # stage-implied drop -> the hop refuses; a guard built on a wrong-time read is
            # worse than an honest SKIP.
            stripped, ok = list(hs), True
            for h in c["heads"]:
                sh, good = _strip_positional_head(h, dctx["positional"], dctx["alts"])
                if not good:
                    ok = False
                    break
                if sh:
                    stripped.append((sh, c["method"] == "changeState"))
            if not ok:
                unwrapped.append({"room": num, "why": "arrival-commit arming at %s: positional "
                                  "register in an unstrippable head" % where})
                continue
            if c["method"] == "changeState":
                up = T.arming_contexts(text, c["instance"], ego=ego)
                if not up:
                    unwrapped.append({"room": num, "why": "mid-cutscene arming at %s (state %s) "
                                      "with no in-file armer" % (where, c["state_case"])})
                    continue
                nxt += [(u, stripped, c["instance"]) for u in up]
                continue
            # a committed arrival: the refusal belongs in the delivering rooms
            if not deliverers:
                pinned = [pins[prev_g]] if prev_g in pins else []
                deliverers = pinned or dctx["preds"](num)
            state_born = [h for (h, born) in stripped if born]
            if state_born:
                unwrapped.append({"room": num, "why": "arrival-commit arming at %s: state-born "
                                  "head %r cannot ride upstream" % (where, state_born[0])})
                continue
            bad = [h for (h, _b) in stripped if not _portable_head(h)]
            if bad:
                unwrapped.append({"room": num, "why": "arrival-commit arming at %s: head %r "
                                  "cannot cross files" % (where, bad[0])})
                continue
            stage2 = (stage_override if not stripped
                      else "(and %s %s)" % (stage_override,
                                            " ".join(h for (h, _b) in stripped)))
            if dctx["depth"] >= 4:
                unwrapped.append({"room": num, "why": "arrival-commit chain from %s exceeds "
                                  "depth" % where})
                continue
            u_before, climbed = len(unwrapped), False
            for X in deliverers:
                if (X, num) in dctx["visited"]:
                    continue
                dctx["visited"].add((X, num))
                reason = dctx["site_ok"](X, num)
                if reason:
                    unwrapped.append({"room": num, "why": "chain hop to rm%s refused: %s"
                                      % (X, reason)})
                    continue
                sp2 = {**sp, "from_room": num}
                p2, _stg, u2 = _guard_arrival_entries(
                    dest, sp2, titles_by_num, rooms, own_path, placement, seen, [X],
                    site=site, stage_override=stage2,
                    defer_ctx={**dctx, "depth": dctx["depth"] + 1})
                placed += [{**pp, "via_room": num} for pp in p2]
                unwrapped += u2
                climbed = climbed or bool(p2)
            if not climbed and len(unwrapped) == u_before:
                unwrapped.append({"room": num, "why": "arrival-commit arming at %s: no chain "
                                  "hop landed" % where})
        if not nxt:
            break
        frontier = nxt
    # The benign armings still need their cover -- the legacy flow will not run for this site.
    t2_path = os.path.join(dest, "src", ttl + ".sc")
    for (c, hs, tgt, controllable) in benign:
        state_born = [h for (h, born) in hs if born]
        if state_born:
            unwrapped.append({"room": num, "why": "benign arming at %s::%s carries state-born "
                              "head %r: wrong-time guard refused"
                              % (c["instance"], c["method"], state_born[0])})
            continue
        htxt = [h for (h, _b) in hs]
        guard_c = ("(or (not %s) %s)" % (stage_override, cond) if not htxt
                   else "(or (not (and %s %s)) %s)" % (stage_override, " ".join(htxt), cond))
        key = (ttl, sp["from_room"], guard_c, c["instance"], c["method"], tgt)
        if key in seen or not os.path.exists(t2_path):
            continue
        t2 = open(t2_path, errors="replace").read()
        pl = {"kind": "setscript" if controllable else "arm-event",
              "trigger_instance": c["instance"], "trigger_method": c["method"],
              "target_script": tgt, "target_pattern": re.escape(tgt)}
        if controllable:
            if REFUSE is None:
                unwrapped.append({"room": num, "why": "no refusal form for the controllable "
                                  "arming at %s::%s" % (c["instance"], c["method"])})
                continue
            nt, n = T.wrap_all_armings_in_source(t2, pl, guard_c, REFUSE, site=site)
            if n:
                nt = _ensure_refusal_use(nt, titles_by_num)
        else:
            nt, n = T.wrap_trigger_in_source(t2, pl, guard_c, REFUSE, site=site)
        if n:
            open(t2_path, "w").write(nt)
            seen.add(key)
            placed.append({"title": ttl, "kind": ("chain-refusal" if controllable
                                                  else "arm-event"), "sites": n})
        else:
            unwrapped.append({"room": num, "why": "benign arming at %s::%s found but not "
                              "rewritten" % (c["instance"], c["method"])})
    return True, placed, unwrapped


def _guard_arrival_entries(dest, sp, titles_by_num, rooms, own_path, placement, seen,
                           entry_rooms, site=None, stage_override=None, defer_ctx=None):
    """An ARRIVAL COMMIT cannot be refused in place. Play-found (finding #5, the winged-guards
    capture): the proc-call wrap put a refusal inside `rm340::init`, and by then the seizure
    has begun -- the refusal left a half-armed scene and the game hung two rooms later. The
    refusal belongs at the last CONTROLLABLE crossing INTO the room (the cliff climb), with the
    commit's own arming stage keeping every other visit free:

        (or (not <stage>) <items>)

    <stage> is the TEST of the game's own arming clause, taken from the PRISTINE source (an
    already-edited file yields garbage guards -- the first failed text-level attempt) -- for
    the capture, `(and (not (proc913_0 1)) (proc913_0 2))` -- so pre-tribute visits to the isle
    cross unchallenged.

    `entry_rooms` is the MODEL's pocket frontier (`guards.commit_entry_frontier`): only rooms
    that cross INTO the commit room from OUTSIDE its pocket. That is what makes this safe where
    the second failed text-level attempt was not -- a title-scan wrapped the pocket's own
    interior returns (350/370/405 -> 340), walling players already inside, the compliance
    doctrine violated.

    Refusal-bearing wraps go on controllable kinds. An arm-event site (KQ6's cliff ascent:
    `nextCliffUp` armed from `rm320::cue` -- a CUED chain, whose controllable moment is that one
    arming hop upstream of the `newRoom`) cannot carry a refusal -- the mid-cutscene hazard
    again -- so it gets the no-else arm-gate: at commit stage without the items, the ascent
    simply does not arm. ⚠️ SILENT-WALL RISK, flagged for play: better than a hang or the
    restored softlock, and the stage condition keeps every non-commit visit untouched.

    `seen` dedups across the sibling rows that share one commit (the capture rows would
    otherwise stack identical nested wraps on one crossing)."""
    if stage_override is not None:
        # A SOLE-EXIT deferral arrives with its stage already derived from the MODEL (the
        # out-edge's own `_emeta` requirement, `guards.defer_to_entry`) -- there is no proc-call
        # arming to read clause heads off, and the pocket's own file has nothing to say about
        # which crossing the demand scopes to. The dedup key carries the stage: sibling rows off
        # one pocket share a CONDITION (LB2's three pressPass rows) while meaning different
        # crossings, and keying on the condition alone would place the first act's guard and
        # silently swallow the rest.
        stage = stage_override
    else:
        pris = globals().get("_PRISTINE_DIR")
        ppath = os.path.join(pris, os.path.basename(own_path)) if pris else own_path
        text = open(ppath if os.path.exists(ppath) else own_path, errors="replace").read()
        # THE STAGE: the game's own test of when this room's arrival commits the player, read off
        # the PRISTINE init. One placement names one proc-call, but a room can commit through
        # several calls into the same helper script (rm340: proc342_0 -> the Celeste flight,
        # proc342_1 -> seized returning from the spring, proc342_2 -> seized on arrival), so every
        # same-script call contributes its clause head. A head that tests the PREVIOUS-ROOM
        # register is dropped: it names an in-pocket arrival (`(== global12 440)` -- coming back
        # out of the lair), which cannot hold at the frontier this guard is being re-sited to --
        # keeping it would make the whole guard vacuously true there. What survives on rm340 is
        # exactly the capture-arm test, `(and (not (proc913_0 1)) (proc913_0 2))`.
        m_script = re.match(r"proc(\d+)_", placement.get("target_script") or "")
        prev_g = None
        if _IR is not None:
            import extract as _X
            prev_g = _X.prev_room_global(_IR)
        heads = []
        inst_span = _find_region(text,
                                 r"\(instance\s+%s\b" % re.escape(placement["trigger_instance"]))
        if inst_span and m_script:
            i0, i1 = inst_span
            meth_rel = _find_region(text[i0:i1],
                                    r"\(method\s+\(%s\b" % re.escape(placement["trigger_method"]))
            if meth_rel:
                region = text[i0 + meth_rel[0]:i0 + meth_rel[1]]
                for pm in re.finditer(r"\(proc%s_\d+\s*\)" % m_script.group(1), region):
                    head = enclosing_clause_head(region, pm.start())
                    if not head or not head.startswith("("):
                        continue               # an `else` arm or a switch case: no test to keep
                    if prev_g is not None and re.search(r"\bglobal%d\b" % prev_g, head):
                        continue               # an in-pocket arrival; meaningless at the frontier
                    if head not in heads:
                        heads.append(head)
        stage = heads[0] if len(heads) == 1 else ("(or %s)" % " ".join(heads) if heads else None)
    cond = to_source_syntax(sp["condition"])
    guard = "(or (not %s) %s)" % (stage, cond) if stage else cond
    placed, unwrapped, siteless = [], [], []
    for num in entry_rooms:
        ttl = titles_by_num.get(num)
        if ttl is None or (rooms and num not in rooms) or num == sp["from_room"]:
            continue
        key = ((ttl, sp["from_room"], guard) if stage_override is not None
               else (ttl, sp["from_room"], sp["condition"]))
        if key in seen:
            continue
        p2 = os.path.join(dest, "src", ttl + ".sc")
        if not os.path.exists(p2):
            unwrapped.append({"room": num, "why": "no source"})
            continue
        try:
            forms2 = read_file(p2)
        except Exception:                              # noqa: BLE001
            unwrapped.append({"room": num, "why": "unparseable"})
            continue
        if stage_override is not None:
            # THE NIGHT-GUARD SHAPE FIRST (user ruling 2026-08-11: guards condition the STATE
            # CHANGE, not rooms): if this entry room spells the commit as an exit-interceptor
            # clause pinning the spec's own stage, conjoin the demand INTO that clause -- one
            # site, re-tested every exit, held = the stock else arm. Every boundary without an
            # interceptor falls through to the triage below unchanged.
            it2 = open(p2, errors="replace").read()
            nt2, n2 = guard_flip_interceptor(it2, sp["from_room"], stage_override, cond)
            if n2:
                open(p2, "w").write(nt2)
                seen.add(key)
                placed.append({"title": ttl, "kind": "flip-interceptor-hold", "sites": n2})
                continue
        trig = find_trigger(forms2, sp["from_room"], ego=_EGO)
        if (stage_override is not None and defer_ctx is not None
                and trig["kind"] in ("arm-event", "sole-exit", "setscript")):
            # THE ARRIVAL-COMMIT TRIAGE (sole-exit deferral only). A deferral site is not a
            # refusal point just because it precedes the pocket: its own arming may sit inside
            # a commit (LB2's rm250, play-found 2026-08-11). Classified from the game's own
            # arming context; committed sites re-site up the chain, benign ones keep the
            # in-place wrap, and a site whose path contradicts the stage carries nothing.
            handled, p3, u3 = _defer_triage_site(
                dest, num, ttl, sp, trig, cond, stage_override, titles_by_num, rooms,
                own_path, placement, seen, site, defer_ctx)
            if handled:
                placed += p3
                unwrapped += u3
                continue
        if trig["kind"] == "arm-event" and REFUSE is not None:
            # A silent arm-gate prevents the softlock and wastes the player's climb (play
            # feedback 2026-08-04: solve the face, step every rock, and the ascent just...
            # does not arm). The controllable, refusal-capable moment is where the CHAIN that
            # cues the room is armed -- often in shared code the room merely `(use)`s -- so
            # search the entry room's own file and its use-targets for those armings and
            # refuse THERE, before any climbing. The arm-gate is still placed below as the
            # backstop for paths that reach the cue without the chain (the cheat path).
            room_text = open(p2, errors="replace").read()
            for used in re.findall(r"^\(use\s+(\w+)\s*\)", room_text, re.M):
                p3 = os.path.join(dest, "src", used + ".sc")
                if not os.path.exists(p3):
                    continue
                ckey = ((used, sp["from_room"], guard, "chain") if stage_override is not None
                        else (used, sp["from_room"], sp["condition"], "chain"))
                if ckey in seen:
                    continue
                t3 = open(p3, errors="replace").read()
                chain = find_cue_chain_armings(room_text, t3, _ROOM, trig["target_script"])
                total = 0
                for arm in chain:
                    t3, n3 = wrap_all_armings_in_source(t3, arm, guard, REFUSE, site=site)
                    total += n3
                if total:
                    open(p3, "w").write(_ensure_refusal_use(t3, titles_by_num))
                    seen.add(ckey)
                    placed.append({"title": used, "kind": "cue-chain", "sites": total})
        if trig["kind"] not in ("direct", "trigger", "setscript", "arm-event"):
            # No trigger in the room's own file -- defer to the second pass: a nav-property
            # shortcut re-route is a LAST resort, judged after every chain wrap has landed.
            siteless.append((num, ttl, key, p2, forms2))
            continue
        if trig["kind"] != "arm-event" and REFUSE is None:
            unwrapped.append({"room": num, "why": "no refusal form"})
            continue                       # a wordless refusal is the "game lied" class
        t2 = open(p2, errors="replace").read()
        nt, n = wrap_trigger_in_source(t2, trig, guard, REFUSE, site=site)
        if n:
            if trig["kind"] != "arm-event":            # an arm-gate prints nothing
                nt = _ensure_refusal_use(nt, titles_by_num)
            open(p2, "w").write(nt)
            seen.add(key)
            placed.append({"title": ttl, "kind": trig["kind"], "sites": n})
        else:
            unwrapped.append({"room": num, "why": "site found but not rewritten (%s)"
                              % trig["kind"]})
    # SECOND PASS -- the nav-assign re-route, only where the refusals left a real hole. The
    # shortcut spelling (`(self north: 340)` consumed by shared region code) was finding #8's
    # bypass, but re-routing it costs the player the game's own convenience: after the play
    # pass landed the CHAIN refusals, the shortcut's route crosses the same guarded steps, so
    # re-deciding it would only re-impose the long climb on players the guard already vetted
    # (play feedback 2026-08-04: "you have to climb the whole thing the second time too").
    # A chain wrap anywhere on this row therefore supersedes the re-route; the assignment is
    # gated only when no chain refusal landed and the shortcut would otherwise be unguarded.
    chain_landed = any(p["kind"] == "cue-chain" for p in placed)
    for (num, ttl, key, p2, forms2) in siteless:
        trig = None if chain_landed else find_nav_assign(forms2, sp["from_room"])
        if trig is None:
            if not chain_landed:
                unwrapped.append({"room": num, "why": "no wrappable site"})
            continue
        t2 = open(p2, errors="replace").read()
        nt, n = wrap_trigger_in_source(t2, trig, guard, REFUSE, site=site)
        if n:
            open(p2, "w").write(nt)                    # a route re-decision prints nothing
            seen.add(key)
            placed.append({"title": ttl, "kind": trig["kind"], "sites": n})
        else:
            unwrapped.append({"room": num, "why": "site found but not rewritten (nav-assign)"})
    return placed, stage, unwrapped


def _also_place_capture(dest, sp, titles_by_num, rooms, primary):
    """Guard the OTHER way through the same edge: the one the game takes FOR you.

    An edge can have two implementations and only one of them is a move the player makes. KQ6's
    catacombs are the case, reported from live play: `rm340::doit` walks you in when you step on
    the cave mouth (guarded), and `rm340::init` has the guards SEIZE you on arrival, via
    `(proc342_2)` -> `toGehenna` -> `tossEmIn` -> `newRoom: 405` (not guarded, so climbing the
    cliff without the four items still threw the player in).

    Derived: for each helper script that performs this edge's `newRoom`, look in the FROM room's
    own file for a call to one of that script's procedures and guard the clause around it. Returns
    the extra placements, which are reported on the row -- a second edit made silently is how a
    patch stops being reviewable.

    RETIRED 2026-08-04 (finding #5): every site this found is an init proc-call -- an ARRIVAL
    COMMIT -- and wrapping one with a refusal is precisely the mid-commit refusal that hung the
    game in play (the winged-guards capture: "Not yet!", a half-armed seizure, a hang two rooms
    later). The capture class is now covered by `_guard_arrival_entries`, which puts the
    stage-conditioned refusal on the controllable crossings INTO the room instead. Kept as a
    no-op for the history; the hazard class must not come back through it."""
    return []
    if REFUSE is None:
        return []
    own = titles_by_num.get(sp["from_room"])
    if not own:
        return []
    own_path = os.path.join(dest, "src", own + ".sc")
    cond = to_source_syntax(sp["condition"])
    extra = []
    for cand in _edit_candidates(dest, titles_by_num, sp, rooms):
        if cand == own:
            continue
        try:
            names = reaching_procs(read_file(os.path.join(dest, "src", cand + ".sc")),
                                   sp["to_room"])
        except Exception:                          # noqa: BLE001 -- unparseable candidate
            continue
        if not names:
            continue
        for arm in find_proc_calls(read_file(own_path), names):
            if primary.get("target_script") == arm.get("target_script"):
                continue                           # already guarded as the primary site
            text = open(own_path, errors="replace").read()
            new_text, n = wrap_trigger_in_source(text, arm, cond, REFUSE)
            if not n:
                continue
            open(own_path, "w").write(_ensure_refusal_use(new_text, titles_by_num))
            extra.append({"title": own, "placement": arm, "sites": n})
    return extra


def run(args, cwd):
    p = subprocess.run([SCICOMPILE] + args, cwd=cwd, capture_output=True, text=True, timeout=1800)
    return p.returncode, p.stdout + p.stderr


def hoist_rest_targets(text, lines):
    """Rewrite `((<call-or-send>) sel: ... &rest)` at the reported `lines` into
    `(= restTgt (<call-or-send>)) (restTgt sel: ... &rest)`, declaring the temp.

    The compiler refuses `&rest` when the send TARGET itself performs a call or send: params are
    emitted before the target's code, so the target's own call would consume the `rest` count at
    runtime -- a real PMachine hazard, guarded upstream rather than fixed. The decompiler emits
    the pattern freely (KQ6: rm880/rm430/boringBook, five statement-level sites), which is what
    kept those scripts in the 336/341. Hoisting the target into a temp is the transform the
    compiler's own error message asks for, applied ONLY at lines it reported -- benign `&rest`
    sends keep their evaluation order untouched."""
    out = text
    for line_no in sorted(set(lines), reverse=True):
        # the site: on this line, a form whose head is itself a parenthesized form and whose
        # params include &rest
        starts = [i for i, c in enumerate(out) if c == "\n"]
        ls = starts[line_no - 2] + 1 if line_no >= 2 else 0
        le = starts[line_no - 1] if line_no - 1 < len(starts) else len(out)
        seg = out[ls:le]
        om = re.search(r"\(\s*\(", seg)
        if not om:
            continue
        bs, be = _block_span(out, ls + om.start())
        body = out[bs:be]
        if "&rest" not in body:
            continue
        tm = re.match(r"\(\s*", body)
        tgs, tge = _block_span(body, tm.end())
        target = body[tgs:tge]
        # the enclosing method/procedure header, for the &tmp declaration
        hm = None
        for cand in re.finditer(r"\((?:method|procedure)\s*\(", out[:bs]):
            hs, he = _block_span(out, cand.start())
            if hs <= bs < he:
                hm = cand
        if hm is None:
            continue
        hs2, he2 = _block_span(out, hm.end() - 1)      # the (name params...) list
        header = out[hs2:he2]
        if "restTgt" not in header:
            new_header = (header[:-1] + " restTgt)") if "&tmp" in header \
                else (header[:-1] + " &tmp restTgt)")
            out = out[:hs2] + new_header + out[he2:]
            delta = len(new_header) - len(header)
            bs, be = bs + delta, be + delta
            body = out[bs:be]
            tgs, tge = _block_span(body, re.match(r"\(\s*", body).end())
        indent = re.search(r"[ \t]*$", out[:bs]).group(0)
        rewritten = ("(= restTgt %s)\n%s(restTgt%s"
                     % (target, indent, body[tge:-1] + ")"))
        out = out[:bs] + rewritten + out[be:]
    return out, (out != text)


def compile_project(dest):
    """--sco (interfaces from source + game) then --all (compile everything).

    A script the compiler rejects ONLY for the `&rest`-with-nested-target dialect gets the
    hoist rewrite at the reported lines and one retry -- see hoist_rest_targets. Anything else
    still fails as itself."""
    parent, name = os.path.dirname(dest) or ".", os.path.basename(dest)
    rc, out = run(_version_args() + ["--sco", name], parent)
    sco = re.search(r"Generate SCO: (\d+) written", out)
    rc2, out2 = run(_version_args() + ["--all", name], parent)
    allr = re.search(r"result: (\d+)/(\d+) scripts compiled", out2)
    failed = re.findall(r"^  (\S+)\s+line \d+: Error: (.*)$", out2, re.M)
    # `--all` reports only the FIRST error per script, so a script with several &rest sites
    # needs one round per site: fix what was reported, recompile, repeat until the report is
    # clean of the pattern (bounded -- each round must fix something or it stops).
    for _round in range(6):
        rest_lines = defaultdict(set)
        for m in re.finditer(r"^\s*(\S+)\s+line (\d+): Error: \(\S+\.sc\) &rest cannot be used",
                             out2, re.M):
            rest_lines[m.group(1)].add(int(m.group(2)))
        fixed_any = False
        for title, lines in sorted(rest_lines.items()):
            path = os.path.join(dest, "src", title + ".sc")
            try:
                text = open(path, errors="replace").read()
            except OSError:
                continue
            new_text, changed = hoist_rest_targets(text, lines)
            if changed:
                open(path, "w").write(new_text)
                fixed_any = True
        if not fixed_any:
            break
        rc2, out2 = run(_version_args() + ["--all", name], parent)
        allr = re.search(r"result: (\d+)/(\d+) scripts compiled", out2)
        failed = re.findall(r"^  (\S+)\s+line \d+: Error: (.*)$", out2, re.M)
    return {"sco_written": int(sco.group(1)) if sco else 0,
            "compiled": int(allr.group(1)) if allr else 0,
            "total": int(allr.group(2)) if allr else 0,
            "failures": failed}


def compile_one(dest, title, out_bin):
    """Compile a single script to its raw resource bytes (--all only writes .sco).

    On a SeparateHeapResources version the compiler also writes `<out_bin>.hep`; a missing heap
    there is a FAILURE, not a partial success, because the interpreter reads objects out of it."""
    parent, name = os.path.dirname(dest) or ".", os.path.basename(dest)
    rc, out = run(_version_args() + [name, os.path.join(name, "src", title + ".sc"), out_bin],
                  parent)
    ok = os.path.exists(out_bin) and (not _SCHEME["heap"] or os.path.exists(out_bin + ".hep"))
    return ok, out


def emit_patches(dest, titles, nums, out_dir):
    """Compile each edited script and wrap it as a ScummVM loose patch.

    The FILENAME and whether a heap accompanies it come from `_SCHEME`, derived from the game's own
    resource map: `script.NNN` for SCI0, `NNN.SCR` for SCI1, `NNN.SCR` + `NNN.HEP` for SCI1.1. The
    two-byte header is `[0x80|type][0x00]` either way -- confirmed against KQ6's own shipped
    patches, `82 00` for 420.SCR and `91 00` for 420.HEP.

    The output dir is CLEARED first: a build must never leave a previous run's patches (or another
    game's) sitting alongside this one's -- a stale script.NNN silently overrides the game just as a
    fresh one does. Both entry points (pipeline, patcher.main) call this once with the full set."""
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for title in sorted(titles):
        num = nums[title]
        raw = os.path.join(dest, "%s.bin" % title)
        ok, log = compile_one(dest, title, raw)
        if not ok:
            written.append({"title": title, "script": num, "ok": False,
                            "error": log.strip().splitlines()[-1] if log.strip() else "no output"})
            continue
        parts, total = [], 0
        for src_path, fmt, rtype in ((raw, _SCHEME["script"], RES_TYPE_SCRIPT),
                                     (raw + ".hep", _SCHEME["heap"], RES_TYPE_HEAP)):
            if not fmt:
                continue
            data = open(src_path, "rb").read()
            dst = os.path.join(out_dir, fmt % num)
            with open(dst, "wb") as f:
                f.write(bytes([0x80 | rtype, 0x00]))
                f.write(data)
            parts.append(dst)
            total += len(data) + 2
        written.append({"title": title, "script": num, "ok": True,
                        "path": parts[0], "paths": parts, "bytes": total})
    return written


def main():
    dest = os.path.join(_ROOT, "build", "patch_project")
    out_dir = os.path.join(_ROOT, "build", "patch")

    print("loading analysis...")
    s = M.load()
    sinks = G.sink_remedies(s)

    print("assembling project from %s" % config.ACTIVE.src_dir)
    nums = assemble(dest)
    titles_by_num = {n: t for t, n in nums.items()}
    cedits = install_mode_chooser(dest, titles_by_num)   # feasibility gate BEFORE any wrap
    for e in cedits:
        print("  [%s] mode-ui %-10s %s" % ("ok " if e["applied"] else "SKIP",
                                           e.get("title", "?"), e.get("why", "")))

    print("\napplying %d sink remedies:" % len(sinks))
    edits = apply_sink_remedies(dest, sinks, titles_by_num)
    for e in edits:
        mark = "ok " if e["applied"] else "SKIP"
        where = e.get("title", "script%s" % e["script"])
        extra = ("  (also dropped the %d penalty)" % e["score_removed"]
                 if e.get("score_removed") else "")
        print("  [%s] %-10s %s%s" % (mark, where, e["why"], extra))
    resedits = apply_resource_remedies(dest, G.resource_remedies(s), titles_by_num)
    if resedits:
        print("\napplying %d resource remedies:" % len(resedits))
        for e in resedits:
            print("  [%s] %-10s %s" % ("ok " if e["applied"] else "SKIP",
                                       e.get("title", "?"), e["why"]))
    specs = G.guard_specs(s)
    print("\napplying %d guard specs:" % sum(1 for x in specs if x["site"] == "edge"))
    gedits = apply_guards(dest, specs, titles_by_num, nums,
                          s_drops=lambda it: s.drops.get(it, set()), rooms=set(s.rooms))
    for e in gedits:
        mark = "ok " if e["applied"] else "SKIP"
        pl = e.get("placement", {})
        how = ("%s @ %s.%s state %s" % (pl.get("kind"), pl.get("instance"),
                                        pl.get("trigger_method", pl.get("method")),
                                        pl.get("trigger_state", "-"))) if e["applied"] else e["why"]
        loc = ("rm%s->rm%s" % (e["from_room"], e["to_room"]) if e.get("from_room") is not None
               else "%s g%s" % (e.get("title", "?"), e.get("register", "?")))  # register-write spec
        print("  [%s] %-16s %s" % (mark, loc, how))
        if e["applied"]:
            print("        %s" % to_source_syntax(e["condition"]))
    uedits = cedits + declare_mode_globals(dest)
    for e in uedits[len(cedits):]:
        print("  [%s] mode-ui %-10s %s" % ("ok " if e["applied"] else "SKIP",
                                           e.get("title", "?"), e.get("why", "")))
    touched = sorted({e["title"] for e in edits + resedits + gedits + uedits
                      if e["applied"] and e.get("title")})

    print("\ncompiling...")
    r = compile_project(dest)
    print("  .sco written: %d;  compiled: %d/%d" % (r["sco_written"], r["compiled"], r["total"]))
    for t, err in r["failures"]:
        print("  FAILED %-10s %s" % (t, err))
    unpatchable = [t for t, _ in r["failures"] if t in touched]
    if unpatchable:
        print("\nREFUSING to emit: an edited script failed to compile: %s" % unpatchable)
        return 1

    print("\nemitting loose patch files for %d edited scripts:" % len(touched))
    for w in emit_patches(dest, touched, nums, out_dir):
        if w["ok"]:
            print("  %-24s %-10s %d bytes"
                  % (" + ".join(os.path.basename(p) for p in w["paths"]), w["title"], w["bytes"]))
        else:
            print("  FAILED script %d %s: %s" % (w["script"], w["title"], w["error"]))
    print("\npatch files in: %s" % out_dir)
    print("copy them into a COPY of the game folder; delete them to revert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
