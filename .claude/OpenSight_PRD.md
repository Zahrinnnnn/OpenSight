# Product Requirements Document
## OpenSight — Intelligent Cash Flow Forecasting Engine
**Version:** 1.0  
**Author:** Zahrin Bin Jasni  
**Status:** Planning  
**Last Updated:** April 2026

---

## 1. Overview

### 1.1 Project Summary
OpenSight is an intelligent cash flow forecasting engine that ingests historical transaction data from CSV, trains a time-series forecasting model (Prophet), and uses DeepSeek to explain projections in plain language. It detects seasonal patterns, recurring payments, and irregular spikes — then generates a 30/60/90-day cash flow forecast with confidence intervals, delivered via a Streamlit dashboard and optional Telegram alerts.

### 1.2 Problem Statement
Business owners and finance teams managing cash flow face:
- No visibility into future cash position until it's too late
- Manual cash flow projections are time-consuming and often inaccurate
- Recurring payments are tracked mentally, not systematically
- Seasonal patterns are only recognised in hindsight
- Projected cash shortfalls are discovered too late to act on
- Finance reports show history — not what's coming next

### 1.3 Objective
Build a Python application that:
- Ingests raw transaction CSV as standalone input
- Cleans and categorises transactions automatically
- Trains a Prophet forecasting model on historical cash flow
- Detects recurring payments, seasonal patterns, and anomalies
- Generates 30/60/90-day cash flow forecast with confidence bands
- Uses DeepSeek to explain the forecast in plain language
- Alerts on projected cash shortfalls via Telegram
- Delivers everything through a clean Streamlit dashboard
- Runs entirely on free tier with DeepSeek as the only cost

---

## 2. Scope

### In Scope
- CSV transaction data input (standalone, no external dependencies)
- Automated transaction categorisation using rule-based + DeepSeek fallback
- Prophet time-series forecasting (30/60/90-day horizon)
- Recurring payment detection
- Seasonal pattern identification
- Anomaly detection on historical data
- Plain-language forecast explanation via DeepSeek
- Cash shortfall alerting via Telegram
- Streamlit dashboard with interactive visualisations
- SQLite for data persistence and forecast history
- Free tier only — DeepSeek pay-as-you-go only cost

### Out of Scope
- Live bank API connection
- Multi-currency forecasting
- Integration with external accounting software
- ARIMA model (Prophet covers this scope adequately)
- Mobile app
- Multi-user support
- Budget vs forecast comparison (Phase 2)

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   INPUT LAYER                        │
│              Raw Transaction CSV                     │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│               DATA PROCESSING LAYER                  │
│   Cleaner │ Categoriser │ Aggregator │ Validator     │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                  ANALYSIS LAYER                      │
│  Recurring Detector │ Anomaly Detector │ Seasonality │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│               FORECASTING LAYER                      │
│         Prophet Model │ Confidence Intervals         │
│         30/60/90-day Horizon │ Scenario Engine       │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│              EXPLANATION LAYER                       │
│         DeepSeek — Plain Language Narrative          │
│         Shortfall Alerts │ Action Recommendations    │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                  OUTPUT LAYER                        │
│     Streamlit Dashboard │ Telegram Alerts │ Excel    │
└─────────────────────────────────────────────────────┘
```

---

## 4. Input Data Specification

### 4.1 Expected CSV Format

```csv
date,description,amount,type,category,account
2026-01-05,Client Payment - ABC Sdn Bhd,15000.00,inflow,Revenue,CIMB
2026-01-08,Office Rental January,3500.00,outflow,Operating Expense,CIMB
2026-01-10,Salary Run,8200.00,outflow,Payroll,HLB
2026-01-15,Vendor Payment - Supplier X,1200.00,outflow,Cost of Goods,CIMB
```

### 4.2 Required Columns

| Column | Type | Required | Notes |
|---|---|---|---|
| date | Date | Yes | Any common format, auto-parsed |
| description | Text | Yes | Transaction narration |
| amount | Decimal | Yes | Always positive |
| type | Text | Yes | inflow or outflow |
| category | Text | No | Auto-assigned if missing |
| account | Text | No | Bank account name |

### 4.3 Minimum Data Requirements
- Minimum 3 months of historical data for meaningful forecast
- Recommended 12 months for seasonal pattern detection
- At least 30 data points (transactions) for model training

---

## 5. Data Processing

### 5.1 Data Cleaning Pipeline

```python
def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    # 1. Parse dates with dateutil — handle mixed formats
    # 2. Convert amounts to float — strip commas and symbols
    # 3. Standardise type column — inflow/outflow/credit/debit
    # 4. Strip and normalise description text
    # 5. Remove true duplicates — same date, description, amount
    # 6. Flag and quarantine suspicious rows for review
    # 7. Sort by date ascending
    return cleaned_df
