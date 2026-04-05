# OpenSight — Build Phases

**5 phases, built in order. Each phase must be complete and working before the next starts.**

---

## Phase 1 — Foundation ✅ COMPLETE
**Goal:** Skeleton is up, data can get in, nothing breaks.

### Deliverables
- [x] Git repo initialised, connected to GitHub, `.gitignore` configured
- [x] Folder structure created as per PRD section 12
- [x] `requirements.txt` with all dependencies
- [x] `.env` template (`.env.example`) committed, actual `.env` gitignored
- [x] `loguru` logger configured in `src/utils/logger.py`
- [x] SQLite connection and schema creation in `src/database/connection.py`
  - Tables: `transactions`, `forecast_runs`, `recurring_payments`, `anomalies`, `shortfall_alerts`
- [x] CSV validator in `src/utils/validators.py` — checks required columns, data types, minimum row count
- [x] Data cleaner in `src/processing/cleaner.py`
  - Parse mixed date formats with `dateutil`
  - Strip commas and symbols from amounts
  - Standardise type column to inflow/outflow
  - Remove true duplicates
  - Sort by date ascending
- [x] Basic CLI runner in `main.py` — accepts CSV path as argument

### Done When
Running `python main.py data/sample.csv` loads, cleans, and stores transactions in SQLite without errors.

---

## Phase 2 — Data Processing ✅ COMPLETE
**Goal:** Every transaction has a category. Data is ready for the model.

### Deliverables
- [x] Rule-based categoriser in `src/processing/categoriser.py`
  - Keyword matching for all 9 categories (Payroll, Rent, Utilities, Tax, Loan Repayment, Insurance, Dividend, Refund, Transfer)
  - Case-insensitive, handles Malay and English keywords
- [x] DeepSeek fallback categoriser
  - Calls DeepSeek API for descriptions that don't match any rule
  - Uses the `CATEGORISE_PROMPT` from PRD section 5.2
  - Respects rate limits, handles API errors gracefully
- [x] Daily aggregator in `src/processing/aggregator.py`
  - Groups transactions by date, calculates net cash flow per day
  - Fills missing days with zero
  - Outputs Prophet-compatible `ds`/`y` dataframe
- [x] Malaysian public holidays helper in `src/utils/holidays.py`
- [x] Duplicate prevention — re-uploading same CSV does not insert duplicate rows
- [x] `sample_transactions.csv` in `tests/fixtures/` — 12 months, ~175 rows, realistic Malaysian SME data
- [x] `test_processing.py` — tests for cleaner, categoriser, aggregator

### Done When
Any CSV that passes validation is fully cleaned, categorised, deduplicated, and stored. Daily aggregated dataframe is ready for Prophet.

---

## Phase 3 — Analysis Engine ✅ COMPLETE
**Goal:** Recurring payments and anomalies are detected and stored.

### Deliverables
- [x] Recurring payment detector in `src/analysis/recurring.py`
  - Group transactions by description similarity using `rapidfuzz`
  - Detect monthly fixed, monthly variable, weekly, quarterly patterns
  - Compute `next_expected` date and `confidence` score
  - Store detected patterns in `recurring_payments` table
- [x] Anomaly detector in `src/analysis/anomaly.py`
  - IQR-based outlier detection per category
  - Flag: LARGE_AMOUNT, UNUSUAL_TIMING, NEW_COUNTERPARTY, SPIKE, GAP
  - Store flagged rows in `anomalies` table, link to `transaction_id`
- [x] Seasonality notes in `src/analysis/seasonality.py`
  - Month-end spike detection (payroll, rent, utilities)
  - Quarter-end pattern flags
  - `build_month_end_regressor()` feeds into Prophet as custom regressor (Phase 4)
- [x] `test_analysis.py` — 30 tests covering recurring detector, anomaly detector, seasonality

### Done When
After processing the sample CSV, recurring payments are detected with the correct frequency, and known anomalies in the fixture data are flagged correctly.

---

## Phase 4 — Forecasting + Explanation ✅ COMPLETE
**Goal:** 90-day forecast is generated, explained in plain language, shortfalls are detected.

