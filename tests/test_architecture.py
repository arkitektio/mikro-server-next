"""Guards for the dependency rules between the apps.

The rule (documented in ``core/models/__init__.py``): core may depend on
datalayer, but datalayer is the storage backend and must never import core.
"""

import ast
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

DATALAYER_DIR = Path(__file__).parent.parent / "datalayer"

# Explicit list — a new datalayer module should be added here deliberately.
DATALAYER_MODULES = [
    "admin.py",
    "apps.py",
    "base_models.py",
    "datalayer.py",
    "duck.py",
    "fields.py",
    "inputs.py",
    "fabriks.py",
    "models.py",
    "mutations/bigfile.py",
    "mutations/media.py",
    "mutations/fabriks.py",
    "mutations/parquet.py",
    "mutations/sparse.py",
    "mutations/zarr.py",
    "scalars.py",
    "sporadik.py",
    "types.py",
]


def _imported_top_level_packages(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    packages = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                packages.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            packages.add(node.module.split(".")[0])
    return packages


def test_datalayer_module_list_is_current() -> None:
    """Fail when a datalayer module is added without registering it above."""
    on_disk = sorted(
        str(p.relative_to(DATALAYER_DIR))
        for p in DATALAYER_DIR.rglob("*.py")
        if p.name != "__init__.py" and "migrations" not in p.parts and "__pycache__" not in p.parts
    )
    assert on_disk == sorted(DATALAYER_MODULES)


@pytest.mark.parametrize("module", DATALAYER_MODULES)
def test_datalayer_does_not_import_core(module: str) -> None:
    """datalayer is the storage backend; it must stay ignorant of the domain apps."""
    imported = _imported_top_level_packages(DATALAYER_DIR / module)
    assert "core" not in imported, f"datalayer/{module} imports core"


# ==========================================================================================
# Guards against the drift classes a coordinate-system review found by hand.
#
# Each of these would have caught real findings at the commit that introduced them, rather
# than years later by reading: a docstring naming a function that was never written, a lookup
# table keyed on an enum that stopped backing its field, and a model edited without its
# migration.
# ==========================================================================================

CORE_DIR = Path(__file__).parent.parent / "core"

#: Words that look like dotted identifiers inside prose and are not references to resolve.
#: Explicit, in the same spirit as `DATALAYER_MODULES` above -- the friction of adding a name
#: here is the point, because it is the moment to ask whether the prose meant a real symbol.
_PROSE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "e.g",
        "i.e",
        "a.u",
        "etc",
        "vs",
        "np.float32",
        "fabriks.json",
    }
)

#: Sphinx cross-reference roles whose target must name something that exists.
_XREF = re.compile(r":(?:func|meth|attr|class|mod|data|exc):`~?([A-Za-z_][\w.]*)`")


def _core_symbols() -> tuple[set[str], dict[str, set[str]]]:
    """Every name `core` defines, and every class' member names, read statically.

    Static rather than by import because a reference may legitimately name something in a module
    this test never imports, and because importing all of `core` to answer "does this name
    exist" would make the guard depend on import side effects.
    """
    names: set[str] = set()
    members: dict[str, set[str]] = {}
    for path in CORE_DIR.rglob("*.py"):
        if "__pycache__" in path.parts or "migrations" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover - a broken file is another test's problem
            continue
        names.add(path.stem)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
            if isinstance(node, ast.ClassDef):
                owned = members.setdefault(node.name, set())
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        owned.add(child.name)
                    elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                        owned.add(child.target.id)
                    elif isinstance(child, ast.Assign):
                        owned.update(t.id for t in child.targets if isinstance(t, ast.Name))
    return names, members


