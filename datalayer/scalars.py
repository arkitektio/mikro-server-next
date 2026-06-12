"""Custom GraphQL scalars for the datalayer app.

The NewTypes are used in annotations; the GraphQL definitions in
:data:`SCALAR_MAP` are merged into the schema's ``StrawberryConfig.scalar_map``
in ``mikro_server/schema.py``.
"""

from typing import NewType

import strawberry
from strawberry.types.scalar import ScalarDefinition

MediaLike = NewType("MediaLike", str)


def _identity(v: object) -> object:
    """Pass-through serialization: the scalar carries its JSON value unchanged."""
    return v


SCALAR_MAP: dict[object, ScalarDefinition] = {
    MediaLike: strawberry.scalar(
        name="MediaLike",
        description="A type representing a media store reference, which can be either a string ID or a more complex object.",
        serialize=_identity,
        parse_value=_identity,
    ),
}
