"""Guards for the dependency rules between the apps.

The rule (documented in ``core/models/__init__.py``): core may depend on
datalayer, but datalayer is the storage backend and must never import core.
"""

import ast
from pathlib import Path

import pytest

DATALAYER_DIR = Path(__file__).parent.parent / "datalayer"

# Explicit list — a new datalayer module should be added here deliberately.
DATALAYER_MODULES = [
    "admin.py",
    "apps.py",
    "base_models.py",
    "datalayer.py",
    "fields.py",
    "inputs.py",
    "models.py",
    "mutations/bigfile.py",
    "mutations/media.py",
    "mutations/parquet.py",
    "mutations/zarr.py",
    "scalars.py",
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
