from app.models.rbac import PermissionDefinition, Role, UserGroup
from app.models.auth import AuthToken, User
from app.models.eventwall import EventEnvironment, EventRecord, EventSource
from app.models.module import SystemModuleSetting
from app.models import domain_generated as _domain_generated
from app.core.database import Base

for _name in _domain_generated.__all__:
    globals()[_name] = getattr(_domain_generated, _name)

__all__ = [
    "AuthToken",
    "EventEnvironment",
    "EventRecord",
    "EventSource",
    "PermissionDefinition",
    "Role",
    "SystemModuleSetting",
    "User",
    "UserGroup",
] + _domain_generated.__all__

# 所有业务表统一使用 MySQL 8 的事务引擎和完整 Unicode 字符集。
for _table in Base.metadata.tables.values():
    _table.kwargs["mysql_engine"] = "InnoDB"
    _table.kwargs["mysql_charset"] = "utf8mb4"
