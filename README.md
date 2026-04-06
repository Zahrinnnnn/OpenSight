# OpenSight

Cash flow forecasting for Malaysian SMEs.

OpenSight takes raw bank transaction CSVs, runs them through a multi-stage analysis pipeline, trains a time-series model, and produces 30/60/90-day forecasts with plain-language explanations and automated shortfall alerts. Everything is accessible through a Streamlit dashboard or a Telegram bot.

---

## The Problem

Small businesses in Malaysia run into cash flow surprises all the time. A tax payment lands the same week as payroll. Rent goes out before a client invoice clears. A seasonal dip in revenue goes unnoticed until the account is already in the red. Most SME owners manage this with spreadsheets, gut feel, or a bank statement they check once a week.

The result is avoidable shortfalls, missed payments, and decisions made with stale data.

---

## What I Built

A fully automated pipeline that turns historical transaction data into forward-looking cash intelligence:

| Stage | What happens |
|---|---|
| **Ingestion** | CSV loaded, dates parsed (any format), amounts cleaned, duplicates dropped |
| **Categorisation** | Rule-based keyword matching, with DeepSeek as a fallback for uncategorised rows |
| **Aggregation** | Daily net cash flow calculated, missing days zero-filled, monthly summaries generated |
| **Recurring detection** | rapidfuzz fuzzy-matches transaction descriptions to cluster repeated payments and predict next expected dates |
| **Anomaly detection** | IQR and statistical thresholds flag large amounts, unusual timing, new vendors, spending spikes, and activity gaps |
| **Seasonality analysis** | Identifies month-end effects, quarter-end patterns, and holiday-adjacent spend |
| **Forecasting** | Prophet trained with Malaysian public holidays and month-end regressors, producing base / best / worst case projections |
| **Shortfall detection** | Cumulative cash position tracked across the forecast horizon; anything that drops below the threshold gets flagged with severity |
| **Narrative** | DeepSeek writes a plain-language summary of risks, patterns, and recommendations |
| **Delivery** | Streamlit dashboard with interactive charts, Telegram bot with scheduled alerts |

---

## Key Technical Decisions

**Prophet over ARIMA.** Prophet handles missing days, public holidays, and seasonal effects out of the box, and it holds up reasonably well on sparse or irregular data. ARIMA needs stationarity checks and manual lag selection, which adds unnecessary complexity when the end user is an SME owner rather than a data scientist.

**DeepSeek as the only LLM.** The openai SDK's compatibility layer means the same client code works against any OpenAI-compatible API. DeepSeek was picked for cost: categorisation and narrative calls together come in under USD 0.03 per pipeline run. GPT-4o would be roughly 15x more expensive for the same output.

**rapidfuzz for recurring detection.** Exact string matching does not work on bank transaction descriptions because banks abbreviate inconsistently (`MYEG SERVICES` vs `MYEG SVC`). rapidfuzz fuzzy-matches at a configurable threshold, clusters similar descriptions, and correctly groups payments that a simple `groupby` would split.

**SQLite for persistence.** No infrastructure to stand up, no connection pool to manage, and the data fits in a single file. The schema covers transactions, forecast runs, detected patterns, anomalies, and shortfall alerts with full history.

**Rule-based categorisation first.** Calling an LLM for every transaction row is slow and costs money. A keyword dictionary handles roughly 80% of typical Malaysian SME transactions (salary, rent, utilities, tax, loans, insurance). DeepSeek is only called for whatever is left over.

---

## Architecture

```
CSV input
    |
    v
+-------------+   clean dates/amounts    +--------------+
| cleaner.py  | -----------------------> | categoriser  |
+-------------+                           +------+-------+
                                                 | rule-based + DeepSeek fallback
                                                 v
                                          +--------------+
                                          |  aggregator  |  daily net cash flow
                                          +------+-------+
                                                 |
                          +----------------------+----------------------+
                          v                      v                      v
                   +------------+        +------------+        +--------------+
                   | recurring  |        |  anomaly   |        | seasonality  |
                   +------------+        +------------+        +--------------+
                          |                      |                      |
                          +----------------------+----------------------+
                                                 |
                                                 v
                                        +-----------------+
                                        |  prophet_model  |  30/60/90-day forecast
                                        +--------+--------+
                                                 |
                                        +--------+--------+
                                        |    shortfall    |  balance projection
                                        +--------+--------+
                                                 |
                                        +--------+--------+
                                        |    deepseek     |  plain-language narrative
                                        +--------+--------+
                                                 |
                              +------------------+------------------+
                              v                                      v
                     +-----------------+                   +-----------------+
                     | Streamlit (app) |                   |  Telegram (bot) |
                     +-----------------+                   +-----------------+
```

---

## Tests

83 tests, all passing. Written with pytest against real data structures, no mocks.

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

**Duplicate-safe ingestion.** Re-uploading the same CSV does not create duplicate records. A composite key hash is checked before each insert, so only genuinely new transactions get written to the database.

