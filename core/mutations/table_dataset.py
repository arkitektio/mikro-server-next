"""Mutations for table datasets: parquet-backed tables of scientific records.

A table dataset is the coordinate graph's home for tabular data -- one row per
segmented object, per localization, per cell. It parallels ``createADataset`` but
is backed by a Parquet store and has no multiscale. Its declared coordinate columns
become the axes of a coordinate system it owns, which is what lets a localization
table be placed in a scene; a table with no coordinate columns degenerates to a
single INDEX axis whose only honest edge is UNMAPPABLE -- the measurement-table case
the old FeatureCollection served.
"""

from typing import Annotated, ClassVar, Literal

import strawberry
from django.db import transaction
from kante.types import Info
from pydantic import BaseModel, ConfigDict, Field

import kante
from kanne_server import scalars as kanne_scalars

from core import enums, models, scalars, types
from core.creation import CreationContext
from core.input_unions import parse_union_member, prose_errors, union_memberships
from core.inputs.file_link import SourceFileInput, SourceFileInputModel
from core.inputs.coords import AxisInputModel, DerivedFromInput, DerivedFromSpec
from core.logic import coordinate_system as coordinate_system_logic
from core.logic import file_link as file_link_logic
from core.logic import folder as folder_logic
from core.logic import graph as graph_logic
from core.logic import tables as tables_logic
from core.mutations._generic import make_delete, self_owner
from core.scoping import get_for_org

#: The degenerate space of a table with no coordinate columns: one axis enumerating the
#: rows. No unit (nothing to measure between object 3 and object 4), no second axis (the
#: columns are named in the Parquet, not indexed by position). Its only honest edge to a
#: source is UNMAPPABLE.
_INDEX_AXES = [AxisInputModel(name="object", type=enums.AxisType.INDEX)]

#: The coordinate axis types a table column may declare. MICROTIME/SPECTRUM pass the unit and
#: ordering checks but nothing renders them from a table yet, so they are held back.
#:
#: INDEX is here for lineage, not rendering: an id column whose values are a label mask's
#: pixels is the *coordinate* of the space those pixels point into, exactly as an `x` column
#: in nanometres is the coordinate of a spatial axis. A coordinate column's values are always
#: its coordinates -- that rule is what makes this consistent rather than an exception. The
#: rendering rationale that holds MICROTIME back does not reach it, and it cannot leak into a
#: layer: both layer paths filter coordinate columns to SPACE.
_COORDINATE_AXIS_TYPES = {enums.AxisType.SPACE, enums.AxisType.TIME, enums.AxisType.INDEX}

#: The roles a unit means something on. A coordinate's position and a measurement's value are
#: both quantities -- an area is 'micrometer**2', a marker level is 'a.u.' -- and a client that
#: plots either needs the unit as much as the number. An id, a track id, a label and a colour
#: are not measured, so a unit on one would name a metric that does not exist: the same argument
#: the INDEX rule below makes, applied to the roles rather than the axis types.
_UNIT_BEARING_ROLES = {enums.TableColumnRole.COORDINATE, enums.TableColumnRole.ATTRIBUTE}


class TableColumnInputModel(BaseModel):
    name: str
    dtype: str
    role: enums.TableColumnRole = enums.TableColumnRole.ATTRIBUTE
    axis_type: enums.AxisType | None = None
    unit: str | None = None
    long_name: str | None = None
    description: str | None = None
    references: str | None = None


