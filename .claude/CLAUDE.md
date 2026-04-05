# OpenSight — Claude Code Instructions

## Project Overview

OpenSight is an intelligent cash flow forecasting engine built in Python. It ingests CSV transaction data, trains a Prophet time-series model, detects recurring payments and anomalies, generates 30/60/90-day forecasts with confidence intervals, and delivers plain-language explanations via DeepSeek — all surfaced through a Streamlit dashboard and Telegram alerts.

**GitHub:** https://github.com/Zahrinnnnn/OpenSight.git

**Purpose:** This is a resume/CV portfolio project — the code quality, architecture, and commit history will be seen by potential employers. Keep everything clean, professional, and genuinely well-built.

---

## Build Status

| Phase | Focus | Status |
|---|---|---|
| 1 | Foundation — git, structure, SQLite, cleaner, CLI | ✅ Complete |
| 2 | Data Processing — categoriser, aggregator, sample data | ✅ Complete |
| 3 | Analysis Engine — recurring detector, anomaly detector | ✅ Complete |
| 4 | Forecasting + Explanation — Prophet, shortfall, DeepSeek | ✅ Complete |
| 5 | Delivery — Streamlit dashboard, Telegram bot, README | ✅ Complete |

---

## Git & Commit Rules

- All commits must be authored as **Zahrinnnn** with email **zahrin16@proton.me** only
- Never add "Co-Authored-By: Claude" or any AI attribution to commits
- Commit messages must read like a human wrote them — short, direct, in plain English
- Good examples: `add recurring payment detector`, `fix date parsing for mixed formats`, `update Prophet config to use multiplicative seasonality`
- Bad examples: `refactor: implement AbstractDataProcessingPipelineFactory`, `feat(forecasting): add interval_width parameter`

Configure git identity before committing:
```bash
git config user.name "Zahrinnnn"
git config user.email "zahrin16@proton.me"
```

---

## Code Style

- Write human-readable code — clear variable names, straightforward logic
- Keep functions short and focused on one thing
- Prefer explicit over clever — no one-liners that need decoding
- Add comments only where the logic genuinely needs explaining, not everywhere
- Use docstrings sparingly — only for functions where the purpose isn't obvious from the name and parameters
- Malaysian Ringgit context: amounts are always in RM, positive values only, inflow/outflow typed separately

---

## Project Structure

```
opensight/
├── main.py                 # CLI entry point
├── bot.py                  # Telegram bot
├── app.py                  # Streamlit entry point
├── requirements.txt
├── .env                    # Never commit this
├── data/
│   ├── database.db
│   ├── uploads/
│   ├── models/             # Saved Prophet models
│   └── reports/
├── src/
│   ├── processing/         # cleaner.py, categoriser.py, aggregator.py
│   ├── analysis/           # recurring.py, anomaly.py, seasonality.py
│   ├── forecasting/        # prophet_model.py, scenarios.py, shortfall.py
│   ├── explanation/        # deepseek.py
│   ├── database/           # connection.py, queries.py
│   └── utils/              # validators.py, holidays.py, logger.py
├── tests/
│   ├── test_processing.py
│   ├── test_forecasting.py
│   ├── test_analysis.py
│   └── fixtures/
│       └── sample_transactions.csv
└── ui/
    └── pages/              # home, overview, forecast, cashflow, recurring, anomalies, narrative, history
```

---

## Architecture Summary

The pipeline flows in layers:

1. **Input** — raw CSV with columns: date, description, amount, type, category, account
2. **Processing** — clean dates/amounts, categorise transactions (rule-based first, DeepSeek fallback), aggregate to daily net cash flow
3. **Analysis** — detect recurring payments (rapidfuzz clustering), anomalies (IQR-based), seasonal patterns
4. **Forecasting** — Prophet model with Malaysian public holidays, 80% confidence intervals, cumulative cash position
5. **Explanation** — DeepSeek generates plain-language narrative and Telegram shortfall alerts
6. **Output** — Streamlit dashboard + Telegram bot

---

## Key Technical Decisions

- **Prophet** for forecasting, not ARIMA (ARIMA is Phase 2)
- **DeepSeek** as the only LLM — cost target under USD 0.03 per forecast run
- **SQLite** for persistence — no external database needed
- **openai SDK** pointing to DeepSeek's base URL (compatible API)
- **rapidfuzz** for fuzzy-matching transaction descriptions to detect recurring payments
- Minimum 3 months of data required; 12 months recommended for seasonal detection
- Re-uploading the same CSV must not create duplicate transactions

---

## Environment Variables

```env
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
TELEGRAM_BOT_TOKEN=your_token_here
DB_PATH=data/database.db
UPLOAD_DIR=data/uploads
MODEL_DIR=data/models
MINIMUM_BALANCE=0
ALERT_THRESHOLD=5000
HIGH_VALUE_THRESHOLD=5000
FORECAST_HORIZON=90
CONFIDENCE_INTERVAL=0.80
```

Never commit `.env`. Always load via `python-dotenv`.

---

## Transaction Categories

Rule-based keywords (checked first before calling DeepSeek):

| Keyword | Category |
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

---

## Anomaly Types

| Type | Logic |
|---|---|
| LARGE_AMOUNT | Amount > 3 standard deviations from category mean |
| UNUSUAL_TIMING | Transaction on public holiday or weekend |
| NEW_COUNTERPARTY | First-time vendor with amount above RM5,000 |
| SPIKE | Single-day outflow > 200% of 30-day average |
| GAP | No transactions for 7+ consecutive days |

---

## SQLite Schema (summary)

Tables: `transactions`, `forecast_runs`, `recurring_payments`, `anomalies`, `shortfall_alerts`

All schema definitions are in the PRD at `.claude/OpenSight_PRD.md` section 9.

---

## What NOT to Do

- Do not use ARIMA — Prophet is the chosen model
- Do not add multi-currency support — RM only for now
- Do not connect to live bank APIs — CSV input only
- Do not add multi-user support — single user
- Do not over-engineer abstractions — keep it simple and readable
- Do not commit `.env`, `data/database.db`, or any model files
- Do not add "Co-Authored-By" or AI credits to any commit