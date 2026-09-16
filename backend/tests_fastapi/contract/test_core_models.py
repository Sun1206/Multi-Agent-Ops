from sqlalchemy import inspect

from ops.modules.models import SystemModuleSetting
from eventwall.models import EventRecord
from rbac.models import User


def test_auth_and_module_columns_preserve_contract() -> None:
    user = inspect(User)
    assert user.columns.username.unique is True
    assert user.columns.password_hash.nullable is False
    assert SystemModuleSetting.__table__.c.code.unique is True


def test_event_metadata_uses_safe_python_attribute() -> None:
    assert hasattr(EventRecord, "event_metadata")
    assert EventRecord.event_metadata.property.columns[0].name == "metadata"
    assert EventRecord.__table__.c.metadata.type.python_type is dict
