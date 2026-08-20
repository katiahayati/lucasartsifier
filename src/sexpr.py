"""S-expression reader for decompiled Sierra Script (.sc) files.

The decompiled sources (sluicebox / SCICompanion syntax) are Lisp-like. This
reader turns a .sc file into nested Python lists of typed atoms. We deliberately
keep it faithful to *lexical* structure and let a later pass (sci_model.py)
impose meaning (classes, methods, message sends, guards, effects).

Atom types:
  Sym      - a symbol/identifier/operator, incl. selectors written `foo:`
             (trailing colon preserved) and keyword args written `#foo`.
  int      - a number (decimal, negative, or $hex)
  Str      - a brace string literal  {like this}   (message text; usually discarded)
  Said     - a parser Said spec       'get/lotion'  (kept raw; the effect is what
             matters, the string is dropped downstream per the plan)

Lists are plain Python lists. Comments (`;` to end of line) are dropped, except
they never terminate inside a {..} or '..' literal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Sym:
    name: str

    def __repr__(self) -> str:
        return self.name

    def is_selector(self) -> bool:
        return self.name.endswith(":")

    @property
    def sel(self) -> str:
        """Selector name without the trailing colon."""
        return self.name[:-1] if self.name.endswith(":") else self.name


@dataclass(frozen=True)
class Str:
    text: str

    def __repr__(self) -> str:
        return "{%s}" % self.text


@dataclass(frozen=True)
class Said:
    spec: str

    def __repr__(self) -> str:
        return "'%s'" % self.spec


class SexprError(Exception):
    pass


_DELIMS = "(){}';\""
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WS = " \t\r\n\f"


class _Lexer:
    def __init__(self, text: str, filename: str = "<str>"):
        self.s = text
        self.n = len(text)
        self.i = 0
        self.filename = filename

    def tokens(self):
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            if c in _WS:
                self.i += 1
                continue
            if c == ";":  # line comment
                nl = s.find("\n", self.i)
                self.i = n if nl < 0 else nl + 1
                continue
            if c == "(":
                self.i += 1
                yield ("(", None)
                continue
            if c == ")":
                self.i += 1
                yield (")", None)
                continue
            if c == "{":  # brace string, honoring backslash escapes
                yield ("atom", self._read_delimited("{", "}", Str))
                continue
            if c == '"':  # EricOakford-dialect double-quote string, e.g. name "Magic Hen"
                yield ("atom", self._read_delimited('"', '"', Str))
                continue
            if c == "'":  # Said spec (opaque: may contain parens, commas, slashes)
                yield ("atom", self._read_delimited("'", "'", Said))
                continue
            # bare atom: read until whitespace or a structural delimiter
            j = self.i
            while j < n and s[j] not in _WS and s[j] not in _DELIMS:
                j += 1
            if j == self.i:  # at an unhandled delimiter (e.g. a stray '}'): skip it, never spin
                self.i += 1
                continue
            raw = s[self.i:j]
            self.i = j
            # `ownedBy:self` -- a selector and its argument with no space between.
            # SCI's compiler does not care; our reader did, silently. Reading to the
            # next whitespace made one Sym named "ownedBy:self", which `is_selector()`
            # rejects (it does not END with ':'), so the message send simply was not
            # there. 155 sites in KQ4, 12 in LSL2 -- including `Actor::has` itself:
            #     (= theItem (inventory at:what))
            #     (return (and theItem (theItem ownedBy:self)))
            # i.e. the definition of possession, unreadable on a whitespace
            # convention. Split it: the colon is the selector marker, not part of a
            # name.
            head, sep, rest = raw.partition(":")
            if sep and rest and _IDENT.match(head):
                yield ("atom", Sym(head + ":"))
                yield ("atom", self._classify(rest))
                continue
            yield ("atom", self._classify(raw))

    def _read_delimited(self, open_c: str, close_c: str, ctor):
        s, n = self.s, self.n
        assert s[self.i] == open_c
        self.i += 1  # consume opener
        start = self.i
        buf = []
        while self.i < n:
            c = s[self.i]
            if c == "\\" and self.i + 1 < n:  # escape: keep next char verbatim
                buf.append(s[self.i + 1])
                self.i += 2
                continue
            if c == close_c:
                self.i += 1  # consume closer
                return ctor("".join(buf))
            buf.append(c)
            self.i += 1
        raise SexprError(f"unterminated {open_c}..{close_c} literal at {self.filename} "
                         f"(started offset {start})")

    @staticmethod
    def _classify(raw: str):
        # numbers: decimal, negative decimal, or $hex
        if raw and (raw[0].isdigit() or (raw[0] == "-" and raw[1:2].isdigit())):
            try:
                return int(raw, 10)
            except ValueError:
                pass
        if raw.startswith("$"):
            try:
                return int(raw[1:], 16)
            except ValueError:
                pass
        return Sym(raw)


def read_all(text: str, filename: str = "<str>") -> list:
    """Parse a whole file, returning the list of top-level forms."""
    lx = _Lexer(text, filename)
    stack = [[]]  # stack[0] is the top-level form list
    for kind, val in lx.tokens():
        if kind == "(":
            new = []
            stack[-1].append(new)
            stack.append(new)
        elif kind == ")":
            if len(stack) == 1:
                raise SexprError(f"unbalanced ')' in {filename}")
            stack.pop()
        else:  # atom
            stack[-1].append(val)
    if len(stack) != 1:
        raise SexprError(f"unbalanced '(' in {filename} (depth {len(stack) - 1} at EOF)")
    return stack[0]


def read_file(path: str) -> list:
    with open(path, "r", encoding="latin-1") as f:
        return read_all(f.read(), path)


# --- WHAT IS NOT CODE, in one place ------------------------------------------------------------
#
# The reader above tokenises; the PATCHER and the TRIGGER placement layer do not -- they compute
# spans by walking raw source text, because a guard is inserted into bytes and has to come back
# out as bytes. Both therefore need the same answer to one question: is this offset really code?
# They each grew their own answer, and the 2026-08-20 review found what that costs -- one of them
# filtered its span walk and not the scan that fed it (R1), and the other filtered its span walk
# and not its region search at all (live on KQ6 and LB2). One rule, one home, two importers
# ([[same-rule-two-places]]).

def skip_noncode(text, j, end):
    """If `text[j]` opens a comment or a quoted form, the offset just past it; else None.

    Four constructs look like code and are not, and the taxonomy matters because only one of them
    carries parens in this corpus. Measured 2026-08-20 across the five source trees:

      * `;` LINE COMMENTS -- everywhere, and they eat to end of line;
      * `{...}` MESSAGE TEXT -- everywhere, may span lines, free to contain a lone paren, and on
        KQ6 and LB2 free to contain WHOLE SCI SOURCE (`WriteFeature.sc` writes scripts);
      * `'...'` SAID AND MENU SPECS -- 3,100 in code position on LSL2 and KQ4, and the only
        non-code form here that legitimately carries parens (`'(get,take)/lamp'` is a grouped
        alternation). All 3,100 balance today, none contains a `;` or a `{`, and no line carries
        a stray quote -- so handling them changes not one span in the corpus. "Balanced today" is
        a fact about these five games, not a property of the arithmetic;
      * `"..."` -- DEAD. Every double quote in the corpus is inside a `{...}` message, which is
        consumed above it. Kept, line-bounded, for a decompiler that emits one.

    The quoted forms are bounded to their own LINE, so an unterminated one is an ordinary
    character rather than a skip that runs to the end of the file -- or, in the inline copy this
    replaced in `trigger`, a `find` returning -1, an index of 0, and a walk that restarts from
    the top of the file forever. Every `'...'` in the corpus is on one line, measured: no line
    carries a stray quote."""
    c = text[j]
    if c == ";":
        k = text.find("\n", j)
        return end if k < 0 else min(k + 1, end)
    if c == "{":
        k = text.find("}", j + 1)
        return end if k < 0 else min(k + 1, end)
    if c in "'\"":
        nl = text.find("\n", j + 1)
        stop = end if nl < 0 else min(nl, end)
        k = j + 1
        while k < stop and text[k] != c:
            k += 2 if text[k] == "\\" else 1
        return min(k + 1, end) if k < stop else None
    return None


def noncode_spans(text):
    """Every `(start, end)` in `text` that `skip_noncode` consumes whole, in order.

    One linear pass, so a scanner can ask "is this match really code?" by bisection rather than
    re-deriving the answer per candidate."""
    out, j, n = [], 0, len(text)
    while j < n:
        nxt = skip_noncode(text, j, n)
        if nxt is not None:
            out.append((j, nxt))
            j = max(nxt, j + 1)
            continue
        j += 1
    return out


def code_finditer(text, pattern, spans=None):
    """`re.finditer`, minus every match that STARTS inside a comment or a quoted form.

    ⛔ THE SCAN AND THE SPAN WALK MUST AGREE. Filtering one half of a two-half arithmetic is not
    a fix: `patcher._enclosing_if_test` skipped strings when it measured a span and not when it
    chose which span to measure, so an `(if` written inside a message was picked as the arming
    and the demand was written into the message -- with the placement row reporting
    `applied: True`. `trigger._find_region` had the same shape and a live instance."""
    import bisect
    if spans is None:
        spans = noncode_spans(text)
    starts = [s for (s, _e) in spans]
    for m in re.finditer(pattern, text):
        i = bisect.bisect_right(starts, m.start()) - 1
        if i >= 0 and m.start() < spans[i][1]:
            continue
        yield m


def code_search(text, pattern, spans=None):
    """The first match of `pattern` that is really code, or None -- `re.search`'s replacement
    wherever a raw first-match-wins scan chooses a region to rewrite."""
    return next(code_finditer(text, pattern, spans), None)


# --- WRITING code, the other direction ------------------------------------------------------

def line_indent(text, pos):
    """The leading whitespace of the line `pos` sits on."""
    ls = text.rfind("\n", 0, pos) + 1
    return re.match(r"[ \t]*", text[ls:]).group(0)


def mark_line(text, at, marker, cont_indent=None):
    """`marker`, extended with a line break when it would otherwise EAT `text[at:]`'s line.

    ⛔ `;` OPENS A LINE COMMENT. Every emitter in this project signs its edit with one, and the
    edit is spliced as `text[:s] + <new form> + marker + text[e:]` -- so whatever stock wrote
    after `e` on that line is inside the comment. The failure mode is not a broken build, which
    would be the lucky case: when the eaten text happens to balance, the file still compiles
    and a statement has been silently DELETED with the placement row reporting `applied: True`.

    This is the rule's THIRD outing. It was found on `_conjoin_marked` (2026-08-20, review
    minor list), fixed there alone -- and the same commit made `_wrap_statement`, twenty lines
    away, the common path for exactly the shape that trips it. It lives here now because
    twelve emitters across `patcher` and `trigger` splice a marker in front of preserved text
    ([[same-rule-two-places]]).

    ⛔ WHAT IS AT RISK IS CODE, NOT BYTES. The rest of the line is safe when it holds nothing a
    comment can destroy -- whitespace, or a comment already. LB2's `rm520` is the corpus's one
    live instance: two act-flip rows conjoin onto the SAME head, so the second one's marker
    lands in front of the first one's, and a `strip()`-shaped test would push a comment onto a
    line of its own and move the bytes of a play-confirmed patch to protect nothing. A `{...}`
    message or a `'...'` Said IS at risk -- an argument on the next line is not whitespace --
    so those count as content.

    Byte-identical at every site in the five source trees, LB2's double marker included -- so
    this changes no emission, it removes a class of them. `cont_indent` is what the pushed-down
    remainder is indented with; None means the indent of the line `at` sits on, plus a tab."""
    nl = text.find("\n", at)
    end = nl if nl >= 0 else len(text)
    j = at
    while j < end:
        nxt = skip_noncode(text, j, end)
        if nxt is not None:
            if text[j] == ";":
                break                              # a comment: the line is already spent
            return marker + "\n" + (line_indent(text, at) + "\t" if cont_indent is None
                                    else cont_indent)
        if text[j] not in _WS:
            return marker + "\n" + (line_indent(text, at) + "\t" if cont_indent is None
                                    else cont_indent)
        j += 1
    return marker


# Heads whose form has a BODY, and how many leading elements come before it: the test, the
# signature, the value dispatched on. `(procedure (name p1) body...)` -- element 0 is the head,
# element 1 the signature, so a body statement is at index >= 2. Anything not named here is a
# send, an operator or a call, and its arguments are in VALUE position.
_BODY_HEADS = {"if": 1, "while": 1, "until": 1, "switchto": 1,
               "method": 1, "procedure": 1, "for": 3, "repeat": 0, "else": 0}
# ...and the two whose children are CLAUSES rather than statements. A `cond` clause and a
# `switch` case are the game's own alternatives; neither is a form anything may be wrapped
# around, and it is the GRANDPARENT that tells a clause `((> a b) (foo))` from a
# computed-receiver send `((gInv at: 25) owner:)`, which look identical from inside.
_CLAUSE_PARENTS = ("cond", "switch")


def _elements(text, form_start, form_end, spans):
    """Offsets of the top-level elements of the form at `[form_start, form_end)`, in order.

    An element is a parenthesised form, a `[...]` index, or a bare token. Comments and quoted
    forms are skipped whole, so a `;` between two statements does not become one."""
    import bisect
    starts = [s for (s, _e) in spans]
    out, j = [], form_start + 1
    while j < form_end - 1:
        i = bisect.bisect_right(starts, j) - 1
        if i >= 0 and j < spans[i][1]:
            j = spans[i][1]
            continue
        c = text[j]
        if c in _WS:
            j += 1
            continue
        out.append(j)
        if c == "(":
            j = _forward_span(text, j, form_end, spans)
        elif c == "[":
            k = text.find("]", j)
            j = form_end if k < 0 else k + 1
        else:
            while j < form_end - 1 and text[j] not in _WS and text[j] not in "()":
                j += 1
        if j <= out[-1]:                           # never stall on an unreadable element
            j = out[-1] + 1
    return out


def _forward_span(text, start, limit, spans):
    """End offset of the balanced form opening at `start`, bounded by `limit`."""
    import bisect
    starts = [s for (s, _e) in spans]
    depth, j = 0, start
    while j < limit:
        i = bisect.bisect_right(starts, j) - 1
        if i >= 0 and j < spans[i][1]:
            j = spans[i][1]
            continue
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return limit


def form_chain(text, pos, spans=None):
    """Every balanced form containing `pos`, INNERMOST FIRST, as `(start, end)` pairs.

    The one walk that answers "what encloses this, and what encloses that": which fork an
    arming sits in, and whether the form around it is a statement or an argument. A form
    OPENING at `pos` is the innermost one, which is what every caller here means by "the form
    at this offset".

    ONE FORWARD PASS with a stack, not a backward `rfind` loop: the chain runs to the top of
    the file, so measuring each candidate by scanning forward from it is quadratic on a
    100KB source. Only the chain's own members -- a dozen, never thousands -- get spanned."""
    if spans is None:
        spans = noncode_spans(text)
    import bisect
    starts = [s for (s, _e) in spans]
    stack, j = [], 0
    while j < pos:
        i = bisect.bisect_right(starts, j) - 1
        if i >= 0 and j < spans[i][1]:
            j = max(spans[i][1], j + 1)
            continue
        if text[j] == "(":
            stack.append(j)
        elif text[j] == ")" and stack:
            stack.pop()
        j += 1
    opened_here = False
    if pos < len(text) and text[pos] == "(":
        i = bisect.bisect_right(starts, pos) - 1
        if not (i >= 0 and pos < spans[i][1]):
            stack.append(pos)
            opened_here = True
    # ...and ONE more pass forward to close them, innermost first. Spanning each member
    # separately would re-scan to the end of the file once per level.
    ends, depth, n = {}, len(stack), len(text)
    top = depth                                    # the shallowest chain level still open
    j = pos + 1 if opened_here else pos
    while j < n and depth:
        i = bisect.bisect_right(starts, j) - 1
        if i >= 0 and j < spans[i][1]:
            j = max(spans[i][1], j + 1)
            continue
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth < top:                        # ...and only the FIRST close of a level is
                ends[stack[depth]] = j + 1         # its end: a SIBLING that opens and closes
                top = depth                        # after it returns to the same depth
        j += 1
    return [(s, ends.get(s, n)) for s in reversed(stack)]


