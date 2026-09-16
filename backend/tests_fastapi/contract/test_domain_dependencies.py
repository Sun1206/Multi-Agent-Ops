import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def cross_domain_imports(package: str, forbidden: set[str]) -> list[str]:
    offenders: list[str] = []
    for path in sorted((BACKEND_ROOT / package).rglob("*.py")):
        imported = imported_roots(path) & forbidden
        if imported:
            relative = path.relative_to(BACKEND_ROOT).as_posix()
            offenders.append(f"{relative}: {', '.join(sorted(imported))}")
    return offenders


def test_ops_does_not_depend_on_aiops_internals():
    assert cross_domain_imports("ops", {"aiops"}) == []


def test_rbac_does_not_depend_on_aiops_or_ops():
    assert cross_domain_imports("rbac", {"aiops", "ops"}) == []


def test_aidevops_does_not_import_rbac_internal_layers():
    offenders: list[str] = []
    for path in [BACKEND_ROOT / "aidevops" / "dependencies.py"]:
        forbidden = {
            module
            for module in imported_modules(path)
            if (module == "rbac" or module.startswith("rbac."))
            and module != "rbac.public"
        }
        if forbidden:
            relative = path.relative_to(BACKEND_ROOT).as_posix()
            offenders.append(f"{relative}: {', '.join(sorted(forbidden))}")
    assert offenders == []
