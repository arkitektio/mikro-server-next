from authentikate.errors import AuthentikatePermissionDenied
import time
from django.contrib.auth.models import Group
from authentikate import models, structs
import logging


logger = logging.getLogger(__name__)


def token_to_username(token: structs.JWTToken):
    """Convert a JWT token to a username"""
    return f"{token.iss}_{token.sub}"


def set_user_groups(user: models.User, roles: list[str]):
    """Set the groups of a user"""
    for role in roles:
        g, _ = Group.objects.get_or_create(name=role)
        user.groups.add(g)


def expand_token(token: structs.JWTToken, force_client: bool = True) -> structs.Auth:
    if token.sub is None:
        raise AuthentikatePermissionDenied("Missing sub parameter in JWT token")

    if token.iss is None:
        raise AuthentikatePermissionDenied("Missing iss parameter in JWT token")

    if token.exp is None:
        raise AuthentikatePermissionDenied("Missing exp parameter in JWT token")

    # Check if token is expired
    if token.exp < time.time():
        raise AuthentikatePermissionDenied("Token has expired")

    if token.client_id is None:
        if force_client:
            raise AuthentikatePermissionDenied(
                "Missing client_id parameter in JWT token"
            )

    try:
        if token.client_id is None:
            app = None
        else:
            app, _ = models.App.objects.get_or_create(
                client_id=token.client_id, iss=token.iss
            )

        user = models.User.objects.get(username=token_to_username(token))
        if user.changed_hash != token.changed_hash:
            # User has changed, update the user object
            user.first_name = token.preferred_username
            user.changed_hash = token.changed_hash
            set_user_groups(user, token.roles)
            user.save()

    except models.User.DoesNotExist:
        user = models.User(
            sub=token.sub,
            username=token_to_username(token),
            iss=token.iss,
            first_name=token.preferred_username,
        )
        user.set_unusable_password()
        user.save()
        user.first_name = token.preferred_username
        user.changed_hash = token.changed_hash
        set_user_groups(user, token.roles)
        user.save()
    except Exception as e:
        logger.error(f"Error while authenticating: {e}", exc_info=True)
        raise AuthentikatePermissionDenied(f"Error while authenticating: {e}")

    return structs.Auth(
        token=token,
        user=user,
        app=app,
    )