**Mixed-format date parsing.** Real bank exports come in `DD/MM/YYYY`, `YYYY-MM-DD`, `D MMM YYYY`, and a dozen other variations. The cleaner uses `python-dateutil` with a fallback chain and surfaces a clear error for rows it cannot parse, rather than silently dropping them or crashing the whole run.

**Graceful offline mode.** Both the CLI and the dashboard accept `--no-deepseek` to skip all LLM calls. The pipeline runs fully offline, narratives are omitted, and categorisation falls back to rule-based only. Useful for testing and for cases where the API key has not been set up yet.

**Structured logging throughout.** Every pipeline stage logs to both stdout (coloured, readable) and a rotating file via `loguru`. An error in one stage does not silently kill the rest of the pipeline.

**Malaysian public holidays baked in.** Prophet's holiday regressor is loaded with all Malaysian federal public holidays, including state-specific ones like Selangor and Kelantan. This improves forecast accuracy around Hari Raya, Chinese New Year, and Deepavali.

---

## Further Improvements

These are deliberate omissions rather than oversights. The scope was kept tight to keep the codebase clean and easy to walk through.

| Area | What could be added |
|---|---|
| **Multi-account view** | Aggregate across multiple bank accounts and treat inter-account transfers as their own flow type |
| **ARIMA fallback** | If Prophet's MAPE on the training set is too high, fall back to ARIMA for data that does not have clear seasonality |
| **Live bank feeds** | Replace CSV upload with an OFX/QIF parser or a BaaS API integration for automatic daily sync |
| **Budget vs actuals** | Let users set a monthly budget per category and show variance each period |
| **Forecast accuracy tracking** | Once 30/60/90 days pass, compare actual cash position against what Prophet predicted and track MAPE over time |
| **Multi-user support** | Add authentication and per-user data isolation; at that point SQLite would be swapped for PostgreSQL |
| **Mobile-friendly UI** | The Streamlit dashboard is desktop-first; a React Native front end over a FastAPI backend would make it usable on the go |
| **Held-out evaluation window** | Hold out the last 30 days of training data, score prediction accuracy, and include that confidence score with every forecast run |

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

Fill in `.env`. You only need `DEEPSEEK_API_KEY` to get started. Everything else has a sensible default.

---

## Running the dashboard

```bash
streamlit run app.py
```

1. Open [http://localhost:8501](http://localhost:8501)
2. Upload your CSV on the Home page
3. Set your opening balance
4. Click Run Full Pipeline
5. Navigate through Overview, Forecast, Cash Flow, Recurring, Anomalies, and Narrative

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

Shortfall checks run every 6 hours. If a shortfall is projected within 30 days, the bot sends an alert automatically.

---

## CSV format

| Column | Required | Notes |
|---|---|---|
| `date` | Yes | Any common format, auto-parsed |
| `description` | Yes | Transaction narration |
| `amount` | Yes | Always positive |
| `type` | Yes | `inflow` or `outflow` (also accepts `credit` / `debit`) |
| `category` | No | Auto-assigned if blank |
| `account` | No | Bank account name |

```csv
date,description,amount,type,category,account
2026-01-05,Client Payment - ABC Sdn Bhd,15000.00,inflow,Revenue,CIMB
2026-01-08,Office Rental January,3500.00,outflow,Rent,CIMB
2026-01-10,Salary Run,8200.00,outflow,Payroll,HLB
```

A sample file with 12 months of realistic Malaysian SME data is at `tests/fixtures/sample_transactions.csv`.

Minimum 30 transactions. 12 months is recommended for accurate seasonal detection.

---

## Tech stack

| Component | Technology | Why |
|---|---|---|
| Forecasting | [Prophet](https://facebook.github.io/prophet/) | Handles holidays, missing data, and multiple seasonalities without manual tuning |
| LLM | [DeepSeek](https://api.deepseek.com) via openai SDK | Under USD 0.03/run and easy to swap out if needed |
| Fuzzy matching | [rapidfuzz](https://github.com/maxbachmann/RapidFuzz) | Groups recurring payments correctly even when bank descriptions are inconsistent |
| Dashboard | [Streamlit](https://streamlit.io) + [Plotly](https://plotly.com) | Fast to build interactive financial charts without a full frontend |
| Telegram bot | [python-telegram-bot](https://python-telegram-bot.org) | Async, well-documented, has a built-in job scheduler for the alert polling |
| Database | SQLite (stdlib) | No infrastructure needed; a single file is enough for this use case |
| Date parsing | [python-dateutil](https://dateutil.readthedocs.io) | Handles the inconsistent date formats that show up in real bank exports |
| Logging | [loguru](https://loguru.readthedocs.io) | Coloured stdout and a rotating log file with almost no setup |

---

## Project structure

```
opensight/
├── main.py                 # CLI entry point
├── bot.py                  # Telegram bot
├── app.py                  # Streamlit dashboard
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