@kante.pydantic_input(TableColumnInputModel, description="One declared column of a table dataset: its name, dtype, and role. A COORDINATE column also carries an axis type and becomes an axis of the table's space; a COORDINATE or ATTRIBUTE column may state the unit its values are in")
class TableColumnInput:
    """One declared column of a table dataset."""

    name: str = strawberry.field(description="The column name, matching the Parquet column")
    dtype: str = strawberry.field(description="The column's data type as a DuckDB type string, e.g. 'DOUBLE', 'BIGINT'")
    role: enums.TableColumnRole = strawberry.field(default=enums.TableColumnRole.ATTRIBUTE, description="What the column is for: COORDINATE (becomes an axis and places the row), ATTRIBUTE, ID, TRACK_ID, LABEL or COLOR")
    axis_type: enums.AxisType | None = strawberry.field(default=None, description="(coordinate) The axis type this column samples, SPACE or TIME. Required for a COORDINATE column, forbidden otherwise")
    unit: kanne_scalars.Unit | None = strawberry.field(
        default=None,
        description="The unit the column's values are in, e.g. 'nanometer' or 'micrometer**2'. A pint unit, validated on the way in; 'a.u.' for arbitrary units. On a COORDINATE column it becomes the unit of the derived axis -- omit it for pixel-index coordinates, and note a table's spatial columns must be all calibrated or all pixel-index. On an ATTRIBUTE column it is what the measurement is in, and nothing but parseability is checked (an area is not a length). Carried by those two roles only: an id or a colour is not measured",
    )
    long_name: str | None = strawberry.field(default=None, description="A human-readable name for the column")
    description: str | None = strawberry.field(default=None, description="A free-form description of what the column holds, e.g. 'mean GFP intensity within the segmented object'. Carried onto the derived axis for a COORDINATE column")
    references: strawberry.ID | None = strawberry.field(
        default=None,
        description="The table dataset whose rows this column's values identify -- a declared foreign key, e.g. an `instance_id` column referencing a table of tracks. The target must already exist and be keyed by a single INDEX coordinate column; which column that is stays declared on the target, so this states only *which table*. Refused on a COORDINATE column: a coordinate places the row, it does not point elsewhere",
    )


_KEYED_BY_NAME_DESCRIPTION = "An optional name for the edge. Defaults to '<source> -> <table>'"

_KEYED_BY_VALIDITY_DESCRIPTION = (
    "How much this dereference is actually known. Defaults to MANUAL -- someone authored it. Say VALIDATED when the ids the source carries were checked against the table's rows"
)


class KeyedByInputBase(BaseModel):
    """The fields every keying entry carries, whichever kind of source it names."""

    model_config = ConfigDict(extra="forbid")

    kind: enums.KeyedBySourceKind
    name: str | None = None
    validity: enums.PlacementValidity | None = None

    #: The member's own id field, so the reader below needs no per-member branch. A
    #: ClassVar, so pydantic treats it as neither a field nor a private attribute.
    SOURCE_FIELD: ClassVar[str] = "source"

    @property
    def source_id(self) -> str:
        """The id of whichever source this member names."""
        return getattr(self, type(self).SOURCE_FIELD)


class DatasetKeyedByInputModel(KeyedByInputBase):
    """Keyed by a label mask, through its intrinsic pixel grid."""

    kind: Literal[enums.KeyedBySourceKind.DATASET] = enums.KeyedBySourceKind.DATASET
    dataset: str
    SOURCE_FIELD: ClassVar[str] = "dataset"


class MeshCollectionKeyedByInputModel(KeyedByInputBase):
    """Keyed by a mesh collection, through its vertex coordinate system."""

    kind: Literal[enums.KeyedBySourceKind.MESH_COLLECTION] = enums.KeyedBySourceKind.MESH_COLLECTION
    mesh_collection: str
    SOURCE_FIELD: ClassVar[str] = "mesh_collection"


#: Every keying source kind, keyed by discriminator value.
KEYED_BY_MEMBERS: dict[str, type[BaseModel]] = {
    enums.KeyedBySourceKind.DATASET.value: DatasetKeyedByInputModel,
    enums.KeyedBySourceKind.MESH_COLLECTION.value: MeshCollectionKeyedByInputModel,
}

#: The union the pydantic side carries, so `write_key_edges` never sees the flat wire shape.
KeyedBySpec = Annotated[DatasetKeyedByInputModel | MeshCollectionKeyedByInputModel, Field(discriminator="kind")]

#: The wire fields carrying a source id, one per member.
_KEYED_BY_SOURCE_FIELDS = ("dataset", "mesh_collection")


