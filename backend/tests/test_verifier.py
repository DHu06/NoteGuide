import pytest

from app.verifier import check_step


def status(current, previous=None):
    return check_step(current, previous).status


# --- valid algebra: the step must be accepted -------------------------------


@pytest.mark.parametrize(
    "previous,current",
    [
        ("x + 3 = 7", "x = 4"),  # subtract 3 from both sides
        ("x + 3 = 7", "2*x + 6 = 14"),  # multiply both sides by 2
        ("x + 3 = 7", "7 = x + 3"),  # swap sides
        ("x + 3 = 7", "x + 3 - 7 = 0"),  # move everything left
        ("2*x = 8", "x = 4"),
        ("x^2 - 4 = 0", "(x-2)*(x+2) = 0"),  # factoring
        ("3*(x + 1) = 12", "3*x + 3 = 12"),  # distribute
    ],
)
def test_valid_steps_are_correct(previous, current):
    assert status(current, previous) == "correct"


def test_expression_simplification_is_correct():
    assert status("2*(x + 3)", "2*x + 6") == "correct"


def test_first_line_is_accepted_without_a_reference():
    result = check_step("x + 3 = 7", None)
    assert result.status == "correct"
    assert result.previous is None


# --- broken algebra: the step must be rejected, with a witness --------------


def test_arithmetic_slip_is_caught():
    result = check_step("2*x + 5 = 14", "2*x + 6 = 14")
    assert result.status == "incorrect"
    assert result.witness is not None


def test_operation_applied_to_one_side_only():
    # 3 subtracted on the left but not on the right.
    result = check_step("x = 7", "x + 3 = 7")
    assert result.status == "incorrect"
    assert "4" in result.witness


def test_squaring_that_introduces_a_solution_is_caught():
    result = check_step("x^2 = 4", "x = 2")
    assert result.status == "incorrect"
    # x = -2 satisfies the squared line but not x = 2.
    assert "-2" in result.witness


def test_dropped_solution_is_caught():
    result = check_step("x = 2", "x^2 = 4")
    assert result.status == "incorrect"
    assert result.witness is not None


def test_unequal_expressions_get_a_numeric_witness():
    result = check_step("2*x + 7", "2*(x + 3)")
    assert result.status == "incorrect"
    assert result.witness is not None


def test_two_variable_error_is_caught():
    result = check_step("x + 2*y = 10", "x + y = 10")
    assert result.status == "incorrect"


# --- honest uncertainty -----------------------------------------------------


def test_unreadable_line_is_uncertain_not_wrong():
    result = check_step("what is x???", "x + 3 = 7")
    assert result.status == "uncertain"
    assert result.parse_error is not None


def test_equation_versus_expression_is_uncertain():
    assert status("2*x + 6", "x + 3 = 7") == "uncertain"


def test_unreadable_previous_line_is_uncertain():
    assert status("x = 4", "!!!") == "uncertain"
