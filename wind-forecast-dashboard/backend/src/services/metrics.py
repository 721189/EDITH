"""Forecast accuracy metrics; missing observations never count as zero."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .matching import MatchedPair


@dataclass
class MetricsResult:
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    mape: float | None = None
    coverage_percentage: float = 0.0
    total_expected_intervals: int = 0
    intervals_with_eligible_forecast: int = 0
    intervals_with_actual: int = 0
    valid_matched_count: int = 0
    excluded_count: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    sample_descriptions: dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        return self.valid_matched_count > 0 and self.mae is not None


def calculate_metrics(
    pairs: list[MatchedPair],
    *,
    total_expected_intervals: int | None = None,
    intervals_with_eligible_forecast: int | None = None,
    intervals_with_actual: int | None = None,
) -> MetricsResult:
    """Calculate MAE, RMSE, forecast-minus-actual bias, MAPE, and coverage."""
    matched = [p for p in pairs if p.match_status == "matched"
               and p.signed_error_mw is not None and p.actual_generation_mw is not None]
    forecast_count = sum(p.forecast_generation_mw is not None for p in pairs)
    actual_count = sum(p.actual_generation_mw is not None for p in pairs)
    expected = total_expected_intervals if total_expected_intervals is not None else len(pairs)
    expected = max(0, int(expected))
    exclusions: dict[str, int] = {}
    for pair in pairs:
        if pair.match_status != "matched":
            key = pair.match_status
            exclusions[key] = exclusions.get(key, 0) + 1

    result = MetricsResult(
        total_expected_intervals=expected,
        intervals_with_eligible_forecast=forecast_count if intervals_with_eligible_forecast is None else intervals_with_eligible_forecast,
        intervals_with_actual=actual_count if intervals_with_actual is None else intervals_with_actual,
        valid_matched_count=len(matched),
        excluded_count=sum(1 for p in pairs if p.match_status != "matched"),
        exclusion_reasons=exclusions,
    )
    result.coverage_percentage = (len(matched) / expected * 100.0) if expected else 0.0
    if not matched:
        result.sample_descriptions = {
            "matched_count": 0,
            "forecast_only_count": sum(p.match_status == "forecast_only" for p in pairs),
            "actual_only_count": sum(p.match_status == "actual_only" for p in pairs),
            "missing_count": sum(p.match_status == "missing" for p in pairs),
            "mape_denominator_count": 0,
            "bias_description": "not available (no matched intervals)",
        }
        return result

    errors = [float(p.signed_error_mw) for p in matched]
    absolute_errors = [abs(error) for error in errors]
    actual_values = [float(p.actual_generation_mw) for p in matched]
    result.mae = sum(absolute_errors) / len(matched)
    result.rmse = (sum(error * error for error in errors) / len(matched)) ** 0.5
    result.bias = sum(errors) / len(matched)

    # MAPE excludes actual zeroes because division by zero is undefined.
    percentage_errors = [
        abs(float(p.signed_error_mw)) / abs(float(p.actual_generation_mw)) * 100.0
        for p in matched if p.actual_generation_mw not in (None, 0)
    ]
    result.mape = sum(percentage_errors) / len(percentage_errors) if percentage_errors else None
    mean_actual = sum(actual_values) / len(actual_values)
    result.sample_descriptions = {
        "matched_count": len(matched),
        "forecast_only_count": sum(p.match_status == "forecast_only" for p in pairs),
        "actual_only_count": sum(p.match_status == "actual_only" for p in pairs),
        "missing_count": sum(p.match_status == "missing" for p in pairs),
        "mean_actual_mw": round(mean_actual, 2),
        "mape_denominator_count": len(percentage_errors),
        "bias_description": (
            "positive (forecast overestimation)" if result.bias > 0 else
            "negative (forecast underestimation)" if result.bias < 0 else
            "zero mean signed error"
        ),
    }
    return result
