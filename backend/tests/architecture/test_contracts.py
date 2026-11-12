"""The import contracts in pyproject.toml reach packages that don't exist yet.

Each case adds a violation to a copy of app/ and expects lint-imports to name the contract
it breaks, so a new package (01 §8: notifier, …) is held to the same rules, at
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
            "app/notifier/__init__.py": "",
            "app/notifier/service.py": "def tick(): ...\n",
            "app/notifier/schemas.py": "from app.notifier.service import tick\n",
        },
        "Inside a feature",
    ),
    "status imports a new package": (
        {
            "app/notifier/__init__.py": "",
            "app/notifier/service.py": "def tick(): ...\n",
            "app/status/clock.py": "from app.notifier.service import tick\n",
        },
        "The status engine is pure logic",
    ),
    "new package imports app.models": (
        {
            "app/notifier/__init__.py": "",
            "app/notifier/service.py": "from app.models import Call\n",
        },
        "app.models is for Alembic",
    ),
    "new package's router imports another router": (
        {
            "app/notifier/__init__.py": "",
            "app/notifier/router.py": "from app.voice.router import router\n",
        },
        "Only app.main imports a router",
    ),
    "an old package imports a higher one": (
        {"app/auth/clock.py": "from app.seniors.service import reach\n"},
        "Packages sit in layers",
    ),
    "a new package is not placed in a layer": (
        {
            "app/notifier/__init__.py": "",
            "app/notifier/service.py": "def tick(): ...\n",
        },
        "Packages sit in layers",
    ),
    "agent imports seniors": (
        {"app/agent/leak.py": "from app.seniors.models import Senior\n"},
        "The agent talks only to voice",
    ),
    "agent opens a database session": (
        {"app/agent/leak.py": "from app.core.db import Session\n"},
        "The agent talks only to voice",
    ),
    "two packages in one layer import each other": (
        {"app/calls/leak.py": "from app.agent.relay import heard\n"},
        "Packages sit in layers",
    ),
    "new package's models import fastapi": (
        {
            "app/notifier/__init__.py": "",
            "app/notifier/models.py": "import fastapi\n",
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
    # today; map the odd one by hand (python-dateutil -> dateutil; pydantic-ai-slim -> pydantic_ai) when it arrives.
    imported_as = {
        re.match(r"[\w-]+", dep)[0].replace("-", "_").lower().replace("_slim", "")
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
    constructor, insert/update/delete(X), `row.attr = …` (also in a tuple target),
    setattr(row, …) or session.delete(row). X is a name the module imports from an
    app package's models.py, under any alias, so a same-named class from elsewhere
    (status.engine's Answer) is no write. A row's class comes from its annotation (a
    parameter's or a local one), or from what it is bound to (=, :=, a for loop) when
    that is X(...), select(X) or session.get(X, …). An unknown row's column names the
    class when one class has it, and every class with it when all of those are another
    package's. ponytail: missed, for review to catch: sa.update(X), an aliased insert,
    update(X.__table__), and chained a.b.c = … writes.
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

    def imported(tree: ast.Module) -> dict[str, str]:
        """The module's local name for each ORM class it imports."""
        return {
            alias.asname or alias.name: alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and re.fullmatch(r"app\.\w+\.models", node.module or "")
            for alias in node.names
            if alias.name in owner
        }

    def annotated(annotation: ast.expr | None, known: dict[str, str]) -> str | None:
        names = {
            known[n.id]
            for n in ast.walk(annotation or ast.Constant(None))
            if isinstance(n, ast.Name) and n.id in known
        }
        return names.pop() if len(names) == 1 else None

    def loaded(value: ast.expr, known: dict[str, str]) -> str | None:
        for n in ast.walk(value):
            if not isinstance(n, ast.Call):
                continue
            if isinstance(n.func, ast.Name) and n.func.id in known:
                return known[n.func.id]
            if (
                (
                    (getattr(n.func, "id", None) == "select" and len(n.args) == 1)
                    or getattr(n.func, "attr", None) == "get"
                )
                and n.args
                and isinstance(n.args[0], ast.Name)
                and n.args[0].id in known
            ):
                return known[n.args[0].id]
        return None

    found = set()
    for path in sorted(app.rglob("*.py")):
        module = path.relative_to(app).as_posix()
        if module.startswith("models/") or path.name == "models.py":
            continue
        package = module.split("/")[0]
        tree = ast.parse(path.read_text())
        known = imported(tree)
        written: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in known:
                    written.add(known[node.func.id])
                elif node.func.id in ("insert", "update", "delete") and node.args:
                    written.add(known.get(getattr(node.args[0], "id", ""), ""))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            args = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
            rows = {a.arg: c for a in args if (c := annotated(a.annotation, known))}
            for node in ast.walk(fn):
                match node:
                    case ast.Assign(targets=[ast.Name(id=name)], value=value) | (
                        ast.NamedExpr(target=ast.Name(id=name), value=value)
                    ):
                        c = loaded(value, known)
                    case ast.AnnAssign(target=ast.Name(id=name)):
                        c = annotated(node.annotation, known) or (
                            node.value and loaded(node.value, known)
                        )
                    case (
                        ast.For(target=ast.Name(id=name))
                        | ast.AsyncFor(target=ast.Name(id=name))
                    ):
                        c = loaded(node.iter, known)
                    case _:
                        c = None
                if c:
                    rows[name] = c
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
                    targets = [
                        e
                        for t in getattr(node, "targets", None) or [node.target]
                        for e in (
                            t.elts if isinstance(t, ast.Tuple | ast.List) else [t]
                        )
                    ]
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
                    # setattr's column, when it is a literal, guesses an unknown row.
                    column = node.args[1] if len(node.args) > 1 else None
                    attr = column.value if isinstance(column, ast.Constant) else ""
                    pairs = [(getattr(node.args[0], "id", ""), str(attr))]
                else:
                    continue
                for name, attr in pairs:
                    if name == "self":
                        continue
                    if name in rows:
                        written.add(rows[name])
                        continue
                    # An unknown row: a column one class has names it; a column only
                    # other packages' classes have is a foreign write whichever it is.
                    guess = columns.get(attr, set())
                    if len(guess) == 1 or all(owner[c] != package for c in guess):
                        written |= guess
        found |= {(module, c) for c in written if owner.get(c, package) != package}
    return found