@prose_errors
@strawberry.input(
    description=(
        "A source whose own contents are the ids this table is indexed by, as a discriminated union: `kind` selects which sort of source is being named, and only that member's id "
        "field is read -- any other is rejected. It authors the FIELD edge in the direction the map actually runs -- source -> table rows -- which is the direction attributePlans "
        "discovers, and the opposite of the lineage `derivedFrom` records"
    ),
)
class KeyedByInput:
    """One source keying this table, discriminated by `kind`.

    Deliberately not pydantic-backed: the wire type is flat because GraphQL has no input
    unions, and ``to_pydantic`` is where that flatness is corrected into the strict member.
    """

    kind: enums.KeyedBySourceKind = strawberry.field(description="Which sort of thing the source is. It fixes which id field below is read; any other is rejected")
    dataset: strawberry.ID | None = strawberry.field(
        default=None,
        description="(DATASET) The label dataset whose pixels are the map. Its own pixel grid is both the edge's input and its field, which is what a label mask is: the array being mapped is the array doing the mapping",
    )
    mesh_collection: strawberry.ID | None = strawberry.field(
        default=None,
        description="(MESH_COLLECTION) The mesh collection whose geometry carries the ids. Its own vertex space is both the edge's input and its field, exactly as a mask's grid is -- what differs is only where the id was materialised: on the geometry rows rather than in pixels, so a client that picked a surface is already holding one and samples nothing",
    )
    name: str | None = strawberry.field(default=None, description=_KEYED_BY_NAME_DESCRIPTION)
    validity: enums.PlacementValidity | None = strawberry.field(default=None, description=_KEYED_BY_VALIDITY_DESCRIPTION)

    def to_pydantic(self) -> BaseModel:
        """Match the flat wire fields to the member model `kind` selects, strictly."""
        supplied = {name: getattr(self, name) for name in ("kind", "name", "validity", *_KEYED_BY_SOURCE_FIELDS)}
        data = {name: value for name, value in supplied.items() if value is not None}
        return parse_union_member(KEYED_BY_MEMBERS, data, noun="keying")


def _keyed_by_member(model: type, key: "enums.KeyedBySourceKind", description: str):  # noqa: ANN202 - a decorator factory
    """Publish one member input of the KeyedByInput union."""
    return kante.pydantic_input(
        model,
        directives=union_memberships("KeyedByInput", key=key.value),
        description=f"{description}. Published for codegen; the wire type is the flat KeyedByInput",
    )


@_keyed_by_member(DatasetKeyedByInputModel, enums.KeyedBySourceKind.DATASET, "The fields a DATASET keying reads")
class DatasetKeyedByInput:
    """The DATASET member of the keying source union."""

    kind: enums.KeyedBySourceKind = strawberry.field(description="The discriminator: which member of KeyedByInput this is")
    dataset: strawberry.ID = strawberry.field(description="The label dataset whose pixels are the map")
    name: str | None = strawberry.field(default=None, description=_KEYED_BY_NAME_DESCRIPTION)
    validity: enums.PlacementValidity | None = strawberry.field(default=None, description=_KEYED_BY_VALIDITY_DESCRIPTION)


@_keyed_by_member(MeshCollectionKeyedByInputModel, enums.KeyedBySourceKind.MESH_COLLECTION, "The fields a MESH_COLLECTION keying reads")
class MeshCollectionKeyedByInput:
    """The MESH_COLLECTION member of the keying source union."""

    kind: enums.KeyedBySourceKind = strawberry.field(description="The discriminator: which member of KeyedByInput this is")
    mesh_collection: strawberry.ID = strawberry.field(description="The mesh collection whose geometry carries the ids")
    name: str | None = strawberry.field(default=None, description=_KEYED_BY_NAME_DESCRIPTION)
    validity: enums.PlacementValidity | None = strawberry.field(default=None, description=_KEYED_BY_VALIDITY_DESCRIPTION)


#: The member inputs published to the SDL, for the schema's ``types=[...]``. Dropping one
#: erases it from the SDL silently -- they are referenced by no field.
keyed_by_union_types: list[type] = [DatasetKeyedByInput, MeshCollectionKeyedByInput]


class CreateTableDatasetInputModel(BaseModel):
    name: str
    data: str
    columns: list[TableColumnInputModel] = Field(default_factory=list)
    description: str | None = None
    folder: str | None = None
    derived_from: list[DerivedFromSpec] | None = None
    source_files: list[SourceFileInputModel] | None = None
    keyed_by: list[KeyedBySpec] | None = None
    validate_schema: bool = False


