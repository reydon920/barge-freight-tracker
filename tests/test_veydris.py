"""Offline business arithmetic, source validation, report and refresh checks."""

import csv
import hashlib
import json
import os
import subprocess
import sys
import shutil
import uuid
import re
from contextlib import contextmanager
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from veydris.core import (BENCHMARKS, SAMPLE, Observation, compare,
                          dollars_per_ton, load, money, write_csv, timeline)
from veydris.refresh import publish
from veydris.report import report

FIXTURE = Path(__file__).with_name('fixtures') / 'usda-2026-11-15.csv'


@contextmanager
def workspace_temp():
    directory = Path(__file__).resolve().parent.parent / 'output' / 'tests'
    directory = directory / uuid.uuid4().hex
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


class FreightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load(FIXTURE)

    def test_usda_worked_examples(self):
        self.assertEqual(dollars_per_ton('Twin Cities', 200), Decimal('12.38'))
        self.assertEqual(money(dollars_per_ton('St. Louis', 271)), Decimal('10.81'))

    def test_every_origin_mapping(self):
        expected = ['6.19', '5.32', '4.64', '3.99', '4.69', '4.46', '3.14']
        for origin, benchmark in zip(BENCHMARKS, expected):
            with self.subTest(origin=origin):
                self.assertEqual(dollars_per_ton(origin, 100), Decimal(benchmark))
        self.assertEqual({r.origin for r in self.records.values()}, set(BENCHMARKS))

    def test_fixed_volume_arithmetic_and_rounding(self):
        estimate = compare(self.records, 'St. Louis', '1500', '2026-11-03', '2026-11-10')
        self.assertEqual(estimate.budget_cost_usd, Decimal('33758.99'))
        self.assertEqual(estimate.comparison_cost_usd, Decimal('32810.37'))
        self.assertEqual(estimate.variance_usd, Decimal('-948.62'))
        self.assertEqual(estimate.percent_change, Decimal('-2.81'))
        reverse = compare(self.records, 'St. Louis', '1500', '2026-11-10', '2026-11-03')
        self.assertEqual(reverse.variance_usd, -estimate.variance_usd)
        self.assertEqual(money(Decimal('1.005')), Decimal('1.01'))

    def test_missing_quotes_and_absent_dates(self):
        missing = next(r for r in self.records.values() if r.quote is None)
        with self.assertRaisesRegex(ValueError, 'Unavailable quote'):
            compare(self.records, missing.origin, 1500, missing.day, '2026-11-10')
        with self.assertRaisesRegex(ValueError, 'Unavailable quote'):
            compare(self.records, 'St. Louis', 1500, '2026-11-09', '2026-11-10')

    def test_whole_missing_week_remains_a_gap(self):
        first, last = date(2026, 1, 6), date(2026, 1, 20)
        rows = {('St. Louis', day): Observation(day, 'St. Louis', Decimal(200)) for day in (first, last)}
        self.assertEqual(timeline(rows), [first, date(2026, 1, 13), last])

    def test_zero_rate_and_invalid_volume(self):
        day = date(2026, 1, 1)
        records = {('St. Louis', day): Observation(day, 'St. Louis', Decimal(0))}
        self.assertIsNone(compare(records, 'St. Louis', 1, day, day).percent_change)
        for value in ['0', '-1', 'NaN', 'Infinity', 'abc']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare(self.records, 'St. Louis', value, '2026-11-03', '2026-11-10')

    def test_bad_source_records(self):
        header = 'Date,Location,Rate\n'
        rows = ['11/10/2026,St. Louis,-2\n', '11/31/2026,St. Louis,200\n',
                '11/10/2026,Unknown,200\n', '11/10/2026,St. Louis,NaN\n',
                '11/10/2026,St. Louis,200\n'*2, '', '11/10/2026,St. Louis,abc\n']
        with workspace_temp() as tmp:
            path = Path(tmp)/'bad.csv'
            for row in rows:
                with self.subTest(row=row):
                    path.write_text(header+row, encoding='utf-8')
                    with self.assertRaises(ValueError):
                        load(path)
            path.write_text('Wrong,Headers\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                load(path)

    def test_sample_provenance(self):
        metadata = json.loads(SAMPLE.with_suffix('.json').read_text())
        self.assertEqual(hashlib.sha256(SAMPLE.read_bytes()).hexdigest(), metadata['sample_sha256'])
        current = load()
        self.assertEqual(len(current), metadata['sample_rows'])
        self.assertEqual({r.origin for r in current.values()}, set(BENCHMARKS))
        self.assertEqual(str(min(r.day for r in current.values())), metadata['first_observation'])
        self.assertEqual(str(max(r.day for r in current.values())), metadata['last_observation'])
        self.assertLess(SAMPLE.stat().st_size, 1_000_000)

    def test_report_and_csv_offline(self):
        with workspace_temp() as tmp, patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            estimate = compare(self.records, 'St. Louis', 1500, '2026-11-03', '2026-11-10')
            path = Path(tmp)/'report.html'
            report(self.records, path, estimate.origin, estimate.short_tons, estimate.budget_date, estimate.comparison_date)
            text = path.read_text(encoding='utf-8')
            self.assertIn('"St. Louis"', text)
            self.assertIn('null', text)
            self.assertNotIn('__PAYLOAD__', text)
            self.assertNotIn('<script src=', text)
            self.assertNotIn('fetch(', text)
            write_csv(estimate, path.with_suffix('.csv'))
            with path.with_suffix('.csv').open() as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row['variance_usd'], '-948.62')

    def test_failed_refresh_keeps_last_good_snapshot(self):
        with workspace_temp() as tmp:
            path = Path(tmp)/'sample.csv'
            path.write_bytes(FIXTURE.read_bytes())
            original = path.read_bytes()
            for raw in [b'wrong,headers\n', b'Date,Location,Rate\n11/10/2026,St. Louis,200\n']:
                with self.assertRaises(ValueError):
                    publish(raw, path)
                self.assertEqual(original, path.read_bytes())
            metadata = publish(original, path)
            self.assertEqual(metadata['sample_rows'], len(self.records))

    def test_metadata_publish_failure_restores_csv(self):
        with workspace_temp() as tmp:
            path = tmp/'sample.csv'
            publish(FIXTURE.read_bytes(), path)
            original, metadata = path.read_bytes(), path.with_suffix('.json').read_bytes()
            replace = os.replace

            def fail_metadata(source, destination):
                if str(source).endswith('.staged.json'):
                    raise PermissionError('Simulated metadata publication failure')
                return replace(source, destination)

            with patch('veydris.refresh.os.replace', side_effect=fail_metadata):
                with self.assertRaises(PermissionError):
                    publish(original.replace(b'548.21', b'548.22'), path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.with_suffix('.json').read_bytes(), metadata)

    def test_cli_creates_report(self):
        with workspace_temp() as tmp:
            result = subprocess.run([sys.executable, '-m', 'veydris', '--data', str(FIXTURE), '--budget', '2026-11-03',
                                     '--comparison', '2026-11-10', '--output', str(Path(tmp)/'report.html')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('-948.62', result.stdout)

    def test_report_normalizes_scientific_decimal_notation(self):
        with workspace_temp() as tmp:
            path = tmp / 'report.html'
            report(self.records, path, 'St. Louis', Decimal('1e3'),
                   '2026-11-03', '2026-11-10')
            payload = re.search(r'<script id="data" type="application/json">(.*?)</script>',
                                path.read_text(encoding='utf-8')).group(1)
            self.assertEqual(json.loads(payload)['tons'], '1000')

    @unittest.skipUnless(shutil.which('node'), 'Optional browser logic parity checks require Node.js')
    def test_browser_calculator_matches_python(self):
        cases = []
        dates = sorted({str(day) for _, day in self.records})
        for origin in BENCHMARKS:
            for before, after in zip(dates, dates[1:]):
                for tons in ('1500', '0.5', '1.005'):
                    try:
                        cases.append(compare(self.records, origin, tons, before, after).row())
                    except ValueError:
                        pass  # Missing quotes are exercised explicitly by the JS check.
        with workspace_temp() as tmp:
            path = tmp/'report.html'
            report(self.records, path, 'St. Louis', 1500, dates[-2], dates[-1])
            (tmp/'cases.json').write_text(json.dumps(cases), encoding='utf-8')
            result = subprocess.run(['node', str(Path(__file__).with_name('ui_check.cjs')), str(path), str(tmp/'cases.json')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_showcase_images(self):
        import struct
        from veydris.showcase import showcase
        with workspace_temp() as tmp, patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            estimate = compare(self.records, 'St. Louis', 1500, '2026-11-03', '2026-11-10')
            showcase(self.records, estimate, tmp)
            images = list(tmp.glob('*.png'))
            self.assertEqual(len(images), 3)
            for path in images:
                content = path.read_bytes()
                self.assertEqual(content[:8], b'\x89PNG\r\n\x1a\n')
                width, height = struct.unpack('>II', content[16:24])
                self.assertGreaterEqual(width, 1000)
                self.assertGreaterEqual(height, 600)
                self.assertLess(len(content), 5_000_000)


if __name__ == '__main__':
    unittest.main()
