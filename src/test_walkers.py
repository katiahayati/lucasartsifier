"""Sweep OUR OWN source for the "rule implemented in one of two places" bug.

Three of this project's bugs had exactly this shape, and every one was found only when a GAME
produced a wrong answer:

  * `asserts_eq` -- "does this atom assert equality" -- lived in `required_values` AND in
    `edge_meta.reqs`. Fixing one left KQ4's night gate parsed and completely toothless.
  * the `rm<N>` room lookup lived in `extract._room_object` AND `opmodel.region_rooms`.
    Fixing one left KQ4 with 0 of its 26 region scripts.
  * `Increment` was handled for LOCALS only, so KQ4's dig counter and its clock are invisible.

RESOLVED STRUCTURALLY for control flow: `ir.control_shape` now names SCI's statement forms once,
and all four walkers consume it (`extract.walk_stream` for the three streaming ones,
`compile._paths_of` for the path enumerator). If/Cond/Loop have vanished from this matrix as a
result. What remains here is the EFFECT vocabulary, which legitimately differs per walker -- and
that is exactly the distinction worth keeping the matrix for.

The structural cause is that we run SEVERAL walkers over the same IR, each recognising its own
partially-overlapping set of node types and selectors. A construct one walker knows and another
does not is either a deliberate asymmetry or a latent bug, and nothing tells them apart -- so this
builds the matrix and asserts every asymmetry is one we have written down and justified.

Reads our source, not the game's, so it finds these WITHOUT a game having to expose them first.
It found the `Loop`-inside-`changeState` bug on its first run.

Run: python3 test_walkers.py
"""
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, ".")

SRC = os.path.dirname(os.path.abspath(__file__))

def _walker_files():
    """Every file that walks IR nodes -- DERIVED, not listed.

    A hardcoded list is the same catalogue bug this whole test exists to catch: a seventh walker
    added later would simply not be checked. A file is a walker if it touches IR node structure.
    `ir.py` is excluded because it IS the classifier they all consume."""
    out = []
    for name in sorted(os.listdir(SRC)):
        if not name.endswith(".py") or name.startswith("test_") or name == "ir.py":
            continue
        with open(os.path.join(SRC, name)) as f:
            text = f.read()
        if any(k in text for k in ('["t"]', '.get("t")', '["kids"]', 'get("kids"')):
            out.append(name)
    return out


WALKERS = _walker_files()

_SUBJ = (r'(?:sel|tp|t|pair\[0\]|mn|mname|'
         r'(?:n|x|y|k|m|node|param)\s*(?:\.get\("t"\)|\["t"\]))')
EQ = re.compile(_SUBJ + r'\s*==\s*"([A-Za-z_]+)"')
IN = re.compile(_SUBJ + r'\s+(?:not\s+)?in\s+\(([^)]*)\)')
LIT = re.compile(r'"([A-Za-z_]+)"')

