"""Input types for a sparse dataset's axes: the one question each axis has to answer.

A sparse matrix is a grid of numbers with **no row labels and no column labels**. To mean
anything it has to say what its rows are and what its columns are, and there are exactly three
ways to answer -- a mask whose pixels are the ids, a collection whose geometry carries them, or a
table whose rows the positions are. Every axis answers exactly once.

**That is why the answer lives on the axis.** It used to be split across two sibling lists,
``keyedBy`` and ``axisReferences``, of which only the second named an axis at all -- the first was
matched to its axis by subtraction inside ``write_key_edges``, which is correct and invisible.
Here the pairing is the input's own shape, so "identified exactly once" stops being a check the
mutation performs and becomes a thing a caller cannot express otherwise.

Two of the three kinds author a FIELD edge and the third does not, and that difference is real
rather than an implementation detail: a mask and a collection are things whose *contents* identify
an object, which is a claim about space and therefore an edge; a table is already in record-land,
where the relation is a foreign key. :class:`core.enums.KeyedBySourceKind` draws that same line for
tables, and this is a superset of it -- ``TABLE`` is valid here and nowhere else, because a table
cannot key a table but an axis whose positions are its rows is the ordinary case.

Flat-discriminated in the wire shape, following ``core.input_unions`` exactly as ``KeyedByInput``
and ``DerivedFromInput`` do, because GraphQL has no input unions.
"""

from typing import Annotated, ClassVar, Literal

import strawberry
from pydantic import BaseModel, ConfigDict, Field

import kante

from core import enums
from core.input_unions import parse_union_member, prose_errors, union_memberships

_NAME_DESCRIPTION = (
    "What to call the edge this authors, in a graph a person has to read. Defaults to `<source> -> <dataset>`. Only meaningful for the kinds that author one"
)

_AXIS_NAME_DESCRIPTION = (
    "The axis' name, free-form and unique within this dataset -- `bin`, `gene`, `metabolite`, `neuron`. It is the name a colouring names a position along, and the name the "
    "server reports back in `indexableAxes`"
)


class SparseIdentificationInputBase(BaseModel):
    """The fields every identification carries, whichever kind of thing it names."""

    model_config = ConfigDict(extra="forbid")

    kind: enums.SparseIdentificationKind
    name: str | None = None
    validity: enums.PlacementValidity | None = None

    #: The member's own id field, so a reader needs no per-member branch. A ClassVar, so pydantic
    #: treats it as neither a field nor a private attribute.
    SOURCE_FIELD: ClassVar[str] = "source"

    #: Whether this kind authors a FIELD edge. The one behavioural difference between the members,
    #: stated once here rather than branched on at every call site.
    AUTHORS_EDGE: ClassVar[bool] = True

    @property
    def source_id(self) -> str:
        """The id of whichever source this member names."""
        return getattr(self, type(self).SOURCE_FIELD)


class DatasetIdentifiesInputModel(SparseIdentificationInputBase):
    """Identified by a label mask, through its intrinsic pixel grid."""

    kind: Literal[enums.SparseIdentificationKind.DATASET] = enums.SparseIdentificationKind.DATASET
    dataset: str
    SOURCE_FIELD: ClassVar[str] = "dataset"


class MeshCollectionIdentifiesInputModel(SparseIdentificationInputBase):
    """Identified by a mesh collection, through its vertex coordinate system."""

    kind: Literal[enums.SparseIdentificationKind.MESH_COLLECTION] = enums.SparseIdentificationKind.MESH_COLLECTION
    mesh_collection: str
    SOURCE_FIELD: ClassVar[str] = "mesh_collection"


class TableIdentifiesInputModel(SparseIdentificationInputBase):
    """Identified by a table whose rows this axis' positions are.

    Authors no edge. That is not an omission: an edge is a claim about how one space maps into
    another, and this claim is a foreign key -- *the values along this axis identify rows of that
    table*. It is also what lets a FIELD edge land on the same dataset at all, since an axis
    identified this way is one the edge is not expected to supply.
    """

    kind: Literal[enums.SparseIdentificationKind.TABLE] = enums.SparseIdentificationKind.TABLE
    table: str
    SOURCE_FIELD: ClassVar[str] = "table"
    AUTHORS_EDGE: ClassVar[bool] = False


#: Every identification kind, keyed by discriminator value.
SPARSE_IDENTIFICATION_MEMBERS: dict[str, type[BaseModel]] = {
    enums.SparseIdentificationKind.DATASET.value: DatasetIdentifiesInputModel,
    enums.SparseIdentificationKind.MESH_COLLECTION.value: MeshCollectionIdentifiesInputModel,
    enums.SparseIdentificationKind.TABLE.value: TableIdentifiesInputModel,
}

#: The union the pydantic side carries, so the mutation never sees the flat wire shape.
SparseIdentificationSpec = Annotated[
    DatasetIdentifiesInputModel | MeshCollectionIdentifiesInputModel | TableIdentifiesInputModel,
    Field(discriminator="kind"),
]

#: The wire fields carrying a source id, one per member.
_SOURCE_FIELDS = ("dataset", "mesh_collection", "table")


