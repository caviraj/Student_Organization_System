"""Roles and permissions, readable (DESIGN.md §5, RBAC).

Three reads, no writes: a route that only reports is one the frontend can build its access-control
screen against now, and the writes (create a role, grant it, revoke it) arrive with the
role-management API, where the anti-escalation rules live.

Both admin reads answer from app/core/permissions.py rather than from the `permissions` / `roles`
tables. The module is the source of truth - it is what `require_permission` validates route keys
against at import - so reading it can never serve a row that has drifted. The tables are its synced
copy, and `tests/test_rbac.py` fails if the two disagree.

shortcut: no custom roles here, because `is_system=False` roles do not exist until the
role-management API creates them. Upgrade when that lands: the matrix then reads the tables and
merges the module's system roles in.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.authz import effective_permissions, require_permission, role_keys
from app.core.deps import get_current_user, get_db
from app.core.permissions import CATALOG, PRIVILEGED_ROLES, ROLE_PERMISSIONS, ROLE_SPECS
from app.models import User
from app.schemas import MyPermissionsOut, PermissionOut, RoleMatrixOut, RoleOut

router = APIRouter(prefix="/admin", tags=["RBAC"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])


def _permission_out(permission) -> PermissionOut:
    return PermissionOut(
        key=permission.key,
        category=permission.category,
        description=permission.description,
        is_privileged=permission.is_privileged,
    )


@auth_router.get(
    "/permissions",
    response_model=MyPermissionsOut,
    summary="Your own effective permissions",
    description="What the caller may do right now, so the UI can hide a button rather than show a 403.",
)
def my_permissions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = role_keys(user)
    return MyPermissionsOut(
        role=user.role,
        roles=sorted(roles),
        permissions=sorted(effective_permissions(db, user)),
    )


@router.get(
    "/permissions",
    response_model=list[PermissionOut],
    summary="The permission catalog (admin)",
    description="Every permission key the code knows, grouped-nothing: each row carries its category.",
)
def list_permissions(_: User = Depends(require_permission("roles.view"))):
    return [_permission_out(permission) for permission in CATALOG]


@router.get(
    "/rbac/matrix",
    response_model=RoleMatrixOut,
    summary="Roles and their permissions (admin)",
    description="Roles down, permissions across - the access-control screen in one call.",
)
def role_matrix(_: User = Depends(require_permission("roles.view"))):
    return RoleMatrixOut(
        permissions=[_permission_out(permission) for permission in CATALOG],
        roles=[
            RoleOut(
                key=spec.key,
                name=spec.name,
                description=spec.description,
                inherits=spec.inherits,
                is_privileged=spec.key in PRIVILEGED_ROLES,
                permissions=sorted(ROLE_PERMISSIONS[spec.key]),
            )
            for spec in ROLE_SPECS
        ],
    )
