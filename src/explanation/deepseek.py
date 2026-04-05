import os

from openai import OpenAI

from src.utils.logger import logger


FORECAST_NARRATIVE_PROMPT = """\
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
Use plain language suitable for a non-technical business owner."""


SHORTFALL_ALERT_PROMPT = """\
A cash flow shortfall has been detected. Write a brief, urgent alert message
suitable for Telegram (max 200 words).

Projected shortfall date: {shortfall_date}
Projected balance at shortfall: RM {shortfall_amount}
Days until shortfall: {days_until}
Primary cause: {primary_cause}

Include: what's happening, when, why, and what to do immediately.
Keep it concise and actionable."""


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def _call_deepseek(prompt: str, max_tokens: int = 400) -> str:
    """Make a single call to DeepSeek. Returns empty string on any error."""
    try:
        client = _get_client()
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"DeepSeek call failed: {e}")
        return ""


def _format_recurring(recurring_list: list) -> str:
    if not recurring_list:
        return "None detected"
    lines = []
    for r in recurring_list[:8]:  # cap at 8 to keep prompt concise
        direction = "inflow" if r.is_inflow else "outflow"
        lines.append(
            f"- {r.description}: RM {r.average_amount:,.2f} {r.frequency} {direction}, "
            f"next expected {r.next_expected}"
        )
    return "\n".join(lines)


def _format_anomalies(anomaly_list: list) -> str:
    if not anomaly_list:
        return "None detected"
    # Only surface HIGH and MEDIUM severity items to keep the prompt clean
    notable = [a for a in anomaly_list if a.severity in ("HIGH", "MEDIUM")][:6]
    if not notable:
        return "No significant anomalies"
    return "\n".join(f"- [{a.anomaly_type}] {a.description}" for a in notable)


def generate_forecast_narrative(
    avg_inflow: float,
    avg_outflow: float,
    avg_net: float,
    current_balance: float,
    forecast_30: float,
    forecast_60: float,
    forecast_90: float,
    closing_balance: float,
    shortfall_risk: str,
    recurring_list: list,
    anomaly_list: list,
) -> str:
    prompt = FORECAST_NARRATIVE_PROMPT.format(
        avg_inflow=f"{avg_inflow:,.2f}",
        avg_outflow=f"{avg_outflow:,.2f}",
        avg_net=f"{avg_net:,.2f}",
        current_balance=f"{current_balance:,.2f}",
        forecast_30=f"{forecast_30:,.2f}",
        forecast_60=f"{forecast_60:,.2f}",
        forecast_90=f"{forecast_90:,.2f}",
        closing_balance=f"{closing_balance:,.2f}",
        shortfall_risk=shortfall_risk,
        recurring_payments=_format_recurring(recurring_list),
        anomalies=_format_anomalies(anomaly_list),
    )

    logger.info("Generating forecast narrative via DeepSeek")
    narrative = _call_deepseek(prompt, max_tokens=450)

    if not narrative:
        narrative = (
            f"Current cash balance is RM {current_balance:,.2f}. "
            f"The 90-day forecast projects a net flow of RM {forecast_90:,.2f}, "
            f"closing at RM {closing_balance:,.2f}. "
            f"Shortfall risk: {shortfall_risk}."
        )

    logger.success("Narrative generated")
    return narrative


def generate_shortfall_alert(
    shortfall_date,
    shortfall_amount: float,
    days_until: int,
    primary_cause: str,
) -> str:
    prompt = SHORTFALL_ALERT_PROMPT.format(
        shortfall_date=str(shortfall_date),
        shortfall_amount=f"{shortfall_amount:,.2f}",
        days_until=days_until,
        primary_cause=primary_cause,
    )

    logger.info("Generating shortfall alert via DeepSeek")
    alert = _call_deepseek(prompt, max_tokens=300)

    if not alert:
        alert = (
            f"OPENSIGHT ALERT — Cash Shortfall Detected\n\n"
            f"Projected balance drops to RM {shortfall_amount:,.2f} "
            f"in {days_until} days ({shortfall_date}).\n"
            f"Cause: {primary_cause}\n\n"
            f"Act now to avoid a cash shortfall."
        )

    return alert
