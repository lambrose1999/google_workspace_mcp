#!/usr/bin/env python3
"""Daily PO Status Email — main entry point.

Queries Airtable for active POs, enriches each status group with Gmail/field data,
builds an HTML email, and sends it via Gmail API.

Usage:
    cd /Users/lukasambrose/google_workspace_mcp
    uv run python automations/po_status_email.py
"""

import logging
import re
import sys
import traceback
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Ensure project root is on sys.path so `automations.*` imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automations.config import (
    AIRTABLE_FILTER_FORMULA,
    EMAIL_CC,
    EMAIL_TO,
    FIELD_CUSTOMER,
    FIELD_DELIVERY_DATE,
    FIELD_INVOICE_DUE_DATE,
    FIELD_PO_DUE_DATE,
    FIELD_PO_NUMBER,
    FIELD_SO_NUMBER,
    FIELD_STATUS,
    FIELD_TRACKING,
    LOG_DIR,
    STATUS_ORDER,
    TRACKING_URLS,
    URGENT_GMAIL_QUERY,
)
from automations.airtable_client import AirtableClient
from automations.email_template import build_email_html
from automations.gmail_client import GmailClient

logger = logging.getLogger("po_status_email")


def _setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"po_status_{date.today().isoformat()}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )


def _parse_tracking(raw: str) -> tuple[str, str]:
    """Parse 'Carrier - TrackingNumber' into (carrier, tracking_number).

    Returns lowercased carrier and stripped tracking number.
    Falls back to ('unknown', raw) if pattern doesn't match.
    """
    if not raw:
        return ("", "")
    match = re.match(r"^(.+?)\s*[-–]\s*(.+)$", raw.strip())
    if match:
        return (match.group(1).strip().lower(), match.group(2).strip())
    return ("unknown", raw.strip())


def _build_tracking_url(carrier: str, tracking: str) -> str | None:
    """Generate a tracking URL for known carriers."""
    for key, template in TRACKING_URLS.items():
        if key in carrier:
            return template.format(tracking=tracking)
    return None


def _parse_date(date_str: str) -> datetime | None:
    """Parse an M/D/YYYY date string. Returns None on failure."""
    if not date_str or date_str == "—":
        return None
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except (ValueError, AttributeError):
        return None


def _sort_by_date(records: list[dict], date_key: str) -> list[dict]:
    """Sort records by a date field (soonest first), empty dates at bottom."""
    def sort_key(rec):
        parsed = _parse_date(rec.get(date_key, ""))
        # Push unparseable/empty to bottom
        return (0, parsed) if parsed else (1, datetime.max)
    return sorted(records, key=sort_key)


def _scan_urgent_updates(gmail: GmailClient, po_numbers: set[str]) -> dict[str, str]:
    """Scan Gmail for urgent PO-related issues. Returns {po_number: html_snippet}."""
    urgent_map: dict[str, str] = {}
    if not po_numbers:
        return urgent_map

    try:
        results = gmail.search_messages(URGENT_GMAIL_QUERY, max_results=50)
    except Exception as e:
        logger.warning(f"Urgent Gmail scan failed: {e}")
        return urgent_map

    for msg in results:
        text = f"{msg.get('subject', '')} {msg.get('snippet', '')}"
        for po in po_numbers:
            if po in text:
                # Keep first (most recent) match per PO
                if po not in urgent_map:
                    subj = msg.get("subject", "")
                    snippet = msg.get("snippet", "")[:100]
                    urgent_map[po] = (
                        f"<strong>{subj}</strong><br>"
                        f"<span style='color:#6B7280;font-size:12px;'>{snippet}</span>"
                    )
    return urgent_map


