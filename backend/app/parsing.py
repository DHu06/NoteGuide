"""Turn a line of student math into a SymPy object.

SymPy's ``parse_expr`` ultimately calls ``eval``, so untrusted input goes through
a character whitelist first. Underscores are banned outright, which is what kills
dunder-attribute attacks (``(1).__class__.__bases__``) — the tokenizer's
``auto_symbol`` pass turns bare unknown names into Symbols, but it deliberately
leaves names after a ``.`` alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import sympy
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

MAX_LEN = 200

# Digits, letters, the four operators, ^ for powers, parens, comma, decimal
# point, equals, whitespace. Nothing else. No underscore, quote, bracket,
# colon, semicolon, backslash, or comparison operator.
_ALLOWED = re.compile(r"^[A-Za-z0-9+\-*/^().,= \t]*$")

_TRANSFORMS = standard_transformations + (
    implicit_multiplication_application,  # "2x" -> 2*x
    convert_xor,  # "x^2" -> x**2
)

# The tokenizer rewrites bare names and literals into constructor calls
# (`x` -> `Symbol('x')`, `3` -> `Integer(3)`), so those constructors have to be
# resolvable at eval time. Harmless if a student types them directly.
_CONSTRUCTORS: dict[str, object] = {
    "Symbol": sympy.Symbol,
    "Integer": sympy.Integer,
    "Float": sympy.Float,
    "Rational": sympy.Rational,
}

# Names the student is allowed to reference. Everything else becomes a Symbol.
_ALLOWED_NAMES: dict[str, object] = {
    **_CONSTRUCTORS,
    "pi": sympy.pi,
    "E": sympy.E,
    "sqrt": sympy.sqrt,
    "abs": sympy.Abs,
    "exp": sympy.exp,
    "log": sympy.log,
    "ln": sympy.log,
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "asin": sympy.asin,
    "acos": sympy.acos,
    "atan": sympy.atan,
}


class ParseError(ValueError):
    """The line is not something we can turn into math."""


Kind = Literal["equation", "expression"]


@dataclass(frozen=True)
class Statement:
    """One parsed line. An equation carries lhs/rhs; an expression carries expr."""

    kind: Kind
    raw: str
    lhs: sympy.Expr | None = None
    rhs: sympy.Expr | None = None
    expr: sympy.Expr | None = None

    @property
    def difference(self) -> sympy.Expr:
        """lhs - rhs for an equation; the expression itself otherwise.

        Two equations are equivalent exactly when their differences vanish on
        the same set, which is what makes this the useful normal form.
        """
        if self.kind == "equation":
            return sympy.together(self.lhs - self.rhs)
        return self.expr

    @property
    def free_symbols(self) -> set[sympy.Symbol]:
        return set(self.difference.free_symbols)


def _reject_bad_characters(text: str) -> None:
    if len(text) > MAX_LEN:
        raise ParseError(f"Line is too long (limit {MAX_LEN} characters).")
    if "_" in text:
        raise ParseError("Underscores are not allowed in a math step.")
    if not _ALLOWED.match(text):
        bad = sorted({c for c in text if not _ALLOWED.match(c) or c == "_"})
        raise ParseError(f"Unsupported character(s): {' '.join(bad)}")


def _parse_side(text: str) -> sympy.Expr:
    try:
        parsed = parse_expr(
            text,
            local_dict={},
            global_dict=dict(_ALLOWED_NAMES),
            transformations=_TRANSFORMS,
            evaluate=True,
        )
    except ParseError:
        raise
    except Exception as exc:  # SymPy raises a wide range of tokenizer errors
        raise ParseError(f"Could not read {text.strip()!r} as math.") from exc

    if not isinstance(parsed, sympy.Basic):
        raise ParseError(f"Could not read {text.strip()!r} as math.")
    return parsed


def parse_line(text: str) -> Statement:
    """Parse one line into an equation or a bare expression."""
    stripped = text.strip()
    if not stripped:
        raise ParseError("The line is empty.")

    _reject_bad_characters(stripped)

    parts = stripped.split("=")
    if len(parts) > 2:
        raise ParseError(
            "Chained equalities like a = b = c are not supported yet — "
            "write one equation per line."
        )

    if len(parts) == 2:
        left, right = (p.strip() for p in parts)
        if not left or not right:
            raise ParseError("An equation needs an expression on both sides of '='.")
        return Statement(
            kind="equation", raw=stripped, lhs=_parse_side(left), rhs=_parse_side(right)
        )

    return Statement(kind="expression", raw=stripped, expr=_parse_side(stripped))
