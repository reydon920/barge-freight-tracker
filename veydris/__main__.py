"""Run with python -m veydris; the default run uses bundled public data."""

import argparse
from pathlib import Path

from .core import BENCHMARKS, SAMPLE, compare, load, write_csv, number
from .report import report


def main():
    parser = argparse.ArgumentParser(description='Veydris | Barge Freight Budget Tracker')
    parser.add_argument('--data', type=Path, default=SAMPLE)
    parser.add_argument('--origin', choices=BENCHMARKS, default='St. Louis')
    parser.add_argument('--tons', default='1500', help='Shipment volume in short tons (2,000 lb)')
    parser.add_argument('--budget', help='Exact observation date, YYYY-MM-DD; default penultimate date')
    parser.add_argument('--comparison', help='Exact observation date, YYYY-MM-DD; default latest date')
    parser.add_argument('--output', type=Path, default=Path('output/report.html'))
    parser.add_argument('--showcase', type=Path, metavar='DIRECTORY')
    parser.add_argument('--refresh', action='store_true', help='Fetch USDA data (requires network)')
    args = parser.parse_args()
    try:
        if args.refresh:
            from .refresh import refresh
            print(refresh())
            return
        records = load(args.data)
        dates = sorted({str(day) for _, day in records})
        budget = args.budget or dates[max(0, len(dates)-2)]
        comparison = args.comparison or dates[-1]
        tons = number(args.tons, 'short tons', positive=True)
        # Reports remain usable when an explicitly selected quote is missing.
        report(records, args.output, args.origin, tons, budget, comparison, source=args.data)
        try:
            estimate = compare(records, args.origin, tons, budget, comparison)
        except ValueError:
            args.output.with_suffix('.csv').unlink(missing_ok=True)
            raise
        write_csv(estimate, args.output.with_suffix('.csv'))
        print(f'{estimate.origin}: {budget} -> {comparison} | {tons} short tons')
        print(f'Freight estimate: ${estimate.budget_cost_usd:,.2f} -> ${estimate.comparison_cost_usd:,.2f}')
        print(f'Budget variance: ${estimate.variance_usd:+,.2f} ({estimate.percent_change}%)')
        print(f'Report: {args.output}')
        if args.showcase:
            from .showcase import showcase
            showcase(records, estimate, args.showcase)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f'Veydris: {exc}\n')


if __name__ == '__main__':
    main()