@kante.pydantic_input(
    CreateTableDatasetInputModel,
    description="Input for creating a table dataset from a Parquet store. Its coordinate columns become the axes of a coordinate system it owns; declare no coordinate columns for a pure measurement table (its rows enumerate objects and its lineage edge is UNMAPPABLE)",
)
class CreateTableDatasetInput:
    """Input for creating a table dataset."""

    name: str = strawberry.field(description="The name of the table dataset")
    data: scalars.ParquetLike = strawberry.field(description="The uploaded Parquet store holding the rows. Upload it through the normal parquet path (requestParquetUpload) and pass the store id here")
    columns: list[TableColumnInput] = strawberry.field(default_factory=list, description="The declared column schema. COORDINATE columns become the table's axes (in declared order, which must obey the type ordering time-then-space); the rest are data")
    description: str | None = strawberry.field(default=None, description="An optional description")
    folder: strawberry.ID | None = strawberry.field(
        default=None,
        description="The folder to file this table dataset in. Organisational only -- it says nothing about where the rows sit in space. Defaults to the user's default folder",
    )
    derived_from: list[DerivedFromInput] | None = strawberry.field(
        default=None,
        description="What this table was computed from -- the instance mask its rows were segmented out of, say. One entry per source; the first is the primary parent. Each names its source and how the table's own space relates to that source's: **omit the transform and the edge is UNMAPPABLE**, which records the lineage and claims no geometry, the truth for a measurement table whose rows are not anywhere. To place a localization table, state a mappable kind. Registering the table's space into a scene is a separate step: createTransformation, then the layer",
    )
    source_files: list[SourceFileInput] | None = strawberry.field(
        default=None,
        description="Optional statement of which files this table was loaded from -- the CSV or parquet a converter read. **Not a `derivedFrom` entry, deliberately**: a derivation is an edge of the coordinate graph and relates two spaces, while a file has no space. This records lineage between bytes and data and leaves the graph untouched",
    )
    keyed_by: list[KeyedByInput] | None = strawberry.field(
        default=None,
        description="The sources whose own contents are the ids this table is indexed by -- the instance mask its rows were measured out of, or the mesh collection whose surfaces they describe. A list, because siblings may key one table. This is the *other* edge from `derivedFrom` and not a repetition of it: `derivedFrom` runs table -> source and records what the table was computed from, while this runs source -> table and is the map a client follows to answer 'what object is here'. Only this direction is discoverable through attributePlans",
    )
    validate_schema: bool = strawberry.field(default=False, description="When true, DESCRIBE the Parquet and reject any declared column whose name/dtype does not match the file. Off by default (the store may not be reachable at create time)")


