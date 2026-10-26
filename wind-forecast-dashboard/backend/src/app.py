"""
Main FastAPI application for the Wind Forecast Intelligence dashboard.

Exposes API endpoints for data retrieval, forecast selection, matching, and metrics.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
import uvicorn

from api.elexon_client import ElexonAPIClient

app = FastAPI(
    title="Wind Forecast Intelligence API",
    description="Historical wind forecast accuracy analysis for UK day-ahead procurement",
    version="1.0.0"
)

client = ElexonAPIClient()


@app.get("/api/health", response_model=dict)
async def health_check():
    """Check backend health status."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


@app.get("/api/overview", response_model=dict)
async def get_overview(
    decision_date_from: str = Query(None, description="Start date for decision dates (YYYY-MM-DD)"),
    decision_date_to: str = Query(None, description="End date for decision dates (YYYY-MM-DD)"),
    cutoff_time: str = Query("12:00", description="Decision cutoff time (HH:MM UTC)"),
):
    """Get overview metrics and coverage for an evaluation period."""
    from collections import defaultdict
    from services.normalization import parse_utc_timestamp, normalize_generation, is_valid_fuel_type, validate_record
    from services.forecast_selection import ForecastSelector, ForecastSelectionResult
    from services.metrics import calculate_metrics, MetricsResult
    from services.matching import ForecastActualMatcher, MatchedPair, MatchingResult

    # Parse decision date range
    try:
        from_date = datetime.fromisoformat(decision_date_from).date() if decision_date_from else datetime(2026, 1, 1).date()
        to_date = datetime.fromisoformat(decision_date_to).date() if decision_date_to else datetime(2026, 1, 31).date()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Set decision cutoff time
    cutoff_hour, cutoff_minute = map(int, cutoff_time.split(":"))

    # Fetch FUELHH data for wind actuals
    fuelhh_start = "2025-12-20T00:00:00Z"
    fuelhh_end = "2026-02-05T00:00:00Z"

    try:
        fuelhh_records = client.get_fuelhh(fuelhh_start, fuelhh_end)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching FUELHH data: {str(e)}")

    # Filter to wind only and normalize
    wind_actuals = []
    for record in fuelhh_records:
        validated = validate_record(record, "FUELHH")
        if validated.get("is_wind") and validated.get("startTime_utc") and validated.get("generation_mw") is not None:
            wind_actuals.append(validated)

    # Fetch WINDFOR data
    windfor_start = "2025-12-20T00:00:00Z"
    windfor_end = "2026-02-05T00:00:00Z"

    try:
        windfor_records = client.get_windfor(windfor_start, windfor_end)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching WINDFOR data: {str(e)}")

    # Normalize WINDFOR records
    normalized_forecasts = []
    for record in windfor_records:
        from services.normalization import parse_utc_timestamp
        validated = {
            "startTime_utc": parse_utc_timestamp(record.get("startTime")),
            "publishTime_utc": parse_utc_timestamp(record.get("publishTime")),
            "generation_mw": normalize_generation(record.get("generation")),
            "source_record_id": record.get("sourceRecordId"),
        }
        if validated["startTime_utc"] and validated.get("generation_mw") is not None:
            normalized_forecasts.append(validated)

    # Apply decision-time forecast selection for each interval
    forecasts_by_interval: Dict[str, List[Dict]] = defaultdict(list)
    for f in normalized_forecasts:
        interval_key = f["startTime_utc"].isoformat() if f["startTime_utc"] else "unknown"
        forecasts_by_interval[interval_key].append(f)

    # Select the most recent eligible forecast for each interval
    decision_cutoff = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)  # Default example
    selector = ForecastSelector(decision_cutoff)

    selected_forecasts = []
    for interval_key, forecasts in forecasts_by_interval.items():
        result = selector.select_forecast(forecasts)
        if result.eligible:
            selected_forecasts.append({
                "startTime_utc": result.delivery_start_utc,
                "publishTime_utc": result.publish_time_utc,
                "forecast_generation_mw": result.forecast_generation_mw,
                "source_record_id": result.source_record_id,
            })

    # Match forecasts with actuals
    matcher = ForecastActualMatcher(decision_cutoff)
    matching_result = matcher.match(selected_forecasts, wind_actuals)

    # Calculate metrics
    metrics_result = calculate_metrics(matching_result.matched_pairs)

    # Combine results
    overview = {
        "decision_period": {
            "from": decision_date_from or "2026-01-01",
            "to": decision_date_to or "2026-01-31",
        },
        "cutoff_time": cutoff_time,
        "coverage": {
            "total_expected_intervals": metrics_result.total_expected_intervals,
            "valid_matched_intervals": metrics_result.valid_matched_count,
            "coverage_percentage": round(metrics_result.coverage_percentage, 2) if metrics_result.coverage_percentage else None,
            "intervals_with_eligible_forecast": metrics_result.intervals_with_eligible_forecast,
            "intervals_with_actual": metrics_result.intervals_with_actual,
        },
        "metrics": {
            "mae_mw": round(metrics_result.mae, 2) if metrics_result.mae else None,
            "rmse_mw": round(metrics_result.rmse, 2) if metrics_result.rmse else None,
            "bias_mw": round(metrics_result.bias, 2) if metrics_result.bias else None,
            "mape_percentage": round(metrics_result.mape, 2) if metrics_result.mape else None,
            "sample_count": metrics_result.valid_matched_count,
        },
        "exclusions": metrics_result.exclusion_reasons,
        "descriptions": metrics_result.sample_descriptions,
    }

    return overview