@prose_errors
@strawberry.input(
    description=(
        "What one axis of a sparse dataset **is**, as a discriminated union: `kind` selects which sort of thing is being named, and only that member's id field is read -- any "
        "other is rejected. Every axis carries exactly one of these, which is what makes 'identified exactly once' a property of the input rather than a check on it. `DATASET` "
        "and `MESH_COLLECTION` author a FIELD edge from the source into this matrix, which is also what makes the matrix reachable from a layer over that source; `TABLE` authors "
        "no edge and states a foreign key instead"
    ),
)
class SparseIdentificationInput:
    """How one axis is identified, discriminated by `kind`.

    Deliberately not pydantic-backed: the wire type is flat because GraphQL has no input unions,
    and ``to_pydantic`` is where that flatness is corrected into the strict member.
    """

    kind: enums.SparseIdentificationKind = strawberry.field(description="Which sort of thing identifies this axis. It fixes which id field below is read; any other is rejected")
    dataset: strawberry.ID | None = strawberry.field(
        default=None,
        description="(DATASET) The label dataset whose pixel values are the positions along this axis. Its own pixel grid is both the edge's input and its field, which is what a label mask is",
    )
    mesh_collection: strawberry.ID | None = strawberry.field(
        default=None,
        description="(MESH_COLLECTION) The mesh collection whose geometry rows carry the positions. Its vertex space is both the edge's input and its field, exactly as a mask's grid is",
    )
    table: strawberry.ID | None = strawberry.field(
        default=None,
        description="(TABLE) The table whose rows this axis' positions are. Must be keyed by exactly one INDEX coordinate column, which is where a position is looked up -- the same contract `TableColumn.references` carries. A matrix with 19 059 features costs one picker entry because of this, not 19 059",
    )
    name: str | None = strawberry.field(default=None, description=_NAME_DESCRIPTION)
    validity: enums.PlacementValidity | None = strawberry.field(default=None, description="How far the edge this authors may be trusted. Only meaningful for the kinds that author one")

    def to_pydantic(self) -> BaseModel:
        """Match the flat wire fields to the member model `kind` selects, strictly."""
        supplied = {name: getattr(self, name) for name in ("kind", "name", "validity", *_SOURCE_FIELDS)}
        data = {name: value for name, value in supplied.items() if value is not None}
        return parse_union_member(SPARSE_IDENTIFICATION_MEMBERS, data, noun="identification")


def _identification_member(model: type, key: "enums.SparseIdentificationKind", description: str):  # noqa: ANN202 - a decorator factory
    """Publish one member input of the SparseIdentificationInput union."""
    return kante.pydantic_input(
        model,
        directives=union_memberships("SparseIdentificationInput", key=key.value),
        description=f"{description}. Published for codegen; the wire type is the flat SparseIdentificationInput",
    )


@_identification_member(DatasetIdentifiesInputModel, enums.SparseIdentificationKind.DATASET, "The fields a DATASET identification reads")
class DatasetIdentifiesInput:
    """The DATASET member of the identification union."""

    kind: enums.SparseIdentificationKind = strawberry.field(description="The discriminator: which member of SparseIdentificationInput this is")
    dataset: strawberry.ID = strawberry.field(description="The label dataset whose pixel values are the positions along this axis")
    name: str | None = strawberry.field(default=None, description=_NAME_DESCRIPTION)
    validity: enums.PlacementValidity | None = strawberry.field(default=None, description="How far the edge this authors may be trusted")


@_identification_member(MeshCollectionIdentifiesInputModel, enums.SparseIdentificationKind.MESH_COLLECTION, "The fields a MESH_COLLECTION identification reads")
class MeshCollectionIdentifiesInput:
    """The MESH_COLLECTION member of the identification union."""

    kind: enums.SparseIdentificationKind = strawberry.field(description="The discriminator: which member of SparseIdentificationInput this is")
    mesh_collection: strawberry.ID = strawberry.field(description="The mesh collection whose geometry rows carry the positions")
    name: str | None = strawberry.field(default=None, description=_NAME_DESCRIPTION)
    validity: enums.PlacementValidity | None = strawberry.field(default=None, description="How far the edge this authors may be trusted")


@_identification_member(TableIdentifiesInputModel, enums.SparseIdentificationKind.TABLE, "The fields a TABLE identification reads")
class TableIdentifiesInput:
    """The TABLE member of the identification union."""

    kind: enums.SparseIdentificationKind = strawberry.field(description="The discriminator: which member of SparseIdentificationInput this is")
    table: strawberry.ID = strawberry.field(description="The table whose rows this axis' positions are, keyed by its single INDEX coordinate column")


class SparseAxisInputModel(BaseModel):
    """One axis of a sparse dataset: its name, and what it is."""

    model_config = ConfigDict(extra="forbid")

    name: str
    identified_by: SparseIdentificationSpec
    long_name: str | None = None
    description: str | None = None


@kante.pydantic_input(
    SparseAxisInputModel,
    description=(
        "One axis of a sparse matrix, and what its positions **are**. Every axis carries exactly one `identifiedBy`, so an axis identified twice or not at all is not something "
        "this input can express -- which matters, because an axis nothing identifies is not a lax dataset, it is one no source could ever key. There is no `type` field: both "
        "axes of a sparse matrix enumerate and neither has a metric, so INDEX is the only thing it could ever be"
    ),
)
class SparseAxisInput:
    """One axis of a sparse dataset."""

    name: str = strawberry.field(description=_AXIS_NAME_DESCRIPTION)
    identified_by: SparseIdentificationInput = strawberry.field(description="What this axis' positions are: a source whose contents are the ids, or the table whose rows they are")
    long_name: str | None = strawberry.field(default=None, description="A human-readable name for the axis")
    description: str | None = strawberry.field(default=None, description="What this axis enumerates, for a reader of the schema")


#: The member inputs published to the SDL, for the schema's ``types=[...]``. Dropping one erases
#: it from the SDL silently, and the union then advertises a member nobody can construct.
sparse_identification_union_types: list[type] = [DatasetIdentifiesInput, MeshCollectionIdentifiesInput, TableIdentifiesInput]
