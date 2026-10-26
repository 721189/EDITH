"""
Forecast selection service.

Implements the decision-time forecast selection algorithm as specified in the PRD.

For each delivery interval t, selects the most recently published forecast 
available at or before the decision cutoff D_t.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .normalization import parse_utc_timestamp


@dataclass
class ForecastSelectionResult:
    """Result of forecast selection for a single delivery interval."""
    delivery_start_utc: Optional[datetime]
    publish_time_utc: Optional[datetime]
    forecast_generation_mw: Optional[float]
    eligible: bool
    reason: str = ""
    source_record_id: Optional[str] = None


class ForecastSelector:
    """Selects eligible forecasts based on decision-time cutoff rules."""
    
    def __init__(self, decision_cutoff: datetime):
        """Initialize with the decision cutoff timestamp.
        
        Args:
            decision_cutoff: The cutoff time for forecast eligibility.
                Forecasts published at or before this time are eligible.
        """
        self.decision_cutoff = decision_cutoff.astimezone(timezone.utc) if decision_cutoff.tzinfo else \
            decision_cutoff.replace(tzinfo=timezone.utc)
    
    def select_forecast(self, forecasts: List[Dict], 
                       decision_cutoff: datetime = None) -> ForecastSelectionResult:
        """Select the most recent eligible forecast for a delivery interval.
        
        Args:
            forecasts: List of forecast records for the same delivery interval,
                already normalized with publishTime_utc populated.
            decision_cutoff: Override the instance's decision cutoff.
        
        Returns:
            ForecastSelectionResult with the selected forecast or None if
            no eligible forecast exists.
        """
        cutoff = self.decision_cutoff if decision_cutoff is None else \
            parse_utc_timestamp(decision_cutoff).astimezone(timezone.utc) if decision_cutoff else self.decision_cutoff
        
        # Filter forecasts published at or before the cutoff
        eligible = []
        for f in forecasts:
            publish_time = f.get("publishTime_utc")
            if publish_time is None:
                continue
            if publish_time <= cutoff:
                eligible.append(f)
        
        if not eligible:
            return ForecastSelectionResult(
                delivery_start_utc=None,
                publish_time_utc=None,
                forecast_generation_mw=None,
                eligible=False,
                reason="No forecast published on or before decision cutoff"
            )
        
        # Select the most recently published forecast (max publishTime)
        selected = max(eligible, key=lambda f: f.get("publishTime_utc", datetime.min.replace(tzinfo=timezone.utc)))
        
        return ForecastSelectionResult(
            delivery_start_utc=selected.get("startTime_utc"),
            publish_time_utc=selected.get("publishTime_utc"),
            forecast_generation_mw=selected.get("generation_mw"),
            eligible=True,
            reason=f"Selected forecast published at {selected.get('publishTime_utc')}",
            source_record_id=selected.get("source_record_id")
        )
    
    def select_for_interval(self, interval_forecasts: List[Dict]) -> Optional[ForecastSelectionResult]:
        """Select forecast for a single delivery interval.
        
        This is the main entry point - given all forecasts for a delivery interval,
        select the most recent one published on or before the decision cutoff.
        
        Args:
            interval_forecasts: List of forecast records for one delivery interval.
                Each should have: startTime_utc, publishTime_utc, generation_mw
        
        Returns:
            ForecastSelectionResult or None if no data available
        """
        if not interval_forecasts:
            return None
        
        return self.select_forecast(interval_forecasts)