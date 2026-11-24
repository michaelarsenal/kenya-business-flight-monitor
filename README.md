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
Choose **one** of the following providers:
- **Amadeus Self-Service API (Recommended, free tier)**:
  1. Sign up at [developers.amadeus.com](https://developers.amadeus.com/).
  2. Create an app to get `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET`.
  3. Note: New apps start in the `test` environment; set GitHub Variable `AMADEUS_ENV=test` for testing or switch to `production` when approved for live fares.
- **SerpApi (Google Flights API)**:
  1. Sign up at [serpapi.com](https://serpapi.com/) and copy your `SERPAPI_API_KEY`.

### 2. Get an Email App Password (for Gmail)
1. Enable 2-Step Verification on your Google account.
2. Create an **App Password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

### 3. Add GitHub Repository Secrets
Go to your repository **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret Name | Required | Example / Description |
|---|---|---|
| `AMADEUS_CLIENT_ID` | If using Amadeus | Your Amadeus API Key |
| `AMADEUS_CLIENT_SECRET` | If using Amadeus | Your Amadeus API Secret |
| `SERPAPI_API_KEY` | If using SerpApi | Your SerpApi Key |
| `SMTP_USER` | Yes | `yourname@gmail.com` |
| `SMTP_PASSWORD` | Yes | 16-character Gmail App Password |
| `ALERT_EMAIL_TO` | Yes | Recipient email(s), comma-separated |
| `SMTP_HOST` | Optional | Defaults to `smtp.gmail.com` |
| `SMTP_PORT` | Optional | Defaults to `587` |

*(Optional)* Under **Variables**, set `AMADEUS_ENV` to `test` if using Amadeus sandbox credentials, or `FLIGHT_PROVIDER` to `amadeus` / `serpapi`.

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
