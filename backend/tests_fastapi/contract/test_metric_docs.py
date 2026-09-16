from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]


# 部署示例必须公开独立指标 origin 白名单变量，但不能包含真实环境地址。
def test_metric_origin_allowlist_is_documented() -> None:
    env_example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    readme = (BACKEND / "README.md").read_text(encoding="utf-8")
    assert "AIOPS_METRIC_ALLOWED_ORIGINS=[]" in env_example
    assert "AIOPS_METRIC_ALLOWED_ORIGINS" in readme
    assert "可观测性指标查询" in readme


# 指标实现不应修改任何历史迁移或新增指标表迁移。
def test_metric_feature_reuses_existing_table_without_new_migration() -> None:
    versions = sorted(path.name for path in (BACKEND / "alembic" / "versions").glob("*.py"))
    assert versions == ["0001_fastapi_initial.py", "0002_normalize_aiops_names.py"]
