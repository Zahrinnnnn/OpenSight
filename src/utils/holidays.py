from datetime import date


# Malaysian national public holidays (fixed dates)
# Excludes state-specific holidays — national only
_FIXED_HOLIDAYS = {
    (1,  1):  "New Year's Day",
    (5,  1):  "Labour Day",
    (6,  1):  "Yang di-Pertuan Agong's Birthday",
    (8, 31):  "National Day",
    (9, 16):  "Malaysia Day",
    (12, 25): "Christmas Day",
}

# Approximate moveable holidays by year (manually curated for 2024-2027)
# Dates shift each year based on the Islamic / lunar calendar
_MOVEABLE_HOLIDAYS: dict[int, list[tuple[int, int, str]]] = {
    2024: [
        (1, 25, "Thaipusam"),
        (2, 10, "Chinese New Year"),
        (2, 11, "Chinese New Year Holiday"),
        (4, 10, "Hari Raya Aidilfitri"),
        (4, 11, "Hari Raya Aidilfitri Holiday"),
        (6, 17, "Hari Raya Aidiladha"),
        (7,  7, "Awal Muharram"),
        (9, 16, "Prophet Muhammad's Birthday"),
        (10, 31, "Deepavali"),
    ],
    2025: [
        (1, 29, "Thaipusam"),
        (1, 29, "Chinese New Year"),
        (1, 30, "Chinese New Year Holiday"),
        (3, 31, "Hari Raya Aidilfitri"),
        (4,  1, "Hari Raya Aidilfitri Holiday"),
        (6,  7, "Hari Raya Aidiladha"),
        (6, 27, "Awal Muharram"),
        (9,  5, "Prophet Muhammad's Birthday"),
        (10, 20, "Deepavali"),
    ],
    2026: [
        (1, 18, "Thaipusam"),
        (2, 17, "Chinese New Year"),
        (2, 18, "Chinese New Year Holiday"),
        (3, 20, "Hari Raya Aidilfitri"),
        (3, 21, "Hari Raya Aidilfitri Holiday"),
        (5, 27, "Hari Raya Aidiladha"),
        (6, 16, "Awal Muharram"),
        (8, 26, "Prophet Muhammad's Birthday"),
        (11,  9, "Deepavali"),
    ],
    2027: [
        (1,  7, "Thaipusam"),
        (2,  6, "Chinese New Year"),
        (2,  7, "Chinese New Year Holiday"),
        (3,  9, "Hari Raya Aidilfitri"),
        (3, 10, "Hari Raya Aidilfitri Holiday"),
        (5, 16, "Hari Raya Aidiladha"),
        (6,  6, "Awal Muharram"),
        (8, 15, "Prophet Muhammad's Birthday"),
        (10, 29, "Deepavali"),
    ],
}


def get_holidays_for_year(year: int) -> dict[date, str]:
    """Returns a dict of {date: holiday_name} for the given year."""
    holidays: dict[date, str] = {}

    for (month, day), name in _FIXED_HOLIDAYS.items():
        try:
            holidays[date(year, month, day)] = name
        except ValueError:
            pass

    for month, day, name in _MOVEABLE_HOLIDAYS.get(year, []):
        holidays[date(year, month, day)] = name

    return holidays


def is_public_holiday(d: date) -> bool:
    return d in get_holidays_for_year(d.year)


def get_holidays_in_range(start: date, end: date) -> dict[date, str]:
    """Returns all public holidays between start and end dates (inclusive)."""
    all_holidays: dict[date, str] = {}
    for year in range(start.year, end.year + 1):
        for d, name in get_holidays_for_year(year).items():
            if start <= d <= end:
                all_holidays[d] = name
    return all_holidays


def get_prophet_holiday_df():
    """
    Returns a dataframe formatted for Prophet's holidays parameter.
    Covers 2024–2027.
    """
    import pandas as pd

    rows = []
    for year in range(2024, 2028):
        for d, name in get_holidays_for_year(year).items():
            rows.append({"ds": pd.Timestamp(d), "holiday": name})

    return pd.DataFrame(rows)
