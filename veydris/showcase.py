"""Render actual sample-data charts with a headless Matplotlib backend."""

from pathlib import Path
import os

from .core import BENCHMARKS, dollars_per_ton, timeline


def showcase(records, estimate, directory):
    # Keep font caches alongside generated output, including in restricted runners.
    cache = Path('output/.matplotlib').resolve()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(cache))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 12,
        'figure.facecolor': '#0c1724', 'axes.facecolor': '#142536',
        'text.color': '#e4edf5', 'axes.labelcolor': '#adbecf',
        'xtick.color': '#adbecf', 'ytick.color': '#adbecf',
        'axes.edgecolor': '#34485b', 'grid.color': '#34485b',
        'savefig.facecolor': '#0c1724',
    })

    def finish(fig, name, caption):
        fig.text(.07, .035, caption, color='#adbecf', fontsize=11)
        fig.savefig(directory / name, dpi=120)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 6.5))
    fig.subplots_adjust(left=.09, right=.95, top=.78, bottom=.22)
    fig.text(.07, .92, 'VEYDRIS / THE COST OF A RATE CHANGE', color='#65d5b4', fontsize=12)
    fig.text(.07, .85, f'{estimate.origin}: ${estimate.variance_usd:+,.2f} against budget', fontsize=24, weight='bold')
    costs = [float(estimate.budget_cost_usd), float(estimate.comparison_cost_usd)]
    bars = ax.bar(['Budget\n'+estimate.budget_date, 'Comparison\n'+estimate.comparison_date], costs,
                  color=['#6b93bb', '#65d5b4'], width=.48)
    ax.bar_label(bars, labels=[f'${value:,.2f}' for value in costs], padding=12, fontsize=18, color='#e4edf5')
    ax.set_ylim(0, max(costs)*1.3 or 1)
    ax.set_ylabel('Estimated freight cost / USD')
    ax.yaxis.set_major_formatter('${x:,.0f}')
    ax.grid(axis='y', alpha=.4)
    ax.set_axisbelow(True)
    finish(fig, 'budget-variance.png',
           f'{estimate.short_tons:,} short tons held constant • Rate change {estimate.percent_change}% • Freight estimate only\nSource: USDA AMS / Downbound Grain Barge Rates • Excludes accessorial charges')

    fig, ax = plt.subplots(figsize=(12, 6.5))
    fig.subplots_adjust(left=.09, right=.95, top=.78, bottom=.22)
    fig.text(.07, .92, 'VEYDRIS / QUOTE HISTORY', color='#65d5b4', fontsize=12)
    fig.text(.07, .85, f'{estimate.origin}: put the weekly change in context', fontsize=23, weight='bold')
    dates = timeline(records)
    # Include every source observation date so a missing quote breaks the line.
    values = []
    for day in dates:
        row = records.get((estimate.origin, day))
        values.append(float(dollars_per_ton(row.origin, row.quote))
                      if row and row.quote is not None else float('nan'))
    ax.plot(dates, values, color='#65d5b4', linewidth=2.5)
    ax.set_ylabel('USD / short ton (2,000 lb)')
    ax.set_xlabel('USDA observation date')
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.grid(alpha=.4)
    finish(fig, 'rate-history.png',
           f'{dates[0]} through {dates[-1]} • Gaps mean unavailable quotes; no filling\nSource: USDA AMS • Percent-of-tariff quotes converted using the origin benchmark')

    fig, ax = plt.subplots(figsize=(12, 6.5))
    fig.subplots_adjust(left=.23, right=.9, top=.78, bottom=.20)
    latest = max(day for _, day in records)
    origins = list(BENCHMARKS)
    values = []
    labels = []
    for origin in origins:
        row = records.get((origin, latest))
        value = float(dollars_per_ton(origin, row.quote)) if row and row.quote is not None else None
        values.append(value if value is not None else 0)
        labels.append(f'${value:.2f}' if value is not None else 'Unavailable')
    bars = ax.barh(origins, values, color='#65d5b4', height=.6)
    ax.invert_yaxis()
    ax.bar_label(bars, labels=labels, padding=8, color='#e4edf5')
    ax.set_xlim(0, max(values)*1.25 or 1)
    ax.set_xlabel('Estimated freight / USD per short ton')
    ax.grid(axis='x', alpha=.4)
    ax.set_axisbelow(True)
    fig.text(.07, .92, 'VEYDRIS / SEVEN ORIGINS, EXPLICIT UNITS', color='#65d5b4', fontsize=12)
    fig.text(.07, .85, f'Compare freight estimates on {latest}', fontsize=24, weight='bold')
    finish(fig, 'origin-rates.png',
           'Different origins cover different river distances; these are not interchangeable routes.\nSource: USDA AMS • Freight estimates only; no accessorial charges included')
