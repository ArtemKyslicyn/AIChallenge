"""The hexagonal layer rule, enforced by the suite rather than by review."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"

FRAMEWORKS = ("fastapi", "starlette", "sqlalchemy", "httpx", "alembic", "pydantic", "yaml")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _modules(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


def test_domain_imports_no_framework_and_no_adapter() -> None:
    for path in _modules("domain"):
        for module in _imports(path):
            assert not module.startswith(FRAMEWORKS), f"{path.name} imports {module}"
            if module.startswith("app."):
                assert module.startswith("app.domain"), f"{path.name} imports {module}"


def test_application_depends_only_on_domain_and_itself() -> None:
    allowed = ("app.domain", "app.application")
    for path in _modules("application"):
        for module in _imports(path):
            assert not module.startswith(FRAMEWORKS), f"{path.name} imports {module}"
            if module.startswith("app."):
                assert module.startswith(allowed), f"{path.name} imports {module}"