def _validate_columns(columns: list[TableColumnInputModel]) -> None:
    """Reject a column schema that is internally inconsistent, before anything is written."""
    names = [col.name for col in columns]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"Each column must have a distinct name, but {', '.join(duplicates)} appear{'s' if len(duplicates) == 1 else ''} more than once.")

    for col in columns:
        is_coord = col.role == enums.TableColumnRole.COORDINATE
        if is_coord:
            if col.axis_type is None:
                raise ValueError(f"COORDINATE column '{col.name}' must declare an axisType (SPACE, TIME or INDEX).")
            if col.axis_type not in _COORDINATE_AXIS_TYPES:
                raise ValueError(f"COORDINATE column '{col.name}' has axisType {col.axis_type.value}, but a table's coordinate columns must be SPACE, TIME or INDEX.")
            # An INDEX axis enumerates -- object 3, object 4 -- and the distance between two
            # of them is not a small number, it is not a number. A unit would name a metric
            # that does not exist. Refused here because `assert_unit_matches_type` cannot:
            # INDEX is absent from its dimension map, which reads as "any unit is fine".
            if col.axis_type == enums.AxisType.INDEX and col.unit is not None:
                raise ValueError(f"COORDINATE column '{col.name}' is an INDEX axis, which has no metric -- the distance between object 3 and object 4 means nothing -- so it carries no unit. Drop `unit`.")
        elif col.axis_type is not None:
            raise ValueError(f"Column '{col.name}' has role {col.role.value} but declares an axisType. Only COORDINATE columns carry one.")

        # The unit is parseable by the time it gets here -- the scalar sees to that -- so all
        # that is left is whether the column is the kind of thing a unit can be *of*.
        if col.unit is not None and col.role not in _UNIT_BEARING_ROLES:
            raise ValueError(f"Column '{col.name}' declares a unit but has role {col.role.value}, which is not measured -- a unit on it would name a metric that does not exist. Only COORDINATE and ATTRIBUTE columns carry one; declare the measurement as ATTRIBUTE.")

        # A coordinate column's values ARE its coordinates -- they place the row in the
        # table's own space. Claiming they simultaneously identify rows elsewhere would make
        # the column two different maps at once, and which one a reader follows would be
        # convention again.
        if is_coord and col.references is not None:
            raise ValueError(f"COORDINATE column '{col.name}' cannot reference another table: a coordinate places the row in this table's own space, it does not point elsewhere. Declare the reference on a data column (ID, TRACK_ID, ...).")

    for role, label in ((enums.TableColumnRole.TRACK_ID, "TRACK_ID"), (enums.TableColumnRole.ID, "ID")):
        count = sum(1 for col in columns if col.role == role)
        if count > 1:
            raise ValueError(f"A table has at most one {label} column, but {count} were declared.")


def _resolve_reference_target(info: Info, col: TableColumnInputModel) -> models.TableDataset:
    """Resolve and vet the table a column declares it references.

    A reference must support the dereference: given a value, fetch *the row*. That is a
    property of the target table -- it must be keyed by exactly one INDEX axis, and that
    axis must be backed by a real coordinate column (the degenerate no-coordinate table
    also has a single INDEX axis, but it is synthetic row enumeration with no column to
    bind in a WHERE clause). Everything else -- which column, its dtype -- stays declared
    on the target and is derived, never restated here.
    """
    target = get_for_org(models.TableDataset, info, id=col.references)
    axes = target.axes
    if len(axes) != 1 or axes[0].type != enums.AxisType.INDEX.value:
        described = ", ".join(f"{axis.name}:{axis.type}" for axis in axes) or "none"
        raise ValueError(f"Column '{col.name}' references table '{target.name}', but a reference target must be keyed by exactly one INDEX axis (its axes are [{described}]). A composite-keyed table cannot be identified by a single value.")
    if not target.columns.filter(role=enums.TableColumnRole.COORDINATE.value, name=axes[0].name).exists():
        raise ValueError(f"Column '{col.name}' references table '{target.name}', whose INDEX axis '{axes[0].name}' is synthetic row enumeration (the table declares no coordinate columns). There is no column to look a value up in, so it cannot be a reference target.")
    return target


