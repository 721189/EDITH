"""
Elexon BMRS API client for FUELHH and WINDFOR datasets.

Handles data retrieval, pagination, and basic error handling.
"""

import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


class ElexonAPIClient:
    """Client for Elexon BMRS API datasets."""
    
    def __init__(self, client: httpx.Client = None):
        self._client = client or httpx.Client(timeout=30.0)
    
    def _request(self, method: str, endpoint: str, params: Dict = None) -> Any:
        """Make an API request with error handling."""
        url = f"{BASE_URL}{endpoint}"
        try:
            response = self._client.request(method, url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            logger.error(f"Timeout requesting {url}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} from {url}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request error for {url}: {e}")
            raise
    
    def get_fuelhh(self, start_time: str, end_time: str) -> List[Dict]:
        """Retrieve FUELHH data for a given time range.
        
        Args:
            start_time: ISO 8601 formatted start time (UTC)
            end_time: ISO 8601 formatted end time (UTC)
        
        Returns:
            List of FUELHH records
        """
        # Dataset streams filter by publication timestamp, not delivery startTime.
        params = {
            "publishDateTimeFrom": start_time,
            "publishDateTimeTo": end_time,
        }
        data = self._request("GET", "/datasets/FUELHH/stream", params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        return []
    
    def get_windfor(self, start_time: str, end_time: str) -> List[Dict]:
        """Retrieve WINDFOR data for a given time range.
        
        Args:
            start_time: ISO 8601 formatted start time (UTC)
            end_time: ISO 8601 formatted end time (UTC)
        
        Returns:
            List of WINDFOR records
        """
        # WINDFOR history is queried by publication time to retain revisions.
        params = {
            "publishDateTimeFrom": start_time,
            "publishDateTimeTo": end_time,
        }
        data = self._request("GET", "/datasets/WINDFOR/stream", params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        return []