"""
Forecast accuracy metrics calculation service.

Calculates MAE, RMSE, bias, and coverage metrics from matched forecast-actual pairs.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from .matching import MatchedPair


@dataclass
class MetricsResult:
    """Result of metrics calculation."""
    mae: Optional[float] = None
    rmse: Optional[float] = None
    bias: Optional[float] = None
    mape: Optional[float] = None  # Optional normalized metric
    coverage_percentage: Optional[float] = None
    total_expected_intervals: int = 0
    intervals_with_eligible_forecast: int = 0
    intervals_with_actual: int = 0
    valid_matched_count: int = 0
    excluded_count: int = 0
    exclusion_reasons: Dict[str, int] = field(default_factory=dict)
    sample_descriptions: Dict[str, Any] = field(default_factory=dict)
    
    def is_valid(self) -> bool:
        """Check if metrics have valid values."""
        return self.valid_matched_count > 0 and self.mae is not None


def calculate_metrics(pairs: List[MatchedPair]) -> MetricsResult:
    """Calculate forecast accuracy metrics from matched pairs.
    
    Only pairs with match_status="matched" contribute to primary metrics.
    
    Args:
        pairs: List of MatchedPair objects (typically only "matched" status)
    
    Returns:
        MetricsResult with calculated values
    """
    # Filter to only matched pairs
    matched = [p for p in pairs if p.match_status == "matched"]
    
    result = MetricsResult(
        total_expected_intervals=len(matched) + len([p for p in pairs if p.match_status != "matched"]),
        valid_matched_count=len(matched),
        exclusion_reasons={}
    )
    
    if not matched:
        return result
    
    n = len(matched)
    
    # Calculate MAE
    absolute_errors = [p.absolute_error_mw for p in matched]
    result.mae = sum(absolute_errors) / n
    
    # Calculate RMSE
    squared_errors = [p.signed_error_mw ** 2 for p in matched]
    result.rmse = (sum(squared_errors) / n) ** 0.5
    
    # Calculate bias (mean signed error)
    result.bias = sum(p.signed_error_mw for p in matched) / n
    
    # Calculate MAPE (optional normalized metric)
    # Only if mean actual generation is positive and suitable
    actual_values = [p.actual_generation_mw for p in matched]
    mean_actual = sum(actual_values) / n if actual_values else 0
    
    if mean_actual > 0 and mean_actual is not None:
        result.mape = (result.mae / mean_actual) * 100
    
    # Coverage metrics
    # Count intervals with eligible forecasts and actual observations
    intervals_with_forecast = len(set(p.delivery_start_utc.isoformat() if p.delivery_start_utc else "" for p in pairs))
    intervals_with_actual = len(set(a.delivery_start_utc.isoformat() if hasattr(a, 'delivery_start_utc') and a.delivery_start_utc else "" for a in pairs))
    
    result.intervals_with_eligible_forecast = intervals_with_forecast
    result.intervals_with_actual = intervals_with_actual
    
    # Coverage = valid matched intervals / expected intervals
    if result.total_expected_intervals > 0:
        result.coverage_percentage = (result.valid_matched_count / result.total_expected_intervals) * 100
    
    # Sample descriptions for reporting
    result.sample_descriptions = {
        "matched_count": n,
        "forecast_only_count": len([p for p in pairs if p.match_status == "forecast_only"]),
        "actual_only_count": len([p for p in pairs if p.match_status == "actual_only"]),
        "mean_actual_mw": round(mean_actual, 2) if mean_actual else None,
        "bias_description": "positive (overestimation)" if result.bias and result.bias > 0 else 
                           "negative (underestimation)" if result.bias and result.bias < 0 else
                           "near zero (cancellation)"
    }
    
    return result