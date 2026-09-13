import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]


def test_backend_has_no_standalone_quoted_documentation() -> None:
    remaining = []
    for root in (BACKEND / 'app', BACKEND / 'scripts'):
        for path in root.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    remaining.append(f'{path.relative_to(BACKEND)}:{node.lineno}')
    assert not remaining, '\n'.join(remaining)