### Deliverables
- [x] Prophet model in `src/forecasting/prophet_model.py`
  - Config: multiplicative seasonality, yearly + weekly, `changepoint_prior_scale=0.05`, `interval_width=0.80`
  - Malaysian public holidays added via `add_country_holidays('MY')`
  - Month-end regressor added
  - Model saved to `data/models/` after training
- [x] Forecast generator — 30/60/90 day horizon, returns `ds`, `yhat`, `yhat_lower`, `yhat_upper`
- [x] Cash position calculator in `src/forecasting/shortfall.py`
  - Cumulative cash position from opening balance
  - Best case, base case, worst case
- [x] Shortfall detector — finds dates where projected balance crosses threshold, stores in `shortfall_alerts`
- [x] Forecast run stored in `forecast_runs` table with all summary fields
- [x] DeepSeek explanation in `src/explanation/deepseek.py`
  - Forecast narrative using `FORECAST_NARRATIVE_PROMPT` from PRD section 8.1
  - Shortfall alert message using `SHORTFALL_ALERT_PROMPT` from PRD section 8.2
  - Narrative saved to `forecast_runs.narrative`
- [x] `src/database/queries.py` — helpers for saving/reading forecast runs, anomalies, recurring, shortfalls
- [x] `test_forecasting.py` — 25 tests covering model training, forecast generation, cash position, shortfall detection
- [x] `main.py` refactored into two CLI commands: `ingest` and `forecast`

### Done When
Running a forecast on the sample CSV produces a 90-day projection with confidence intervals, a cash position curve, and a DeepSeek-generated narrative paragraph — all stored in SQLite.

---

## Phase 5 — Delivery Layer ✅ COMPLETE
**Goal:** Everything is visible through the dashboard and Telegram. Project is presentable.

### Deliverables
- [x] Streamlit app entry point `app.py` with sidebar multi-page navigation
- [x] `ui/pages/home.py` — CSV upload, opening balance input, full pipeline runner with progress bar
- [x] `ui/pages/overview.py` — KPI cards (current balance, 30/60/90 projections, burn rate, runway), shortfall red banner, recent transactions
- [x] `ui/pages/forecast.py` — interactive Plotly chart: historical solid line, forecast dashed line, confidence band shaded, shortfall/alert threshold lines, anomaly markers, recurring payment markers, 30/60/90 toggle, date range slider
- [x] `ui/pages/cashflow.py` — inflow vs outflow category pie charts, MoM grouped bar + net line chart, category totals table
- [x] `ui/pages/recurring.py` — recurring payments table, upcoming in 30 days, frequency and direction filters
- [x] `ui/pages/anomalies.py` — anomaly list with type, severity emoji, description, breakdown bar chart
- [x] `ui/pages/narrative.py` — DeepSeek commentary display with regenerate button
- [x] `ui/pages/history.py` — past forecast runs table with drill-down, shortfall alerts per run, narrative per run
- [x] Telegram bot in `bot.py`
  - Commands: `/start`, `/forecast`, `/status`, `/shortfalls`, `/recurring`, `/anomalies`, `/narrative`, `/history`, `/alert on/off`, `/help`
  - Automated shortfall alert job — runs every 6 hours, sends message if shortfall within 30 days
- [x] `README.md` — setup instructions, CLI usage, Telegram commands, CSV format, project structure, env var reference

### Done When
A reviewer can clone the repo, follow the README, upload the sample CSV, and see the full dashboard working — forecast chart, narrative, and a Telegram alert if a shortfall is projected.

---

## Phase Summary

| Phase | Focus | Key Output |
|---|---|---|
| 1 | Foundation | Git, SQLite, CSV cleaner, CLI |
| 2 | Data Processing | Categoriser, aggregator, sample data |
| 3 | Analysis Engine | Recurring detector, anomaly detector |
| 4 | Forecasting + Explanation | Prophet model, shortfall detection, DeepSeek narrative |
| 5 | Delivery Layer | Streamlit dashboard, Telegram bot, README |