"""Download a complete USDA export; publish a validated bounded sample atomically."""

import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen

from .core import ROOT, BENCHMARKS, load

SOURCE = 'https://agtransport.usda.gov/api/views/deqi-uken/rows.csv?accessType=DOWNLOAD'


def publish(raw, destination):
    """Stage and validate before replacing the last good sample."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_suffix('.staged.csv')
    staged_metadata = destination.with_suffix('.staged.json')
    previous = destination.read_bytes() if destination.exists() else None
    replaced = False
    try:
        staged.write_bytes(raw)
        records = load(staged)
        if {origin for origin, _ in records} != set(BENCHMARKS):
            raise ValueError('Export must cover all seven origins')
        latest = max(day for _, day in records)
        cutoff = latest - timedelta(days=366)
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        with staged.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=['Date', 'Week', 'Month', 'Year', 'Location', 'Rate'])
            writer.writeheader()
            for row in rows:
                if datetime.strptime(row['Date'], '%m/%d/%Y').date() >= cutoff:
                    writer.writerow(row)
        sample = load(staged)
        if not all(any(r.origin == origin and r.quote is not None for r in sample.values()) for origin in BENCHMARKS):
            raise ValueError('Recent sample must contain quotes for all origins')
        metadata = {
            'source_url': SOURCE,
            'retrieved_utc': datetime.now(timezone.utc).isoformat(),
            'raw_sha256': hashlib.sha256(raw).hexdigest(),
            'sample_sha256': hashlib.sha256(staged.read_bytes()).hexdigest(),
            'raw_rows': len(records), 'sample_rows': len(sample),
            'first_observation': str(min(day for _, day in sample)),
            'last_observation': str(latest),
            'selection': 'All rows within 366 days of newest observation, inclusive',
            'quote_unit': 'percent of 1976 tariff', 'ton_unit': 'short ton (2,000 lb)',
        }
        staged_metadata.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        os.replace(staged, destination)
        replaced = True
        os.replace(staged_metadata, destination.with_suffix('.json'))
        return metadata
    except OSError:
        # Restore the data if publishing its metadata fails after the CSV swap.
        if replaced:
            if previous is None:
                destination.unlink(missing_ok=True)
            else:
                staged.write_bytes(previous)
                os.replace(staged, destination)
        raise
    finally:
        staged.unlink(missing_ok=True)
        staged_metadata.unlink(missing_ok=True)


def refresh():
    with urlopen(SOURCE, timeout=60) as response:
        raw = response.read()
    raw_path = ROOT / 'data/raw/usda.csv'
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    return publish(raw, ROOT / 'data/sample.csv')
