import pytest
import sympy

from app.parsing import ParseError, parse_line


def test_equation_splits_into_sides():
    stmt = parse_line("x + 3 = 7")
    assert stmt.kind == "equation"
    assert sympy.simplify(stmt.difference - (sympy.Symbol("x") - 4)) == 0


def test_bare_expression():
    stmt = parse_line("2x + 6")
    assert stmt.kind == "expression"
    assert sympy.simplify(stmt.difference - (2 * sympy.Symbol("x") + 6)) == 0


def test_implicit_multiplication_and_caret():
    stmt = parse_line("3x^2 = 12")
    x = sympy.Symbol("x")
    assert sympy.simplify(stmt.difference - (3 * x**2 - 12)) == 0


def test_known_functions_resolve():
    stmt = parse_line("sqrt(4) = 2")
    assert sympy.simplify(stmt.difference) == 0


@pytest.mark.parametrize(
    "line",
    [
        "__import__('os').system('echo hi')",
        "(1).__class__.__bases__",
        "x_1 = 2",
        "lambda: 1",
        "open('/etc/passwd')",
        "x[0] = 1",
        'x = "a"',
        "exec(1)" + ";" + "1",
    ],
)
def test_rejects_code_injection_attempts(line):
    with pytest.raises(ParseError):
        parse_line(line)


def test_rejects_overlong_input():
    with pytest.raises(ParseError):
        parse_line("x+" * 500 + "1 = 0")


def test_rejects_chained_equality():
    with pytest.raises(ParseError, match="Chained"):
        parse_line("a = b = c")


def test_rejects_empty_side():
    with pytest.raises(ParseError):
        parse_line("x = ")


def test_rejects_blank_line():
    with pytest.raises(ParseError):
        parse_line("   ")
