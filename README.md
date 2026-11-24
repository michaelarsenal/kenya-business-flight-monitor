# Kenya Business Class Flight Price Monitor

Automated daily monitor for **Business Class** flights from major **US departure cities** (`JFK`, `EWR`, `IAD`, `BOS`, `ORD`, `ATL`, `DFW`, `IAH`, `LAX`, `SFO`) to **Kenya** (`NBO`) for **June 2027** (10–18 day trips).

## Features
- **Daily Summary Email**: Ranked table of the cheapest Business Class fares, price changes vs. previous check, and lowest price ever seen.
- **Instant Deal Alerts**: Triggers when a fare is:
  - **Within target budget** (`<= $3,500` USD), **OR**
  - **25%+ cheaper** than the previous check or historical average.
- **Alert Deduplication**: Avoids repeating alerts for the same itinerary unless the price drops by at least `$50` more.
- **Automated History**: Stores rolling price history in `data/price_history.json` and the latest report in `data/latest_report.md` via GitHub Actions.

---

## Setup Instructions (GitHub Actions)

### 1. Get a Flight Pricing API Key
*(Note: Amadeus decommissioned its Self-Service portal in July 2026 and is now Enterprise-only.)*

Choose **one** of these self-serve Google Flights APIs:
- **SerpApi (Recommended — Free tier: 250 searches/month)**:
  1. Sign up at [serpapi.com](https://serpapi.com/) and copy your `SERPAPI_API_KEY`.
  2. **Quota tip:** To stay within the free 250 searches/month (~8 searches/day), trim `config.yaml` to 4 US hubs (e.g., `JFK`, `IAD`, `ORD`, `LAX`), 2 `departure_dates`, and 1 `trip_lengths_days` (`4 * 2 * 1 = 8/day = ~240/month`).
- **SearchApi (Free tier: 100 requests, no card required)**:
  1. Sign up at [searchapi.io](https://www.searchapi.io/) and copy your `SEARCHAPI_API_KEY`.

### 2. Get an Email App Password (for Gmail)
1. Enable 2-Step Verification on your Google account.
2. Create an **App Password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

### 3. Add GitHub Repository Secrets
Go to your repository **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret Name | Required | Example / Description |
|---|---|---|
| `SERPAPI_API_KEY` | If using SerpApi | Your SerpApi API Key |
| `SEARCHAPI_API_KEY` | If using SearchApi | Your SearchApi API Key |
| `SMTP_USER` | Yes | `yourname@gmail.com` |
| `SMTP_PASSWORD` | Yes | 16-character Gmail App Password |
| `ALERT_EMAIL_TO` | Yes | Recipient email(s), comma-separated |
| `SMTP_HOST` | Optional | Defaults to `smtp.gmail.com` |
| `SMTP_PORT` | Optional | Defaults to `587` |

*(Optional)* Under **Variables**, set `FLIGHT_PROVIDER` to `serpapi` or `searchapi` (auto-detected from whichever secret is set).

### 4. Customize Routes or Thresholds
Edit `config.yaml` to adjust:
- `origins` / `destinations` (e.g., uncomment `MBA` for Mombasa)
- `departure_dates` & `trip_lengths_days`
- `target_max_price_usd` (default `3500.0`)
- `drop_threshold_pct` (default `25.0`)

### 5. Run Manually to Test
Go to **Actions → Daily Business Class Flight Monitor → Run workflow**.

---

## Local Testing
```bash
pip install -r requirements.txt
pytest
python -m src.main --provider mock --dry-run
```
