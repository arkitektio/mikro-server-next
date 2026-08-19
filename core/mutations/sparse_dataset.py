"""Creating a sparse dataset: two identified axes, and one or both stored layouts.

The shape is stated in :mod:`core.models.sparse_dataset`. What this module adds is the
checking, and every check here exists because the thing it catches is otherwise silent:

* a store whose declared shape contradicts the axes, which would place every lookup one
  position out and never raise;
* two stores indexing the same axis, which is two copies of one capability with nothing to say
  which a reader should use;
* an axis identified twice, or not at all -- the second being what makes a FIELD edge
  unwritable, since ``assert_edge_rank`` can only account for an axis the edge supplies or the
  target identifies.

Nothing about the *matrix* is declared: the encoding, the shape, the nonzero count and the
chunking were read off the artifact when its upload was finished, and are compared against the
declaration rather than taken from it.
"""

import strawberry
from django.db import transaction
from kante.types import Info
from pydantic import BaseModel, Field

import kante
from core import enums, models, scalars, types
from core.creation import CreationContext
from core.inputs.coords import AxisInput, AxisInputModel, DerivedFromInput, DerivedFromSpec
from core.inputs.file_link import SourceFileInput, SourceFileInputModel
from core.logic import coordinate_system as coordinate_system_logic
from core.logic import file_link as file_link_logic
from core.logic import folder as folder_logic
from core.logic import graph as graph_logic
from core.logic import pickers
from core.mutations._generic import make_delete, self_owner
from core.mutations.table_dataset import KeyedByInput, KeyedBySpec, resolve_reference_target
from core.scoping import get_for_org

#: The rank a sparse dataset is built for. Two, and stated rather than assumed: a matrix over
#: two enumerations is what every consumer of this -- the layout rule, the colouring, the
#: hover lookup -- is written against. Nothing in the model forbids three, and an N-D sparse
#: tensor is a real thing, but it would need each of those to say what it means first.
_RANK = 2


class SparseAxisReferenceInputModel(BaseModel):
    """One axis identified by a table: its name, and the table whose rows its positions are."""

    axis: str
    references: str


@kante.pydantic_input(
    SparseAxisReferenceInputModel,
    description=(
        "Identifies one axis of a sparse dataset by naming the table whose rows its positions are -- the same relation `TableColumn.references` carries, said of an axis, because a "
        "matrix has no columns to hang it on. An axis identified this way is one a FIELD edge is not expected to supply"
    ),
)
class SparseAxisReferenceInput:
    """One axis identified by a table."""

    axis: str = strawberry.field(description="The name of the axis being identified. One of this dataset's own")
    references: strawberry.ID = strawberry.field(description="The table whose rows this axis' positions are. Must be keyed by exactly one INDEX coordinate column, which is where a position is looked up")


class CreateSparseDatasetInputModel(BaseModel):
    name: str
    stores: list[str] = Field(default_factory=list)
    axes: list[AxisInputModel] = Field(default_factory=list)
    keyed_by: list[KeyedBySpec] | None = None
    axis_references: list[SparseAxisReferenceInputModel] | None = None
    description: str | None = None
    folder: str | None = None
    derived_from: list[DerivedFromSpec] | None = None
    source_files: list[SourceFileInputModel] | None = None


