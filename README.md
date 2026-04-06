# OpenSight

**Intelligent cash flow forecasting engine for Malaysian SMEs.**

OpenSight takes raw bank transaction CSVs, runs them through a multi-stage analysis pipeline, trains a time-series model, and surfaces 30/60/90-day cash flow forecasts — with plain-language explanations and automated shortfall alerts — through a Streamlit dashboard and a Telegram bot.

---

## The Problem

Small businesses in Malaysia routinely run into cash flow surprises: a tax payment lands the same week as payroll, rent goes out before a client invoice clears, or a seasonal dip in revenue goes unnoticed until the account is already in the red. Most SME owners manage this with spreadsheets, gut feel, or a bank statement they check once a week.

The result is avoidable shortfalls, missed payments, and decisions made with stale information.

---

## What I Built

A fully automated pipeline that turns historical transaction data into forward-looking cash intelligence:

| Stage | What happens |
|---|---|
| **Ingestion** | CSV loaded, dates parsed (any format), amounts cleaned, duplicates dropped |
| **Categorisation** | Rule-based keyword matching, DeepSeek LLM as fallback for uncategorised rows |
| **Aggregation** | Daily net cash flow calculated, missing days zero-filled, monthly summaries generated |
| **Recurring detection** | rapidfuzz fuzzy-matches transaction descriptions to cluster repeated payments, calculates frequency and next expected date |
| **Anomaly detection** | IQR + statistical thresholds flag large amounts, unusual timing, new vendors, spending spikes, and activity gaps |
| **Seasonality analysis** | Identifies month-end effects, quarter-end patterns, and holiday-adjacent spend |
| **Forecasting** | Prophet trained with Malaysian public holidays and month-end regressors; generates base / best / worst case projections |
| **Shortfall detection** | Cumulative cash position calculated; any point where balance drops below threshold is flagged with severity |
| **Narrative** | DeepSeek generates a plain-language summary of risks, patterns, and recommendations |
| **Delivery** | Streamlit dashboard with interactive charts, Telegram bot with scheduled alerts |

---

## Key Technical Decisions

**Prophet over ARIMA** — Prophet handles missing days, public holidays, and seasonal effects out of the box, and degrades gracefully with irregular or sparse data. ARIMA requires stationarity checks and manual lag selection; that friction is unnecessary when the end user is an SME owner, not a data scientist.

**DeepSeek as the only LLM** — The openai SDK's compatibility layer means the same client code works with any OpenAI-compatible API. DeepSeek was chosen for cost: the categorisation + narrative calls together run under USD 0.03 per pipeline execution. GPT-4o would cost roughly 15× more for the same output.

**rapidfuzz for recurring detection** — Exact string matching fails on transaction descriptions because banks abbreviate inconsistently (`MYEG SERVICES` vs `MYEG SVC`). rapidfuzz fuzzy-matches at configurable thresholds, clusters similar descriptions, and correctly identifies payments that a simple `groupby` would miss.

**SQLite for persistence** — No infrastructure to stand up, no connection pool to manage, and the data fits comfortably in a single file. The schema stores transactions, forecast runs, detected patterns, anomalies, and shortfall alerts with full history.

**Rule-based categorisation first** — Calling an LLM for every row is slow and expensive. A keyword dictionary covers roughly 80% of typical Malaysian SME transactions (salary, rental, utilities, tax, loans, insurance). DeepSeek is only invoked for the remainder.

---

## Architecture

