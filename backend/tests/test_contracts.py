"""The import contracts in pyproject.toml reach packages that don't exist yet.

Each case adds a violation to a copy of app/ and expects lint-imports to name the contract
it breaks, so a new package (01 §8: scheduler, notifier, …) is held to the same rules.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).parent.parent
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"

CASES = {
    "new package re-exports in __init__": (
        {
            "app/scheduler/__init__.py": "from app.scheduler.service import tick\n",
            "app/scheduler/service.py": "def tick(): ...\n",
        },
        "Package __init__ files import nothing",
    ),
    "app/__init__ re-exports": (
        {"app/__init__.py": "from app.core.phones import normalize\n"},
        "Package __init__ files import nothing",
    ),
    "new package's schemas import its service": (
        {
            "app/scheduler/__init__.py": "",
            "app/scheduler/service.py": "def tick(): ...\n",
            "app/scheduler/schemas.py": "from app.scheduler.service import tick\n",
        },
        "Inside a feature",
    ),
    "status imports a new package": (
        {
            "app/scheduler/__init__.py": "",
            "app/scheduler/service.py": "def tick(): ...\n",
            "app/status/clock.py": "from app.scheduler.service import tick\n",
        },
        "The status engine is pure logic",
    ),
    "new package imports app.models": (
        {
            "app/scheduler/__init__.py": "",
            "app/scheduler/service.py": "from app.models import Call\n",
        },
        "app.models is for Alembic",
    ),
}


@pytest.mark.parametrize(("files", "contract"), CASES.values(), ids=CASES.keys())
def test_contracts_cover_new_code(tmp_path, files, contract):
    shutil.copytree(
        BACKEND / "app",
        tmp_path / "app",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copy(BACKEND / "pyproject.toml", tmp_path)
    for path, source in files.items():
        (tmp_path / path).parent.mkdir(exist_ok=True)
        (tmp_path / path).write_text(source)
    run = subprocess.run(
        [LINT_IMPORTS, "--no-cache"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    broken = [line for line in run.stdout.splitlines() if " BROKEN" in line]
    assert any(line.startswith(contract) for line in broken), run.stdout
