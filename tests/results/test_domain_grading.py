"""Unit tests for FR11 grading policy and score_objective boundary."""
from __future__ import annotations

from decimal import Decimal
import pytest

from backend.app.features.results import compute_attempt_total, score_finalized_item, score_objective
from backend.app.features.results.domain import ValidationFailed, validate_manual_award


def test_single_choice_exact_scoring():
    assert score_objective("single", [1], [1], "exact", Decimal("2.00")) == Decimal("2.00")
    assert score_objective("single", [2], [1], "exact", Decimal("2.00")) == Decimal("0.00")
    assert score_objective("single", [], [1], "exact", Decimal("2.00")) == Decimal("0.00")
    # Defensive: multiple selections on a single-choice item never earn marks
    assert score_objective("single", [1, 2], [1], "exact", Decimal("2.00")) == Decimal("0.00")


def test_multiple_select_exact_and_partial_credit():
    # AT07 exact example: 4-mark partial-credit keyed {A,C} = {1,3}, chosen {A} = {1} -> 2.00
    assert score_objective("multiple", [1], [1, 3], "partial_no_wrong", "4.00") == Decimal("2.00")
    assert score_objective("multiple", [1, 3], [1, 3], "partial_no_wrong", "4.00") == Decimal("4.00")
    # Extra wrong selection earns zero
    assert score_objective("multiple", [1, 2], [1, 3], "partial_no_wrong", "4.00") == Decimal("0.00")
    assert score_objective("multiple", [1, 2, 3], [1, 3], "partial_no_wrong", "4.00") == Decimal("0.00")
    assert score_objective("multiple", [], [1, 3], "partial_no_wrong", "4.00") == Decimal("0.00")

    # Exact-set multiple select: incomplete earns zero
    assert score_objective("multiple", [1], [1, 3], "exact", "4.00") == Decimal("0.00")
    assert score_objective("multiple", [1, 3], [1, 3], "exact", "4.00") == Decimal("4.00")


def test_partial_credit_rounding_half_up_to_two_decimals():
    assert score_objective("multiple", [1], [1, 2, 3], "partial_no_wrong", "4.00") == Decimal("1.33")
    assert score_objective("multiple", [1, 2], [1, 2, 3], "partial_no_wrong", "4.00") == Decimal("2.67")


def test_score_finalized_item_written_blank_vs_nonblank():
    # Blank written response immediately earns 0.00 (never blocks release as pending)
    assert score_finalized_item("written", "manual", "4.00", written_answer="   \n ") == Decimal("0.00")
    # Nonblank written response awaits examiner manual grading
    assert score_finalized_item("written", "manual", "4.00", written_answer="Replication reduces bias.") is None


def test_validate_manual_award_bounds_and_decimals():
    assert validate_manual_award("3", Decimal("4.00")) == Decimal("3.00")
    assert validate_manual_award(Decimal("0.00"), Decimal("4.00")) == Decimal("0.00")
    assert validate_manual_award(4.0, Decimal("4.00")) == Decimal("4.00")
    assert validate_manual_award("2.75", Decimal("4.00")) == Decimal("2.75")

    for bad in ("-0.01", "4.01", "5", "1.234", "abc", True):
        with pytest.raises(ValidationFailed):
            validate_manual_award(bad, Decimal("4.00"))


def test_compute_attempt_total_returns_none_when_any_item_pending():
    assert compute_attempt_total([Decimal("2.00"), Decimal("2.00"), None]) is None
    assert compute_attempt_total([]) is None
    assert compute_attempt_total([Decimal("2.00"), Decimal("2.00"), Decimal("3.00")]) == Decimal("7.00")


def test_invalid_objective_rule_or_kind_rejected():
    with pytest.raises(ValueError):
        score_objective("written", [], [], "manual", "4.00")
    with pytest.raises(ValueError):
        score_objective("single", [1], [1], "partial_no_wrong", "2.00")
