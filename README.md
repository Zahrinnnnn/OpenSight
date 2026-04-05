# OpenSight

Intelligent cash flow forecasting engine for Malaysian SMEs. Ingests historical transaction data from CSV, trains a Prophet time-series model, detects recurring payments and anomalies, and generates 30/60/90-day forecasts with plain-language explanations — all surfaced through a Streamlit dashboard and Telegram alerts.

---

## What it does

- Cleans and categorises transaction data automatically (rule-based + DeepSeek fallback)
- Detects recurring payments (monthly salary, rent, loan repayments) with expected next dates
- Flags anomalies: unusual amounts, suspicious timing, new high-value vendors, spending spikes, activity gaps
- Trains a [Prophet](https://facebook.github.io/prophet/) model with Malaysian public holidays and month-end effects
- Generates 30/60/90-day cash flow forecasts with 80% confidence intervals
- Calculates cumulative cash position (base case, best case, worst case)
- Alerts when projected balance is heading for a shortfall
- Explains everything in plain language via [DeepSeek](https://api.deepseek.com)
- Delivers results via a Streamlit dashboard and Telegram bot

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Zahrinnnnn/OpenSight.git
cd OpenSight
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# DeepSeek API (https://platform.deepseek.com)
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# Telegram bot (https://t.me/BotFather)
TELEGRAM_BOT_TOKEN=your_token_here

# Paths
DB_PATH=data/database.db
UPLOAD_DIR=data/uploads
MODEL_DIR=data/models

# Thresholds (in RM)
MINIMUM_BALANCE=0
ALERT_THRESHOLD=5000
HIGH_VALUE_THRESHOLD=5000
FORECAST_HORIZON=90
CONFIDENCE_INTERVAL=0.80
```

> DeepSeek is the only paid service. Expected cost: under USD 0.03 per forecast run.

---

## Running the dashboard

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

1. Go to **Home**
2. Upload your CSV file (see format below)
3. Set your opening balance
4. Click **Run Full Pipeline**
5. Navigate to **Overview**, **Forecast**, or any other page to explore results

---

## Running the CLI

The CLI has two commands:

**Ingest** — load, clean, categorise, and analyse a CSV:

```bash
python main.py ingest path/to/transactions.csv --opening-balance 50000
```

**Forecast** — train Prophet and generate a forecast from stored data:

```bash
python main.py forecast --opening-balance 50000 --horizon 90
```

Add `--no-deepseek` to either command to skip API calls (faster, offline-compatible).

---

## Running the Telegram bot

```bash
python bot.py
```

Send `/start` to your bot to register your chat. Available commands:

| Command | Description |
|---|---|
| `/status` | Current cash position and latest forecast summary |
| `/forecast` | 30/60/90-day projected balances |
| `/shortfalls` | All projected shortfall dates |
| `/recurring` | Detected recurring payments with next expected dates |
| `/anomalies` | Flagged anomalies with severity |
| `/narrative` | DeepSeek plain-language commentary |
| `/history` | Past forecast runs |
| `/alert on\|off` | Enable or disable automated shortfall alerts |
| `/help` | All commands |

The bot checks for imminent shortfalls every 6 hours and sends an automatic alert if a shortfall is projected within 30 days.

---

## CSV format

| Column | Required | Notes |
|---|---|---|
| `date` | Yes | Any common date format — auto-parsed |
| `description` | Yes | Transaction narration |
| `amount` | Yes | Always positive (no negative values) |
| `type` | Yes | `inflow` or `outflow` (also accepts `credit`/`debit`) |
| `category` | No | Auto-assigned if missing |
| `account` | No | Bank account name |

Example:

```csv
date,description,amount,type,category,account
2026-01-05,Client Payment - ABC Sdn Bhd,15000.00,inflow,Revenue,CIMB
2026-01-08,Office Rental January,3500.00,outflow,Rent,CIMB
2026-01-10,Salary Run,8200.00,outflow,Payroll,HLB
```

A sample file with 12 months of realistic Malaysian SME data is at `tests/fixtures/sample_transactions.csv`.

**Minimum:** 30 transactions
**Recommended:** 12 months for accurate seasonal detection

---

## Running the tests

```bash
pytest tests/ -v
```

Three test suites:

- `tests/test_processing.py` — cleaner, categoriser, aggregator (30 tests)
- `tests/test_analysis.py` — recurring detector, anomaly detector, seasonality (30 tests)
- `tests/test_forecasting.py` — Prophet model, cash position, shortfall detection (25 tests)

---

## Project structure

```
opensight/
├── main.py                 # CLI — ingest and forecast commands
├── bot.py                  # Telegram bot
├── app.py                  # Streamlit dashboard entry point
├── requirements.txt
├── .env.example
├── data/
│   ├── uploads/
│   ├── models/             # Saved Prophet models (.pkl)
│   └── reports/
├── src/
│   ├── processing/         # cleaner, categoriser, aggregator
│   ├── analysis/           # recurring, anomaly, seasonality
│   ├── forecasting/        # prophet_model, shortfall
│   ├── explanation/        # deepseek narrative and alerts
│   ├── database/           # connection, queries
│   └── utils/              # validators, holidays, logger
├── tests/
│   ├── test_processing.py
│   ├── test_analysis.py
│   ├── test_forecasting.py
│   └── fixtures/
│       └── sample_transactions.csv
└── ui/
    └── pages/              # home, overview, forecast, cashflow,
                            # recurring, anomalies, narrative, history
```

---

## Tech stack

| Component | Technology |
|---|---|
| Forecasting | [Prophet](https://facebook.github.io/prophet/) |
| LLM | [DeepSeek](https://api.deepseek.com) via openai SDK |
| Description matching | [rapidfuzz](https://github.com/maxbachmann/RapidFuzz) |
| Dashboard | [Streamlit](https://streamlit.io) + [Plotly](https://plotly.com) |
| Telegram bot | [python-telegram-bot](https://python-telegram-bot.org) |
| Database | SQLite (stdlib) |
| Date parsing | [python-dateutil](https://dateutil.readthedocs.io) |

---

## Environment variables reference

| Variable | Default | Description |
|---|---|---|
| `DEEPSEEK_API_KEY` | — | Your DeepSeek API key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API base URL |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model to use |
| `TELEGRAM_BOT_TOKEN` | — | Token from BotFather |
| `DB_PATH` | `data/database.db` | SQLite database path |
| `UPLOAD_DIR` | `data/uploads` | Where uploaded CSVs are stored |
| `MODEL_DIR` | `data/models` | Where trained Prophet models are saved |
| `MINIMUM_BALANCE` | `0` | Shortfall triggers below this (RM) |
| `ALERT_THRESHOLD` | `5000` | Early warning threshold (RM) |
| `HIGH_VALUE_THRESHOLD` | `5000` | New counterparty threshold (RM) |
| `FORECAST_HORIZON` | `90` | Default forecast days |
| `CONFIDENCE_INTERVAL` | `0.80` | Prophet confidence band width |