```

### 5.2 Transaction Categorisation

**Rule-Based Categories (checked first):**

| Keyword Pattern | Category |
|---|---|
| salary, gaji, payroll | Payroll |
| rental, sewa, rent | Rent |
| utilities, tenaga, air, unifi, telekom | Utilities |
| tax, lhdn, cukai, sst | Tax |
| loan, pinjaman, repayment | Loan Repayment |
| insurance, takaful | Insurance |
| dividend, dividen | Dividend |
| refund, bayaran balik | Refund |
| transfer, pemindahan | Transfer |

**DeepSeek Fallback (for unmatched descriptions):**
```python
CATEGORISE_PROMPT = """
You are a Malaysian finance assistant. Categorise this transaction:

Description: {description}
Amount: RM {amount}
Type: {type}

Choose ONE category from:
Revenue, Cost of Goods, Payroll, Rent, Utilities, Tax, Loan Repayment,
Insurance, Operating Expense, CAPEX, Transfer, Refund, Dividend, Other

Respond with ONLY the category name, nothing else.
"""
```

### 5.3 Daily Aggregation for Forecasting

```python
def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    # Aggregate to daily net cash flow for Prophet
    # net_flow = sum(inflows) - sum(outflows) per day
    # Fill missing days with 0
    # Create Prophet-compatible ds/y columns
    daily = df.groupby('date').apply(
        lambda x: x[x.type == 'inflow']['amount'].sum() -
                  x[x.type == 'outflow']['amount'].sum()
    ).reset_index()
    daily.columns = ['ds', 'y']
    return daily
```

---

## 6. Analysis Engine

### 6.1 Recurring Payment Detection

```python
def detect_recurring_payments(df: pd.DataFrame) -> list[RecurringPayment]:
    # Group by description similarity (rapidfuzz clustering)
    # For each cluster, check if amounts and intervals are regular
    # Regular = same amount appearing within 25-35 day intervals
    # Flag as: Monthly Fixed, Monthly Variable, Weekly, Ad-hoc
    # Return list of RecurringPayment objects with:
    #   - description, amount, frequency, next_expected_date, confidence
```

**RecurringPayment Schema:**
```python
@dataclass
class RecurringPayment:
    description: str
    category: str
    average_amount: float
    frequency: str           # Monthly, Weekly, Quarterly
    last_occurrence: date
    next_expected: date
    confidence: float        # 0.0 to 1.0
    is_inflow: bool
```

### 6.2 Anomaly Detection

```python
def detect_anomalies(df: pd.DataFrame) -> list[Anomaly]:
    # Method: IQR-based outlier detection per category
    # Flag transactions where amount > Q3 + 1.5 * IQR for that category
    # Also flag: transactions on public holidays
    # Also flag: unusually large single-day outflows
    # Also flag: sudden new vendors/counterparties with large amounts
```

**Anomaly Types:**

| Type | Logic |
|---|---|
| LARGE_AMOUNT | Amount > 3 standard deviations from category mean |
| UNUSUAL_TIMING | Transaction on public holiday or weekend (for business accounts) |
| NEW_COUNTERPARTY | First-time vendor with amount above RM5,000 threshold |
| SPIKE | Single day outflow > 200% of 30-day average daily outflow |
| GAP | No transactions for 7+ consecutive days (unusual for active accounts) |

### 6.3 Seasonality Detection
Prophet handles this automatically via:
- `yearly_seasonality=True` — annual patterns
- `weekly_seasonality=True` — day-of-week patterns
- `monthly_seasonality` — custom monthly fourier terms

Additional manual detection:
- Month-end spike detection (payroll, rent, utilities)
- Quarter-end patterns
- Year-end anomalies

---

## 7. Forecasting Engine

### 7.1 Prophet Model Configuration

```python
from prophet import Prophet

def train_forecast_model(daily_df: pd.DataFrame) -> Prophet:
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        seasonality_mode='multiplicative',
        changepoint_prior_scale=0.05,    # Controls trend flexibility
        seasonality_prior_scale=10,
        interval_width=0.80              # 80% confidence interval
    )

    # Add Malaysian public holidays as regressors
    model.add_country_holidays(country_name='MY')

    # Add recurring payment events as custom seasonality
    # Add month-end effect as custom regressor

    model.fit(daily_df)
    return model
