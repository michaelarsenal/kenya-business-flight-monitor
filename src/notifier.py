from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List

from src.config import MonitorConfig
from src.tracker import EvaluatedOffer


def _format_change(item: EvaluatedOffer) -> str:
    if item.drop_vs_prev_pct is None:
        return "New"
    if item.drop_vs_prev_pct > 0:
        return f"-{item.drop_vs_prev_pct:.1f}%"
    if item.drop_vs_prev_pct < 0:
        return f"+{abs(item.drop_vs_prev_pct):.1f}%"
    return "0.0%"


def build_summary_markdown(
    evaluated: List[EvaluatedOffer],
    config: MonitorConfig,
    errors: List[str],
    top_n: int = 15,
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sorted_items = sorted(evaluated, key=lambda e: e.offer.price_usd)
    alerts = [e for e in sorted_items if e.should_alert]

    lines = [
        f"# USA -> Kenya Business Class Daily Summary ({now_str})",
        "",
        f"- **Routes checked:** {len(evaluated)} (Errors: {len(errors)})",
        f"- **Target budget:** <= ${config.target_max_price_usd:,.0f} USD",
        f"- **Drop alert threshold:** >= {config.drop_threshold_pct:.0f}%",
        f"- **New deal alerts today:** {len(alerts)}",
        "",
    ]

    if sorted_items:
        best = sorted_items[0]
        lines.extend(
            [
                f"**Best fare today:** `{best.offer.origin} -> {best.offer.destination}` "
                f"on `{best.offer.departure_date}` to `{best.offer.return_date}` "
                f"({best.offer.trip_length_days}d) — **${best.offer.price_usd:,.2f}** "
                f"({best.offer.airline}, {best.offer.stops} stop(s))",
                "",
            ]
        )

    lines.extend(
        [
            f"## Top {min(top_n, len(sorted_items))} Cheapest Business Class Fares",
            "",
            "| Route | Dates | Days | Airline | Stops | Price | Prev | Change | Lowest Ever |",
            "|---|---|---:|---|---:|---:|---:|---:|---:|",
        ]
    )

    for item in sorted_items[:top_n]:
        o = item.offer
        prev_str = f"${item.previous_price_usd:,.0f}" if item.previous_price_usd else "—"
        lines.append(
            f"| {o.origin}->{o.destination} | {o.departure_date} to {o.return_date} | "
            f"{o.trip_length_days} | {o.airline} | {o.stops} | "
            f"**${o.price_usd:,.0f}** | {prev_str} | {_format_change(item)} | "
            f"${item.lowest_ever_usd:,.0f} |"
        )

    if errors:
        lines.extend(["", "## Errors", ""])
        for err in errors[:10]:
            lines.append(f"- {err}")

    return "\n".join(lines) + "\n"


def _build_summary_html(
    evaluated: List[EvaluatedOffer],
    config: MonitorConfig,
    errors: List[str],
    top_n: int = 15,
) -> str:
    sorted_items = sorted(evaluated, key=lambda e: e.offer.price_usd)
    rows_html = []
    for item in sorted_items[:top_n]:
        o = item.offer
        prev_str = f"${item.previous_price_usd:,.0f}" if item.previous_price_usd else "—"
        badge = "🔥 " if item.should_alert else ""
        link = f'<a href="{o.booking_url}">Search</a>' if o.booking_url else "—"
        rows_html.append(
            f"<tr>"
            f"<td>{badge}{o.origin} &rarr; {o.destination}</td>"
            f"<td>{o.departure_date} to {o.return_date} ({o.trip_length_days}d)</td>"
            f"<td>{o.airline}</td>"
            f"<td style='text-align:center'>{o.stops}</td>"
            f"<td style='text-align:right'><b>${o.price_usd:,.0f}</b></td>"
            f"<td style='text-align:right'>{prev_str}</td>"
            f"<td style='text-align:right'>{_format_change(item)}</td>"
            f"<td style='text-align:right'>${item.lowest_ever_usd:,.0f}</td>"
            f"<td>{link}</td>"
            f"</tr>"
        )

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #222;">
      <h2>USA &rarr; Kenya Business Class Daily Summary</h2>
      <p>
        <b>Routes checked:</b> {len(evaluated)} &nbsp;|&nbsp;
        <b>Target budget:</b> &le; ${config.target_max_price_usd:,.0f} &nbsp;|&nbsp;
        <b>Drop threshold:</b> &ge; {config.drop_threshold_pct:.0f}% &nbsp;|&nbsp;
        <b>Errors:</b> {len(errors)}
      </p>
      <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; font-size: 13px;">
        <thead style="background-color: #f3f4f6;">
          <tr>
            <th>Route</th><th>Dates</th><th>Airline</th><th>Stops</th>
            <th>Price</th><th>Prev</th><th>Change</th><th>Lowest</th><th>Link</th>
          </tr>
        </thead>
        <tbody>
          {"".join(rows_html)}
        </tbody>
      </table>
    </body>
    </html>
    """


def _build_alert_bodies(alerts: List[EvaluatedOffer]) -> tuple[str, str]:
    sorted_alerts = sorted(alerts, key=lambda e: e.offer.price_usd)
    text_lines = ["CHEAP BUSINESS CLASS DEAL ALERT (USA -> Kenya, June 2027)", ""]
    html_items = []

    for item in sorted_alerts:
        o = item.offer
        reasons = "; ".join(item.alert_reasons)
        text_lines.append(
            f"- {o.origin} -> {o.destination} | {o.departure_date} to {o.return_date} "
            f"({o.trip_length_days}d) | ${o.price_usd:,.0f} | {o.airline} ({o.stops} stop(s)) | {reasons}"
        )
        if o.booking_url:
            text_lines.append(f"  Book/Search: {o.booking_url}")

        link_html = f'<a href="{o.booking_url}">View on Google Flights</a>' if o.booking_url else ""
        html_items.append(
            f"<li><b>{o.origin} &rarr; {o.destination}</b> ({o.departure_date} to {o.return_date}, "
            f"{o.trip_length_days} days): <b>${o.price_usd:,.0f}</b> on {o.airline} "
            f"({o.stops} stop(s))<br><i>Reason:</i> {reasons} {link_html}</li>"
        )

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #222;">
      <h2 style="color: #0f766e;">Business Class Deal Alert: USA &rarr; Kenya (June 2027)</h2>
      <ul>{"".join(html_items)}</ul>
    </body>
    </html>
    """
    return "\n".join(text_lines), html_body


def send_smtp_email(subject: str, text_body: str, html_body: str) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    email_to = os.environ.get("ALERT_EMAIL_TO", smtp_user)

    if not smtp_user or not smtp_pass or not email_to:
        raise ValueError(
            "SMTP_USER, SMTP_PASSWORD, and ALERT_EMAIL_TO environment variables are required to send email."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = email_to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [addr.strip() for addr in email_to.split(",")], msg.as_string())


def dispatch_notifications(
    evaluated: List[EvaluatedOffer],
    config: MonitorConfig,
    errors: List[str],
    report_path: str | Path = "data/latest_report.md",
    dry_run: bool = False,
) -> None:
    summary_md = build_summary_markdown(evaluated, config, errors)
    out_path = Path(report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(summary_md, encoding="utf-8")

    alerts = [e for e in evaluated if e.should_alert]

    if dry_run:
        print("[DRY RUN] Skipping SMTP email delivery. Report written to", out_path)
        print(summary_md)
        if alerts:
            text_alert, _ = _build_alert_bodies(alerts)
            print("[DRY RUN] Deal alerts that would be sent:\n" + text_alert)
        return

    if config.send_instant_alerts and alerts:
        best_alert = min(alerts, key=lambda e: e.offer.price_usd)
        subj = (
            f"DEAL ALERT: {best_alert.offer.origin}->{best_alert.offer.destination} "
            f"Business Class ${best_alert.offer.price_usd:,.0f} (June 2027)"
        )
        text_alert, html_alert = _build_alert_bodies(alerts)
        send_smtp_email(subj, text_alert, html_alert)

    if config.send_daily_summary:
        best_price_str = (
            f"${min(e.offer.price_usd for e in evaluated):,.0f}" if evaluated else "N/A"
        )
        subj = f"Daily Business Class Summary: USA -> Kenya (Best: {best_price_str})"
        html_summary = _build_summary_html(evaluated, config, errors)
        send_smtp_email(subj, summary_md, html_summary)
