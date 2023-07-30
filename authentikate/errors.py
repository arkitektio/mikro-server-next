from django.core.exceptions import PermissionDenied


class AuthentikateError(Exception):
    pass


class AuthentikatePermissionDenied(PermissionDenied):
    pass


class AuthentikateTokenExpired(AuthentikatePermissionDenied):
    pass


class JwtTokenError(AuthentikatePermissionDenied):
    pass


class MalformedJwtTokenError(JwtTokenError):
    pass


class InvalidJwtTokenError(JwtTokenError):
    pass