```

### 7.2 Forecast Generation

```python
def generate_forecast(
    model: Prophet,
    horizon_days: int = 90
) -> pd.DataFrame:
    future = model.make_future_dataframe(periods=horizon_days)
    forecast = model.predict(future)

    # Returns dataframe with:
    # ds — date
    # yhat — predicted net cash flow
    # yhat_lower — lower confidence bound (80%)
    # yhat_upper — upper confidence bound (80%)
    # trend — underlying trend component
    # yearly — yearly seasonality component
    # weekly — weekly seasonality component

    return forecast
```

### 7.3 Cumulative Cash Position

```python
def calculate_cash_position(
    forecast: pd.DataFrame,
    opening_balance: float
) -> pd.DataFrame:
    # Cumulative sum of yhat from opening balance
    # Shows projected closing balance per day
    # Calculate worst case (yhat_lower cumulative)
    # Calculate best case (yhat_upper cumulative)
    forecast['cash_position'] = opening_balance + forecast['yhat'].cumsum()
    forecast['worst_case'] = opening_balance + forecast['yhat_lower'].cumsum()
    forecast['best_case'] = opening_balance + forecast['yhat_upper'].cumsum()
    return forecast
```

### 7.4 Shortfall Detection

```python
def detect_shortfalls(
    forecast: pd.DataFrame,
    minimum_balance: float = 0,
    alert_threshold: float = 5000
) -> list[Shortfall]:
    # Find all projected dates where cash_position < minimum_balance
    # Find all dates where cash_position < alert_threshold
    # Calculate days until first shortfall
    # Calculate magnitude of shortfall
    # Return list of Shortfall objects
```

---

## 8. DeepSeek Explanation Layer

### 8.1 Forecast Narrative Prompt

```python
FORECAST_NARRATIVE_PROMPT = """
You are a senior finance officer explaining a cash flow forecast to a business owner.

HISTORICAL SUMMARY (last 3 months):
- Average Monthly Inflow: RM {avg_inflow}
- Average Monthly Outflow: RM {avg_outflow}
- Average Net Cash Flow: RM {avg_net}
- Current Cash Balance: RM {current_balance}

FORECAST SUMMARY (next 90 days):
- Projected 30-day Net Cash Flow: RM {forecast_30}
- Projected 60-day Net Cash Flow: RM {forecast_60}
- Projected 90-day Net Cash Flow: RM {forecast_90}
- Projected Closing Balance (90 days): RM {closing_balance}
- Shortfall Risk: {shortfall_risk}

RECURRING PAYMENTS DETECTED:
{recurring_payments}

ANOMALIES DETECTED IN HISTORY:
{anomalies}

Write a clear, professional 4-5 sentence cash flow commentary that:
1. Summarises the current cash position and trend
2. Highlights the key drivers of the forecast
3. Flags any shortfall risk clearly with timeline
4. Gives 1-2 specific recommended actions
Use plain language suitable for a non-technical business owner.
"""
```

### 8.2 Shortfall Alert Prompt

```python
SHORTFALL_ALERT_PROMPT = """
A cash flow shortfall has been detected. Write a brief, urgent alert message
suitable for Telegram (max 200 words).

Projected shortfall date: {shortfall_date}
Projected balance at shortfall: RM {shortfall_amount}
Days until shortfall: {days_until}
Primary cause: {primary_cause}

Include: what's happening, when, why, and what to do immediately.
Keep it concise and actionable.
"""
```

---

## 9. SQLite Schema

```sql
-- Transaction history
CREATE TABLE transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE NOT NULL,
    description     TEXT NOT NULL,
    amount          REAL NOT NULL,
    type            TEXT NOT NULL,
    category        TEXT,
    account         TEXT,
    is_recurring    INTEGER DEFAULT 0,
    is_anomaly      INTEGER DEFAULT 0,
    source_file     TEXT,
    imported_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Forecast runs
CREATE TABLE forecast_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date        DATETIME DEFAULT CURRENT_TIMESTAMP,
    data_from       DATE,
    data_to         DATE,
    opening_balance REAL,
    horizon_days    INTEGER,
    forecast_30     REAL,
    forecast_60     REAL,
    forecast_90     REAL,
    closing_balance REAL,
    shortfall_risk  TEXT,
    shortfall_date  DATE,
    narrative       TEXT,
    model_path      TEXT
);

