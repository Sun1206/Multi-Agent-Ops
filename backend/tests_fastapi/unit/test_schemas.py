import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from app.schemas.auth import UserResponse
from app.schemas.module import ModuleSettingsBody, normalize_module_payload


def test_demo_compatibility_flag_is_always_false() -> None:
    user = UserResponse(
        id=1,
        username="demo",
        email="",
        first_name="",
        last_name="",
        is_active=True,
        is_staff=False,
        is_superuser=False,
        date_joined="2026-09-12T00:00:00Z",
        last_login=None,
        roles=[],
        user_groups=[],
        effective_permissions=[],
        display_name="demo",
    )
    assert user.is_demo_account is False
    with pytest.raises(ValidationError):
        UserResponse(
            **{
                **user.model_dump(exclude={"is_demo_account"}),
                "is_demo_account": True,
            }
        )


def test_both_module_payload_shapes_normalize_equally() -> None:
    listed = [{"code": "containers", "enabled": False}]
    wrapped = ModuleSettingsBody(modules=listed)
    assert normalize_module_payload(listed) == normalize_module_payload(wrapped)


def test_user_response_restores_utc_for_naive_database_timestamps() -> None:
    user = UserResponse(
        id=1, username="admin", email="", first_name="", last_name="",
        is_active=True, is_staff=True, is_superuser=True,
        date_joined=datetime(2026, 9, 12), last_login=datetime(2026, 9, 12),
        roles=[], user_groups=[], effective_permissions=[], display_name="admin",
    )
    assert user.date_joined.tzinfo == timezone.utc
    assert user.last_login.tzinfo == timezone.utc
