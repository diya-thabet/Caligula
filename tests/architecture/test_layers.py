"""The dependency rule: domain <- application <- adapters.

Checked on every import statement, including imports inside functions.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "caligula"
IO_AND_SDKS = {"anthropic", "httpx", "psycopg", "PIL", "subprocess", "urllib", "requests", "socket", "sqlite3"}


def imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    return found


def modules(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


def top(name: str) -> str:
    return name.split(".")[0]


@pytest.mark.parametrize("path", modules("domain"), ids=lambda p: str(p.relative_to(SRC)))
def test_domain_depends_on_nothing_outside(path):
    bad = [m for m in imports(path)
           if (m.startswith("caligula.") and not m.startswith("caligula.domain")) or top(m) in IO_AND_SDKS]
    assert not bad, f"{path.name} imports {bad}"


@pytest.mark.parametrize("path", modules("application"), ids=lambda p: str(p.relative_to(SRC)))
def test_application_depends_on_domain_and_ports_only(path):
    bad = [m for m in imports(path) if m.startswith("caligula.adapters") or top(m) in IO_AND_SDKS]
    assert not bad, f"{path.name} imports {bad}"


def test_every_module_is_in_a_layer():
    stray = [p.name for p in SRC.glob("*.py") if p.name != "__init__.py"]
    assert not stray, f"modules outside domain/application/adapters: {stray}"
