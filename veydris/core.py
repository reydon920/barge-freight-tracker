"""Validate USDA records and calculate fixed-volume freight variance."""

import csv
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / 'data' / 'sample.csv'
with (ROOT / 'data/benchmarks.csv').open(newline='', encoding='utf-8') as _handle:
    BENCHMARKS = {row['origin']: Decimal(row['usd_per_short_ton']) for row in csv.DictReader(_handle)}


def timeline(records):
    """Include expected weekly dates as gaps when an entire source week is absent."""
    days = {day for _, day in records}
    cursor, last = min(days), max(days)
    while cursor <= last:
        days.add(cursor)
        cursor += timedelta(days=7)
    return sorted(days)


def number(value, label='number', positive=False):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'{label} must be numeric') from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(f'{label} must be finite and {"positive" if positive else "nonnegative"}')
    return result


def money(value):
    return value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def dollars_per_ton(origin, quote):
    """Quote is percent of tariff; benchmark is USD per 2,000-lb short ton."""
    return number(quote, 'quote') * BENCHMARKS[origin] / 100


@dataclass(frozen=True)
class Observation:
    day: date
    origin: str
    quote: Decimal | None


def load(path=SAMPLE):
    records = {}
    with Path(path).open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        required = {'Date', 'Location', 'Rate'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('CSV requires Date, Location, Rate columns')
        for line, row in enumerate(reader, 2):
            try:
                day = datetime.strptime(row['Date'], '%m/%d/%Y').date()
                origin = row['Location']
                if origin not in BENCHMARKS:
                    raise ValueError(f'unknown origin: {origin}')
                quote = number(row['Rate'], 'rate') if row['Rate'].strip() else None
                key = (origin, day)
                if key in records:
                    raise ValueError(f'duplicate origin/date: {key}')
                records[key] = Observation(day, origin, quote)
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f'CSV row {line}: {exc}') from exc
    if not records:
        raise ValueError('CSV contains no observations')
    return records


@dataclass(frozen=True)
class Estimate:
    origin: str
    budget_date: str
    comparison_date: str
    short_tons: Decimal
    budget_usd_per_short_ton: Decimal
    comparison_usd_per_short_ton: Decimal
    budget_cost_usd: Decimal
    comparison_cost_usd: Decimal
    variance_usd: Decimal
    percent_change: Decimal | None

    def row(self):
        return {key: '' if value is None else str(value) for key, value in asdict(self).items()}


def compare(records, origin, tons, budget, comparison):
    tons = number(tons, 'short tons', positive=True)
    rates = []
    for day in (budget, comparison):
        observation = records.get((origin, date.fromisoformat(str(day))))
        if observation is None or observation.quote is None:
            raise ValueError(f'Unavailable quote for {origin} on {day}; choose an exact observation date')
        rates.append(dollars_per_ton(origin, observation.quote))
    before, after = rates
    budget_cost, comparison_cost = money(tons * before), money(tons * after)
    return Estimate(origin, str(budget), str(comparison), tons, before, after,
                    budget_cost, comparison_cost, comparison_cost - budget_cost,
                    money((after / before - 1) * 100) if before else None)


def write_csv(estimate, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        row = estimate.row()
        writer = csv.DictWriter(handle, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)
