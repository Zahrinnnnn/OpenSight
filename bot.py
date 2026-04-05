import os
import logging

import pandas as pd
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

from src.database.connection import init_db
from src.database.queries import (
    get_latest_forecast_run,
    get_all_forecast_runs,
    get_recurring_payments,
    get_anomalies,
    get_shortfall_alerts,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALERT_THRESHOLD_DAYS = 30  # send auto-alert if shortfall within this many days


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(amount: float) -> str:
    return f"RM {amount:,.2f}"


def _get_run() -> dict | None:
    return get_latest_forecast_run()


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *Welcome to OpenSight*\n\n"
        "I give you cash flow forecasts and shortfall alerts.\n\n"
        "Run `/help` to see all commands.",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "*OpenSight Commands*\n\n"
        "/status — Current cash position and latest forecast summary\n"
        "/forecast — Latest 30/60/90-day forecast figures\n"
        "/shortfalls — All projected shortfall dates\n"
        "/recurring — Detected recurring payments\n"
        "/anomalies — Flagged anomalies in history\n"
        "/narrative — DeepSeek plain-language commentary\n"
        "/history — Past forecast runs\n"
        "/alert on | off — Enable or disable automated shortfall alerts\n"
        "/help — This message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    run = _get_run()
    if not run:
        await update.message.reply_text("No forecast found. Run the pipeline first.")
        return

    opening  = run.get("opening_balance", 0) or 0
    closing  = run.get("closing_balance", 0) or 0
    risk     = run.get("shortfall_risk", "NONE")
    run_date = run.get("run_date", "N/A")

    text = (
        f"📊 *Cash Flow Status*\n\n"
        f"Opening balance: {_fmt(opening)}\n"
        f"Projected closing (90d): {_fmt(closing)}\n"
        f"Shortfall risk: `{risk}`\n"
        f"Last forecast: {run_date}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    run = _get_run()
    if not run:
        await update.message.reply_text("No forecast found. Run the pipeline first.")
        return

    opening = run.get("opening_balance", 0) or 0
    fc30    = run.get("forecast_30", 0) or 0
    fc60    = run.get("forecast_60", 0) or 0
    fc90    = run.get("forecast_90", 0) or 0

    text = (
        f"📈 *Forecast Summary*\n\n"
        f"Current balance: {_fmt(opening)}\n"
        f"Projected in 30 days: {_fmt(opening + fc30)}\n"
        f"Projected in 60 days: {_fmt(opening + fc60)}\n"
        f"Projected in 90 days: {_fmt(opening + fc90)}\n"
        f"Net flow (30d): {_fmt(fc30)}\n"
        f"Net flow (60d): {_fmt(fc60)}\n"
        f"Net flow (90d): {_fmt(fc90)}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_shortfalls(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    run = _get_run()
    if not run:
        await update.message.reply_text("No forecast found.")
        return

    alerts = get_shortfall_alerts(forecast_run_id=run["id"])
    if alerts.empty:
        await update.message.reply_text("✅ No shortfalls projected in the current forecast.")
        return

    lines = ["⚠️ *Projected Shortfall Dates*\n"]
    for _, row in alerts.head(10).iterrows():
        lines.append(
            f"• {row['shortfall_date']} — {_fmt(row['projected_balance'])} "
            f"({row['days_until']} days away)"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    df = get_recurring_payments()
    if df.empty:
        await update.message.reply_text("No recurring payments detected.")
        return

    lines = [f"🔁 *Recurring Payments* ({len(df)} patterns)\n"]
    for _, row in df.head(12).iterrows():
        direction = "↑" if row["is_inflow"] else "↓"
        lines.append(
            f"{direction} {row['description'][:35]} — "
            f"{_fmt(row['average_amount'])} {row['frequency']} "
            f"(next: {row['next_expected']})"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_anomalies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    df = get_anomalies()
    if df.empty:
        await update.message.reply_text("No anomalies detected.")
        return

    high   = (df["severity"] == "HIGH").sum()
    medium = (df["severity"] == "MEDIUM").sum()
    low    = (df["severity"] == "LOW").sum()

    lines = [
        f"🚨 *Anomaly Report*\n",
        f"Total: {len(df)}  |  High: {high}  |  Medium: {medium}  |  Low: {low}\n",
    ]

    # Show HIGH severity first
    notable = df[df["severity"].isin(["HIGH", "MEDIUM"])].head(8)
    for _, row in notable.iterrows():
        emoji = "🔴" if row["severity"] == "HIGH" else "🟠"
        lines.append(f"{emoji} [{row['anomaly_type']}] {row['description'][:80]}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_narrative(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    run = _get_run()
    if not run:
        await update.message.reply_text("No forecast found.")
        return

    narrative = run.get("narrative", "")
    if not narrative:
        await update.message.reply_text(
            "No narrative for the latest run. "
            "Re-run the pipeline with DeepSeek enabled to generate one."
        )
        return

    await update.message.reply_text(f"📝 *Forecast Commentary*\n\n{narrative}", parse_mode="Markdown")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    df = get_all_forecast_runs()
    if df.empty:
        await update.message.reply_text("No forecast runs on record.")
        return

    lines = [f"🗂️ *Forecast History* ({len(df)} runs)\n"]
    for _, row in df.head(8).iterrows():
        risk = row.get("shortfall_risk", "NONE") or "NONE"
        lines.append(
            f"• Run #{row['id']} — {row['run_date'][:10]} — "
            f"Closing: {_fmt(row.get('closing_balance', 0) or 0)} — "
            f"Risk: {risk}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Usage: /alert on  or  /alert off")
        return

    state = args[0].lower()
    # Store preference in bot data (in-memory; persists until bot restart)
    context.bot_data["alerts_enabled"] = state == "on"
    status = "enabled ✅" if state == "on" else "disabled ❌"
    await update.message.reply_text(f"Automated shortfall alerts {status}.")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Unknown command. Type /help for the list of commands.")


# ── Automated shortfall alert job ─────────────────────────────────────────────

async def check_and_send_shortfall_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Periodic job — runs every 6 hours.
    Sends a Telegram message if a shortfall is projected within ALERT_THRESHOLD_DAYS.
    Only sends if alerts are enabled and the alert hasn't been sent yet.
    """
    if not context.bot_data.get("alerts_enabled", True):
        return
    if not context.bot_data.get("chat_id"):
        return

    run = _get_run()
    if not run:
        return

    alerts = get_shortfall_alerts(forecast_run_id=run["id"])
    if alerts.empty:
        return

    imminent = alerts[
        (alerts["days_until"] <= ALERT_THRESHOLD_DAYS) &
        (alerts["alert_sent"] == 0)
    ]
    if imminent.empty:
        return

    first = imminent.iloc[0]

    from src.explanation.deepseek import generate_shortfall_alert
    run_df = get_recurring_payments()
    primary_cause = (
        run_df.iloc[0]["description"] if not run_df.empty
        else "high recurring outflows"
    )

    message = generate_shortfall_alert(
        shortfall_date=first["shortfall_date"],
        shortfall_amount=first["projected_balance"],
        days_until=int(first["days_until"]),
        primary_cause=primary_cause,
    )

    await context.bot.send_message(
        chat_id=context.bot_data["chat_id"],
        text=f"🚨 *OPENSIGHT ALERT*\n\n{message}",
        parse_mode="Markdown",
    )

    # Mark alert as sent
    from src.database.connection import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE shortfall_alerts SET alert_sent=1, alert_sent_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(first["id"]),),
    )
    conn.commit()
    conn.close()


# Store chat_id when user sends /start so we know where to send alerts
async def cmd_start_with_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.bot_data["chat_id"] = update.effective_chat.id
    await cmd_start(update, context)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data["alerts_enabled"] = True

    app.add_handler(CommandHandler("start",     cmd_start_with_chat))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("forecast",  cmd_forecast))
    app.add_handler(CommandHandler("shortfalls", cmd_shortfalls))
    app.add_handler(CommandHandler("recurring", cmd_recurring))
    app.add_handler(CommandHandler("anomalies", cmd_anomalies))
    app.add_handler(CommandHandler("narrative", cmd_narrative))
    app.add_handler(CommandHandler("history",   cmd_history))
    app.add_handler(CommandHandler("alert",     cmd_alert))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Check for shortfalls every 6 hours
    app.job_queue.run_repeating(
        check_and_send_shortfall_alert,
        interval=21600,
        first=60,
    )

    logger.info("OpenSight bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