def _reference_resolves(dotted: str, names: set[str], members: dict[str, set[str]]) -> bool:
    """Whether a cited name plausibly exists.

    Three shapes appear in this codebase and all three are legitimate:
    a fully qualified path (``core.logic.graph.is_traversable``), a partial one
    (``coords.to_matrix``), and a bare name relying on context (``placement_path``). So a
    reference resolves when it imports outright, or when its owner is a known class that has
    the member, or when its final component is a name `core` defines somewhere.

    Deliberately permissive about *where* a name lives and strict about whether it exists at
    all -- which is the axis the findings this guards against sat on. `Transformation.registration`
    fails because no class named `Transformation` has that member; `best_path` fails because
    nothing anywhere defines it.
    """
    if _imports(dotted):
        return True
    parts = dotted.split(".")
    if len(parts) >= 2 and parts[-2] in members:
        return parts[-1] in members[parts[-2]]
    return parts[-1] in names


def _imports(dotted: str) -> bool:
    parts = dotted.split(".")
    for split in range(len(parts), 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:split]))
        except Exception:
            continue
        target = module
        for attribute in parts[split:]:
            target = getattr(target, attribute, None)
            if target is None:
                return False
        return True
    return False


def test_sphinx_cross_references_in_core_resolve() -> None:
    """A `:func:`/`:attr:` naming a symbol that does not exist is a docstring describing other code.

    This is the single highest-yield guard in the suite. The coordinate review found six live
    instances by hand -- a `best_path` tie-break that was never written but was cited three times
    as the arbiter of rival registrations, an `intrinsic_of` field removed with the ownership FKs
    and still named in five comments, a `Layer.registration` column that RFC-8 deleted, and a
    `core.logic.roi` module that has never existed. Every one of them was load-bearing prose in a
    codebase where the docstrings *are* the design record, and every one would have failed here.

    Deliberately narrow: only Sphinx roles, which are unambiguous claims that a symbol exists.
    Backticked prose is not checked, because ``a.u.`` and ``fabriks.json`` are not references and
    an allowlist long enough to cover them would stop being read.
    """
    names, members = _core_symbols()
    unresolved: list[str] = []
    for path in sorted(CORE_DIR.rglob("*.py")):
        if "__pycache__" in path.parts or "migrations" in path.parts:
            continue
        for match in _XREF.finditer(path.read_text()):
            dotted = match.group(1)
            if dotted in _PROSE_ALLOWLIST:
                continue
            if not _reference_resolves(dotted, names, members):
                unresolved.append(f"{path.relative_to(CORE_DIR.parent)}: {match.group(0)}")
    assert not unresolved, "docstrings name symbols that do not exist:\n  " + "\n  ".join(unresolved)


def test_minimum_vertex_table_is_keyed_on_the_live_annotation_kinds() -> None:
    """Every key must be a kind an annotation can actually be drawn as.

    It carried six that no longer were -- `spectral_rectangle`, `temporal_cube` and four
    siblings -- left behind when `AnnotationKindChoices` replaced the ROI vocabulary that had
    spelled a box six ways. No lookup could ever reach them, so nothing failed and nothing said
    so. The table and the enum are two halves of one fact; this is the half that was missing.
    """
    from core.enums import AnnotationKindChoices
    from core.inputs.validators import _MINIMUM_VERTICES

    live = {member.value for member in AnnotationKindChoices}
    unreachable = sorted(set(_MINIMUM_VERTICES) - live)
    assert not unreachable, f"_MINIMUM_VERTICES keys no annotation kind can reach: {unreachable}"


def test_the_models_and_the_migrations_agree() -> None:
    """A model edited without its migration is invisible to the rest of this suite.

    `mikro_server.settings_test` sets `MIGRATION_MODULES = DisableMigrations()`, so the test
    database is built with `run-syncdb` straight from the models and **no migration is ever
    executed here**. That makes model/migration drift completely undetectable by every other
    test: you can add a field, forget the migration, and stay green all the way to a deploy that
    fails on `migrate`. So this one runs the check against the real settings, in a subprocess,
    because the drift it looks for is one the test settings are designed not to see.
    """
    result = subprocess.run(
        [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
        cwd=CORE_DIR.parent,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "mikro_server.settings"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"models have changes with no migration:\n{result.stdout}\n{result.stderr}"
