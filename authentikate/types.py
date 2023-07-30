from datetime import datetime
from typing import Annotated, Any, Generic, List, Optional, TypeVar, Union

import strawberry
import strawberry.django
import strawberry_django
from django.contrib.auth import get_user_model
from strawberry import ID, auto
from strawberry.types import Info as _Info
from strawberry_django.filters import FilterLookup

from authentikate.models import App, User
from kante import register_model

from . import models


@register_model(User, pagination=True)
class User:
    id: auto


@register_model(App, pagination=True)
class App:
    id: auto