@kante.pydantic_input(
    CreateSparseDatasetInputModel,
    description=(
        "Create a sparse dataset from one or two uploaded sparse stores. Its axes become the axes of a coordinate system it owns, and **each must be identified exactly once** -- by "
        "`keyedBy`, naming a source whose own contents are the ids, or by `axisReferences`, naming the table whose rows the positions are. Nothing about the matrix is declared: the "
        "encoding, shape and chunking were read from each store when its upload was finished"
    ),
)
class CreateSparseDatasetInput:
    """Input for creating a sparse dataset."""

    name: str = strawberry.field(description="The name of the sparse dataset")
    stores: list[scalars.SparseLike] = strawberry.field(
        description=(
            "The uploaded sparse stores holding this matrix. One or two: which axis a store's `indptr` indexes decides which question it answers in one contiguous read, and asking "
            "the other is a scan of the whole store rather than a slower read. Two stores of the same matrix in the two layouts give it both capabilities"
        )
    )
    axes: list[AxisInput] = strawberry.field(
        description=(
            "The matrix's axes, **in the order its stores' `shape` is written** -- checked against them, so a declaration that disagrees with the bytes is refused rather than "
            "placing every lookup one position out. Both INDEX: a sparse matrix enumerates on both sides and neither has a metric"
        )
    )
    keyed_by: list[KeyedByInput] | None = strawberry.field(default=None, description="The sources whose ids identify an axis, authoring a FIELD edge each. A connectome keys both")
    axis_references: list[SparseAxisReferenceInput] | None = strawberry.field(default=None, description="The axes identified by a table instead")
    description: str | None = strawberry.field(default=None, description="A description of the sparse dataset")
    folder: strawberry.ID | None = strawberry.field(default=None, description="The folder to file it in")
    derived_from: list[DerivedFromInput] | None = strawberry.field(default=None, description="The data this matrix was computed from")
    source_files: list[SourceFileInput] | None = strawberry.field(default=None, description="The files it was converted from")


def _resolve_stores(info: Info, identifiers: list[str], name: str) -> list["models.SparseStore"]:
    """The stores this dataset is, refusing any whose upload was never finished.

    An unfinished store knows nothing about itself -- its encoding, shape and chunking are read
    at ``finishSparseUpload`` -- so registering one would record a matrix whose layout is simply
    unknown, which is the state this whole design exists to make unrepresentable.
    """
    if not identifiers:
        raise ValueError(f"'{name}' names no stores. A sparse dataset is its stores; there is no state in which one exists and its bytes do not.")
    if len(identifiers) > _RANK:
        raise ValueError(
            f"'{name}' names {len(identifiers)} stores, but a matrix over {_RANK} axes has at most {_RANK} layouts -- one per axis its `indptr` could index. A third would be a copy of one of the other two."
        )

    stores = []
    for identifier in identifiers:
        store = get_for_org(models.SparseStore, info, id=identifier)
        if not store.populated:
            raise ValueError(
                f"Sparse store {store.pk} has not been finished, so nothing is known about what it holds. Call `finishSparseUpload` after the three arrays are written -- that step is "
                f"what reads the group's own attributes, and it refuses one whose encoding is missing or whose `indptr` contradicts its shape."
            )
        stores.append(store)
    return stores


def _assert_stores_agree(stores: list["models.SparseStore"], axes: list[AxisInputModel], name: str) -> dict[int, "models.SparseStore"]:
    """Check each store against the declared axes, and return them by the axis they index.

    The shape check is the one that matters, and it is only possible because the store read its
    own: a declaration that disagrees with the bytes places every lookup one position out and
    raises nothing, which is the failure `_assert_axes_agree` guards a mesh collection against
    for the same reason.
    """
    extents = [int(size) for size in (stores[0].shape or [])]
    by_axis: dict[int, "models.SparseStore"] = {}

    for store in stores:
        shape = [int(size) for size in (store.shape or [])]
        if len(shape) != len(axes):
            raise ValueError(
                f"'{name}' declares {len(axes)} axes {[axis.name for axis in axes]} but sparse store {store.pk} holds a matrix of shape {shape}. The axes describe the store, so they are the same number of them."
            )
        if shape != extents:
            raise ValueError(
                f"'{name}' is one matrix in up to two layouts, so its stores hold the same shape -- but {store.pk} is {shape} where another is {extents}. Two different matrices are two datasets."
            )
        indexed = store.indexed_axis
        if indexed is None:
            raise ValueError(f"Sparse store {store.pk} declares encoding {store.encoding!r}, which names no axis for its `indptr` to index.")
        if indexed in by_axis:
            raise ValueError(
                f"'{name}' names two stores whose `indptr` indexes axis {indexed} ('{axes[indexed].name}'): {by_axis[indexed].pk} and {store.pk}. That is one capability twice, and nothing "
                f"could say which a reader should use. Two layouts means one store per axis -- transpose one of them, or drop it."
            )
        by_axis[indexed] = store

    return by_axis