-- Recurring payments
CREATE TABLE recurring_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    description     TEXT,
    category        TEXT,
    average_amount  REAL,
    frequency       TEXT,
    last_occurrence DATE,
    next_expected   DATE,
    confidence      REAL,
    is_inflow       INTEGER,
    detected_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Detected anomalies
CREATE TABLE anomalies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id  INTEGER REFERENCES transactions(id),
    anomaly_type    TEXT,
    severity        TEXT,
    description     TEXT,
    detected_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Shortfall alerts
CREATE TABLE shortfall_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_run_id INTEGER REFERENCES forecast_runs(id),
    shortfall_date  DATE,
    projected_balance REAL,
    days_until      INTEGER,
    alert_sent      INTEGER DEFAULT 0,
    alert_sent_at   DATETIME,
    resolved        INTEGER DEFAULT 0
);
```

---

## 10. Streamlit Dashboard

### 10.1 Pages

| Page | Content |
|---|---|
| Home | Upload CSV, set opening balance, run forecast |
| Overview | Current balance, forecast summary KPIs, shortfall alerts |
| Forecast | Interactive forecast chart with confidence bands, 30/60/90 toggle |
| Inflow / Outflow | Category breakdown, trend charts, MoM comparison |
| Recurring Payments | Detected recurring items, next expected dates, calendar view |
| Anomalies | Historical anomaly list with severity and description |
| Narrative | DeepSeek-generated plain language commentary |
| History | Past forecast runs with drill-down |

### 10.2 Overview Page KPIs
- Current Cash Balance (manual input or calculated)
- Projected Balance in 30 days
- Projected Balance in 60 days
- Projected Balance in 90 days
- Monthly Burn Rate (average)
- Months of Runway (balance divided by burn rate)
- Shortfall Alert (red banner if shortfall detected within 90 days)

### 10.3 Forecast Chart Specification
- X-axis: Date (historical + forecast period)
- Y-axis: Daily net cash flow AND cumulative cash position (toggle)
- Historical data: solid line, dark navy
- Forecast: dashed line, steel blue
- Confidence band: shaded area between yhat_lower and yhat_upper
- Shortfall threshold line: red horizontal line at minimum balance
- Recurring payment markers: vertical dotted lines on expected dates
- Anomaly markers: orange dots on historical anomaly dates
- Toggle: 30 / 60 / 90 day horizon
- Zoom: select date range with range slider

---

## 11. Telegram Bot Interface

### 11.1 Commands

```
/start          — Welcome and setup instructions
/forecast       — Run new forecast (prompts for CSV upload)
/status         — Current cash position and latest forecast summary
/shortfalls     — List all projected shortfalls
/recurring      — Show detected recurring payments
/anomalies      — Show detected anomalies in history
/narrative      — Get DeepSeek plain language commentary
/history        — Past forecast runs
/alert on/off   — Enable or disable shortfall alerts
/help           — All commands
```

### 11.2 Automated Shortfall Alert
When a shortfall is detected within 30 days, Telegram sends:
```
OPENSIGHT ALERT — Cash Shortfall Detected

Your projected cash balance will drop below RM0 in 18 days
(estimated date: 19 May 2026).

Projected balance: -RM 3,420
Primary driver: Recurring payroll of RM8,200 due 15 May
with no matching inflows projected in that period.

Recommended action: Follow up on 3 outstanding AR invoices
totalling RM12,500 due this week to cover the shortfall.
```

---

## 12. Project Structure

```
opensight/
├── main.py                 # CLI entry point
├── bot.py                  # Telegram bot
├── app.py                  # Streamlit entry point
├── requirements.txt
├── README.md
├── .env
├── data/
│   ├── database.db
│   ├── uploads/
│   ├── models/             # Saved Prophet models
│   └── reports/
├── src/
│   ├── processing/
│   │   ├── cleaner.py
│   │   ├── categoriser.py
│   │   └── aggregator.py
│   ├── analysis/
│   │   ├── recurring.py
│   │   ├── anomaly.py
│   │   └── seasonality.py
│   ├── forecasting/
│   │   ├── prophet_model.py
│   │   ├── scenarios.py
│   │   └── shortfall.py
│   ├── explanation/
│   │   └── deepseek.py
│   ├── database/
│   │   ├── connection.py
│   │   └── queries.py
│   └── utils/
│       ├── validators.py
│       ├── holidays.py
│       └── logger.py
├── tests/
│   ├── test_processing.py
│   ├── test_forecasting.py
│   ├── test_analysis.py
│   └── fixtures/
│       └── sample_transactions.csv
└── ui/
    └── pages/
        ├── home.py
        ├── overview.py
        ├── forecast.py
        ├── cashflow.py
        ├── recurring.py
        ├── anomalies.py
        ├── narrative.py
        └── history.py
