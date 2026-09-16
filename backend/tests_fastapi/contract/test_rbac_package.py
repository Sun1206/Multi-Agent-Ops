from aidevops.dependencies import require_any_permission, require_permissions
from rbac.models import AuthToken, PermissionDefinition, Role, User, UserGroup
from rbac.services.accounts import authenticate_credentials
from rbac.services.authorization import sync_rbac


def test_rbac_public_contract():
    assert all((AuthToken, PermissionDefinition, Role, User, UserGroup))
    assert authenticate_credentials and sync_rbac and require_permissions and require_any_permission