@app.get("/api/forecast-history/{delivery_date}", response_model=dict)
async def get_forecast_history(
    delivery_date: str,
    decision_cutoff: str = Query(None, description="Decision cutoff datetime (ISO 8601)"),
):
    """Get available forecast publications and selected forecast for a delivery date."""
    from services.forecast_selection import ForecastSelector
    from datetime import datetime
    from services.normalization import parse_utc_timestamp, normalize_generation, is_valid_fuel_type, validate_record

    # Parse delivery date
    try:
        dt = datetime.fromisoformat(delivery_date).date()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Set decision cutoff if provided
    if decision_cutoff:
        cutoff_dt = datetime.fromisoformat(decision_cutoff).astimezone(timezone.utc) if \
            datetime.fromisoformat(decision_cutoff).tzinfo else \
            datetime.fromisoformat(decision_cutoff).replace(tzinfo=timezone.utc)
    else:
        # Default: 12:00 UTC on the decision date
        cutoff_dt = datetime(dt.year, dt.month, dt.day, 12, 0, 0, tzinfo=timezone.utc)

    selector = ForecastSelector(cutoff_dt)

    # Fetch wind forecasts around this delivery date
    next_day = dt + __import__('datetime').timedelta(days=1)
    windfor_start = dt.strftime("%Y-%m-%d") + "T00:00:00Z"
    windfor_end = next_day.strftime("%Y-%m-%d") + "T00:00:00Z"

    try:
        windfor_records = client.get_windfor(windfor_start, windfor_end)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching WINDFOR data: {str(e)}")

    # Normalize
    from services.normalization import parse_utc_timestamp
    normalized = []
    for record in windfor_records:
        v = {
            "startTime_utc": parse_utc_timestamp(record.get("startTime")),
            "publishTime_utc": parse_utc_timestamp(record.get("publishTime")),
            "generation_mw": normalize_generation(record.get("generation")),
            "source_record_id": record.get("sourceRecordId"),
        }
        if v["startTime_utc"] and v["generation_mw"] is not None:
            normalized.append(v)

    # Select eligible forecast
    result = selector.select_for_interval(normalized)

    # Find actual generation for this delivery date
    from services.normalization import parse_utc_timestamp, normalize_generation, is_valid_fuel_type
    fuelhh_start = delivery_date + "T00:00:00Z"
    fuelhh_end = next_day.strftime("%Y-%m-%d") + "T00:00:00Z"

    try:
        fuelhh_records = client.get_fuelhh(fuelhh_start, fuelhh_end)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching FUELHH data: {str(e)}")

    wind_actual = None
    for record in fuelhh_records:
        v = {
            "startTime_utc": parse_utc_timestamp(record.get("startTime")),
            "generation_mw": normalize_generation(record.get("generation")),
            "fuelType": record.get("fuelType"),
        }
        if v.get("fuelType") and is_valid_fuel_type(v["fuelType"]) and v.get("generation_mw") is not None:
            wind_actual = v
            break

    return {
        "delivery_date": delivery_date,
        "decision_cutoff": decision_cutoff or f"{delivery_date}T12:00:00Z",
        "eligible": result.eligible if result else False,
        "selected_forecast": {
            "publish_time": result.publish_time_utc.isoformat() if result and result.publish_time_utc else None,
            "forecast_generation_mw": result.forecast_generation_mw if result else None,
            "reason": result.reason if result else "No forecast data available",
        } if result else None,
        "actual_generation": {
            "start_time": wind_actual["startTime_utc"].isoformat() if wind_actual and wind_actual["startTime_utc"] else None,
            "generation_mw": wind_actual["generation_mw"] if wind_actual else None,
        } if wind_actual else None,
        "all_forecasts_for_interval": [
            {
                "publish_time": f["publishTime_utc"].isoformat() if f.get("publishTime_utc") else None,
                "forecast_generation_mw": f["generation_mw"],
            } for f in normalized
        ] if normalized else [],
    }