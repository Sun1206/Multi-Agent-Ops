import ast
from pathlib import Path


APP = Path(__file__).resolve().parents[2] / "app"


def test_public_functions_and_methods_have_chinese_docstrings() -> None:
    missing: list[str] = []
    for path in APP.rglob("*.py"):
        if path.name == "domain_generated.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            docstring = ast.get_docstring(node) or ""
            if not any("\u4e00" <= character <= "\u9fff" for character in docstring):
                missing.append(f"{path.relative_to(APP)}:{node.lineno}:{node.name}")
    assert missing == []
