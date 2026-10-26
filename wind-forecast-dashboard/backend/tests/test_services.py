from datetime import datetime, timezone
from src.services.normalization import parse_utc_timestamp, normalize_generation, is_valid_fuel_type, validate_record
from src.services.forecast_selection import ForecastSelector
from src.services.matching import ForecastActualMatcher
from src.services.metrics import calculate_metrics

UTC = timezone.utc


def forecast(delivery, published, generation):
    return {"startTime_utc": datetime.fromisoformat(delivery).replace(tzinfo=UTC),
            "publishTime_utc": datetime.fromisoformat(published).replace(tzinfo=UTC),
            "generation_mw": generation}


def test_parse_utc_timestamp_accepts_z_and_offsets():
    assert parse_utc_timestamp("2026-01-01T00:00:00Z") == datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_utc_timestamp("2026-01-01T01:00:00+01:00") == datetime(2026, 1, 1, tzinfo=UTC)


def test_normalize_generation_preserves_zero_and_rejects_invalid_values():
    assert normalize_generation(0) == 0.0
    assert normalize_generation("12.5") == 12.5
    assert normalize_generation(True) is None
    assert normalize_generation("invalid") is None
    assert normalize_generation(float("nan")) is None


def test_wind_filter_is_exact_and_case_insensitive():
    assert is_valid_fuel_type("wind")
    assert not is_valid_fuel_type("GAS")


def test_validate_record_does_not_drop_zero_generation():
    value = validate_record({"startTime":"2026-01-01T00:00:00Z","generation":0,"fuelType":"WIND"},"FUELHH")
    assert value["generation_mw"] == 0
    assert value["is_wind"] is True


def test_selector_chooses_latest_publication_at_or_before_cutoff():
    delivery = "2026-01-02T00:00:00"
    rows = [forecast(delivery,"2026-01-01T08:00:00",100),
            forecast(delivery,"2026-01-01T11:59:00",120),
            forecast(delivery,"2026-01-01T12:01:00",999)]
    result = ForecastSelector(datetime(2026,1,1,12,tzinfo=UTC)).select_forecast(rows)
    assert result.eligible
    assert result.forecast_generation_mw == 120
    assert result.publish_time_utc == datetime(2026,1,1,11,59,tzinfo=UTC)


def test_selector_excludes_publications_after_cutoff():
    row = forecast("2026-01-02T00:00:00","2026-01-01T12:01:00",120)
    result = ForecastSelector(datetime(2026,1,1,12,tzinfo=UTC)).select_forecast([row])
    assert not result.eligible
    assert result.forecast_generation_mw is None


def test_matcher_matches_exact_interval_and_preserves_missingness():
    t1 = datetime(2026,1,1,tzinfo=UTC)
    t2 = datetime(2026,1,1,0,30,tzinfo=UTC)
    forecasts = [{"startTime_utc":t1,"publishTime_utc":t1,"forecast_generation_mw":110}]
    actuals = [{"startTime_utc":t1,"generation_mw":100,"fuelType":"WIND"}]
    result = ForecastActualMatcher().match(forecasts,actuals,expected_intervals=[t1,t2])
    assert result.matched_count == 1
    assert result.matched_pairs[0].signed_error_mw == 10
    assert result.matched_pairs[1].match_status == "missing"
    assert result.matched_pairs[1].actual_generation_mw is None


def test_metrics_use_forecast_minus_actual_bias_and_expected_coverage():
    t1 = datetime(2026,1,1,tzinfo=UTC)
    t2 = datetime(2026,1,1,0,30,tzinfo=UTC)
    result = ForecastActualMatcher().match(
        [{"startTime_utc":t1,"publishTime_utc":t1,"forecast_generation_mw":110}],
        [{"startTime_utc":t1,"generation_mw":100,"fuelType":"WIND"}],
        expected_intervals=[t1,t2])
    metrics = calculate_metrics(result.matched_pairs,total_expected_intervals=2)
    assert metrics.mae == 10
    assert metrics.rmse == 10
    assert metrics.bias == 10
    assert metrics.coverage_percentage == 50
    assert metrics.mape == 10


def test_metrics_return_none_when_no_matches():
    metrics = calculate_metrics([])
    assert metrics.mae is None and metrics.rmse is None and metrics.bias is None
    assert metrics.coverage_percentage == 0
