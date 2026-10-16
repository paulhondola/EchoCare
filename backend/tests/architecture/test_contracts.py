"""The import contracts in pyproject.toml reach packages that don't exist yet.

Each case adds a violation to a copy of app/ and expects lint-imports to name the contract
it breaks, so a new package (01 §8: scheduler, notifier, …) is held to the same rules, at
any depth. The last two tests check what import-linter can't express, by reading files.
"""

import ast
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).parents[2]
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"

CASES = {
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
    "new package's router imports another router": (
        {
            "app/scheduler/__init__.py": "",
            "app/scheduler/router.py": "from app.voice.router import router\n",
        },
        "Only app.main imports a router",
    ),
    "new package and an old one import each other": (
        {
            "app/scheduler/__init__.py": "",
            "app/scheduler/service.py": "from app.staff.service import user_for\n",
            "app/staff/clock.py": "from app.scheduler.service import user_for\n",
        },
        "No import cycles between packages",
    ),
    "new package's models import fastapi": (
        {
            "app/scheduler/__init__.py": "",
            "app/scheduler/models.py": "import fastapi\n",
        },
        "Models and schemas import no web framework",
    ),
    "nested package's models import its router": (
        {
            "app/voice/providers/__init__.py": "",
            "app/voice/providers/router.py": "router = None\n",
            "app/voice/providers/models.py": "from app.voice.providers.router import router\n",
        },
        "Inside a feature",
    ),
    "nested package's logic imports its router": (
        {
            "app/voice/providers/__init__.py": "",
            "app/voice/providers/router.py": "router = None\n",
            "app/voice/providers/telnyx.py": "from app.voice.providers.router import router\n",
        },
        "Only app.main imports a router",
    ),
    "nested package's schemas import httpx": (
        {
            "app/voice/providers/__init__.py": "",
            "app/voice/providers/schemas.py": "import httpx\n",
        },
        "Models and schemas import no web framework",
    ),
    "status imports pydantic": (
        {"app/status/forms.py": "import pydantic\n"},
        "The status engine is pure logic",
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


def test_package_inits_import_nothing():
    # app/models is the one aggregator, for Alembic, scripts and tests.
    importing = [
        str(init.relative_to(BACKEND))
        for init in (BACKEND / "app").rglob("__init__.py")
        if init != BACKEND / "app/models/__init__.py"
        and any(
            isinstance(node, ast.Import | ast.ImportFrom)
            for node in ast.walk(ast.parse(init.read_text()))
        )
    ]
    assert importing == []


def test_status_forbids_every_dependency():
    pyproject = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    # ponytail: "firebase-admin>=7.7.0" -> firebase_admin holds for every dependency
    # today; map the odd one by hand (python-dateutil -> dateutil) when it arrives.
    imported_as = {
        re.match(r"[\w-]+", dep)[0].replace("-", "_").lower()
        for dep in pyproject["project"]["dependencies"]
    }
    status = next(
        contract
        for contract in pyproject["tool"]["importlinter"]["contracts"]
        if contract["name"].startswith("The status engine")
    )
    assert imported_as - set(status["forbidden_modules"]) == set()
