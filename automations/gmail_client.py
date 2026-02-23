"""Gmail API client using existing OAuth credentials from workspace-mcp."""

import base64
import json
import logging
import os
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from automations.config import CREDENTIALS_PATH

logger = logging.getLogger(__name__)


def _load_credentials() -> Credentials:
    """Load and refresh OAuth credentials.

    Checks GMAIL_CREDENTIALS_JSON env var first (for CI), then falls back to
    the local credential file. The env var should contain a JSON string with
    client_id, client_secret, refresh_token, and token_uri.
    """
    env_creds = os.environ.get("GMAIL_CREDENTIALS_JSON")

    if env_creds:
        logger.info("Loading Gmail credentials from GMAIL_CREDENTIALS_JSON env var")
        creds_data = json.loads(env_creds.strip(), strict=False)
        # In CI we always refresh — treat the token as expired
        creds = Credentials(
            token=None,
            refresh_token=creds_data["refresh_token"],
            token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds_data["client_id"],
            client_secret=creds_data["client_secret"],
        )
        creds.refresh(Request())
        logger.info("Obtained fresh access token from refresh token")
        return creds

    logger.info(f"Loading Gmail credentials from {CREDENTIALS_PATH}")
    with open(CREDENTIALS_PATH, "r") as f:
        creds_data = json.load(f)

    expiry = None
    if creds_data.get("expiry"):
        try:
            expiry = datetime.fromisoformat(creds_data["expiry"])
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)
        except (ValueError, TypeError):
            pass

    creds = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data.get("token_uri"),
        client_id=creds_data.get("client_id"),
        client_secret=creds_data.get("client_secret"),
        scopes=creds_data.get("scopes"),
        expiry=expiry,
    )

    if creds.expired and creds.refresh_token:
        logger.info("Refreshing expired Gmail credentials")
        creds.refresh(Request())
        # Save refreshed token back
        creds_data["token"] = creds.token
        creds_data["expiry"] = creds.expiry.isoformat() if creds.expiry else None
        with open(CREDENTIALS_PATH, "w") as f:
            json.dump(creds_data, f, indent=2)
        logger.info("Saved refreshed credentials")

    return creds


class GmailClient:
    def __init__(self):
        creds = _load_credentials()
        self.service = build("gmail", "v1", credentials=creds)

    def search_messages(self, query: str, max_results: int = 3) -> list[dict]:
        """Search Gmail and return message snippets + subjects."""
        resp = self.service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = resp.get("messages", [])
        if not messages:
            return []

        results = []
        for msg_ref in messages:
            msg = self.service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["Subject", "Date"]
            ).execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            results.append({
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            })

        return results

    def send_html_email(self, to: str, subject: str, html_body: str, cc: str | None = None) -> str:
        """Send an HTML email via Gmail API."""
        message = MIMEMultipart("alternative")
        message["To"] = to
        if cc:
            message["Cc"] = cc
        message["Subject"] = subject
        message.attach(MIMEText(html_body, "html"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = self.service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        msg_id = sent.get("id")
        logger.info(f"Email sent: {msg_id}")
        return msg_id
