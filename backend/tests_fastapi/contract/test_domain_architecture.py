import importlib.util
import hashlib
import json
from pathlib import Path

from aidevops.database import Base, load_domain_models
from aidevops.main import create_app


BACKEND = Path(__file__).resolve().parents[2]
BASELINE = json.loads((Path(__file__).with_name("domain_baseline.json")).read_text("utf-8"))


def snapshot_digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def route_snapshot():
    document = create_app(initialize_database=False).openapi()
    return sorted(
        [path, method]
        for path, item in document["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    )


def metadata_snapshot():
    load_domain_models()
    return {
        name: {
            "columns": sorted(column.name for column in table.columns),
            "foreign_keys": sorted(key.target_fullname for key in table.foreign_keys),
            "indexes": sorted(sorted(column.name for column in index.columns) for index in table.indexes),
            "unique_constraints": sorted(
                sorted(column.name for column in constraint.columns)
                for constraint in table.constraints
                if constraint.__class__.__name__ == "UniqueConstraint"
            ),
        }
        for name, table in sorted(Base.metadata.tables.items())
    }


def test_domain_packages_replace_app():
    for package in ("aidevops", "aiops", "ops", "eventwall", "rbac"):
        assert importlib.util.find_spec(package) is not None
    assert not (BACKEND / "app").exists()


def test_routes_match_baseline():
    snapshot = route_snapshot()
    assert len(snapshot) == BASELINE["route_count"]
    assert snapshot_digest(snapshot) == BASELINE["route_sha256"]


def test_metadata_matches_baseline():
    snapshot = metadata_snapshot()
    assert len(snapshot) == BASELINE["table_count"]
    assert snapshot_digest(snapshot) == BASELINE["metadata_sha256"]