def head_of(text, form_start):
    """The head token of the form at `form_start`, or None when its head is itself a form."""
    m = re.match(r"\(\s*([^\s()\[\]]+)", text[form_start:])
    return m.group(1) if m else None


def depth1_else(text, start, end, spans=None):
    """Offset of the `else` keyword belonging to the `(if` that opens at `start`, or None.

    Depth is counted from that `if`'s own paren, so an `else` inside a nested form is that
    form's -- KQ5's henchman arms itself under `view: (if (== global11 58) 898 else 884)`, an
    `else` three levels down that says nothing about where the arming sits. The word must
    stand alone: `elsewhere` is not an else, and neither is one written in a message.

    Three emitters had grown their own copy of this walk, two of which skipped no non-code at
    all ([[same-rule-two-places]])."""
    if spans is None:
        spans = noncode_spans(text)
    import bisect
    starts = [s for (s, _e) in spans]
    depth, j = 0, start
    while j < end:
        i = bisect.bisect_right(starts, j) - 1
        if i >= 0 and j < spans[i][1]:
            j = max(spans[i][1], j + 1)
            continue
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 1 and text.startswith("else", j) \
                and not (j and (text[j - 1].isalnum() or text[j - 1] in "_-")) \
                and not text[j + 4:j + 5].isalnum() and text[j + 4:j + 5] not in ("_", "-"):
            return j
        j += 1
    return None


