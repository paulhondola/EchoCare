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
            "app/scheduler/service.py": "from app.auth.service import user_for\n",
            "app/auth/clock.py": "from app.scheduler.service import user_for\n",
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


def foreign_writes(app: Path) -> set[tuple[str, str]]:
    """(module, ORM class) for every write to a table another package owns (ADR-005).

    The owner is the package whose models.py defines the class. A write is a
    constructor, insert/update/delete(X), `row.attr = …`, setattr(row, …) or
    session.delete(row). A row's class comes from its annotation, from its assignment
    from X(...), select(X) or session.get(X, …), or else from a column only one class
    has. ponytail: a row whose class none of these names is missed; review catches it.
    """
    owner: dict[str, str] = {}
    columns: dict[str, set[str]] = {}
    for models in app.glob("*/models.py"):
        for node in ast.parse(models.read_text()).body:
            if isinstance(node, ast.ClassDef) and any(
                isinstance(b, ast.Name) and b.id == "Base" for b in node.bases
            ):
                owner[node.name] = models.parent.name
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(
                        item.target, ast.Name
                    ):
                        columns.setdefault(item.target.id, set()).add(node.name)

    def annotated(annotation: ast.expr | None) -> str | None:
        names = {
            n.id
            for n in ast.walk(annotation or ast.Constant(None))
            if isinstance(n, ast.Name) and n.id in owner
        }
        return names.pop() if len(names) == 1 else None

    def loaded(value: ast.expr) -> str | None:
        for n in ast.walk(value):
            if not isinstance(n, ast.Call):
                continue
            if isinstance(n.func, ast.Name) and n.func.id in owner:
                return n.func.id
            if (
                (
                    (getattr(n.func, "id", None) == "select" and len(n.args) == 1)
                    or getattr(n.func, "attr", None) == "get"
                )
                and n.args
                and isinstance(n.args[0], ast.Name)
                and n.args[0].id in owner
            ):
                return n.args[0].id
        return None

    found = set()
    for path in sorted(app.rglob("*.py")):
        module = path.relative_to(app).as_posix()
        if module.startswith("models/") or path.name == "models.py":
            continue
        package = module.split("/")[0]
        tree = ast.parse(path.read_text())
        written: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in owner:
                    written.add(node.func.id)
                elif node.func.id in ("insert", "update", "delete") and node.args:
                    written.add(getattr(node.args[0], "id", ""))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            args = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
            rows = {a.arg: c for a in args if (c := annotated(a.annotation))}
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Assign)
                    and isinstance(node.targets[0], ast.Name)
                    and (c := loaded(node.value))
                ):
                    rows[node.targets[0].id] = c
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
                    targets = getattr(node, "targets", None) or [node.target]
                    pairs = [
                        (t.value.id, t.attr)
                        for t in targets
                        if isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name)
                    ]
                elif (
                    isinstance(node, ast.Call)
                    and node.args
                    and (
                        getattr(node.func, "id", None) == "setattr"
                        or (
                            getattr(node.func, "attr", None) == "delete"
                            and getattr(node.func.value, "id", None) == "session"
                        )
                    )
                ):
                    pairs = [(getattr(node.args[0], "id", ""), "")]
                else:
                    continue
                for name, attr in pairs:
                    if name == "self":
                        continue
                    guess = columns.get(attr, set())
                    cls = rows.get(name) or (
                        next(iter(guess)) if len(guess) == 1 else None
                    )
                    if cls:
                        written.add(cls)
        found |= {(module, c) for c in written if owner.get(c, package) != package}
    return found


# Today's foreign writes (ADR-005's write map); each task deletes the pairs it fixes.
KNOWN = {
    ("calls/ending.py", "Call"),
    ("calls/ending.py", "Incident"),
    ("calls/ending.py", "Senior"),
    ("calls/ending.py", "Consent"),
    ("calls/mock.py", "Call"),
    ("calls/mock.py", "Answer"),
    ("calls/mock.py", "CallTurn"),
    ("calls/service.py", "Call"),
    ("campaigns/service.py", "Call"),
}


def test_only_the_owner_writes_a_table():
    assert foreign_writes(BACKEND / "app") == KNOWN


LEAK = """from app.seniors.models import Senior


def make():
    return Senior(full_name="x")


def rename(senior: Senior):
    senior.full_name = "y"
"""


def test_a_foreign_write_is_found(tmp_path):
    shutil.copytree(
        BACKEND / "app",
        tmp_path / "app",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (tmp_path / "app/system/leak.py").write_text(LEAK)
    assert {("system/leak.py", "Senior")} <= foreign_writes(tmp_path / "app")