def _assert_every_axis_identified(info: Info, model: CreateSparseDatasetInputModel, axis_names: list[str]) -> dict[str, "models.TableDataset"]:
    """Every axis identified exactly once, and the referenced ones resolved.

    The load-bearing check. An axis nothing identifies cannot be accounted for: a FIELD edge
    supplies the axes it produces, and ``assert_edge_rank`` refuses one whose target carries an
    axis neither supplied nor identified -- so an unidentified axis is not a lax dataset, it is
    a dataset no source can ever key. Caught here, where the message can say which axis and
    what the two ways of fixing it are, rather than as a rank mismatch later.
    """
    references = {entry.axis: entry.references for entry in (model.axis_references or [])}
    unknown = sorted(set(references) - set(axis_names))
    if unknown:
        raise ValueError(f"`axisReferences` names {unknown}, which {'is not an axis' if len(unknown) == 1 else 'are not axes'} of '{model.name}' ({axis_names}).")

    # A keying source produces the axes the target has and it does not, which is the same
    # derivation `write_key_edges` makes -- asked here only to know *how many* axes the keys
    # will account for, so the count can be checked before anything is written.
    keyed_count = 0
    for entry in model.keyed_by or []:
        source_model, keyword = coordinate_system_logic._DERIVATION_SOURCES[entry.kind.value if hasattr(entry.kind, "value") else entry.kind]
        source = get_for_org(source_model, info, id=entry.source_id)
        source_system = coordinate_system_logic.resolve_source_system(**{keyword: source})
        produced = [axis for axis in axis_names if axis not in {axis.name for axis in source_system.axes.all()} and axis not in references]
        keyed_count += 1
        if not produced:
            raise ValueError(
                f"'{model.name}' cannot be keyed by that source: every axis it does not share is already identified by `axisReferences`, so the edge would produce nothing. A source keys an axis by supplying its ids."
            )

    unidentified = [axis for axis in axis_names if axis not in references]
    if len(unidentified) != keyed_count:
        detail = f"{sorted(unidentified)} identified by nothing" if len(unidentified) > keyed_count else "more keys than axes to key"
        raise ValueError(
            f"'{model.name}' has {len(axis_names)} axes {axis_names}, of which {sorted(references)} are identified by `axisReferences` and {keyed_count} by `keyedBy` -- leaving {detail}. "
            "Every axis is identified exactly once: by a source whose contents are its ids, or by the table whose rows its positions are. An axis nothing identifies is one no FIELD edge can ever land beside."
        )

    return {axis: resolve_reference_target(info, target, f"Axis '{axis}'") for axis, target in references.items()}


