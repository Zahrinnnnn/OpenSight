from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from rapidfuzz import fuzz, process

from src.utils.logger import logger
from src.database.connection import get_connection


@dataclass
class RecurringPayment:
    description: str
    category: str
    average_amount: float
    frequency: str        # Monthly, Weekly, Quarterly, Ad-hoc
    last_occurrence: date
    next_expected: date
    confidence: float     # 0.0 to 1.0
    is_inflow: bool


# How many days gap between occurrences qualifies as which frequency
_FREQUENCY_BANDS = {
    "Weekly":    (5,  10),
    "Monthly":   (25, 35),
    "Quarterly": (80, 100),
}

# Minimum occurrences before we call something recurring
_MIN_OCCURRENCES = 2

# Fuzzy match threshold — descriptions above this score are considered the same payment
_SIMILARITY_THRESHOLD = 80


def _group_by_similarity(descriptions: list[str]) -> list[list[int]]:
    """
    Cluster description indices by fuzzy similarity.
    Returns list of clusters, each cluster is a list of integer indices.
    """
    used = set()
    clusters = []

    for i, desc in enumerate(descriptions):
        if i in used:
            continue
        cluster = [i]
        used.add(i)
        for j in range(i + 1, len(descriptions)):
            if j in used:
                continue
            score = fuzz.token_sort_ratio(desc, descriptions[j])
            if score >= _SIMILARITY_THRESHOLD:
                cluster.append(j)
                used.add(j)
        clusters.append(cluster)

    return clusters


def _detect_frequency(gaps: list[int]) -> tuple[str, float]:
    """
    Given a list of day gaps between consecutive occurrences,
    return (frequency_label, confidence).
    Confidence is higher when gaps are tighter and more consistent.
    """
    if not gaps:
        return "Ad-hoc", 0.0

    avg_gap = sum(gaps) / len(gaps)

    for label, (low, high) in _FREQUENCY_BANDS.items():
        if low <= avg_gap <= high:
            # Confidence: penalise variance in gaps
            if len(gaps) == 1:
                return label, 0.70
            variance = sum((g - avg_gap) ** 2 for g in gaps) / len(gaps)
            # Tighter variance = higher confidence, capped at 0.99
            confidence = min(0.99, max(0.50, 1.0 - (variance / (avg_gap ** 2))))
            return label, round(confidence, 2)

    return "Ad-hoc", 0.40


def _next_date(last: date, frequency: str, avg_gap: float) -> date:
    """Estimate the next expected occurrence date."""
    if frequency == "Weekly":
        return last + timedelta(days=7)
    if frequency == "Monthly":
        # Add roughly one month
        month = last.month + 1
        year = last.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(last.day, [31,28,31,30,31,30,31,31,30,31,30,31][month - 1])
        return date(year, month, day)
    if frequency == "Quarterly":
        month = last.month + 3
        year = last.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(last.day, [31,28,31,30,31,30,31,31,30,31,30,31][month - 1])
        return date(year, month, day)
    # Ad-hoc: use the average gap
    return last + timedelta(days=int(avg_gap))


def detect_recurring_payments(df: pd.DataFrame) -> list[RecurringPayment]:
    """
    Analyse a cleaned transaction dataframe and return detected recurring payments.
    Uses rapidfuzz to cluster similar descriptions, then checks for regular intervals.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    descriptions = df["description"].tolist()
    clusters = _group_by_similarity(descriptions)

    results = []

    for cluster_indices in clusters:
        if len(cluster_indices) < _MIN_OCCURRENCES:
            continue

        subset = df.iloc[cluster_indices].sort_values("date")

        # Skip if mixed inflow/outflow — unlikely to be a single recurring item
        if subset["type"].nunique() > 1:
            continue

        dates = subset["date"].dt.date.tolist()
        gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates) - 1)]

        frequency, confidence = _detect_frequency(gaps)

        if frequency == "Ad-hoc" and confidence < 0.50:
            continue

        avg_gap = sum(gaps) / len(gaps) if gaps else 30
        last = dates[-1]
        next_exp = _next_date(last, frequency, avg_gap)

        rep_desc = subset["description"].iloc[0]
        category = subset["category"].iloc[0] if "category" in subset.columns else "Other"
        avg_amount = round(subset["amount"].mean(), 2)
        is_inflow = subset["type"].iloc[0] == "inflow"

        results.append(RecurringPayment(
            description=rep_desc,
            category=str(category) if pd.notna(category) else "Other",
            average_amount=avg_amount,
            frequency=frequency,
            last_occurrence=last,
            next_expected=next_exp,
            confidence=confidence,
            is_inflow=is_inflow,
        ))

    logger.info(f"Recurring detection complete — {len(results)} patterns found")
    return results


def save_recurring_payments(payments: list[RecurringPayment]) -> None:
    """Clear old recurring records and save the newly detected ones."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM recurring_payments")

    for p in payments:
        cursor.execute(
            """
            INSERT INTO recurring_payments
                (description, category, average_amount, frequency,
                 last_occurrence, next_expected, confidence, is_inflow)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p.description,
                p.category,
                p.average_amount,
                p.frequency,
                str(p.last_occurrence),
                str(p.next_expected),
                p.confidence,
                1 if p.is_inflow else 0,
            ),
        )

    conn.commit()
    conn.close()
    logger.success(f"Saved {len(payments)} recurring payment records")
