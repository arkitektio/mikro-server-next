from typing import NewType

import strawberry

ArrayLike = strawberry.scalar(
    NewType("ArrayLike", str),
    serialize=lambda v: v,
    parse_value=lambda v: v,
)


Matrix = strawberry.scalar(
    NewType("Matrix", object),
    description="The `Matrix` scalar type represents a matrix values as specified by",
    serialize=lambda v: v,
    parse_value=lambda v: v,
)


Vector = strawberry.scalar(
    NewType("Vector", list),
    description="The `Vector` scalar type represents a matrix values as specified by",
    serialize=lambda v: v,
    parse_value=lambda v: v,
)
