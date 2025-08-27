from core import models, types
from guardian.shortcuts import assign_perm
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from guardian.models import UserObjectPermission
import strawberry
from strawberry import ID

User = get_user_model()

identifier_model_map = {
    "@mikro/image": models.Image,
    "@mikro/dataset": models.Dataset,
    "@mikro/file": models.File,
}


@strawberry.input
class AssignUserPermissionInput:
    identifier: str            # e.g. "@mikro/image"
    object: ID                 # Object primary key (as string)
    user: ID                   # User primary key (as string)
    permissions: list[str]     # e.g. ["view_image", "change_image"]


def assign_user_permission(
    info,
    input: AssignUserPermissionInput,
) -> list[types.UserObjectPermission]:
    # Resolve the model
    model = identifier_model_map.get(input.identifier)
    if model is None:
        raise ValueError(f"Unknown identifier: {input.identifier}")

    # Get the object and user
    obj = model.objects.get(pk=input.object)
    user = User.objects.get(sub=input.user)

    # Assign each permission
    for perm in input.permissions:
        x = Permission.objects.get(id=perm)
        assign_perm(x.codename, user, obj)

    # Return all permissions for this object and user
    content_type = ContentType.objects.get_for_model(model)
    
    user_permissions = UserObjectPermission.objects.filter(
        object_pk=input.object,
        content_type=content_type, user__sub__isnull=False
    ).all()

    return [types.UserObjectPermission(user=user_permissions.user, permission=user_permissions.permission.codename) for user_permissions in user_permissions]
