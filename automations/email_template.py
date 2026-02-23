"""HTML email template builder for PO status report."""

from datetime import date

STATUS_STYLES = {
    "Delivery Scheduled": {"color": "#F59E0B", "bg": "#FFFBEB", "label": "Delivery Scheduled"},
    "En Route": {"color": "#14B8A6", "bg": "#F0FDFA", "label": "En Route"},
    "Delivered": {"color": "#22C55E", "bg": "#F0FDF4", "label": "Delivered"},
    "Invoiced": {"color": "#A855F7", "bg": "#FAF5FF", "label": "Invoiced"},
}


def _render_detail(record: dict, status: str) -> str:
    """Render the detail column content based on status."""
    detail = record.get("enrichment", "")
    if status == "En Route":
        tracking_url = record.get("tracking_url")
        eta = record.get("eta", "")
        parts = []
        if tracking_url:
            carrier = record.get("carrier", "Track")
            parts.append(f'<a href="{tracking_url}" style="color:#14B8A6;">{carrier} Tracking</a>')
        if eta:
            parts.append(f"ETA: {eta}")
        return "<br>".join(parts) if parts else "—"
    if not detail:
        return "—"
    return detail


def build_email_html(enriched_groups: dict, date_str: str, total_count: int) -> str:
    """Build the full HTML email body."""
    sections = []

    for status, records in enriched_groups.items():
        if not records:
            continue

        style = STATUS_STYLES.get(status, {"color": "#6B7280", "bg": "#F9FAFB", "label": status})

        # Detail column header per status
        detail_headers = {
            "Delivery Scheduled": "Latest Email",
            "En Route": "Tracking / ETA",
            "Delivered": "Delivery Date",
            "Invoiced": "Invoice Due Date",
        }
        detail_header = detail_headers.get(status, "Details")

        rows = ""
        for r in records:
            detail = _render_detail(r, status)
            urgent = r.get("urgent_update", "")
            urgent_style = (
                "padding:8px 12px;border-bottom:1px solid #E5E7EB;background:#FEF2F2;color:#DC2626;"
                if urgent
                else "padding:8px 12px;border-bottom:1px solid #E5E7EB;"
            )
            rows += f"""<tr>
                <td style="padding:8px 12px;border-bottom:1px solid #E5E7EB;">{r.get('po_number','—')}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #E5E7EB;">{r.get('customer','—')}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #E5E7EB;">{detail}</td>
                <td style="{urgent_style}">{urgent if urgent else '—'}</td>
            </tr>"""

        sections.append(f"""
        <div style="margin-bottom:24px;">
            <div style="background:{style['bg']};border-left:4px solid {style['color']};padding:10px 16px;margin-bottom:0;border-radius:4px 4px 0 0;">
                <strong style="color:{style['color']};font-size:16px;">{style['label']}</strong>
                <span style="color:#6B7280;margin-left:8px;">({len(records)})</span>
            </div>
            <table style="width:100%;border-collapse:collapse;font-size:14px;border:1px solid #E5E7EB;border-top:none;">
                <thead>
                    <tr style="background:#F9FAFB;">
                        <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #E5E7EB;">PO #</th>
                        <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #E5E7EB;">Customer</th>
                        <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #E5E7EB;">{detail_header}</th>
                        <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #E5E7EB;">Urgent Updates</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>""")

    body_content = "\n".join(sections) if sections else '<p style="color:#6B7280;">No active POs found.</p>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#1F2937;max-width:900px;margin:0 auto;padding:20px;">
    <div style="background:linear-gradient(135deg,#1E3A5F,#2563EB);padding:20px 24px;border-radius:8px;margin-bottom:24px;">
        <h1 style="color:white;margin:0;font-size:22px;">PO Status Report</h1>
        <p style="color:#93C5FD;margin:4px 0 0;">{date_str} &middot; {total_count} active PO{'' if total_count == 1 else 's'}</p>
    </div>
    {body_content}
    <p style="color:#9CA3AF;font-size:12px;margin-top:32px;border-top:1px solid #E5E7EB;padding-top:12px;">
        Automated report from Surge Supply Co. &middot; Data from Airtable Sales Tracker
    </p>
</body>
</html>"""
