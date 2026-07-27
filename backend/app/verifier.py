"""Decide whether step N follows from step N-1.

The rule for equations is equivalence of solution sets, not textual similarity:
`2x + 6 = 14` follows from `x + 3 = 7` because both vanish on exactly x = 4.

Every verdict here is either proved or explicitly `UNKNOWN`. When a step is
wrong we try to produce a *witness* — a concrete value that satisfies the
previous line but not this one — which is far more useful to a student than
"this is incorrect".
"""

from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TypeVar

import sympy

from .parsing import ParseError, Statement, parse_line

# SymPy's simplify has no notion of a deadline, so we bound each call by running
# it on a worker thread. The thread is not killed on timeout (Python can't), but
# the request returns promptly and the pool is small enough to bound the damage.
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sympy")
CALL_TIMEOUT_SECONDS = 3.0

T = TypeVar("T")


class Timeout(Exception):
    pass


def bounded(fn: Callable[[], T]) -> T:
    """Run `fn`, raising Timeout if it outstays CALL_TIMEOUT_SECONDS."""
    future = _POOL.submit(fn)
    try:
        return future.result(timeout=CALL_TIMEOUT_SECONDS)
    except FutureTimeout as exc:
        raise Timeout("SymPy took too long on this step.") from exc


class Relation(Enum):
    EQUIVALENT = "equivalent"
    NOT_EQUIVALENT = "not_equivalent"
    UNKNOWN = "unknown"


@dataclass
class Comparison:
    relation: Relation
    reason: str
    # e.g. "x = 4" — a value satisfying the previous line but not this one.
    witness: str | None = None


def _simplify(expr: sympy.Expr) -> sympy.Expr:
    return bounded(lambda: sympy.simplify(expr))


def _vanishes(expr: sympy.Expr) -> bool:
    return _simplify(expr) == 0


def _numeric_solutions(expr: sympy.Expr, symbol: sympy.Symbol) -> list[sympy.Expr] | None:
    """Concrete roots of `expr` in `symbol`, or None if SymPy can't give a finite set."""
    try:
        raw = bounded(lambda: sympy.solve(expr, symbol, dict=False))
    except (Timeout, NotImplementedError, Exception):
        return None
    if not isinstance(raw, (list, tuple)):
        return None
    solutions = []
    for value in raw:
        value = sympy.nsimplify(value) if value.is_number else value
        if not value.is_number:
            return None  # parametric / symbolic solution — not a finite set
        solutions.append(sympy.simplify(value))
    return solutions


def _format(symbol: sympy.Symbol, value: sympy.Expr) -> str:
    return f"{symbol} = {sympy.nsimplify(value)}"


def _sample_points(symbols: list[sympy.Symbol], attempts: int = 40):
    rng = random.Random(20260726)  # deterministic: same note gives the same witness
    for _ in range(attempts):
        yield {s: sympy.Integer(rng.randint(-9, 9)) for s in symbols}


def _find_expression_witness(
    a: sympy.Expr, b: sympy.Expr, symbols: list[sympy.Symbol]
) -> str | None:
    """A substitution where two expressions take different values."""
    for point in _sample_points(symbols):
        try:
            va = sympy.simplify(a.subs(point))
            vb = sympy.simplify(b.subs(point))
        except Exception:
            continue
        if not (va.is_number and vb.is_number):
            continue
        if sympy.simplify(va - vb) != 0:
            assignment = ", ".join(_format(s, v) for s, v in point.items())
            return f"at {assignment}, the two sides give {va} and {vb}"
    return None