def test_only_the_owner_writes_a_table():
    assert foreign_writes(BACKEND / "app") == set()


# One planted foreign write per rule, each in its own module. Those in voice/ write a
# column voice's own Call shares (`reason`, `state`), so only knowing the row's class
# finds them; those in system/ write where every class with the column is foreign.
LEAKS = {
    "constructor": ("system", "Senior", "return Senior(full_name='x')"),
    "insert": ("system", "Senior", "return insert(Senior)"),
    "update": ("system", "Senior", "return update(Senior)"),
    "delete": ("system", "Senior", "return delete(Senior)"),
    "annotated parameter": ("voice", "SeniorStatus", "row.reason = 'x'"),
    "setattr": ("voice", "SeniorStatus", "setattr(row, 'reason', 'x')"),
    "session.delete": ("voice", "SeniorStatus", "await session.delete(row)"),
    "loop variable": (
        "voice",
        "SeniorStatus",
        "for s in await session.scalars(select(SeniorStatus)):\n        s.reason = 'x'",
    ),
    "local annotation": (
        "voice",
        "SeniorStatus",
        "s: SeniorStatus = rows[0]\n    s.reason = 'x'",
    ),
    "walrus": (
        "voice",
        "SeniorStatus",
        (
            "if (s := await session.scalar(select(SeniorStatus))) is not None:\n"
            "        s.reason = 'x'"
        ),
    ),
    "unpacked row, a column only foreign classes have": (
        "system",
        "Call",
        "call, _ = rows\n    call.state = 'x'",
    ),
    "aliased import": ("system", "Senior", "return S(full_name='x')"),
    "setattr on an unknown row": (
        "system",
        "Call",
        "call, _ = rows\n    setattr(call, 'state', 'x')",
    ),
    "tuple target": ("voice", "SeniorStatus", "row.reason, n = 'x', 1"),
}
LEAK = """from sqlalchemy import delete, insert, select, update

from app.codes.models import SeniorStatus
from app.seniors.models import Senior
from app.seniors.models import Senior as S
from app.voice.models import Call


async def leak(session, row: SeniorStatus, rows):
    {}
"""


@pytest.mark.parametrize(("package", "cls", "body"), LEAKS.values(), ids=LEAKS.keys())
def test_a_foreign_write_is_found(tmp_path, package, cls, body):
    shutil.copytree(
        BACKEND / "app",
        tmp_path / "app",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (tmp_path / f"app/{package}/leak.py").write_text(LEAK.format(body))
    assert (f"{package}/leak.py", cls) in foreign_writes(tmp_path / "app")


def test_a_same_named_class_from_elsewhere_is_no_write(tmp_path):
    # status.engine has its own Answer; only voice.models' Answer is a table.
    shutil.copytree(
        BACKEND / "app",
        tmp_path / "app",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (tmp_path / "app/calls/rule.py").write_text(
        "from app.status.engine import Answer\n\n\n"
        "def rule():\n    return Answer('bine', True, 'Bine')\n"
    )
    assert ("calls/rule.py", "Answer") not in foreign_writes(tmp_path / "app")


def test_no_instrumentation():
    # No senior words reach a tracing backend (design §7).
    banned = ("logfire", "instrument=True", "instrument_all")
    hits = [
        str(path.relative_to(BACKEND))
        for path in (BACKEND / "app").rglob("*.py")
        if any(word in path.read_text() for word in banned)
    ]
    assert hits == []
