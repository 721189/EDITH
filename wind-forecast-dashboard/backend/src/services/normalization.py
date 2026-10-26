"""Normalization helpers for Elexon FUELHH and WINDFOR records."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Mapping

logger = logging.getLogger(__name__)


def parse_utc_timestamp(value: Any) -> datetime | None:
    """Parse ISO-8601 timestamps; naive timestamps are interpreted as UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text)
        except ValueError:
            logger.warning("Could not parse timestamp %r", value)
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_generation(value: Any) -> float | None:
    """Return a finite numeric MW value; preserve zero and reject booleans."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        logger.warning("Could not convert generation to float: %r", value)
        return None
    return result if math.isfinite(result) else None


def is_valid_fuel_type(fuel_type: Any) -> bool:
    """Only the national WIND fuel-type records are used for actual generation."""
    return fuel_type is not None and str(fuel_type).strip().upper() == "WIND"


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def validate_record(record: Mapping[str, Any], dataset: str) -> dict[str, Any]:
    """Normalize the fields required from a FUELHH or WINDFOR record."""
    if not isinstance(record, Mapping):
        raise TypeError("Elexon record must be a mapping")
    dataset = dataset.upper()
    if dataset not in {"FUELHH", "WINDFOR"}:
        raise ValueError("dataset must be FUELHH or WINDFOR")

    normalized: dict[str, Any] = {
        "dataset": dataset,
        "source_record_id": _first_present(record, "sourceRecordId", "source_record_id"),
        "startTime_utc": parse_utc_timestamp(_first_present(record, "startTime", "StartTime", "startTime_utc")),
        "generation_mw": normalize_generation(
            _first_present(record, "generation", "Generation", "generation_mw")
        ),
    }
    if dataset == "WINDFOR":
        normalized["publishTime_utc"] = parse_utc_timestamp(
            _first_present(record, "publishTime", "PublishTime", "publishTime_utc")
        )
    else:
        fuel_type = _first_present(record, "fuelType", "FuelType", "fuel_type")
        normalized["fuelType"] = fuel_type
        normalized["is_wind"] = is_valid_fuel_type(fuel_type)
    return normalized


def aggregate_actuals_hourly(actuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate two complete FUELHH half-hour readings into hourly average MW.

    An hour is emitted only when both its :00 and :30 UTC readings exist and are
    valid. Missing half-hours are not imputed or averaged away.
    """
    grouped: dict[datetime, dict[int, float]] = {}
    for row in actuals:
        start = parse_utc_timestamp(row.get("startTime_utc", row.get("startTime")))
        value = normalize_generation(row.get("generation_mw", row.get("generation")))
        if start is None or value is None:
            continue
        hour = start.replace(minute=0, second=0, microsecond=0)
        minute = start.minute
        if minute not in (0, 30):
            continue
        grouped.setdefault(hour, {})[minute] = value

    hourly: list[dict[str, Any]] = []
    for hour, readings in sorted(grouped.items()):
        if set(readings) != {0, 30}:
            continue
        hourly.append({
            "startTime_utc": hour,
            "generation_mw": (readings[0] + readings[30]) / 2.0,
            "fuelType": "WIND",
            "is_wind": True,
            "source_interval_minutes": 30,
            "aggregation": "mean of complete :00 and :30 FUELHH readings",
        })
    return hourly
