"""Match selected forecasts and actual generation by exact UTC delivery interval."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from .normalization import parse_utc_timestamp, normalize_generation, is_valid_fuel_type


@dataclass
class MatchedPair:
    delivery_start_utc: datetime
    forecast_generation_mw: float | None = None
    forecast_publish_time_utc: datetime | None = None
    actual_generation_mw: float | None = None
    signed_error_mw: float | None = None
    absolute_error_mw: float | None = None
    match_status: str = "missing"
    data_quality_flags: list[str] = field(default_factory=list)


@dataclass
class MatchingResult:
    matched_pairs: list[MatchedPair]
    forecast_only: list[MatchedPair]
    actual_only: list[MatchedPair]
    total_intervals: int
    matched_count: int
    exclusions: dict[str, int] = field(default_factory=dict)


class ForecastActualMatcher:
    """Match using startTime, never by row order or by date alone.

    The caller should pass only forecasts already selected by the decision-time
    cutoff. When expected_intervals is supplied, missing observations remain
    missing records instead of being silently filled with zero.
    """

    def __init__(self, decision_cutoff: datetime | None = None):
        self.decision_cutoff = parse_utc_timestamp(decision_cutoff) if decision_cutoff else None

    def match(
        self,
        forecasts: Iterable[dict[str, Any]],
        actuals: Iterable[dict[str, Any]],
        expected_intervals: Iterable[datetime] | None = None,
    ) -> MatchingResult:
        forecast_by_time: dict[datetime, dict[str, Any]] = {}
        actual_by_time: dict[datetime, dict[str, Any]] = {}

        for record in forecasts:
            start = parse_utc_timestamp(record.get("startTime_utc", record.get("delivery_start_utc", record.get("startTime"))))
            value = normalize_generation(record.get("forecast_generation_mw", record.get("generation_mw", record.get("generation"))))
            if start is None or value is None:
                continue
            published = parse_utc_timestamp(record.get("publishTime_utc", record.get("forecast_publish_time_utc", record.get("publishTime"))))
            normalized = dict(record)
            normalized.update({
                "startTime_utc": start,
                "publishTime_utc": published,
                "forecast_generation_mw": value,
            })
            # If duplicate selected rows exist, retain the row with the latest publication.
            previous = forecast_by_time.get(start)
            if previous is None or (published is not None and (
                previous.get("publishTime_utc") is None or published > previous["publishTime_utc"]
            )):
                forecast_by_time[start] = normalized

        for record in actuals:
            if record.get("is_wind") is False:
                continue
            fuel = record.get("fuelType", record.get("fuel_type"))
            if fuel is not None and not is_valid_fuel_type(fuel):
                continue
            start = parse_utc_timestamp(record.get("startTime_utc", record.get("startTime")))
            value = normalize_generation(record.get("generation_mw", record.get("generation")))
            if start is None or value is None:
                continue
            actual_by_time.setdefault(start, {**record, "startTime_utc": start, "generation_mw": value})

        expected = {
            parsed for value in (expected_intervals or [])
            if (parsed := parse_utc_timestamp(value)) is not None
        }
        keys = sorted(expected or (set(forecast_by_time) | set(actual_by_time)))
        pairs: list[MatchedPair] = []
        forecast_only: list[MatchedPair] = []
        actual_only: list[MatchedPair] = []
        exclusions: dict[str, int] = {}

        for start in keys:
            forecast = forecast_by_time.get(start)
            actual = actual_by_time.get(start)
            fv = forecast.get("forecast_generation_mw") if forecast else None
            av = actual.get("generation_mw") if actual else None
            published = forecast.get("publishTime_utc") if forecast else None
            if fv is not None and av is not None:
                error = fv - av
                pair = MatchedPair(start, fv, published, av, error, abs(error), "matched")
            elif fv is not None:
                pair = MatchedPair(start, fv, published, None, None, None, "forecast_only")
                forecast_only.append(pair)
                exclusions["actual_missing"] = exclusions.get("actual_missing", 0) + 1
            elif av is not None:
                pair = MatchedPair(start, None, None, av, None, None, "actual_only")
                actual_only.append(pair)
                exclusions["eligible_forecast_missing"] = exclusions.get("eligible_forecast_missing", 0) + 1
            else:
                pair = MatchedPair(start, None, None, None, None, None, "missing")
                exclusions["forecast_and_actual_missing"] = exclusions.get("forecast_and_actual_missing", 0) + 1
            pairs.append(pair)

        matched_count = sum(pair.match_status == "matched" for pair in pairs)
        return MatchingResult(
            matched_pairs=pairs,
            forecast_only=forecast_only,
            actual_only=actual_only,
            total_intervals=len(keys),
            matched_count=matched_count,
            exclusions=exclusions,
        )
