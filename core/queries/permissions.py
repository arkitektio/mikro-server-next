from core import models, types, enums, filters as f, pagination as p
from core.utils import paginate_querysets
import strawberry
from typing import List, Optional, Union
from itertools import chain
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.models import ContentType
from guardian.models import UserObjectPermission 
import strawberry_django
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
import strawberry


identifier_model_map = {
    "@mikro/image": models.Image,
    "@mikro/dataset": models.Dataset,
    "@mikro/file": models.File,
}


def permissions(
    info,
    identifier: str,
    object: strawberry.ID,
) -> list[types.UserObjectPermission]:
    
    
    
    model = identifier_model_map.get(identifier)
    if model is None:
        raise ValueError(f"Unknown identifier: {identifier}")
    

    content_type = ContentType.objects.get_for_model(model)
    user_permissions = UserObjectPermission.objects.filter(object_pk=object, content_type=content_type, user__sub__isnull=False).all()
        
    return [types.UserObjectPermission(user=user_permissions.user, permission=user_permissions.permission.codename) for user_permissions in user_permissions]



# Your identifier-to-model map
identifier_model_map = {
    "@mikro/image": models.Image,
    "@mikro/dataset": models.Dataset,
    "@mikro/file": models.File,
}


@strawberry.type
class PermissionOption:
    value: strawberry.ID  # the Permission ID
    label: str            # human-readable name


def available_permissions(
    identifier: str,
    search: Optional[str] = None,
    values: Optional[List[strawberry.ID]] = None,
) -> List[PermissionOption]:
    model = identifier_model_map.get(identifier)
    if model is None:
        raise ValueError(f"Unknown identifier: {identifier}")

    content_type = ContentType.objects.get_for_model(model)
    qs = Permission.objects.filter(content_type=content_type)

    if values:
        qs = qs.filter(id__in=values)
    elif search:
        qs = qs.filter(name__icontains=search)

    return [
        PermissionOption(value=str(p.id), label=p.name)
        for p in qs
    ]