def create_table_dataset(info: Info, input: CreateTableDatasetInput) -> types.TableDataset:
    """Create a table dataset, its owned coordinate system, and (optionally) its lineage edge."""
    model = input.to_pydantic()
    ctx = CreationContext.from_info(info)

    _validate_columns(model.columns)

    # Resolved before anything is written, so a bad reference rejects the whole creation.
    # Keyed by column name: names are already validated distinct.
    reference_targets = {col.name: _resolve_reference_target(info, col) for col in model.columns if col.references is not None}

    store = get_for_org(models.ParquetStore, info, id=model.data)
    store.fill_info()

    if model.validate_schema:
        actual = {row[0]: row[1] for row in tables_logic.columns_for_store(store)}
        for col in model.columns:
            if col.name not in actual:
                raise ValueError(f"Declared column '{col.name}' is not in the Parquet file (has: {sorted(actual)}).")

    # Atomic, because the table row, its columns and its space are all written before its
    # derivation edges are checked: an edge whose rank the axes refuse -- a SCALE onto an
    # INDEX space, say -- would otherwise leave an orphan table behind and return an error.
    # The same guarantee `create_coordinate_system` keeps for a space and its registrations.
    with transaction.atomic():
        dataset = models.TableDataset.objects.create(
            name=model.name,
            description=model.description,
            store=store,
            folder=folder_logic.folder_for_new_container(info, ctx, model.folder, model.derived_from),
            creator=ctx.user,
            organization=ctx.organization,
            **ctx.provenance_kwargs(),
        )

        models.TableColumn.objects.bulk_create(
            [
                models.TableColumn(
                    table=dataset,
                    order=index,
                    name=col.name,
                    dtype=col.dtype,
                    role=col.role.value,
                    axis_type=col.axis_type.value if col.axis_type is not None else None,
                    unit=col.unit,
                    long_name=col.long_name,
                    description=col.description,
                    references=reference_targets.get(col.name),
                )
                for index, col in enumerate(model.columns)
            ]
        )

        coordinate_columns = [col for col in model.columns if col.role == enums.TableColumnRole.COORDINATE]
        system = models.CoordinateSystem.objects.create(
            name=f"{model.name}/table",
            creator=ctx.user,
            organization=ctx.organization,
        )
        dataset.coordinate_system = system
        dataset.save(update_fields=["coordinate_system"])
        if coordinate_columns:
            graph_logic.create_table_axes(system, coordinate_columns)
        else:
            graph_logic.create_pixel_axes(system, _INDEX_AXES)

        # A keyedBy edge produces one of this table's axes out of the ids the source
        # carries, so that axis has to be a real coordinate column -- something an id can be
        # looked up *in*. The synthetic `object` axis above has no column behind it, and an
        # edge onto it would be written happily and then silently dropped by
        # `attributePlans`, which is the failure this check exists to turn into a sentence.
        if model.keyed_by and not coordinate_columns:
            raise ValueError(
                f"'{model.name}' declares no COORDINATE columns, so its space is the synthetic `object` axis that merely enumerates rows -- there is no column to look an id up in, and a keyedBy edge onto it would never resolve. "
                "Declare the column holding the source's ids as COORDINATE with axisType INDEX."
            )

        coordinate_system_logic.write_derivation_edges(info, name=dataset.name, own_system=system, derived_from=model.derived_from or [], ctx=ctx)
        file_link_logic.write_file_links(info, container=dataset, source_files=model.source_files or [], ctx=ctx)
        coordinate_system_logic.write_key_edges(info, name=dataset.name, own_system=system, keyed_by=model.keyed_by or [], ctx=ctx)

    return dataset


class UpdateTableDatasetInputModel(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None


@kante.pydantic_input(UpdateTableDatasetInputModel, description="Input for renaming or redescribing a table dataset. These two fields are the whole of what is editable: the store, the declared columns and the coordinate system derived from them are fixed at creation, and a recomputation is a new table")
class UpdateTableDatasetInput:
    """Input for updating a table dataset."""

    id: strawberry.ID = strawberry.field(description="The ID of the table dataset to update")
    name: str | None = strawberry.field(default=None, description="A new name")
    description: str | None = strawberry.field(default=None, description="A new description")


def update_table_dataset(info: Info, input: UpdateTableDatasetInput) -> types.TableDataset:
    """Rename a table dataset, or redescribe it. Those two fields are the whole of what is editable.

    Deliberately not here: the store, the declared columns, and the coordinate system derived
    from them. All three are written once by ``create_table_dataset``, and a table's own system
    is refused by ``updateCoordinateSystem`` besides -- axis order is written by enumeration and
    the rest of the graph is measured against it, so an axis edit is a different space, not an
    edit of this one. A recomputation is a new table.
    """
    model = input.to_pydantic()
    dataset = get_for_org(models.TableDataset, info, id=model.id)
    if model.name is not None:
        dataset.name = model.name
    if model.description is not None:
        dataset.description = model.description
    dataset.save()
    return dataset


class DeleteTableDatasetInputModel(BaseModel):
    id: str = Field(description="The ID of the table dataset to delete")


@kante.pydantic_input(DeleteTableDatasetInputModel, description="Input for deleting a table dataset by ID")
class DeleteTableDatasetInput:
    """Input for deleting a table dataset by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the table dataset to delete")


delete_table_dataset = make_delete(models.TableDataset, DeleteTableDatasetInput, owner=self_owner)
