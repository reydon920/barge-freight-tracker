"""Build a standalone report with embedded data and no network dependencies."""

import html
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from .core import BENCHMARKS, SAMPLE, dollars_per_ton, timeline, number


def report(records, path, origin, tons, budget, comparison, source=SAMPLE):
    dates = [str(day) for day in timeline(records)]
    series = {}
    for name in BENCHMARKS:
        series[name] = {}
        for day in dates:
            observation = records.get((name, date.fromisoformat(day)))
            series[name][day] = (format(dollars_per_ton(name, observation.quote), 'f')
                                 if observation and observation.quote is not None else None)
    payload = {'series': series, 'dates': dates, 'origin': origin,
               'tons': format(number(tons, 'short tons', positive=True), 'f'),
               'budget': str(budget), 'comparison': str(comparison)}
    template = Path(__file__).with_name('report.html').read_text(encoding='utf-8')
    # JSON lives in a script element; escaping '<' prevents closing-tag injection.
    rendered = template.replace('__PAYLOAD__', json.dumps(payload).replace('<', '\\u003c'))
    rendered = rendered.replace('__RANGE__', html.escape(f'{dates[0]} to {dates[-1]}'))
    provenance = 'Source retrieval time is not verified.'
    snapshot_retrieval = ''
    source = Path(source)
    try:
        metadata = json.loads(source.with_suffix('.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        metadata = None
    if isinstance(metadata, dict) and metadata.get('sample_sha256') == hashlib.sha256(source.read_bytes()).hexdigest():
        timestamp = metadata.get('retrieved_utc')
        try:
            retrieved = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else None
            if retrieved is not None and retrieved.tzinfo is not None:
                retrieved = retrieved.astimezone(timezone.utc)
                browser_timestamp = retrieved.isoformat(timespec='milliseconds')
                snapshot_retrieval = (
                    f' &middot; Retrieved <time id="snapshot-retrieved" datetime="{browser_timestamp}">'
                    f'{retrieved.date()}</time> UTC'
                )
                provenance = f"Source retrieved UTC: {retrieved.isoformat()}. Data SHA-256: {metadata['sample_sha256']}."
        except (ValueError, OverflowError):
            pass
    rendered = rendered.replace('__SNAPSHOT_RETRIEVAL__', snapshot_retrieval)
    rendered = rendered.replace('__PROVENANCE__', html.escape(provenance))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding='utf-8')
    return path
