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
from trigger import (find_trigger, find_arming, find_proc_calls, exports_of,
                     reaching_procs, wrap_trigger_in_source, _block_span,
                     _enclosing_clause_body)

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
    global _EGO, _GAME, _ROOM, _IR, REFUSE, _JUST_KIDDING
    _IR = ir
    form = refusal_form(ir)
    # No derivable way to show a line -> emit NO refusal text at all. A guard that refuses
    # silently is the "the game lied to the player" class that only play-testing caught last time,
    # so `apply_guards` treats an empty refusal as a reason not to place a refusal-bearing guard.
    REFUSE = (form % "Not yet!") if form else None
    _JUST_KIDDING = (form % "Just kidding! You still need it.") if form else None
    globals()["_RETRACTION_FORM"] = form or "%s"
    import extract as X
    X.install_vocabulary(ir)                       # sets X._EGO = the ego holder global(s)
    _EGO = min(X._EGO) if X._EGO else 0
    _GAME = _dominant_receiver(ir, "changeScore", 1)
    _ROOM = _dominant_receiver(ir, "newRoom", 2)


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


def apply_sink_remedies(dest, sinks, titles_by_num):
    """Delete the item consumption in each dangerous PURE SINK.

    Safe by construction: a pure sink is a clause that does nothing EXCEPT destroy the item (it
    arms no machine state and writes no register any guard reads), so removing its one effect
    cannot perturb anything else. The joke and the score penalty stay; the player keeps the item."""
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
        pat = re.compile(r"^\s*\(global%d\s+put:\s*%d\s*(?:%d\s*)?\)\s*$"
                         % (_EGO, sk["item"], disposal))
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
        retraction = "%s%s\n" % (indent, _RETRACTION_FORM
                                 % "Just kidding! You hold on to it because you still need it.")
        del lines[i]
        end = _clause_end_line(lines, i)
        lines.insert(end, retraction)
        # Drop the penalty too. It was the price of DESTROYING the item, and the destruction is
        # gone -- charging for something that did not happen also caps the reachable score
        # permanently, which is a small unwinnable state of its own in a scored game. Only ever a
        # NEGATIVE score adjacent to the consumption; a positive one rewards something legitimate.
        dropped_score = None
        if i + 1 < len(lines):
            sm = re.match(r"\s*\(global%d\s+changeScore:\s*(-\d+)\)\s*$" % _GAME, lines[i + 1])
            if sm:
                dropped_score = int(sm.group(1))
                del lines[i + 1]
        open(path, "w").write(_ensure_refusal_use("".join(lines), titles_by_num))
        edits.append({**sk, "applied": True, "title": title, "line": i + 1,
                      "score_removed": dropped_score})
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

    Walks forward tracking parenthesis depth relative to the deleted line's position: the clause
    ends where depth would go negative, i.e. at its own closing paren. Used to put a retraction
    AFTER the text it retracts."""
    depth = 0
    for j in range(i, len(lines)):
        for ch in _strip_literals(lines[j]):
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
_PLACED_KINDS = ("trigger", "direct", "setscript", "arm-event", "proc-call")


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
    wrapped = ("\n\t\t\t\t(if %s%s\n\t\t\t\telse\n"
               "\t\t\t\t\t(%s setMotion: 0)\n"
               "\t\t\t\t\t(%s x: (- (%s x:) 12))\n"
               "\t\t\t\t\t(%s edgeHit: 0)   ; else the clause re-fires every cycle\n"
               "\t\t\t\t\t%s  ; softlock-guard\n\t\t\t\t)\n\t\t\t"
               % (cond, body, ego, ego, ego, ego, REFUSE))
    return text[:m.end()] + wrapped + text[i - 1:], 1


def _recycle_counter_break(text, write_start, msg):
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
            nt, ok = _recycle_counter_break(text, m.start(), _JUST_KIDDING)
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
            lines[i] = "%s; [softlock-guard] %s no longer wasted here\n" % (indent, r["item_name"])
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
            lines[tgt] = lines[tgt].rstrip("\n") + "\n%s%s  ; [softlock-guard]\n" % (aind, msg)
        open(path, "w").write("".join(lines))
        out.append({**r, "applied": True, "title": title, "sites": len(hits)})
    return out


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
    wrapped = ("(if %s\n\t\t\t\t%s\n\t\t\telse\n\t\t\t\t%s  ; softlock-guard: cannot board without it"
               "\n\t\t\t)" % (cond, text[bs:be], REFUSE))
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
           % (indent, indent, cond, closes, indent))
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
                       % (cond, region[es:ee]))
            return text[:bs] + region[:es] + wrapped + region[ee:] + text[be:], 1
    return text, 0


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
        cond, recv_src, sel, word, mask)
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


def apply_guards(dest, specs, titles_by_num, nums, s_drops=lambda it: set(), rooms=None):
    """Place each EDGE guard at its CONTROLLABLE TRIGGER.

    A frontier `newRoom: N` usually sits at the last state of a changeState cutscene -- an
    UNCONTROLLABLE transition that has already consumed resources and started animating. Guarding
    it there hangs the game. `trigger.find_trigger` walks back to the player-facing handler that
    STARTS the cutscene and we guard that instead, so the refusal happens before anything runs.
    `wrap_trigger_in_source` wraps the whole enclosing cond-clause, not just the changeState, so
    side-effecting siblings (score, sounds, flag sets) cannot fire ahead of the refusal."""
    out_unplaced = []
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
                k = find_trigger(forms, sp["to_room"])["kind"]
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
        if not placed:
            out.append({**sp, "applied": False, "why": "no free-running trap write found",
                        "from_room": None, "to_room": None})
    for title, group in sorted((k, v) for k, v in by_title.items() if k):
        for sp in group:
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
                p = find_trigger(cforms, sp["to_room"])
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
            if placement["kind"] not in _PLACED_KINDS and placement.get("instance"):
                # The cutscene that performs the `newRoom` is in one file and the ARMING that
                # starts it is in another: KQ6's rm340 does `(setScript: (ScriptID 344 3))` and
                # script 344's `catchNiteMare` does the `newRoom: 155`. Look for that arming in the
                # other candidate files -- under either spelling, the instance's name or its
                # export number -- and guard it there.
                # Targets: the instance itself, and EVERY export of the script it lives in. The
                # second is needed because a cutscene script hands off internally -- KQ6's rm340
                # arms `(ScriptID 344 3)` (`blowinIt`), which several states later becomes
                # `catchNiteMare`, and only that last one performs the `newRoom`. The arming a
                # room can be guarded at is the one that starts the SCRIPT, so any export of it
                # is the right commit point; staying inside one script keeps that tight.
                snum, exps = exports_of(forms)
                targets = {placement["instance"]}
                if snum is not None:
                    targets |= {("ScriptID", snum, idx) for idx in exps}
                    targets.add(("proc", snum))    # ...or the room just CALLS one of its procedures
                for cand in _edit_candidates(dest, titles_by_num, sp, rooms):
                    if cand == title:
                        continue
                    cpath = os.path.join(dest, "src", cand + ".sc")
                    try:
                        arm = find_arming(read_file(cpath), targets)
                    except Exception:               # noqa: BLE001 -- unparseable candidate
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
                out.append({**sp, "applied": False,
                            "why": "no controllable trigger (%s) and no room-property exit"
                                   % placement["kind"],
                            "placement": placement})
                continue
            if REFUSE is None and placement["kind"] != "arm-event":
                # An `arm-event` gate has no `else` branch and so says nothing either way; every
                # other placement REFUSES the player's command, and refusing without a word is the
                # "the game lied to the player" failure only play-testing catches.
                out.append({**sp, "applied": False, "placement": placement,
                            "why": "no literal-display form derives for this game, so a refusal "
                                   "would be silent"})
                continue
            text = open(path, errors="replace").read()
            new_text, n = wrap_trigger_in_source(
                text, placement, to_source_syntax(sp["condition"]), REFUSE)
            if n == 0:
                out.append({**sp, "applied": False, "why": "trigger found but no site rewritten",
                            "placement": placement})
                continue
            open(path, "w").write(_ensure_refusal_use(new_text, titles_by_num))
            row = {**sp, "applied": True, "title": title, "sites": n, "placement": placement}
            also = _also_place_capture(dest, sp, titles_by_num, rooms, placement)
            if also:
                row["also_placed"] = also
            out.append(row)
    return out


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
    patch stops being reviewable."""
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
    touched = sorted({e["title"] for e in edits + resedits + gedits if e["applied"]})

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