```
CSV input
    │
    ▼
┌─────────────┐   clean dates/amounts    ┌──────────────┐
│  cleaner.py │ ────────────────────────▶│ categoriser  │
└─────────────┘                           └──────┬───────┘
                                                 │ rule-based + DeepSeek fallback
                                                 ▼
                                          ┌──────────────┐
                                          │  aggregator  │  daily net cash flow
                                          └──────┬───────┘
                                                 │
                          ┌──────────────────────┼──────────────────────┐
                          ▼                      ▼                      ▼
                   ┌────────────┐        ┌────────────┐        ┌──────────────┐
                   │ recurring  │        │  anomaly   │        │ seasonality  │
                   └────────────┘        └────────────┘        └──────────────┘
                          │                      │                      │
                          └──────────────────────┴──────────────────────┘
                                                 │
                                                 ▼
                                        ┌─────────────────┐
                                        │  prophet_model  │  30/60/90-day forecast
                                        └────────┬────────┘
                                                 │
                                        ┌────────┴────────┐
                                        │    shortfall    │  balance projection
                                        └────────┬────────┘
                                                 │
                                        ┌────────┴────────┐
                                        │    deepseek     │  plain-language narrative
                                        └────────┬────────┘
                                                 │
                              ┌──────────────────┴──────────────────┐
                              ▼                                      ▼
                     ┌─────────────────┐                   ┌─────────────────┐
                     │ Streamlit (app) │                   │  Telegram (bot) │
                     └─────────────────┘                   └─────────────────┘
```

---

## Tests

83 tests, all passing. Written with `pytest` against real data structures — no mocks.

| Suite | Tests | What it covers |
|---|---|---|
| `test_processing.py` | 33 | Date parsing edge cases, amount normalisation, duplicate removal, category keyword matching, aggregation correctness, monthly summaries |
| `test_analysis.py` | 28 | Recurring frequency detection, next-date projection, all five anomaly types, seasonality pattern identification |
| `test_forecasting.py` | 22 | Prophet training on sample data, confidence interval output shape, cumulative cash position calculation, shortfall detection across threshold scenarios |

```bash
pytest tests/ -v
# 83 passed in 32.64s
```

---

## Engineering Highlights

**Duplicate-safe ingestion** — Re-uploading the same CSV does not create duplicate records. A composite key hash is checked before insert; only genuinely new transactions are written to the database.

**Mixed-format date parsing** — Real bank exports come in `DD/MM/YYYY`, `YYYY-MM-DD`, `D MMM YYYY`, and a dozen variations. The cleaner uses `python-dateutil` with a fallback chain and surfaces a clear error for rows it cannot parse, rather than silently dropping them or crashing.

**Graceful offline mode** — Both the CLI and the dashboard accept `--no-deepseek` to skip all LLM calls. The pipeline runs fully offline; narratives are omitted and categorisation falls back to rule-based only. Useful for testing and for users who have not configured an API key yet.

**Structured logging throughout** — Every pipeline stage logs to both stdout (coloured, human-readable) and a rotating file via `loguru`. Errors in one stage do not silently kill the rest of the pipeline.

**Malaysian public holidays baked in** — Prophet's holiday regressor is populated with all Malaysian federal public holidays, correctly handling states that observe different holidays (e.g. Selangor vs Kelantan). This improves forecast accuracy around Hari Raya, Chinese New Year, and Deepavali.

---

## Further Improvements

These are deliberate omissions, not oversights — scope was kept tight to keep the codebase clean and demonstrable.

| Area | What could be added |
|---|---|
| **Multi-account view** | Aggregate across multiple bank accounts; treat inter-account transfers as a separate flow type |
| **ARIMA fallback** | If Prophet's MAPE on the training set exceeds a threshold, fall back to ARIMA — useful for highly volatile or trend-free data |
| **Live bank feeds** | Replace CSV upload with an OFX/QIF parser or a BaaS API integration for automatic daily sync |
| **Budget vs actuals** | Allow users to set a monthly budget per category; surface variance each period |
| **Forecast accuracy tracking** | After 30/60/90 days pass, compare actual cash position against what Prophet predicted and surface MAPE over time |
| **Multi-user support** | Add authentication and per-user data isolation; SQLite would swap for PostgreSQL at this point |
| **Mobile-friendly UI** | The Streamlit dashboard is desktop-first; a React Native front end calling a FastAPI back end would make it usable on mobile |
| **Held-out evaluation window** | Quantitatively evaluate forecast quality by holding out the last 30 days of training data and scoring prediction accuracy before serving the live forecast |

