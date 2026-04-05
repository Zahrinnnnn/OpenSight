import os
import pandas as pd
from openai import OpenAI

from src.utils.logger import logger


# Rule-based keyword map — checked before hitting DeepSeek
KEYWORD_RULES = {
    "Payroll":        ["salary", "gaji", "payroll"],
    "Rent":           ["rental", "sewa", "rent"],
    "Utilities":      ["utilities", "tenaga", "unifi", "telekom", "air selangor",
                       "syabas", "indah water", "tnb"],
    "Tax":            ["tax", "lhdn", "cukai", "sst", "gst"],
    "Loan Repayment": ["loan", "pinjaman", "repayment", "instalment", "installment"],
    "Insurance":      ["insurance", "takaful", "prudential", "allianz", "aia"],
    "Dividend":       ["dividend", "dividen"],
    "Refund":         ["refund", "bayaran balik", "rebate", "credit note"],
    "Transfer":       ["transfer", "pemindahan", "interbank", "ibg", "rentas", "duitnow"],
}

VALID_CATEGORIES = [
    "Revenue", "Cost of Goods", "Payroll", "Rent", "Utilities",
    "Tax", "Loan Repayment", "Insurance", "Operating Expense",
    "CAPEX", "Transfer", "Refund", "Dividend", "Other",
]

CATEGORISE_PROMPT = """\
You are a Malaysian finance assistant. Categorise this transaction:

Description: {description}
Amount: RM {amount}
Type: {type}

Choose ONE category from:
Revenue, Cost of Goods, Payroll, Rent, Utilities, Tax, Loan Repayment,
Insurance, Operating Expense, CAPEX, Transfer, Refund, Dividend, Other

Respond with ONLY the category name, nothing else."""


def categorise_by_rules(description: str) -> str | None:
    """Check description against keyword rules. Returns category or None."""
    lowered = description.lower()
    for category, keywords in KEYWORD_RULES.items():
        for keyword in keywords:
            if keyword in lowered:
                return category
    return None


def _get_deepseek_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def categorise_via_deepseek(description: str, amount: float, tx_type: str) -> str:
    """Call DeepSeek to categorise a single transaction. Returns 'Other' on any error."""
    try:
        client = _get_deepseek_client()
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        prompt = CATEGORISE_PROMPT.format(
            description=description,
            amount=f"{amount:,.2f}",
            type=tx_type,
        )

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0,
        )

        raw = response.choices[0].message.content.strip()

        # Validate the response is a known category
        for cat in VALID_CATEGORIES:
            if raw.lower() == cat.lower():
                return cat

        logger.warning(f"DeepSeek returned unknown category '{raw}' — falling back to Other")
        return "Other"

    except Exception as e:
        logger.error(f"DeepSeek categorisation failed: {e}")
        return "Other"


def categorise_transactions(df: pd.DataFrame, use_deepseek: bool = True) -> pd.DataFrame:
    """
    Assign a category to every transaction.
    Rule-based first. DeepSeek fallback for anything unmatched.
    Rows that already have a category are left as-is.
    """
    df = df.copy()
    rule_hits = 0
    deepseek_hits = 0
    already_set = 0

    for i, row in df.iterrows():
        existing = row.get("category")
        if pd.notna(existing) and str(existing).strip():
            already_set += 1
            continue

        rule_result = categorise_by_rules(str(row["description"]))
        if rule_result:
            df.at[i, "category"] = rule_result
            rule_hits += 1
            continue

        if use_deepseek:
            deepseek_result = categorise_via_deepseek(
                str(row["description"]), float(row["amount"]), str(row["type"])
            )
            df.at[i, "category"] = deepseek_result
            deepseek_hits += 1
        else:
            df.at[i, "category"] = "Other"

    logger.info(
        f"Categorisation done — {already_set} pre-set, "
        f"{rule_hits} via rules, {deepseek_hits} via DeepSeek"
    )
    return df
