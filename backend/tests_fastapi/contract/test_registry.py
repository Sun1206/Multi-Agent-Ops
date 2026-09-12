from app.registry import BUILTIN_ROLES, PERMISSION_DEFINITIONS


def test_registry_keeps_complete_unique_permission_codes() -> None:
    codes = [item[0] for item in PERMISSION_DEFINITIONS]
    assert len(codes) >= 90
    assert len(codes) == len(set(codes))
    assert "rbac.module.manage" in codes


def test_platform_admin_keeps_all_permission_wildcard() -> None:
    platform_admin = next(item for item in BUILTIN_ROLES if item["code"] == "platform-admin")
    assert platform_admin["permissions"] == ["*"]