```

---

## 13. Dependencies

```txt
# Forecasting
prophet>=1.1.5
pandas>=2.0.0
numpy>=1.24.0

# LLM
openai>=1.0.0

# Matching and clustering
rapidfuzz>=3.0.0
scikit-learn>=1.3.0

# Database
# sqlite3 — stdlib

# Telegram
python-telegram-bot>=20.0

# Web UI
streamlit>=1.30.0
plotly>=5.18.0

# Utilities
python-dotenv>=1.0.0
python-dateutil>=2.8.0
loguru>=0.7.0
click>=8.1.0
rich>=13.0.0
```

---

## 14. Environment Variables

```env
# DeepSeek
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# Telegram
TELEGRAM_BOT_TOKEN=your_token_here

# App config
DB_PATH=data/database.db
UPLOAD_DIR=data/uploads
MODEL_DIR=data/models
MINIMUM_BALANCE=0
ALERT_THRESHOLD=5000
HIGH_VALUE_THRESHOLD=5000
FORECAST_HORIZON=90
CONFIDENCE_INTERVAL=0.80
```

---

## 15. Testing Requirements

| Test | Expected Result |
|---|---|
| Load 12 months CSV, 500 transactions | All transactions imported, dates parsed correctly |
| Categorise known Malaysian transaction descriptions | Correct category assigned via rule-based logic |
| Categorise unknown description via DeepSeek | Valid category returned within 3 seconds |
| Detect monthly salary payment | Flagged as Monthly Fixed recurring, confidence > 0.90 |
| Detect large unusual transaction | Flagged as LARGE_AMOUNT anomaly correctly |
| Prophet model trains on 6 months data | Model fits without error, forecast generates for 90 days |
| Shortfall detected correctly | Alert triggered when projected balance crosses threshold |
| DeepSeek narrative | Returns coherent 4-5 sentence commentary within 5 seconds |
| Telegram shortfall alert | Message delivered with correct figures |
| Streamlit forecast chart | Renders with historical, forecast, and confidence band |
| Re-upload same CSV | No duplicate transactions imported |

---

## 16. Milestones

| Phase | Deliverable | Target |
|---|---|---|
| 1 | Project structure, SQLite schema, data cleaning pipeline | Week 1 |
| 2 | Categoriser — rule-based + DeepSeek fallback | Week 1 |
| 3 | Recurring payment detector | Week 2 |
| 4 | Anomaly detector | Week 2 |
| 5 | Prophet model — training, forecasting, confidence intervals | Week 2-3 |
| 6 | Shortfall detection and cash position calculation | Week 3 |
| 7 | DeepSeek explanation layer — narrative and alerts | Week 3 |
| 8 | Streamlit dashboard — all pages | Week 3-4 |
| 9 | Telegram bot — commands and automated alerts | Week 4 |
| 10 | Sample data generation, testing, README | Week 4-5 |

---

## 17. Success Criteria
- Forecast generates for 90 days with confidence intervals on any CSV input
- Recurring payments detected with 85%+ accuracy on test data
- Anomalies flagged without false positives on clean historical data
- DeepSeek narrative is coherent, factual, and actionable
- Shortfall alert delivered via Telegram before the projected shortfall date
- Streamlit dashboard renders forecast chart cleanly with all interactive features
- Prophet model retrained automatically on each new CSV import
- Total DeepSeek API cost per forecast run under USD 0.03
- README is clear enough for a technical reviewer to run locally

---

## 18. Future Enhancements (Phase 2)
- ARIMA model as alternative forecaster with model comparison
- Budget vs forecast overlay — import budget CSV and compare
- Scenario engine — best case, base case, worst case toggle
- Multi-account aggregation across CIMB, HLB, Maybank
- WhatsApp alerts via Twilio
- Streamlit Cloud deployment (free tier)
- Weekly automated forecast refresh via cron
- Export forecast to Excel with chart embedded

---

*This PRD is a living document. Update as scope or requirements change.*
