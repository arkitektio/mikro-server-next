"""Mutations for table datasets: parquet-backed tables of scientific records.

A table dataset is the coordinate graph's home for tabular data -- one row per
segmented object, per localization, per cell. It parallels ``createADataset`` but
is backed by a Parquet store and has no multiscale. Its declared coordinate columns
become the axes of a coordinate system it owns, which is what lets a localization
table be placed in a scene; a table with no coordinate columns degenerates to a
single INDEX axis whose only honest edge is UNMAPPABLE -- the measurement-table case
the old FeatureCollection served.
"""

import strawberry
from kante.types import Info
from pydantic import BaseModel, Field

import kante
from core import enums, models, scalars, types
from core.creation import CreationContext
from core.inputs.coords import AxisInputModel, DerivationInput, DerivationInputModel
from core.logic import graph as graph_logic
from core.logic import tables as tables_logic
from core.mutations._generic import make_delete, self_owner
from core.scoping import get_for_org

#: The degenerate space of a table with no coordinate columns: one axis enumerating the
#: rows. No unit (nothing to measure between object 3 and object 4), no second axis (the
#: columns are named in the Parquet, not indexed by position). Its only honest edge to a
#: source is UNMAPPABLE.
_INDEX_AXES = [AxisInputModel(name="object", type=enums.AxisType.INDEX)]

#: The coordinate axis types a table column may declare in v1. MICROTIME/SPECTRUM pass the
#: unit and ordering checks but nothing renders them from a table yet, so they are held back.
_COORDINATE_AXIS_TYPES = {enums.AxisType.SPACE, enums.AxisType.TIME}


class TableColumnInputModel(BaseModel):
    name: str
    dtype: str
    role: enums.TableColumnRole = enums.TableColumnRole.ATTRIBUTE
    axis_type: enums.AxisType | None = None
    unit: str | None = None
    long_name: str | None = None
    description: str | None = None


@kante.pydantic_input(TableColumnInputModel, description="One declared column of a table dataset: its name, dtype, and role. A COORDINATE column also carries an axis type and optional unit and becomes an axis of the table's space")
class TableColumnInput:
    """One declared column of a table dataset."""

    name: str = strawberry.field(description="The column name, matching the Parquet column")
    dtype: str = strawberry.field(description="The column's data type as a DuckDB type string, e.g. 'DOUBLE', 'BIGINT'")
    role: enums.TableColumnRole = strawberry.field(default=enums.TableColumnRole.ATTRIBUTE, description="What the column is for: COORDINATE (becomes an axis and places the row), ATTRIBUTE, ID, TRACK_ID, LABEL or COLOR")
    axis_type: enums.AxisType | None = strawberry.field(default=None, description="(coordinate) The axis type this column samples, SPACE or TIME. Required for a COORDINATE column, forbidden otherwise")
    unit: str | None = strawberry.field(default=None, description="(coordinate) The physical unit of the values, e.g. 'nanometer'. Omit for pixel-index coordinates; a table's spatial columns must be all calibrated or all pixel-index")
    long_name: str | None = strawberry.field(default=None, description="A human-readable name for the column")
    description: str | None = strawberry.field(default=None, description="A free-form description of what the column holds, e.g. 'mean GFP intensity within the segmented object'. Carried onto the derived axis for a COORDINATE column")


