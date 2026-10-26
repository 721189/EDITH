"""Select the latest forecast publication available at a decision cutoff."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .normalization import parse_utc_timestamp, normalize_generation


@dataclass(frozen=True)
class ForecastSelectionResult:
    delivery_start_utc: datetime | None
    publish_time_utc: datetime | None
    forecast_generation_mw: float | None
    eligible: bool
    reason: str = ""
    source_record_id: str | None = None


class ForecastSelector:
    """Select one forecast for one delivery interval without future-data leakage."""

    def __init__(self, decision_cutoff: datetime):
        cutoff = parse_utc_timestamp(decision_cutoff)
        if cutoff is None:
            raise ValueError("decision_cutoff must be a valid datetime")
        self.decision_cutoff = cutoff

    def select_forecast(
        self,
        forecasts: Iterable[dict[str, Any]],
        decision_cutoff: datetime | None = None,
    ) -> ForecastSelectionResult:
        cutoff = parse_utc_timestamp(decision_cutoff) if decision_cutoff is not None else self.decision_cutoff
        if cutoff is None:
            cutoff = self.decision_cutoff

        eligible: list[tuple[datetime, dict[str, Any]]] = []
        for forecast in forecasts:
            published = parse_utc_timestamp(forecast.get("publishTime_utc", forecast.get("publishTime")))
            delivery = parse_utc_timestamp(forecast.get("startTime_utc", forecast.get("startTime")))
            generation = normalize_generation(forecast.get("generation_mw", forecast.get("generation")))
            if published is None or delivery is None or generation is None:
                continue
            if published <= cutoff:
                eligible.append((published, forecast))

        if not eligible:
            return ForecastSelectionResult(
                delivery_start_utc=None,
                publish_time_utc=None,
                forecast_generation_mw=None,
                eligible=False,
                reason="No valid forecast was published on or before the decision cutoff.",
            )

        # Stable tie-breaking makes duplicates deterministic.
        published, selected = max(
            eligible,
            key=lambda item: (
                item[0],
                str(item[1].get("source_record_id", item[1].get("sourceRecordId", ""))),
            ),
        )
        return ForecastSelectionResult(
            delivery_start_utc=parse_utc_timestamp(selected.get("startTime_utc", selected.get("startTime"))),
            publish_time_utc=published,
            forecast_generation_mw=normalize_generation(
                selected.get("generation_mw", selected.get("generation"))
            ),
            eligible=True,
            reason="Latest valid publication at or before the decision cutoff.",
            source_record_id=selected.get("source_record_id", selected.get("sourceRecordId")),
        )

    def select_for_interval(self, interval_forecasts: list[dict[str, Any]]) -> ForecastSelectionResult:
        """Compatibility alias. Input records must all describe one delivery interval."""
        return self.select_forecast(interval_forecasts)
