"""Airtable REST API client for querying PO records."""

import os
import logging
import time
from typing import Optional

import requests

from automations.config import AIRTABLE_API_URL, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


class AirtableClient:
    def __init__(self, pat: Optional[str] = None):
        self.pat = pat or os.environ["AIRTABLE_PAT"]
        self.base_url = f"{AIRTABLE_API_URL}/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
        self.headers = {
            "Authorization": f"Bearer {self.pat}",
            "Content-Type": "application/json",
        }

    def list_records(self, formula: str) -> list[dict]:
        """Fetch all records matching the filter formula, handling pagination and retries."""
        all_records = []
        params = {
            "filterByFormula": formula,
            "pageSize": 100,
            "cellFormat": "string",
            "timeZone": "America/Los_Angeles",
            "userLocale": "en-us",
        }
        offset = None

        while True:
            if offset:
                params["offset"] = offset

            resp = self._request_with_retry(params)
            resp.raise_for_status()
            data = resp.json()

            records = data.get("records", [])
            all_records.extend(records)
            logger.info(f"Fetched {len(records)} records (total: {len(all_records)})")

            offset = data.get("offset")
            if not offset:
                break

        return all_records

    def _request_with_retry(self, params: dict) -> requests.Response:
        """Make a GET request with retry on 5xx errors."""
        for attempt in range(1, MAX_RETRIES + 1):
            resp = requests.get(self.base_url, headers=self.headers, params=params)
            if resp.status_code < 500:
                return resp
            logger.warning(f"Airtable returned {resp.status_code}, retry {attempt}/{MAX_RETRIES}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
        return resp