# The multi-arm forms, and how many leading elements come before the first arm.
_FORKS = {"cond": 0, "switch": 1, "switchto": 1}


def fork_arms(text, start, end, spans=None):
    """`[(s, e), ...]`, one per ALTERNATIVE of the fork at `[start, end)`, or None -- not a fork.

    A `cond`'s clauses, a `switch`'s cases, a `switchto`'s positional bodies. An `(if ...)` is
    deliberately NOT one: a demand conjoined onto an `if`'s test does not withhold the else, it
    RUNS it, which is a different failure with a different answer (`patcher._depth1_else`)."""
    if spans is None:
        spans = noncode_spans(text)
    head = head_of(text, start)
    if head not in _FORKS:
        return None
    els = _elements(text, start, end, spans)[1 + _FORKS[head]:]
    return [(s, _forward_span(text, s, end, spans)) for s in els if text[s] == "("]


def statement_span(text, pos, spans=None):
    """`(start, end)` of the innermost form containing `pos` that is a STATEMENT, or None.

    ⛔ A STATEMENT IS NOT MERELY A BALANCED FORM (2026-08-20 third review, N1). The innermost
    form around an arming is routinely an expression in VALUE position -- KQ6 and LB2 spell a
    spawn `(= [local0 0] (theCat init: yourself:))`, and LSL2 spells one as a send argument.
    Wrapping THAT in `(if <demand> ...)` does not withhold the arming; it changes what the
    assignment stores, or what the send is passed. The arming statement is the enclosing
    ASSIGNMENT, which is also what the game's own no-arm path skips.

    So the climb is outward through value positions until a form sits in a body slot: after an
    `if`'s test, after a `method`'s signature, inside a `cond` clause or a `switch` case. None
    when no enclosing form is ever a statement -- an arming performed inside a TEST is the
    shape that reaches that, and it cannot be held without duplicating the test, which is the
    same answer `_enclosing_if_test` gives it."""
    if spans is None:
        spans = noncode_spans(text)
    chain = form_chain(text, pos, spans)
    for depth, (s, e) in enumerate(chain):
        if depth + 1 >= len(chain):
            return None                            # a top-level form has no body to sit in
        ps, pe = chain[depth + 1]
        head = head_of(text, ps)
        # ⛔ THE GRANDPARENT DECIDES FIRST, whatever the parent's head looks like. A `cond`
        # clause is `(<test> <body>...)` and its test can be ANYTHING -- a form
        # `((> a b) ...)`, a literal `(57 ...)`, or a bare variable, which is KQ5's own
        # spelling: `(local2 (= local2 0) (proc0_10 71) (self setScript: bringCedric))`. Read
        # by the parent's head alone, that last one is indistinguishable from a send, so the
        # walk climbed out of the clause, past the `cond`, and returned the WHOLE fork as the
        # arming statement -- measured on rm046, the one emitted file that moved.
        gp = chain[depth + 2] if depth + 2 < len(chain) else None
        gph = head_of(text, gp[0]) if gp else None
        if gph in _CLAUSE_PARENTS:
            gels = _elements(text, gp[0], gp[1], spans)
            if ps not in gels or gels.index(ps) <= _FORKS[gph]:
                return None                        # the `switch` VALUE: evaluating it CHOOSES
            lead = 0                               # a clause body starts after its test
        elif head in _CLAUSE_PARENTS:
            return None                            # a direct child of the fork itself: `pos`
            #                                        is in a clause TEST or a switch VALUE, and
            #                                        both CHOOSE rather than run
        elif head is None or re.match(r"[-$0-9]", head):
            continue                               # a computed-receiver send: value position
        elif head in _BODY_HEADS:
            lead = _BODY_HEADS[head]
        else:
            continue                               # a send, an operator, a call: an argument
        # The first BODY-BEARING parent decides, and it can say no. A form in that parent's
        # LEADING slot -- an `if`'s test, a `while`'s test, a `switch`'s dispatch value, a
        # method's signature -- is not a statement and neither is anything above it for this
        # purpose: holding it would change WHICH BRANCH RUNS, not whether the arming fires,
        # which is the same refusal `patcher._enclosing_if_test` gives an arming in a test.
        els = _elements(text, ps, pe, spans)
        if s not in els or els.index(s) <= lead:
            return None
        return (s, e)
    return None
