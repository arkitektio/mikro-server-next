import strawberry
from strawberry import auto
from strawberry_django.filters import FilterLookup
from authentikate import models


@strawberry.django.order(models.User)
class UserOrder:
    performed_at: auto


@strawberry.django.filter(models.User)
class UserFilter:
    username: FilterLookup[str]
