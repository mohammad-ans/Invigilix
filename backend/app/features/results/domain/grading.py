"""Grading policy for objective auto-scoring and manual written awards (FR11).

``score_objective`` is the public callable boundary invoked by the delivery
feature inside its finalization transaction (see README §4 and attempt-api.md).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable

from .errors import Issue, ValidationFailed
from .values import CENT, ZERO, quantize_marks

OBJECTIVE_RULES: dict[str, frozenset[str]] = {
    "single": frozenset({"exact"}),
    "multiple": frozenset({"exact", "partial_no_wrong"}),
}


def score_objective(
    kind: str,
    selected_ids: Iterable[int],
    correct_ids: Iterable[int],
    rule: str,
    max_marks: Decimal | int | float | str,
) -> Decimal:
    """Compute decimal marks for a finalized single or multiple-select item.

    Policy (FR11):
    - Blank responses always earn ``0.00``.
    - ``single`` (``exact``): full ``max_marks`` when the single selected option
      matches ``correct_ids``; otherwise ``0.00``.
    - ``multiple`` (``exact``): full ``max_marks`` when ``selected == correct``;
      otherwise ``0.00``.
    - ``multiple`` (``partial_no_wrong``): ``0.00`` if any wrong option is
      selected; otherwise ``max_marks * |selected & correct| / |correct|``,
      rounded half-up to two decimal places.
    """
    if kind not in OBJECTIVE_RULES:
        raise ValueError(f"Unsupported objective question kind: {kind!r}")
    if rule not in OBJECTIVE_RULES[kind]:
        raise ValueError(f"Invalid marking rule {rule!r} for kind {kind!r}")

    cap = quantize_marks(max_marks)
    if cap <= ZERO:
        raise ValueError(f"max_marks must be positive, got {cap}")

    selected = frozenset(int(x) for x in selected_ids)
    correct = frozenset(int(x) for x in correct_ids)

    if not selected or not correct:
        return ZERO

    if kind == "single":
        return cap if len(selected) == 1 and selected == correct else ZERO

    if rule == "exact":
        return cap if selected == correct else ZERO

    # partial_no_wrong
    if selected - correct:
        return ZERO
    ratio = Decimal(len(selected & correct)) / Decimal(len(correct))
    return (cap * ratio).quantize(CENT, rounding=ROUND_HALF_UP)


def score_finalized_item(
    kind: str,
    rule: str,
    max_marks: Decimal | int | float | str,
    *,
    selected_ids: Iterable[int] = (),
    correct_ids: Iterable[int] = (),
    written_answer: str = "",
) -> Decimal | None:
    """Determine the initial award written at attempt finalization.

    Returns ``Decimal("0.00")`` for blank responses (including blank written
    answers), the auto-scored Decimal for objective items, or ``None`` for a
    nonblank written response awaiting manual grading.
    """
    if kind == "written":
        if rule != "manual":
            raise ValueError(f"Written items require marking rule 'manual', got {rule!r}")
        cap = quantize_marks(max_marks)
        if cap <= ZERO:
            raise ValueError(f"max_marks must be positive, got {cap}")
        return ZERO if not written_answer.strip() else None

    return score_objective(kind, selected_ids, correct_ids, rule, max_marks)


def validate_manual_award(
    awarded_marks: Decimal | int | float | str,
    max_marks: Decimal,
) -> Decimal:
    """Validate and normalize an examiner's manual mark award in [0, max_marks]."""
    if isinstance(awarded_marks, bool):
        raise ValidationFailed(
            [Issue("invalid_marks", "Awarded marks must be a number.", field="awarded_marks")]
        )
    try:
        dec = awarded_marks if isinstance(awarded_marks, Decimal) else Decimal(str(awarded_marks))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationFailed(
            [Issue("invalid_marks", "Awarded marks must be a valid decimal number.", field="awarded_marks")]
        ) from exc

    if not dec.is_finite():
        raise ValidationFailed(
            [Issue("invalid_marks", "Awarded marks must be finite.", field="awarded_marks")]
        )

    exponent = dec.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValidationFailed(
            [Issue("too_many_decimals", "Awarded marks may have at most 2 decimal places.", field="awarded_marks")]
        )

    normalized = dec.quantize(CENT, rounding=ROUND_HALF_UP)
    cap = quantize_marks(max_marks)
    if normalized < ZERO or normalized > cap:
        raise ValidationFailed(
            [
                Issue(
                    "award_out_of_bounds",
                    f"Awarded marks must be between 0.00 and {cap:.2f}.",
                    field="awarded_marks",
                )
            ]
        )
    return normalized


def compute_attempt_total(awards: Iterable[Decimal | None]) -> Decimal | None:
    """Sum item awards once every item is graded; return None if any award is pending."""
    award_list = list(awards)
    if not award_list or any(award is None for award in award_list):
        return None
    total = sum((quantize_marks(a) for a in award_list if a is not None), ZERO)
    return total.quantize(CENT, rounding=ROUND_HALF_UP)
