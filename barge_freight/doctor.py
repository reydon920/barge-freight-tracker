"""Check the active interpreter and optional chart dependencies offline."""

import os
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid


@contextmanager
def chart_cache():
    # Use normal inherited directory permissions, including on Windows runners.
    path = Path(tempfile.gettempdir()) / f'barge-doctor-{uuid.uuid4().hex}'
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path)


# A child process keeps backend selection, imports and caches out of the caller.
CHART_CHECK = r"""
import io
import re
import matplotlib
print('Matplotlib ' + matplotlib.__version__, flush=True)
version = re.match(r'^(\d+)\.(\d+)(?:\.|$)', matplotlib.__version__)
if version is None or not ( (3, 9) <= tuple(map(int, version.groups())) < (4, 0) ):
    raise RuntimeError('Requires Matplotlib >=3.9,<4 (requirements.txt)')
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
figure = Figure(figsize=(1, 1))
figure.subplots().plot([0, 1], [0, 1])
FigureCanvasAgg(figure).print_png(io.BytesIO())
"""


def doctor():
    """Print diagnostics and return 0 for success, 1 when attention is needed."""
    print(f'Interpreter: {sys.executable}')
    python_ok = sys.version_info[:2] == (3, 12)
    print(f'{"OK" if python_ok else "FAIL"}: Python {sys.version.split()[0]} (requires Python 3.12)')
    if not python_ok:
        print('Create a virtual environment with Python 3.12 and rerun --doctor there.')
    chart_ok = False
    try:
        with chart_cache() as cache:
            environment = dict(os.environ, MPLCONFIGDIR=cache, MPLBACKEND='Agg')
            command = [sys.executable]
            if sys.flags.no_site:
                command.append('-S')
            result = subprocess.run(command + ['-c', CHART_CHECK], env=environment,
                                    capture_output=True, text=True, timeout=30)
            chart_ok = result.returncode == 0
            print(f'{"OK" if chart_ok else "FAIL"}: Matplotlib >=3.9,<4 and headless PNG rendering')
            if result.stdout.strip():
                print(result.stdout.strip())
            if not chart_ok and result.stderr.strip():
                print(result.stderr.strip())
    except (OSError, subprocess.TimeoutExpired) as exc:
        chart_ok = False
        print(f'FAIL: Matplotlib check could not finish: {exc}')
    if not chart_ok:
        requirements = Path(__file__).resolve().parent.parent / 'requirements.txt'
        print('Install or repair chart dependencies with this interpreter:')
        print(f'"{sys.executable}" -m pip install -r "{requirements}"')
        print('In PowerShell, prefix the quoted interpreter path with &.')
    print('Calculator, CSV and HTML report use the standard library; Matplotlib is only needed for --showcase.')
    print('Checks are offline; no packages are installed and no reports are generated.')
    return 0 if python_ok and chart_ok else 1