class CreateTableDatasetInputModel(BaseModel):
    name: str
    data: str
    columns: list[TableColumnInputModel] = Field(default_factory=list)
    description: str | None = None
    coordinate_system: str | None = None
    derived_from: DerivationInputModel | None = None
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
    coordinate_system: strawberry.ID | None = strawberry.field(
        default=None,
        description="The coordinate system the table was computed FROM, e.g. the intrinsic grid of the label image its rows were segmented from. The table owns its own space; this is the space its `derivedFrom` edge relates it to. Omit for a freestanding table",
    )
    derived_from: DerivationInput | None = strawberry.field(
        default=None,
        description="How the table's own space relates to the source `coordinateSystem`. Defaults to UNMAPPABLE (records the lineage, claims no geometry -- the truth for a measurement table). To place a localization table, state a mappable kind (IDENTITY / SCALE / AFFINE / BY_DIMENSION); the rank check holds you to it. Ignored without a `coordinateSystem`. Registering the table's space into a scene is a separate step: createTransformation, then the layer",
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
                raise ValueError(f"COORDINATE column '{col.name}' must declare an axisType (SPACE or TIME).")
            if col.axis_type not in _COORDINATE_AXIS_TYPES:
                raise ValueError(f"COORDINATE column '{col.name}' has axisType {col.axis_type.value}, but a table's coordinate columns must be SPACE or TIME.")
        else:
            if col.axis_type is not None:
                raise ValueError(f"Column '{col.name}' has role {col.role.value} but declares an axisType. Only COORDINATE columns carry one.")
            if col.unit is not None:
                raise ValueError(f"Column '{col.name}' has role {col.role.value} but declares a unit. Only COORDINATE columns carry one.")

    for role, label in ((enums.TableColumnRole.TRACK_ID, "TRACK_ID"), (enums.TableColumnRole.ID, "ID")):
        count = sum(1 for col in columns if col.role == role)
        if count > 1:
            raise ValueError(f"A table has at most one {label} column, but {count} were declared.")


def create_table_dataset(info: Info, input: CreateTableDatasetInput) -> types.TableDataset:
    """Create a table dataset, its owned coordinate system, and (optionally) its lineage edge."""
    model = input.to_pydantic()
    ctx = CreationContext.from_info(info)

    _validate_columns(model.columns)

    store = get_for_org(models.ParquetStore, info, id=model.data)
    store.fill_info()

    if model.validate_schema:
        actual = {row[0]: row[1] for row in tables_logic.columns_for_store(store)}
        for col in model.columns:
            if col.name not in actual:
                raise ValueError(f"Declared column '{col.name}' is not in the Parquet file (has: {sorted(actual)}).")

    dataset = models.TableDataset.objects.create(
        name=model.name,
        description=model.description,
        store=store,
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
            )
            for index, col in enumerate(model.columns)
        ]
    )

    coordinate_columns = [col for col in model.columns if col.role == enums.TableColumnRole.COORDINATE]
    system = models.CoordinateSystem.objects.create(
        name=f"{model.name}/table",
        table_dataset=dataset,
        creator=ctx.user,
        organization=ctx.organization,
    )
    if coordinate_columns:
        graph_logic.create_table_axes(system, coordinate_columns)
    else:
        graph_logic.create_pixel_axes(system, _INDEX_AXES)

    if model.coordinate_system is not None:
        source = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system)
        derivation = model.derived_from
        graph_logic.write_relation_edge(
            name=f"{dataset.name} <- {source.name}",
            input_system=system,
            output_system=source,
            # UNMAPPABLE unless the client authored the geometric relationship: naming a
            # source is not the same as claiming a map, and a fabricated identity would both
            # lie when units differ and outrank a real edge.
            kind=(derivation.kind.value if derivation else enums.TransformKind.UNMAPPABLE.value),
            scale=derivation.scale if derivation else None,
            translation=derivation.translation if derivation else None,
            affine=derivation.affine if derivation else None,
            input_axes=derivation.input_axes if derivation else None,
            output_axes=derivation.output_axes if derivation else None,
            reason=derivation.reason if derivation else None,
            ctx=ctx,
        )

    return dataset


class UpdateTableDatasetInputModel(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None


@kante.pydantic_input(UpdateTableDatasetInputModel, description="Input for updating a table dataset's name or description")
class UpdateTableDatasetInput:
    """Input for updating a table dataset."""

    id: strawberry.ID = strawberry.field(description="The ID of the table dataset to update")
    name: str | None = strawberry.field(default=None, description="A new name")
    description: str | None = strawberry.field(default=None, description="A new description")


def update_table_dataset(info: Info, input: UpdateTableDatasetInput) -> types.TableDataset:
    """Update a table dataset's name or description. A table dataset is mutable, unlike a collection."""
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
