"""Configuration constants for PO status email automation."""

import os
from pathlib import Path

# Airtable
AIRTABLE_BASE_ID = "appYeoskeAm0ostOq"
AIRTABLE_TABLE_ID = "tblQV5OnC8X6IeOdA"
AIRTABLE_API_URL = "https://api.airtable.com/v0"
AIRTABLE_FILTER_FORMULA = (
    'OR({Status}="Delivery Scheduled",{Status}="En Route",'
    '{Status}="Delivered",{Status}="Invoiced")'
)

# Status grouping order
STATUS_ORDER = ["Delivery Scheduled", "En Route", "Delivered", "Invoiced"]

# Airtable field names
FIELD_PO_NUMBER = "PO #"
FIELD_CUSTOMER = "Customer Name"
FIELD_ITEM = "Item Name"
FIELD_SO_NUMBER = "Sales Order"
FIELD_STATUS = "Status"
FIELD_TRACKING = "Tracking / Pro Number"
FIELD_DELIVERY_DATE = "Delivery Date"
FIELD_INVOICE_DUE_DATE = "Invoice Due Date"
FIELD_PO_DUE_DATE = "PO Due Date"

# Urgent Gmail scan
URGENT_GMAIL_QUERY = (
    '(delay OR "missed pickup" OR reschedule OR appointment '
    'OR "unable to deliver" OR "failed pickup" OR hold) newer_than:7d'
)
URGENT_LOOKBACK_DAYS = 7

# Email
EMAIL_TO = "lukas@surgesupplyco.com"
EMAIL_CC = "carson@surgesupplyco.com"
EMAIL_FROM = "lukasambrose@gmail.com"

# Credentials
CREDENTIALS_PATH = Path.home() / ".google_workspace_mcp" / "credentials" / "lukas@surgesupplyco.com.json"

# Logging
LOG_DIR = Path(__file__).parent / "logs"

# Carrier tracking URL templates
TRACKING_URLS = {
    "ups": "https://www.ups.com/track?tracknum={tracking}",
    "fedex": "https://www.fedex.com/fedextrack/?trknbr={tracking}",
    "usps": "https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking}",
}