# Asymmetries we have looked at and accepted. Key: construct -> why it is fine.
# Anything NOT in here that is known to some walkers and not others fails the test, which is the
# whole point: a new asymmetry must be justified in writing before it can be ignored.
ACCEPTED = {
    "changeState": "extract deliberately skips changeState -- the MACHINE owns those bodies, and "
                   "a flat duplicate would bypass the gate (see Extractor.run).",
    "newRoom":     "opmodel does not read newRoom itself; it consumes the edges extract and "
                   "the machine lift already produced.",
    "LocalCall":   "compile works on paths the machine lift already inlined calls into.",
    "PublicCall":  "as LocalCall.",
    "setScript":   "extract/opmodel see setScript only as machine ARMING, which machine owns.",
    "init":        "opmodel and machine treat init specially (forced entry writes); the others "
                   "have no entry concept.",
    "cue":         "cue counting is a machine concern only.",
    "setCycle":    "arming selectors -- machine/compile for cues, extract for cue-armed edges.",
    "setMotion":   "as setCycle.",
    "posn":        "extract._object_departures reads posn (with setMotion/handsOff/handsOn) as "
                   "the POSITION-EVENT vocabulary of the departing-init rule -- the terminal "
                   "off-pic parking that says an init yields no interactive presence (LB2's "
                   "arrival taxi, the street seal). A single-purpose lifecycle reader, not "
                   "control flow: no other walker asks where an object ENDS.",
    "setRegions":  "region membership is built once, in opmodel.",
    "Add":         "arithmetic appears in guard atoms (extract) and in counter detection (vocab).",
    "Sub":         "as Add.",
    "Eq":          "comparison node types are guard-atom concerns: extract builds atoms, vocab "
                   "reads class-table comparisons.",
    "Ne":          "as Eq.",
    "Assignment":  "every walker records writes in its own vocabulary.",
    "Object":      "identifying WHOSE state a send addresses is a vocabulary concern, not a "
                   "control-flow one: vocab reads an Object/Class receiver to decide which "
                   "object's property register a send touches (see _prop_receiver_script -- KQ6 "
                   "addresses the same singleton as both `(ScriptID 30 0)` and `rLab`). The "
                   "control-flow walkers only need to know a Send happened.",
    "Number":      "vocab reads Number literals as BIT MASKS when lowering the property-word "
                   "flag stores (both the accessor spelling's arguments and, since the rFlag "
                   "direct-spelling pass, the masks in `|= rFlag1 $0004` arithmetic and "
                   "literal-AND clears). The control-flow walkers treat numbers as opaque "
                   "leaves; there is no shared rule to drift.",
    "Property":    "extract reads a Property node to recognise `register` -- the setScript "
                   "argument that tells one Script which of its exits it is taking -- and vocab "
                   "reads properties to derive the item-location store. The machine walkers see "
                   "properties only through the atoms extract already built.",
    "Variable":    "the walkers that BUILD guard atoms (extract, machine, compile) and vocab, "
                   "which matches variable IDENTITY to derive vocabulary -- the room-selecting "
                   "variable behind SCI1.1's central `setRegions` dispatch, so the guard's "
                   "membership test can be tied to the receiver. opmodel consumes finished atoms "
                   "and never inspects operand nodes itself.",
    "Send":        "as Cond -- vocab matches sends by selector via ir.send_pairs, not by node type.",
    "Switch":      "extract._var_room_values reads switch CASE LABELS as data (the room "
                   "numbers a revolving-door global can hold) and machine._top_switch finds the "
                   "switch that IS the machine. Neither is control flow -- that now lives only in "
                   "ir.control_shape, which is why If/Cond/Loop no longer appear in this matrix "
                   "at all.",
    "Selector":    "name<->number resolution is a vocabulary/spelling concern, not control flow: "
                   "vocab builds sel_value from Selector nodes (name+number in one node) when "
                   "lowering the prop-flag store, and patcher._selector_name's FALLBACK rebuilds "
                   "the same map for an IR that predates the ir._sel_names stash (the lowering "
                   "consumes those nodes, so the stash is the primary path -- see "
                   "guard_prop_flag_owner_write, the wedding-fuse hold). The control-flow walkers "
                   "dispatch on selectors via ir.send_pairs and never touch Selector nodes.",
    "Decrement":   "KNOWN GAP, tracked as TODO A0g(1): Increment/Decrement are handled for LOCALS "
                   "in the machine walkers and not at all in extract, and never for GLOBALS "
                   "anywhere -- which is why KQ4's dig counter and its clock are invisible. "
                   "vocab's mention is only the mask-global store DISQUALIFYING a candidate "
                   "(a counted global is not a bit word).",
    "Increment":   "as Decrement -- TODO A0g(1).",
    # -- the mask-global store (vocab._mask_site / derive_mask_globals / lower_mask_globals,
    #    2026-08-06) reads node types it either LOWERS exactly or must SEE to refuse a
    #    candidate. None of these is shared control-flow logic: extract's atom() is the only
    #    consumer of the emitted booleans, and the relational/arithmetic mentions exist solely
    #    to disqualify.
    "And":         "vocab EMITS And/Or/Not as the per-bit lowering of a mask-global equality "
                   "(`(== g161 15)` -> a conjunction of bit reads) and treats a bare mask word "
                   "under one as a boolean read it can lower exactly; extract.atom consumes "
                   "them as guard atoms. The control-flow walkers see them only through atoms.",
    "Or":          "as And.",
    "Not":         "as And.",
    "Ge":          "relational compares are guard-atom concerns (extract); vocab reads one ONLY "
                   "to REFUSE a mask-global candidate -- a `<`/`>` on a word is scalar use that "
                   "per-bit lowering would misstate.",
    "Gt":          "as Ge.",
    "Le":          "as Ge.",
    "Lt":          "as Ge.",
    "Uge":         "as Ge.",
    "Ugt":         "as Ge.",
    "Ule":         "as Ge.",
    "Ult":         "as Ge.",
    "AssignmentAdd": "compound-arithmetic assignment: machine walkers thread it for LOCAL "
                   "counters; vocab reads it only to disqualify a mask-global candidate. The "
                   "GLOBAL half is the same known gap as Increment/Decrement (TODO A0g(1)).",
    "AssignmentSub": "as AssignmentAdd.",
}

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))


def matrix():
    """construct -> set of walker files that name it."""
    seen = defaultdict(set)
    for name in WALKERS:
        path = os.path.join(SRC, name)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            text = f.read()
        for m in EQ.finditer(text):
            seen[m.group(1)].add(name)
        for m in IN.finditer(text):
            for lit in LIT.findall(m.group(1)):
                seen[lit].add(name)
    return seen


def run():
    print("Walker coverage matrix -- who recognizes which IR construct")
    seen = matrix()
    shared = {c: f for c, f in seen.items() if len(f) >= 2}
    print(f"  {len(seen)} constructs, {len(shared)} known to more than one walker\n")

    header = f"{'construct':16s} " + " ".join(f"{w.replace('.py','')[:9]:>10s}" for w in WALKERS)
    print(header)
    print("-" * len(header))
    for c, files in sorted(shared.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(files) == len(WALKERS):
            continue                                   # everyone agrees: nothing to explain
        marks = " ".join(f"{('X' if w in files else '.'):>10s}" for w in WALKERS)
        print(f"{c:16s} {marks}")

    print()
    unexplained = sorted(c for c, f in shared.items()
                         if len(f) != len(WALKERS) and c not in ACCEPTED)
    check("every partial-coverage construct is documented in ACCEPTED",
          not unexplained,
          f"undocumented asymmetries: {unexplained} -- each is either a deliberate design "
          f"choice (add it to ACCEPTED with the reason) or the next instance of the "
          f"one-of-two-places bug")

    # the allow-list must not rot: an entry for a construct nobody mentions any more is dead
    dead = sorted(c for c in ACCEPTED if c not in seen)
    check("no dead entries in ACCEPTED", not dead, f"unreferenced: {dead}")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
