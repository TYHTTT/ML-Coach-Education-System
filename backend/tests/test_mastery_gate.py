from __future__ import annotations

import pytest

from app.learning.gate import MasteryGateInput, evaluate_mastery_gate


def passing_state(**overrides: object) -> MasteryGateInput:
    values: dict[str, object] = {
        "mastery": 0.85,
        "valid_attempt_count": 4,
        "checkpoint_count": 1,
        "latest_checkpoint_score": 88,
        "required_dimensions": frozenset(
            {"concept", "mathematics", "mechanism", "engineering"}
        ),
        "checkpoint_dimensions": frozenset(
            {"concept", "mathematics", "mechanism"}
        ),
        "unresolved_critical_misconception_count": 0,
    }
    values.update(overrides)
    return MasteryGateInput(**values)  # type: ignore[arg-type]


def test_all_six_conditions_pass() -> None:
    result = evaluate_mastery_gate(passing_state())

    assert result.passed
    assert result.next_action == "continue_to_next_topic"
    dumped = result.requirements.model_dump()
    assert len(dumped) == 6
    assert all(requirement["passed"] for requirement in dumped.values())


@pytest.mark.parametrize(
    ("override", "requirement", "expected_action"),
    [
        ({"mastery": 0.79}, "mastery_threshold", "practice"),
        ({"valid_attempt_count": 2}, "valid_attempts", "practice"),
        (
            {"checkpoint_count": 0, "latest_checkpoint_score": None},
            "checkpoint_completed",
            "take_checkpoint",
        ),
        ({"latest_checkpoint_score": 79}, "checkpoint_score", "remediate"),
        (
            {"checkpoint_dimensions": frozenset({"concept", "mathematics"})},
            "dimension_coverage",
            "practice",
        ),
        (
            {"unresolved_critical_misconception_count": 1},
            "critical_misconceptions",
            "remediate",
        ),
    ],
)
def test_each_gate_requirement_is_independently_mandatory(
    override: dict[str, object],
    requirement: str,
    expected_action: str,
) -> None:
    result = evaluate_mastery_gate(passing_state(**override))

    assert not result.passed
    assert not getattr(result.requirements, requirement).passed
    assert result.next_action == expected_action


def test_only_required_dimensions_count_toward_coverage() -> None:
    state = passing_state(
        required_dimensions=frozenset({"concept", "mathematics", "mechanism"}),
        checkpoint_dimensions=frozenset(
            {"concept", "irrelevant_one", "irrelevant_two", "irrelevant_three"}
        ),
    )

    result = evaluate_mastery_gate(state)
    assert not result.requirements.dimension_coverage.passed
    assert result.requirements.dimension_coverage.current == 1
    assert result.requirements.dimension_coverage.details == ["concept"]
