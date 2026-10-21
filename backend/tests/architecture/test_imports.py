"""Each entry module loads when it is the first import, in a fresh interpreter.

pytest itself always imports app.main first, which hides cycles that depend on import
order. Alembic starts at app.models, the scripts at one package's models.
"""

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).parents[2]


@pytest.mark.parametrize(
    "module",
    [
        "app.main",
        "app.models",
        "app.auth.models",
        "app.campaigns.models",
        "app.codes.models",
        "app.incidents.models",
        "app.seniors.models",
        "app.voice.models",
        "scripts.dev_token",
        "scripts.grant_das",
        "scripts.place_call",
        "scripts.seed",
    ],
)
def test_imports_first(module):
    run = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
