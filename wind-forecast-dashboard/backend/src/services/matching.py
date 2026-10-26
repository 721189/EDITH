"""
Forecast-actual matching service.

Matches selected forecasts with actual generation by delivery interval.
Handles duplicate detection, missing values, and conflict reporting.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from .normalization import parse_utc_timestamp, normalize_generation, is_valid_fuel_type


@dataclass
class MatchedPair:
    """A matched forecast-actual pair for a delivery interval."""
    delivery_start_utc: datetime
    forecast_generation_mw: float
    forecast_publish_time_utc: datetime
    actual_generation_mw: float
    signed_error_mw: float
    absolute_error_mw: float
    match_status: str  # "matched", "forecast_only", "actual_only"
    data_quality_flags: List[str] = None
    
    def __post_init__(self):
        if self.data_quality_flags is None:
            self.data_quality_flags = []


@dataclass
class MatchingResult:
    """Result of forecast-actual matching operation."""
    matched_pairs: List[MatchedPair]
    forecast_only: List[MatchedPair]  # forecasts without actuals
    actual_only: List[MatchedPair]  # actuals without forecasts
    total_intervals: int
    matched_count: int
    exclusions: Dict[str, int]  # counts of different exclusion reasons