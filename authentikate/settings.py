from authentikate.structs import LokSettings
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_settings() -> LokSettings:
    try:
        user = settings.AUTH_USER_MODEL
        if user != "authentikate.User":
            raise ImproperlyConfigured(
                "AUTH_USER_MODEL must be authentikate.User in order to use authentikate"
            )
    except AttributeError:
        raise ImproperlyConfigured(
            "AUTH_USER_MODEL must be authentikate.User in order to use authentikate"
        )

    try:
        group = settings.AUTHENTIKATE
    except AttributeError:
        raise ImproperlyConfigured("Missing setting AUTHENTIKATE")

    try:
        algorithms = [group["KEY_TYPE"]]
        public_key = group["PUBLIC_KEY"]
        force_client = group.get("FORCE_CLIENT", False)

    except KeyError:
        raise ImproperlyConfigured("Missing setting LOK KEY_TYPE or LOK PUBLIC_KEY")

    return LokSettings(
        algorithms=algorithms, public_key=public_key, force_client=force_client
    )
