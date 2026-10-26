"""
Elexon data normalization utilities.

Handles timestamp parsing, numeric value validation, and data normalization
for FUELHH and WINDFOR datasets.
"""

import re
from datetime import datetime, timezone
from typing import Any, Optional, Dict, List


def parse_utc_timestamp(value: Any) -> Optional[datetime]:
    """Parse a UTC timestamp string into a datetime object.
    
    Handles ISO 8601 formats like '2026-01-15T13:00:00Z'.
    Returns None if parsing fails.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    
    value_str = str(value).strip()
    # Try common ISO 8601 formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S+00:00",
        "%Y-%m-%dT%H:%M:%S.%f+00:00",
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(value_str, fmt)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    
    logger.warning(f"Could not parse timestamp: {value}")
    return None


def normalize_generation(value: Any) -> Optional[float]:
    """Normalize a generation value to float.
    
    Returns None if value is missing or non-numeric.
    Preserves zero and negative values as valid observations.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, bool):
            return None
        return float(value)
    
    try:
        result = float(value)
        return result
    except (ValueError, TypeError):
        logger.warning(f"Could not convert generation to float: {value}")
        return None


def is_valid_fuel_type(fuel_type: Any) -> bool:
    """Check if fuel type indicates wind generation."""
    if fuel_type is None:
        return False
    return str(fuel_type).strip().upper() == "WIND"


def validate_record(record: Dict, dataset: str) -> Dict[str, Any]:
    """Validate and extract core fields from a dataset record.
    
    Args:
        record: Raw API record
        dataset: Either 'FUELHH' or 'WINDFOR'
    
    Returns:
        Dict with normalized fields or raises validation error
    """
    result = {
        "dataset": dataset,
        "source_record_id": record.get("sourceRecordId") 
            if hasattr(record, 'get') else record.get("sourceRecordId"),
    }
    
    # Parse startTime (delivery interval)
    start_time = record.get("startTime") or record.get("StartTime")
    result["startTime_utc"] = parse_utc_timestamp(start_time)
    
    # Parse publishTime (for WINDFOR only)
    if dataset == "WINDFOR":
        publish_time = record.get("publishTime") or record.get("PublishTime")
        result["publishTime_utc"] = parse_utc_timestamp(publish_time)
    
    # Parse generation
    generation = record.get("generation") or record.get("Generation")
    result["generation_mw"] = normalize_generation(generation)
    
    # Parse fuelType (FUELHH only)
    if dataset == "FUELHH":
        fuel_type = record.get("fuelType") or record.get("FuelType")
        result["fuelType"] = fuel_type
        result["is_wind"] = is_valid_fuel_type(fuel_type)
    
    return result