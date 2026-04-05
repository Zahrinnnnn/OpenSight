import click
import pandas as pd
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box

load_dotenv()

from src.utils.logger import logger
from src.utils.validators import load_and_validate_csv, ValidationError
from src.processing.cleaner import clean_transactions, flag_suspicious_rows
from src.processing.categoriser import categorise_transactions
from src.processing.aggregator import aggregate_daily
from src.database.connection import init_db, get_connection
from src.analysis.recurring import detect_recurring_payments, save_recurring_payments
from src.analysis.anomaly import detect_anomalies, save_anomalies
from src.analysis.seasonality import get_seasonality_summary
from src.forecasting.prophet_model import train_forecast_model, generate_forecast, save_model
from src.forecasting.shortfall import (
    calculate_cash_position,
    detect_shortfalls,
    get_forecast_summary,
    save_shortfall_alerts,
)
from src.explanation.deepseek import generate_forecast_narrative, generate_shortfall_alert
from src.database.queries import (
    save_forecast_run,
    get_recurring_payments,
    get_anomalies,
)

console = Console()


def store_transactions(df, source_file: str) -> int:
    """Insert cleaned transactions into the database. Skips existing duplicates."""
    conn = get_connection()
    cursor = conn.cursor()

    inserted = 0
    skipped = 0

    for _, row in df.iterrows():
        cursor.execute(
            """
            SELECT id FROM transactions
            WHERE date = ? AND description = ? AND amount = ? AND type = ?
            """,
            (str(row["date"].date()), row["description"], row["amount"], row["type"]),
        )
        if cursor.fetchone():
            skipped += 1
            continue

        cursor.execute(
            """
            INSERT INTO transactions (date, description, amount, type, category, account, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(row["date"].date()),
                row["description"],
                row["amount"],
                row["type"],
                row.get("category"),
                row.get("account"),
                source_file,
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()

    if skipped > 0:
        logger.info(f"Skipped {skipped} existing transactions (duplicates)")

    return inserted


@click.group()
def cli():
    """OpenSight — Cash Flow Forecasting Engine"""
    pass


@cli.command()
@click.argument("csv_path")
@click.option("--opening-balance", "-b", default=0.0, type=float,
              help="Current cash balance in RM (default: 0)")
@click.option("--no-deepseek", is_flag=True, default=False,
              help="Skip DeepSeek categorisation (use rule-based only)")
def ingest(csv_path: str, opening_balance: float, no_deepseek: bool):
    """
    Load, clean, categorise, and analyse a transaction CSV.

    CSV_PATH: path to your transaction CSV file
    """
    console.print("\n[bold cyan]OpenSight[/bold cyan] — Cash Flow Forecasting Engine\n")

    # 1. Initialise database
    init_db()

    # 2. Load and validate CSV
    console.print(f"[dim]Loading:[/dim] {csv_path}")
    try:
        df, warnings = load_and_validate_csv(csv_path)
    except ValidationError as e:
        console.print(f"[bold red]Validation error:[/bold red] {e}")
        raise SystemExit(1)

    if warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in warnings:
            console.print(f"  [yellow]•[/yellow] {w}")

    # 3. Clean
    console.print("\n[dim]Cleaning transactions...[/dim]")
    clean_df = clean_transactions(df)
    clean_df = flag_suspicious_rows(clean_df)

    suspicious = clean_df["is_suspicious"].sum()
    if suspicious > 0:
        console.print(f"[yellow]  {suspicious} rows flagged as suspicious — review recommended[/yellow]")

    # 4. Categorise
    console.print("[dim]Categorising transactions...[/dim]")
    clean_df = categorise_transactions(clean_df, use_deepseek=not no_deepseek)
    uncategorised = (clean_df["category"] == "Other").sum()
    if uncategorised > 0:
        console.print(f"[yellow]  {uncategorised} transactions categorised as Other[/yellow]")

    # 5. Store in database
    console.print("[dim]Storing in database...[/dim]")
    inserted = store_transactions(clean_df, source_file=csv_path)
    console.print(f"[green]  {inserted} new transactions stored[/green]")

    # 6. Aggregate to daily for forecasting
    daily_df = aggregate_daily(clean_df)
    console.print(f"[dim]  Daily aggregation ready — {len(daily_df)} calendar days[/dim]")

    # 7. Load stored transactions with IDs for analysis
    conn = get_connection()
    stored_df = pd.read_sql_query("SELECT * FROM transactions", conn)
    conn.close()

    # 8. Recurring payment detection
    console.print("[dim]Detecting recurring payments...[/dim]")
    recurring = detect_recurring_payments(stored_df)
    save_recurring_payments(recurring)
    console.print(f"[green]  {len(recurring)} recurring payment patterns detected[/green]")

    if recurring:
        conn = get_connection()
        cursor = conn.cursor()
        for payment in recurring:
            cursor.execute(
                "UPDATE transactions SET is_recurring = 1 WHERE description LIKE ?",
                (f"%{payment.description[:20]}%",),
            )
        conn.commit()
        conn.close()

    # 9. Anomaly detection
    console.print("[dim]Running anomaly detection...[/dim]")
    anomalies = detect_anomalies(stored_df)
    save_anomalies(anomalies, stored_df)
    high = sum(1 for a in anomalies if a.severity == "HIGH")
    console.print(
        f"[green]  {len(anomalies)} anomalies flagged[/green]"
        + (f" [red]({high} high severity)[/red]" if high else "")
    )

    # 10. Seasonality summary
    seasonality = get_seasonality_summary(stored_df)
    if seasonality["month_end_spike_categories"]:
        console.print(
            f"[dim]  Month-end spikes in: "
            f"{', '.join(seasonality['month_end_spike_categories'])}[/dim]"
        )

    # 11. Summary table
    inflows  = clean_df[clean_df["type"] == "inflow"]["amount"].sum()
    outflows = clean_df[clean_df["type"] == "outflow"]["amount"].sum()
    net      = inflows - outflows

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Rows loaded",        str(len(clean_df)))
    table.add_row("Date range",         f"{clean_df['date'].min().date()} to {clean_df['date'].max().date()}")
    table.add_row("Total inflows",      f"RM {inflows:,.2f}")
    table.add_row("Total outflows",     f"RM {outflows:,.2f}")
    table.add_row("Net cash flow",      f"RM {net:,.2f}")
    table.add_row("Opening balance",    f"RM {opening_balance:,.2f}")
    table.add_row("Recurring patterns", str(len(recurring)))
    table.add_row("Anomalies flagged",  str(len(anomalies)))

    console.print("\n")
    console.print(table)
    console.print(
        "[bold green]Ingest complete.[/bold green] "
        "Run the forecast next: [dim]python main.py forecast --opening-balance <RM>[/dim]\n"
    )


@cli.command()
@click.option("--opening-balance", "-b", default=0.0, type=float,
              help="Current cash balance in RM")
@click.option("--horizon", "-h", default=90, type=int,
              help="Forecast horizon in days (default: 90)")
@click.option("--no-deepseek", is_flag=True, default=False,
              help="Skip DeepSeek narrative generation")
def forecast(opening_balance: float, horizon: int, no_deepseek: bool):
    """
    Train Prophet on stored transactions and generate a cash flow forecast.
    Run 'ingest' first to load your CSV data.
    """
    console.print("\n[bold cyan]OpenSight[/bold cyan] — Generating Forecast\n")

    init_db()

    # Load all stored transactions
    conn = get_connection()
    stored_df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date ASC", conn)
    conn.close()

    if stored_df.empty:
        console.print("[bold red]No transactions found. Run 'ingest' first.[/bold red]")
        raise SystemExit(1)

    # Build daily aggregation from stored data
    console.print("[dim]Aggregating daily cash flow...[/dim]")
    daily_df = aggregate_daily(stored_df)

    # Train model
    console.print("[dim]Training Prophet model...[/dim]")
    model = train_forecast_model(daily_df)

    # Generate forecast
    console.print(f"[dim]Generating {horizon}-day forecast...[/dim]")
    forecast_df = generate_forecast(model, daily_df, horizon_days=horizon)

    # Calculate cash position
    forecast_df = calculate_cash_position(forecast_df, opening_balance=opening_balance)

    # Detect shortfalls
    shortfalls = detect_shortfalls(forecast_df)
    shortfall_risk = "NONE"
    shortfall_date = None
    if shortfalls:
        first = shortfalls[0]
        shortfall_risk = f"IN {first.days_until} DAYS"
        shortfall_date = str(first.shortfall_date)

    # Forecast summary figures
    summary = get_forecast_summary(forecast_df, opening_balance)

    # Historical stats for narrative (last 90 days = ~3 months)
    stored_df["date"] = pd.to_datetime(stored_df["date"])
    cutoff = stored_df["date"].max() - pd.Timedelta(days=90)
    recent = stored_df[stored_df["date"] >= cutoff]
    months = max(1, (stored_df["date"].max() - cutoff).days / 30)

    avg_inflow  = recent[recent["type"] == "inflow"]["amount"].sum() / months
    avg_outflow = recent[recent["type"] == "outflow"]["amount"].sum() / months
    avg_net     = avg_inflow - avg_outflow

    # Load recurring and anomaly records for the narrative
    recurring_df = get_recurring_payments()
    anomaly_df   = get_anomalies()

    # Rebuild dataclass-like objects for formatting helpers in deepseek.py
    from src.analysis.recurring import RecurringPayment
    from src.analysis.anomaly import Anomaly
    from datetime import date as dt_date

    def row_to_recurring(r) -> RecurringPayment:
        return RecurringPayment(
            description=r["description"],
            category=r["category"],
            average_amount=r["average_amount"],
            frequency=r["frequency"],
            last_occurrence=dt_date.fromisoformat(r["last_occurrence"]),
            next_expected=dt_date.fromisoformat(r["next_expected"]),
            confidence=r["confidence"],
            is_inflow=bool(r["is_inflow"]),
        )

    def row_to_anomaly(r) -> Anomaly:
        return Anomaly(
            transaction_id=r.get("transaction_id"),
            anomaly_type=r["anomaly_type"],
            severity=r["severity"],
            description=r["description"],
        )

    recurring_list = [row_to_recurring(r) for _, r in recurring_df.iterrows()]
    anomaly_list   = [row_to_anomaly(r) for _, r in anomaly_df.iterrows()]

    # Generate narrative
    narrative = ""
    if not no_deepseek:
        console.print("[dim]Generating DeepSeek narrative...[/dim]")
        narrative = generate_forecast_narrative(
            avg_inflow=avg_inflow,
            avg_outflow=avg_outflow,
            avg_net=avg_net,
            current_balance=opening_balance,
            forecast_30=summary["forecast_30"],
            forecast_60=summary["forecast_60"],
            forecast_90=summary["forecast_90"],
            closing_balance=summary["closing_balance"],
            shortfall_risk=shortfall_risk,
            recurring_list=recurring_list,
            anomaly_list=anomaly_list,
        )

    # Save forecast run to DB
    run_id = save_forecast_run(
        data_from=str(stored_df["date"].min().date()),
        data_to=str(stored_df["date"].max().date()),
        opening_balance=opening_balance,
        horizon_days=horizon,
        forecast_30=summary["forecast_30"],
        forecast_60=summary["forecast_60"],
        forecast_90=summary["forecast_90"],
        closing_balance=summary["closing_balance"],
        shortfall_risk=shortfall_risk,
        shortfall_date=shortfall_date,
        narrative=narrative,
        model_path=save_model(model, run_id=0),  # placeholder — update below
    )

    # Re-save with correct run_id in model filename
    model_path = save_model(model, run_id=run_id)
    conn = get_connection()
    conn.execute(
        "UPDATE forecast_runs SET model_path = ? WHERE id = ?",
        (model_path, run_id),
    )
    conn.commit()
    conn.close()

    # Save shortfall alerts
    if shortfalls:
        save_shortfall_alerts(shortfalls, forecast_run_id=run_id)

    # Print results
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Opening balance",     f"RM {opening_balance:,.2f}")
    table.add_row("Forecast 30 days",    f"RM {summary['forecast_30']:,.2f}")
    table.add_row("Forecast 60 days",    f"RM {summary['forecast_60']:,.2f}")
    table.add_row("Forecast 90 days",    f"RM {summary['forecast_90']:,.2f}")
    table.add_row("Closing balance",     f"RM {summary['closing_balance']:,.2f}")
    table.add_row("Shortfall risk",      shortfall_risk)
    table.add_row("Run ID",              str(run_id))

    console.print("\n")
    console.print(table)

    if narrative:
        console.print("\n[bold]Forecast Commentary:[/bold]")
        console.print(f"[dim]{narrative}[/dim]\n")

    if shortfalls:
        console.print(f"[bold red]⚠  Shortfall detected in {shortfalls[0].days_until} days[/bold red]")
        if not no_deepseek:
            primary_cause = (
                recurring_list[0].description if recurring_list else "elevated recurring outflows"
            )
            alert_msg = generate_shortfall_alert(
                shortfall_date=shortfalls[0].shortfall_date,
                shortfall_amount=shortfalls[0].projected_balance,
                days_until=shortfalls[0].days_until,
                primary_cause=primary_cause,
            )
            console.print(f"\n[red]{alert_msg}[/red]")

    console.print(
        "\n[bold green]Forecast complete.[/bold green] "
        "Launch the dashboard: [dim]streamlit run app.py[/dim]\n"
    )


if __name__ == "__main__":
    cli()
