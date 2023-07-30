from strawberry.types import Info as _Info
from kante.context import ChannelsWSContext
from typing import Any, Generic, TypeVar
import strawberry
import strawberry.django
from strawberry import auto, ID
from typing import List, Optional, Annotated, Union
import strawberry_django
from kante import register_model
from . import models
from django.contrib.auth import get_user_model
from typing import Optional
from strawberry_django.filters import FilterLookup
from datetime import datetime

Info = _Info[ChannelsWSContext, Any]