---

## Setup

### 1. Clone

```bash
git clone https://github.com/Zahrinnnnn/OpenSight.git
cd OpenSight
```

### 2. Virtual environment

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

### 4. Configure

```bash
cp .env.example .env
```

Fill in `.env`. At minimum you need `DEEPSEEK_API_KEY` for categorisation and narrative. Everything else has sensible defaults.

---

## Running the dashboard

```bash
streamlit run app.py
```

1. Open [http://localhost:8501](http://localhost:8501)
2. Upload your CSV on the **Home** page
3. Set your opening balance
4. Click **Run Full Pipeline**
5. Explore **Overview**, **Forecast**, **Cash Flow**, **Recurring**, **Anomalies**, and **Narrative**

---

## Running the CLI

```bash
# Ingest and analyse
python main.py ingest path/to/transactions.csv --opening-balance 50000

# Train and forecast
python main.py forecast --opening-balance 50000 --horizon 90

# Skip LLM calls (offline mode)
python main.py ingest path/to/transactions.csv --opening-balance 50000 --no-deepseek
```

---

## Telegram bot

```bash
python bot.py
```

Send `/start` to register. Available commands:

| Command | Description |
|---|---|
| `/status` | Current cash position and latest forecast summary |
| `/forecast` | 30/60/90-day projected balances |
| `/shortfalls` | All projected shortfall dates |
| `/recurring` | Detected recurring payments with next expected dates |
| `/anomalies` | Flagged anomalies with severity |
| `/narrative` | DeepSeek plain-language commentary |
| `/history` | Past forecast runs |
| `/alert on\|off` | Toggle automated shortfall alerts |
| `/help` | All commands |

Shortfall checks run every 6 hours. If a shortfall is projected within 30 days, the bot sends an automatic alert.

---

## CSV format

| Column | Required | Notes |
|---|---|---|
| `date` | Yes | Any common format — auto-parsed |
| `description` | Yes | Transaction narration |
| `amount` | Yes | Always positive |
| `type` | Yes | `inflow` or `outflow` (also `credit` / `debit`) |
| `category` | No | Auto-assigned if blank |
| `account` | No | Bank account name |

```csv
date,description,amount,type,category,account
2026-01-05,Client Payment - ABC Sdn Bhd,15000.00,inflow,Revenue,CIMB
2026-01-08,Office Rental January,3500.00,outflow,Rent,CIMB
2026-01-10,Salary Run,8200.00,outflow,Payroll,HLB
```

A sample file with 12 months of realistic Malaysian SME data is in `tests/fixtures/sample_transactions.csv`.

Minimum 30 transactions. 12 months recommended for accurate seasonal detection.

---

## Tech stack

| Component | Technology | Why |
|---|---|---|
| Forecasting | [Prophet](https://facebook.github.io/prophet/) | Handles holidays, missing data, and multiple seasonalities without manual tuning |
| LLM | [DeepSeek](https://api.deepseek.com) via openai SDK | Cost under USD 0.03/run; same SDK interface makes it swappable |
| Fuzzy matching | [rapidfuzz](https://github.com/maxbachmann/RapidFuzz) | Correctly clusters recurring payments despite inconsistent bank description formatting |
| Dashboard | [Streamlit](https://streamlit.io) + [Plotly](https://plotly.com) | Fast interactive financial charts without a full front-end build |
| Telegram bot | [python-telegram-bot](https://python-telegram-bot.org) | Async, well-documented, built-in scheduler for alert polling |
| Database | SQLite (stdlib) | Zero infrastructure; self-contained file is sufficient for single-user workload |
| Date parsing | [python-dateutil](https://dateutil.readthedocs.io) | Robust handling of inconsistent date formats from real bank exports |
| Logging | [loguru](https://loguru.readthedocs.io) | Coloured stdout + rotating file with minimal setup |

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
