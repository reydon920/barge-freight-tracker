"""Offline dependency diagnostics and CLI isolation checks."""

import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from barge_freight.__main__ import main
from barge_freight.doctor import doctor
from tests.test_barge_freight import workspace_temp


class DoctorTests(unittest.TestCase):
    def test_doctor_works_without_site_packages(self):
        result = subprocess.run(
            [sys.executable, '-S', '-m', 'barge_freight', '--doctor'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(sys.executable, result.stdout)
        self.assertIn('Python', result.stdout)
        self.assertIn('Matplotlib', result.stdout)
        self.assertIn('FAIL', result.stdout)
        self.assertIn('-m pip install -r', result.stdout)
        self.assertIn('-m ensurepip --upgrade', result.stdout)
        self.assertIn('standard library', result.stdout)

    def test_doctor_precedes_data_and_network_actions(self):
        output = StringIO()
        with patch('sys.argv', ['barge_freight', '--doctor', '--refresh',
                                '--data', 'does-not-exist.csv']), \
                patch('barge_freight.__main__.load', side_effect=AssertionError('data read')), \
                patch('urllib.request.urlopen', side_effect=AssertionError('network')), \
                patch('barge_freight.doctor.sys.version_info', (3, 12, 0)), \
                patch('barge_freight.doctor.subprocess.run',
                      return_value=subprocess.CompletedProcess([], 0, 'Matplotlib 3.9.0', '')), \
                redirect_stdout(output):
            with self.assertRaises(SystemExit) as exit:
                main()
        self.assertEqual(exit.exception.code, 0, output.getvalue())
        self.assertIn('Matplotlib', output.getvalue())
        self.assertIn('OK', output.getvalue())

    def test_incompatible_and_broken_matplotlib(self):
        for version, error in [('2.9.0', 'Requires Matplotlib >=3.9,<4'),
                               ('3.9.0', 'broken binary dependency')]:
            with self.subTest(version=version), workspace_temp() as tmp:
                package = tmp / 'matplotlib'
                package.mkdir()
                (package / '__init__.py').write_text(
                    f'__version__ = {version!r}\n', encoding='utf-8')
                (package / 'figure.py').write_text(
                    "raise OSError('broken binary dependency')\n", encoding='utf-8')
                result = subprocess.run(
                    [sys.executable, '-S', '-m', 'barge_freight', '--doctor'],
                    env=dict(os.environ, PYTHONPATH=str(tmp)), capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(error, result.stdout)
                self.assertIn('-m pip install -r', result.stdout)

    def test_unsupported_python_is_reported(self):
        output = StringIO()
        with patch('barge_freight.doctor.sys.version_info', (3, 11, 0)), redirect_stdout(output):
            self.assertEqual(doctor(), 1)
        self.assertIn('FAIL: Python', output.getvalue())
        self.assertIn('virtual environment with Python 3.12', output.getvalue())

    def test_chart_repair_checks_pip_with_the_active_interpreter(self):
        for pip_result in [subprocess.CompletedProcess([], 0, 'pip 25.0', ''),
                           subprocess.CompletedProcess([], 1, '', 'No module named pip'),
                           subprocess.TimeoutExpired('pip check', 30),
                           OSError('could not start pip')]:
            with self.subTest(pip_result=pip_result), redirect_stdout(StringIO()) as output:
                with patch('barge_freight.doctor.subprocess.run', side_effect=[
                        subprocess.CompletedProcess([], 1, '', 'broken chart dependency'),
                        pip_result]) as run:
                    self.assertEqual(doctor(), 1)
                self.assertEqual(run.call_count, 2)
                command = run.call_args.args[0]
                self.assertEqual(command[0], sys.executable)
                self.assertEqual(command[-3:], ['-m', 'pip', '--version'])
                self.assertEqual(run.call_args.kwargs['timeout'], 30)
                self.assertIn('-m pip install -r', output.getvalue())
                if isinstance(pip_result, subprocess.CompletedProcess) and pip_result.returncode == 0:
                    self.assertIn('pip 25.0', output.getvalue())
                    self.assertNotIn('ensurepip', output.getvalue())
                else:
                    self.assertIn('-m ensurepip --upgrade', output.getvalue())
                    self.assertIn('Python 3.12', output.getvalue())

    def test_chart_check_timeout_is_actionable(self):
        output = StringIO()
        with patch('barge_freight.doctor.subprocess.run',
                   side_effect=subprocess.TimeoutExpired('chart check', 30)), redirect_stdout(output):
            self.assertEqual(doctor(), 1)
        self.assertIn('could not finish', output.getvalue())
        self.assertIn('-m pip install -r', output.getvalue())

    def test_cache_cleanup_failure_returns_failure(self):
        output = StringIO()
        with patch('barge_freight.doctor.chart_cache') as temporary, \
                redirect_stdout(output):
            temporary.return_value.__enter__.return_value = 'unused-cache'
            temporary.return_value.__exit__.side_effect = PermissionError('cleanup denied')
            with patch('barge_freight.doctor.subprocess.run',
                       return_value=subprocess.CompletedProcess([], 0, 'Matplotlib 3.9.0', '')):
                self.assertEqual(doctor(), 1)


if __name__ == '__main__':
    unittest.main()