def compare_equations(previous: Statement, current: Statement) -> Comparison:
    d_prev, d_cur = previous.difference, current.difference

    # 1. Same equation after rearrangement: (lhs - rhs) is identical.
    if _vanishes(d_prev - d_cur):
        return Comparison(Relation.EQUIVALENT, "the same equation, rearranged")

    # 2. Both sides scaled by a nonzero constant. A *constant* ratio is safe;
    #    a symbolic one is not, since it could be zero for some value.
    if _simplify(d_prev) != 0 and _simplify(d_cur) != 0:
        try:
            ratio = _simplify(d_cur / d_prev)
        except Timeout:
            ratio = None
        if ratio is not None and not ratio.free_symbols and ratio != 0:
            if ratio.is_finite is not False:
                return Comparison(
                    Relation.EQUIVALENT, f"both sides multiplied by {ratio}"
                )

    # 3. Single unknown: compare solution sets directly. This is the definition
    #    of equivalence, so it settles cases the shortcuts above miss.
    symbols = sorted(previous.free_symbols | current.free_symbols, key=str)
    if len(symbols) == 1:
        symbol = symbols[0]
        prev_roots = _numeric_solutions(d_prev, symbol)
        cur_roots = _numeric_solutions(d_cur, symbol)
        if prev_roots is not None and cur_roots is not None:
            prev_set = {sympy.srepr(r) for r in prev_roots}
            cur_set = {sympy.srepr(r) for r in cur_roots}
            if prev_set == cur_set:
                return Comparison(
                    Relation.EQUIVALENT, "both lines have the same solution set"
                )

            lost = [r for r in prev_roots if sympy.srepr(r) not in cur_set]
            gained = [r for r in cur_roots if sympy.srepr(r) not in prev_set]
            if lost:
                return Comparison(
                    Relation.NOT_EQUIVALENT,
                    "this line drops a solution of the previous line",
                    witness=(
                        f"{_format(symbol, lost[0])} solves the previous line "
                        f"but not this one"
                    ),
                )
            if gained:
                return Comparison(
                    Relation.NOT_EQUIVALENT,
                    "this line introduces a solution the previous line does not have",
                    witness=(
                        f"{_format(symbol, gained[0])} solves this line "
                        f"but not the previous one"
                    ),
                )
            return Comparison(Relation.NOT_EQUIVALENT, "the solution sets differ")

    # 4. Several unknowns, or SymPy could not solve. Try a numeric witness before
    #    giving up: a point on the previous line that misses the current one.
    witness = _find_multivariate_witness(d_prev, d_cur, symbols)
    if witness:
        return Comparison(
            Relation.NOT_EQUIVALENT, "the two equations are not equivalent", witness
        )

    return Comparison(
        Relation.UNKNOWN, "SymPy could not decide whether these two lines agree"
    )


def _find_multivariate_witness(
    d_prev: sympy.Expr, d_cur: sympy.Expr, symbols: list[sympy.Symbol]
) -> str | None:
    """A point satisfying the previous equation but not the current one.

    Only attempted when there are at least two unknowns: fix all but one at
    sampled integers, solve the previous line for the last, then test.
    """
    if len(symbols) < 2:
        return None
    target = symbols[-1]
    others = symbols[:-1]
    for point in _sample_points(others, attempts=12):
        roots = _numeric_solutions(d_prev.subs(point), target)
        if not roots:
            continue
        for root in roots:
            full = {**point, target: root}
            try:
                residual = sympy.simplify(d_cur.subs(full))
            except Exception:
                continue
            if residual.is_number and residual != 0:
                assignment = ", ".join(_format(s, v) for s, v in full.items())
                return f"{assignment} satisfies the previous line but not this one"
    return None


def compare_expressions(previous: Statement, current: Statement) -> Comparison:
    if _vanishes(previous.difference - current.difference):
        return Comparison(Relation.EQUIVALENT, "the two expressions are equal")

    symbols = sorted(previous.free_symbols | current.free_symbols, key=str)
    witness = _find_expression_witness(previous.difference, current.difference, symbols)
    if witness:
        return Comparison(
            Relation.NOT_EQUIVALENT, "the two expressions are not equal", witness
        )
    if not symbols:
        return Comparison(Relation.NOT_EQUIVALENT, "the two values are different")
    return Comparison(
        Relation.UNKNOWN, "SymPy could not decide whether these expressions are equal"
    )


def compare(previous: Statement, current: Statement) -> Comparison:
    if previous.kind == "equation" and current.kind == "equation":
        return compare_equations(previous, current)
    if previous.kind == "expression" and current.kind == "expression":
        return compare_expressions(previous, current)
    return Comparison(
        Relation.UNKNOWN,
        "one line is an equation and the other is a bare expression, "
        "so there is nothing to compare",
    )


@dataclass
class CheckResult:
    """What SymPy established, before any wording is chosen."""

    status: str  # correct | incorrect | uncertain
    reason: str
    witness: str | None = None
    parse_error: str | None = None
    current: Statement | None = None
    previous: Statement | None = None


def check_step(text: str, previous_text: str | None) -> CheckResult:
    try:
        current = parse_line(text)
    except ParseError as exc:
        return CheckResult(status="uncertain", reason=str(exc), parse_error=str(exc))

    if previous_text is None:
        # Nothing to check against — this line is the premise, not a deduction.
        return CheckResult(
            status="correct",
            reason="starting line — there is no earlier step to check it against",
            current=current,
        )

    try:
        previous = parse_line(previous_text)
    except ParseError as exc:
        return CheckResult(
            status="uncertain",
            reason=f"the previous line could not be read as math ({exc})",
            current=current,
        )

    try:
        comparison = compare(previous, current)
    except Timeout as exc:
        return CheckResult(
            status="uncertain", reason=str(exc), current=current, previous=previous
        )

    status = {
        Relation.EQUIVALENT: "correct",
        Relation.NOT_EQUIVALENT: "incorrect",
        Relation.UNKNOWN: "uncertain",
    }[comparison.relation]

    return CheckResult(
        status=status,
        reason=comparison.reason,
        witness=comparison.witness,
        current=current,
        previous=previous,
    )
