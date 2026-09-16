"""汇总领域模型，仅供迁移、DDL 与完整性检查使用。"""

from aiops import models as _aiops
from eventwall import models as _eventwall
from ops import models as _ops
from ops.modules.models import SystemModuleSetting
from rbac import models as _rbac

for _package in (_aiops, _eventwall, _ops, _rbac):
    for _name in _package.__all__:
        globals()[_name] = getattr(_package, _name)

__all__ = ["SystemModuleSetting"] + _aiops.__all__ + _eventwall.__all__ + _ops.__all__ + _rbac.__all__
