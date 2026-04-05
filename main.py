import click
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

console = Console()


def store_transactions(df, source_file: str) -> int:
    """Insert cleaned transactions into the database. Skips existing duplicates."""
    conn = get_connection()
    cursor = conn.cursor()

    inserted = 0
    skipped = 0

    for _, row in df.iterrows():
        # Check if this transaction already exists
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


@click.command()
@click.argument("csv_path")
@click.option("--opening-balance", "-b", default=0.0, type=float,
              help="Current cash balance in RM (default: 0)")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
              help="Log verbosity level")
def run(csv_path: str, opening_balance: float, log_level: str):
    """
    OpenSight — Cash Flow Forecasting Engine

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
    clean_df = categorise_transactions(clean_df, use_deepseek=True)
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

    # 5. Summary table
    inflows  = clean_df[clean_df["type"] == "inflow"]["amount"].sum()
    outflows = clean_df[clean_df["type"] == "outflow"]["amount"].sum()
    net      = inflows - outflows

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Rows loaded",       str(len(clean_df)))
    table.add_row("Date range",        f"{clean_df['date'].min().date()} → {clean_df['date'].max().date()}")
    table.add_row("Total inflows",     f"RM {inflows:,.2f}")
    table.add_row("Total outflows",    f"RM {outflows:,.2f}")
    table.add_row("Net cash flow",     f"RM {net:,.2f}")
    table.add_row("Opening balance",   f"RM {opening_balance:,.2f}")

    console.print("\n")
    console.print(table)
    console.print("[bold green]Import complete.[/bold green] Run forecasting next with: [dim]python main.py forecast[/dim]\n")


if __name__ == "__main__":
    run()