def _enrich_records(
    groups: dict[str, list[dict]],
    gmail: GmailClient,
    urgent_map: dict[str, str],
) -> dict[str, list[dict]]:
    """Enrich each status group with relevant details."""
    enriched = {}

    for status in STATUS_ORDER:
        records = groups.get(status, [])
        enriched_records = []

        for rec in records:
            fields = rec.get("fields", {})
            entry = {
                "po_number": fields.get(FIELD_PO_NUMBER, "—"),
                "customer": fields.get(FIELD_CUSTOMER, "—"),
                "so_number": fields.get(FIELD_SO_NUMBER, "—"),
            }
            # Handle linked record arrays (Airtable returns arrays for linked fields)
            if isinstance(entry["customer"], list):
                entry["customer"] = ", ".join(str(v) for v in entry["customer"])

            if status == "Delivery Scheduled":
                entry["sort_date"] = fields.get(FIELD_PO_DUE_DATE, "")
                po = entry["po_number"]
                if po and po != "—":
                    try:
                        results = gmail.search_messages(f"PO {po}", max_results=1)
                        if results:
                            msg = results[0]
                            entry["enrichment"] = f"<strong>{msg['subject']}</strong><br><span style='color:#6B7280;font-size:12px;'>{msg['snippet'][:120]}</span>"
                        else:
                            entry["enrichment"] = "No emails found"
                    except Exception as e:
                        logger.warning(f"Gmail search failed for PO {po}: {e}")
                        entry["enrichment"] = "Search error"
                else:
                    entry["enrichment"] = "—"

            elif status == "En Route":
                raw_tracking = fields.get(FIELD_TRACKING, "")
                carrier, tracking_num = _parse_tracking(raw_tracking)
                entry["carrier"] = carrier.upper() if carrier else ""
                entry["tracking_url"] = _build_tracking_url(carrier, tracking_num) if tracking_num else None
                entry["eta"] = fields.get(FIELD_DELIVERY_DATE, "")
                entry["sort_date"] = entry["eta"]

            elif status == "Delivered":
                entry["enrichment"] = fields.get(FIELD_DELIVERY_DATE, "—")
                entry["sort_date"] = entry["enrichment"]

            elif status == "Invoiced":
                entry["enrichment"] = fields.get(FIELD_INVOICE_DUE_DATE, "—")
                entry["sort_date"] = entry["enrichment"]

            # Attach urgent update
            po = entry["po_number"]
            entry["urgent_update"] = urgent_map.get(po, "")

            enriched_records.append(entry)

        # Sort by date (soonest first)
        enriched_records = _sort_by_date(enriched_records, "sort_date")

        if enriched_records:
            enriched[status] = enriched_records

    return enriched


def main():
    _setup_logging()
    logger.info("Starting PO status email automation")

    # Load .env from project root (optional — in CI, env vars come from secrets)
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if load_dotenv is not None:
        load_dotenv(env_path)
    else:
        logger.info("python-dotenv not installed, skipping .env loading")

    # Initialize clients
    airtable = AirtableClient()
    gmail = GmailClient()

    # Fetch records
    logger.info("Querying Airtable for active POs")
    records = airtable.list_records(AIRTABLE_FILTER_FORMULA)
    logger.info(f"Found {len(records)} active POs")

    if not records:
        logger.info("No active POs — skipping email")
        return

    # Log field names from the first record for debugging
    first_fields = records[0].get("fields", {})
    logger.info(f"Available fields: {list(first_fields.keys())}")
    logger.info(f"First record sample: { {k: repr(v)[:80] for k, v in first_fields.items()} }")

    # Group by status
    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        status = rec.get("fields", {}).get(FIELD_STATUS)
        if status:
            groups[status].append(rec)

    # Scan Gmail for urgent PO updates
    all_po_numbers = set()
    for rec in records:
        po = rec.get("fields", {}).get(FIELD_PO_NUMBER, "")
        if po:
            all_po_numbers.add(po)
    logger.info(f"Scanning Gmail for urgent updates across {len(all_po_numbers)} POs")
    urgent_map = _scan_urgent_updates(gmail, all_po_numbers)
    if urgent_map:
        logger.info(f"Found urgent updates for {len(urgent_map)} POs: {list(urgent_map.keys())}")

    # Enrich
    enriched = _enrich_records(groups, gmail, urgent_map)

    # Build and send
    today_str = date.today().strftime("%B %d, %Y")
    html = build_email_html(enriched, today_str, len(records))

    subject = f"PO Status Report — {today_str}"
    logger.info(f"Sending email to {EMAIL_TO}, cc {EMAIL_CC}")
    msg_id = gmail.send_html_email(EMAIL_TO, subject, html, cc=EMAIL_CC)
    logger.info(f"Email sent successfully: {msg_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
