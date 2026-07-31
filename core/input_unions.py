"""Discriminated input unions, announced to client codegen via ``@unionElementOf``.

GraphQL has no input unions, so a union that must arrive through an argument is
wired as one *flat* input: a discriminator field plus the union of every member's
fields, all optional. The flat type is honest on the wire but silent about its
structure, so each member is also published as a real input type that no field
references, annotated with this directive -- which union it belongs to, which
field discriminates, and which discriminator value selects it. A generated client
rebuilds the tagged union from those annotations. The convention, including the
directive's exact name and arguments, is shared with kabinet's ``SelectorInput``.

The server-side half is :func:`parse_union_member`: the flat model is matched to
its member model by the discriminator, and the member models forbid fields that
are not their own -- so a parameter that contradicts the discriminator is an
error naming both, never a silent drop. That strictness is this module's reason
to exist; kabinet's variant models accept and discard strays.

Nothing here is mikro-specific; the module is written to move into kante once the
convention settles.
"""

import strawberry
from pydantic import BaseModel, ValidationError
from strawberry.schema_directive import Location


@strawberry.schema_directive(locations=[Location.INPUT_OBJECT], repeatable=True)
class unionElementOf:  # noqa: N801 -- the SDL directive name is the API, and kabinet already fixed it
    """Marks an input type as one member of a flat discriminated union input."""

    union: str = strawberry.field(description="The name of the flat input type this member belongs to")
    discriminator: str = strawberry.field(description="The field of the flat input whose value selects a member")
    key: str = strawberry.field(description="The discriminator value that selects this member")


def union_memberships(*unions: str, key: str, discriminator: str = "kind") -> list[unionElementOf]:
    """The directive instances declaring one member input's place in each named union."""
    return [unionElementOf(union=union, discriminator=discriminator, key=key) for union in unions]


def parse_union_member(
    members: dict[str, type[BaseModel]],
    data: dict,
    *,
    noun: str,
    discriminator: str = "kind",
    unknown_kind_error: str | None = None,
) -> BaseModel:
    """Match a flat discriminated input's fields to its member model, strictly.

    ``data`` is the flat input's supplied fields (omitted ones absent); the member
    model carries only its own fields and forbids the rest, so this is where a field
    that contradicts the discriminator becomes an error instead of a silent drop.
    ``noun`` names the thing in messages ("transformation", "derivation");
    ``unknown_kind_error`` is a format string with a ``{kind}`` placeholder,
    replacing the message for a discriminator value this union has no member for --
    the place to say what the caller should use instead.
    """
    raw = data.get(discriminator)
    kind = raw.value if hasattr(raw, "value") else raw
    data = {**data, discriminator: kind}

    member = members.get(kind)
    if member is None:
        raise ValueError((unknown_kind_error or "A {noun} cannot be a {kind}.").format(kind=kind, noun=noun))

    try:
        return member.model_validate(data)
    except ValidationError as err:
        raise ValueError(_member_mismatch(err, member=member, kind=kind, noun=noun, discriminator=discriminator)) from err


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.title() for part in tail)


def _an(kind: str) -> str:
    return f"An {kind}" if kind[:1] in "AEIOU" else f"A {kind}"


def _member_mismatch(err: ValidationError, *, member: type[BaseModel], kind: str, noun: str, discriminator: str) -> str:
    reads = [_camel(name) for name in member.model_fields if name != discriminator]
    reads_clause = "it reads " + ", ".join(f"`{name}`" for name in reads) if reads else "it takes no parameters at all"
    for detail in err.errors():
        loc = [str(part) for part in detail["loc"] if str(part) != discriminator]
        field = _camel(loc[0]) if loc else discriminator
        if detail["type"] == "extra_forbidden":
            return f"{_an(kind)} {noun} does not read `{field}`: {reads_clause}. Drop it, or pick the kind whose map it is."
        if detail["type"] == "missing":
            return f"{_an(kind)} {noun} requires `{field}`"
    first = err.errors()[0]
    return f"Invalid {kind} {noun}: {first['msg']}"