def create_sparse_dataset(info: Info, input: CreateSparseDatasetInput) -> types.SparseDataset:
    """Create a sparse dataset, its owned coordinate system, and the edges identifying its axes."""
    model = input.to_pydantic()
    ctx = CreationContext.from_info(info)

    if len(model.axes) != _RANK:
        raise ValueError(
            f"'{model.name}' declares {len(model.axes)} axes, but a sparse dataset is a matrix over {_RANK} of them. An N-dimensional sparse tensor is a real thing and this is not it yet."
        )
    off_index = [axis.name for axis in model.axes if (axis.type.value if hasattr(axis.type, "value") else axis.type) != enums.AxisType.INDEX.value]
    if off_index:
        raise ValueError(
            f"'{model.name}' declares {off_index} as something other than INDEX. Both axes of a sparse matrix enumerate -- an object id, a feature id -- and neither has a metric, "
            "which is what INDEX means. A CHANNEL axis is one a layer samples per position, and there are too many positions here for that to be true."
        )

    stores = _resolve_stores(info, model.stores, model.name)
    axis_names = [axis.name for axis in model.axes]
    by_axis = _assert_stores_agree(stores, model.axes, model.name)
    targets = _assert_every_axis_identified(info, model, axis_names)

    # Atomic for the reason `create_table_dataset` is: the row, its axes and its references are
    # written before the edges are checked, and an edge the rank rule refuses would otherwise
    # leave an orphan dataset behind and return an error.
    with transaction.atomic():
        system = models.CoordinateSystem.objects.create(name=f"{model.name}/sparse", creator=ctx.user, organization=ctx.organization)
        dataset = models.SparseDataset.objects.create(
            name=model.name,
            description=model.description,
            coordinate_system=system,
            folder=folder_logic.folder_for_new_container(info, ctx, model.folder, model.derived_from),
            creator=ctx.user,
            organization=ctx.organization,
            **ctx.provenance_kwargs(),
        )
        graph_logic.create_pixel_axes(system, model.axes)

        models.SparseArray.objects.bulk_create(
            [models.SparseArray(dataset=dataset, store=store, indexed_axis=indexed) for indexed, store in sorted(by_axis.items())]
        )
        # Before the key edges, and that ordering is load-bearing: `write_key_edges` derives its
        # axis split from what the target identifies, so a reference written afterwards would
        # leave the edge trying to produce an axis it should have left alone.
        models.SparseAxisReference.objects.bulk_create(
            [models.SparseAxisReference(dataset=dataset, axis=axis, references=target) for axis, target in targets.items()]
        )

        coordinate_system_logic.write_derivation_edges(info, name=dataset.name, own_system=system, derived_from=model.derived_from or [], ctx=ctx)
        file_link_logic.write_file_links(info, container=dataset, source_files=model.source_files or [], ctx=ctx)
        coordinate_system_logic.write_key_edges(info, name=dataset.name, own_system=system, keyed_by=model.keyed_by or [], ctx=ctx)

    return dataset


class UpdateSparseDatasetInputModel(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None


@kante.pydantic_input(UpdateSparseDatasetInputModel, description="Input for renaming or redescribing a sparse dataset")
class UpdateSparseDatasetInput:
    """Input for updating a sparse dataset."""

    id: strawberry.ID = strawberry.field(description="The ID of the sparse dataset to update")
    name: str | None = strawberry.field(default=None, description="A new name")
    description: str | None = strawberry.field(default=None, description="A new description")


def update_sparse_dataset(info: Info, input: UpdateSparseDatasetInput) -> types.SparseDataset:
    """Rename a sparse dataset, or redescribe it. Those two are the whole of what is editable.

    Not here: the stores, the axes, the references and the coordinate system. All are written
    once at creation, and a sparse dataset's own system is refused by ``updateCoordinateSystem``
    besides. A recomputation is a new dataset.
    """
    model = input.to_pydantic()
    dataset = get_for_org(models.SparseDataset, info, id=model.id)
    if model.name is not None:
        dataset.name = model.name
    if model.description is not None:
        dataset.description = model.description
    dataset.save()
    return dataset


class DeleteSparseDatasetInputModel(BaseModel):
    id: str = Field(description="The ID of the sparse dataset to delete")


@kante.pydantic_input(DeleteSparseDatasetInputModel, description="Input for deleting a sparse dataset by ID")
class DeleteSparseDatasetInput:
    """Input for deleting a sparse dataset by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the sparse dataset to delete")


#: PROTECT, for the reason a table dataset is protected: a colouring names its source by id
#: inside a JSON column, so there is no foreign key to cascade and a deleted matrix leaves an
#: entry nothing can execute. See :func:`core.logic.pickers.assert_sparse_dataset_not_in_a_picker`.
delete_sparse_dataset = make_delete(models.SparseDataset, DeleteSparseDatasetInput, owner=self_owner, guard=pickers.assert_sparse_dataset_not_in_a_picker)
