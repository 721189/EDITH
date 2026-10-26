"""FastAPI API for the EDITH wind forecast intelligence case study."""
from __future__ import annotations
import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from src.api.elexon_client import ElexonAPIClient
from src.services.forecast_selection import ForecastSelector
from src.services.matching import ForecastActualMatcher
from src.services.metrics import calculate_metrics
from src.services.normalization import aggregate_actuals_hourly, parse_utc_timestamp, validate_record

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)
app = FastAPI(title="EDITH — Wind Forecast Intelligence", description="Decision-time-safe UK wind forecast accuracy using Elexon BMRS FUELHH and WINDFOR.", version="1.0.0")
client = ElexonAPIClient()
FIRST, LAST = date(2026, 1, 1), date(2026, 1, 31)


def parse_date(value: str | None, fallback: date) -> date:
    try:
        return date.fromisoformat(value) if value else fallback
    except ValueError as exc:
        raise HTTPException(400, "Dates must use YYYY-MM-DD.") from exc


def parse_cutoff(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, "cutoff_time must use HH:MM UTC.") from exc
    if parsed.tzinfo or parsed.second or parsed.microsecond:
        raise HTTPException(400, "cutoff_time must use HH:MM UTC.")
    return parsed


def fetch_data(start: datetime, end: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fmt = lambda dt: dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        raw_actuals = client.get_fuelhh(fmt(start), fmt(end))
        raw_forecasts = client.get_windfor(fmt(start), fmt(end))
    except Exception as exc:
        logger.exception("Elexon BMRS request failed")
        raise HTTPException(502, "Elexon BMRS data request failed; retry shortly.") from exc
    actuals, forecasts = [], []
    for raw in raw_actuals:
        try:
            row = validate_record(raw, "FUELHH")
        except (TypeError, ValueError):
            continue
        if row.get("is_wind") and row.get("startTime_utc") and row.get("generation_mw") is not None:
            actuals.append(row)
    for raw in raw_forecasts:
        try:
            row = validate_record(raw, "WINDFOR")
        except (TypeError, ValueError):
            continue
        if row.get("startTime_utc") and row.get("publishTime_utc") and row.get("generation_mw") is not None:
            forecasts.append(row)
    return actuals, forecasts


def evaluate(start_date: date, end_date: date, cutoff_time: time) -> dict[str, Any]:
    if start_date < FIRST or end_date > LAST:
        raise HTTPException(400, "This case study is restricted to January 1–31, 2026 delivery dates.")
    if start_date > end_date:
        raise HTTPException(400, "Start date must be on or before end date.")
    actuals, forecasts = fetch_data(
        datetime.combine(start_date - timedelta(days=2), time.min, timezone.utc),
        datetime.combine(end_date + timedelta(days=2), time.min, timezone.utc),
    )
    actuals = aggregate_actuals_hourly(actuals)
    actual_by_time = {}
    for row in actuals:
        actual_by_time.setdefault(row["startTime_utc"], row)
    forecasts_by_time: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in forecasts:
        forecasts_by_time[row["startTime_utc"]].append(row)

    expected, selected, cutoffs = [], [], {}
    cursor = datetime.combine(start_date, time.min, timezone.utc)
    stop = datetime.combine(end_date + timedelta(days=1), time.min, timezone.utc)
    while cursor < stop:
        expected.append(cursor)
        decision_cutoff = datetime.combine(cursor.date() - timedelta(days=1), cutoff_time, timezone.utc)
        cutoffs[cursor] = decision_cutoff
        result = ForecastSelector(decision_cutoff).select_forecast(forecasts_by_time.get(cursor, []))
        if result.eligible:
            selected.append({"startTime_utc": result.delivery_start_utc, "publishTime_utc": result.publish_time_utc,
                             "forecast_generation_mw": result.forecast_generation_mw, "source_record_id": result.source_record_id})
        cursor += timedelta(hours=1)

    matching = ForecastActualMatcher().match(selected, actuals, expected_intervals=expected)
    metrics = calculate_metrics(matching.matched_pairs, total_expected_intervals=len(expected),
                                intervals_with_eligible_forecast=len(selected),
                                intervals_with_actual=sum(t in actual_by_time for t in expected))
    series = [{
        "delivery_start": p.delivery_start_utc.isoformat(),
        "decision_cutoff": cutoffs[p.delivery_start_utc].isoformat(),
        "forecast_mw": p.forecast_generation_mw, "actual_mw": p.actual_generation_mw,
        "error_mw": p.signed_error_mw, "absolute_error_mw": p.absolute_error_mw,
        "status": p.match_status,
        "publish_time": p.forecast_publish_time_utc.isoformat() if p.forecast_publish_time_utc else None,
    } for p in matching.matched_pairs]
    return {
        "decision_period": {"from": start_date.isoformat(), "to": end_date.isoformat()},
        "cutoff_time_utc": cutoff_time.strftime("%H:%M"),
        "data_scope": {"source": "Elexon BMRS", "datasets": ["WINDFOR", "FUELHH"], "interval_minutes": 60, "actual_aggregation": "mean of complete half-hour FUELHH readings per hour"},
        "coverage": {"total_expected_intervals": metrics.total_expected_intervals,
                     "valid_matched_intervals": metrics.valid_matched_count,
                     "coverage_percentage": round(metrics.coverage_percentage, 2),
                     "intervals_with_eligible_forecast": metrics.intervals_with_eligible_forecast,
                     "intervals_with_actual": metrics.intervals_with_actual,
                     "excluded_intervals": metrics.excluded_count},
        "metrics": {"mae_mw": round(metrics.mae, 3) if metrics.mae is not None else None,
                    "rmse_mw": round(metrics.rmse, 3) if metrics.rmse is not None else None,
                    "bias_mw": round(metrics.bias, 3) if metrics.bias is not None else None,
                    "mape_percentage": round(metrics.mape, 3) if metrics.mape is not None else None,
                    "sample_count": metrics.valid_matched_count},
        "exclusions": metrics.exclusion_reasons, "descriptions": metrics.sample_descriptions, "series": series,
        "methodology": {"forecast_selection": "latest valid publication at or before the configured UTC cutoff on the preceding day, selected per delivery interval",
                        "error_sign": "forecast minus actual; positive bias means over-forecasting",
                        "missing_values": "missing observations remain missing and are never imputed as zero",
                        "mape": "mean absolute percentage error excludes matched intervals where actual generation is zero"}
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "edith-api", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/overview")
async def overview(decision_date_from: str | None = Query(None), decision_date_to: str | None = Query(None),
                   cutoff_time: str = Query("12:00", description="Previous-day UTC cutoff, HH:MM")):
    return evaluate(parse_date(decision_date_from, FIRST), parse_date(decision_date_to, LAST), parse_cutoff(cutoff_time))


@app.get("/api/forecast-history/{delivery_date}")
async def forecast_history(delivery_date: str, decision_cutoff: str | None = Query(None)):
    target = parse_date(delivery_date, FIRST)
    if target < FIRST or target > LAST:
        raise HTTPException(400, "delivery_date must be in January 2026.")
    cutoff = parse_utc_timestamp(decision_cutoff) if decision_cutoff else datetime.combine(target - timedelta(days=1), time(12), timezone.utc)
    if cutoff is None:
        raise HTTPException(400, "decision_cutoff must be a valid ISO-8601 timestamp.")
    start = datetime.combine(target, time.min, timezone.utc)
    end = start + timedelta(days=1)
    actuals, forecasts = fetch_data(start - timedelta(days=2), end + timedelta(days=1))
    actuals = aggregate_actuals_hourly(actuals)
    actual_by_time = {r["startTime_utc"]: r for r in actuals}
    grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for r in forecasts:
        if start <= r["startTime_utc"] < end:
            grouped[r["startTime_utc"]].append(r)
    intervals, cursor = [], start
    while cursor < end:
        history = sorted(grouped.get(cursor, []), key=lambda r: r["publishTime_utc"])
        result = ForecastSelector(cutoff).select_forecast(history)
        actual = actual_by_time.get(cursor)
        intervals.append({"delivery_start": cursor.isoformat(), "actual_mw": actual["generation_mw"] if actual else None,
                          "selected_forecast_mw": result.forecast_generation_mw if result.eligible else None,
                          "selected_publish_time": result.publish_time_utc.isoformat() if result.publish_time_utc else None,
                          "eligible": result.eligible, "reason": result.reason,
                          "publications": [{"publish_time": r["publishTime_utc"].isoformat(), "forecast_mw": r["generation_mw"],
                                            "eligible": r["publishTime_utc"] <= cutoff} for r in history]})
        cursor += timedelta(minutes=30)
    return {"delivery_date": target.isoformat(), "decision_cutoff": cutoff.isoformat(), "intervals": intervals,
            "methodology": "Each half-hour delivery interval is matched independently; post-cutoff publications are not eligible."}


# Vercel's FastAPI runtime can serve frontend assets from its CDN. Local/Docker use StaticFiles.
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if hasattr(app, "frontend"):
    # Vercel resolves this project-relative path at build time and serves assets via its CDN.
    app.frontend("/", directory="frontend/dist")
elif _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
