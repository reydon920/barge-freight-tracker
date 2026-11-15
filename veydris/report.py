"""Build a standalone report with embedded data and no network dependencies."""

import html
import hashlib
import json
from datetime import date
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
    provenance = 'Custom data: retrieval time is not verified.'
    source = Path(source)
    if source.with_suffix('.json').exists():
        metadata = json.loads(source.with_suffix('.json').read_text(encoding='utf-8'))
        if metadata.get('sample_sha256') == hashlib.sha256(source.read_bytes()).hexdigest():
            provenance = f"Source retrieved UTC: {metadata['retrieved_utc']}. Data SHA-256: {metadata['sample_sha256']}."
    rendered = rendered.replace('__PROVENANCE__', html.escape(provenance))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding='utf-8')
    return path
