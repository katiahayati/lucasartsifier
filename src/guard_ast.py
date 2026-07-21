"""Guard AST -- the boolean-expression types every stage of the pipeline shares.

Lifted out of the legacy `model.py` (which also read the EricOakford decompilation from .sc
sources) so the JSON-IR pipeline has NO dependency on that tree. The types are pure data: the IR
front-end builds them, the SMV emitter and the missability/guard analyses consume them.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Pred:
    kind: str            # OWN | FLAG | CMP | SAID | POS | OPAQUE
    var: object = None   # item id (OWN) or global name (FLAG/CMP)
    op: str = ""         # comparison op for CMP; "" otherwise
    value: object = None # comparison value
    want: bool = True    # OWN/FLAG polarity (False = negated)
    text: str = ""       # printable fallback for OPAQUE

    def __repr__(self):
        if self.kind == "OWN":
            return f"{'' if self.want else '¬'}own({self.var})"
        if self.kind == "FLAG":
            return f"{'' if self.want else '¬'}flag({self.var})"
        if self.kind == "CMP":
            return f"{self.var}{self.op}{self.value}"
        if self.kind == "LOCAL":
            return f"local:{self.var}{self.op}{self.value}"
        if self.kind == "SAID":
            return "Said"
        if self.kind == "POS":
            return f"pos({self.text})"
        if self.kind == "OPAQUE":
            return f"opaque({self.text})"
        return f"{self.kind}({self.var}{self.op}{self.value})"   # never lie about a kind
        # ^ this used to fall through to `opaque(...)` for ANY unrecognized kind, so a
        #   LOCAL pred printed as `opaque()` -- i.e. as the one thing it is NOT. Cost an
        #   hour of chasing a "guard that evaluates False but reads as unknown".


# --------------------------------------------------------------------------
# Guard TREES. A guard is a boolean expression; the flat `guards` list below is a
# CONJUNCTION and cannot represent `or` -- it emits OPAQUE("or") and drops the
# disjuncts. That silently deletes real conditions: the LSL2 raft's day-3 check is
# `(or (== gWearingSunscreen 1) (== gWearingSunscreen 3))`, so the sunscreen simply
# vanishes and a solver concludes you can win without it. Same root cause as the
# glacier needing Sand OR Ashes. Trees keep the structure; `closure.eval3`
# evaluates them with 3-valued logic (unknown stays unknown, so we only ever block
# on a PROVABLY false guard).
# --------------------------------------------------------------------------
@dataclass
class GAnd:
    kids: list


@dataclass
class GOr:
    kids: list


@dataclass
class GNot:
    kid: object
