"""Async ORM seed helpers shared by the filter/ordering test modules.

All helpers create objects in the organization/user of the supplied context
(the identity the static "test" token resolves to, see conftest.py).
"""

from authentikate.models import Membership, User
from kante.context import HttpContext

from core.models import Folder, File


async def create_folder(ctx: HttpContext, name: str, **kwargs) -> Folder:
    return await Folder.objects.acreate(
        name=name,
        creator=kwargs.pop("creator", ctx.request.user),
        organization=ctx.request.organization,
        membership=kwargs.pop("membership", ctx.request.membership),
        **kwargs,
    )


async def create_file(ctx: HttpContext, name: str, folder: Folder, **kwargs) -> File:
    return await File.objects.acreate(
        name=name,
        folder=folder,
        creator=kwargs.pop("creator", ctx.request.user),
        organization=ctx.request.organization,
        membership=kwargs.pop("membership", ctx.request.membership),
        **kwargs,
    )


async def create_other_user(ctx: HttpContext) -> User:
    """A second user (sub='2') in the same organization as the context user."""
    user, _ = await User.objects.aget_or_create(
        sub="2", iss="static_issuer", defaults={"username": "static_issuer_2"}
    )
    await Membership.objects.aget_or_create(user=user, organization=ctx.request.organization)
    return user


# --- the coordinate graph ---------------------------------------------------
#
# Seeding an array dataset now means seeding its coordinate systems too: the
# axis names and the pyramid scales all live on the graph, not on columns. The
# intrinsic system is the level-0 pixel grid -- structural axes, no units.
# Physical units only exist on physical spaces, seeded
# separately by create_physical_space. These helpers are the sync mirror of
# core.mutations.array_dataset.create_array_dataset, so a test does not have to go
# through GraphQL to get a well-formed dataset.

import uuid

from asgiref.sync import sync_to_async  # noqa: E402

from core import enums  # noqa: E402
from core.creation import CreationContext  # noqa: E402
from core.logic import coords as coords_logic  # noqa: E402
from core.logic import graph as graph_logic  # noqa: E402
from core.models import ArrayDataset, Axis, CoordinateSystem, DataArray, Lens, Scene  # noqa: E402
from core.inputs.coords import (  # noqa: E402
    AffineTransformInputModel,
    AxisInputModel,
    PhysicalAxisInputModel,
    RegistrationPathInputModel,
    ScaleTransformInputModel,
    TranslationTransformInputModel,
)
from core.logic import coordinate_system as coordinate_system_logic  # noqa: E402


def axis(name: str, type_: enums.AxisType) -> AxisInputModel:
    """One structural axis of a test dataset's pixel grid."""
    return AxisInputModel(name=name, type=type_)


def physical_axis(name: str, type_: enums.AxisType, unit: str) -> PhysicalAxisInputModel:
    """One axis of a unit-carrying (physical) space."""
    return PhysicalAxisInputModel(name=name, type=type_, unit=unit)


#: A 2D multi-channel dataset: the minimum an image layer can render.
SIMPLE_AXES = [
    axis("c", enums.AxisType.CHANNEL),
    axis("y", enums.AxisType.SPACE),
    axis("x", enums.AxisType.SPACE),
]

#: A 3D volume whose axis *names* are the world's, for tests about something other than naming.
#: `SIMPLE_AXES` is (c,y,x) and `create_scene`'s world is (z,y,x), so a per-axis transform between
#: them is refused on its names before anything else about it is looked at -- which is right, and
#: is not what those tests are about.
ZYX_AXES = [
    axis("z", enums.AxisType.SPACE),
    axis("y", enums.AxisType.SPACE),
    axis("x", enums.AxisType.SPACE),
]

#: A bare 2D image, no channel axis.
YX_AXES = [
    axis("y", enums.AxisType.SPACE),
    axis("x", enums.AxisType.SPACE),
]


def _creation(ctx: HttpContext) -> CreationContext:
    return CreationContext(
        user=ctx.request.user,
        organization=ctx.request.organization,
        membership=ctx.request.membership,
        task=None,
    )


def _seed_array_dataset_sync(ctx: HttpContext, name: str, axes: list, shapes: list[list[int]]) -> ArrayDataset:
    """Build a dataset, its coordinate systems, and the edges placing each level in intrinsic pixel space."""
    creation = _creation(ctx)
    axis_specs = [coords_logic.AxisSpec(name=a.name, type=a.type.value) for a in axes]
    coords_logic.assert_axis_type_order(axis_specs)

    # The space, then the data that lives in it.
    intrinsic = CoordinateSystem.objects.create(name=f"{name}/intrinsic", creator=creation.user, organization=creation.organization)
    dataset = ArrayDataset.objects.create(name=name, coordinate_system=intrinsic, creator=creation.user, organization=creation.organization)
    graph_logic.create_pixel_axes(intrinsic, axes)

    for level, shape in enumerate(shapes):
        # Level 0 lives in the dataset's own grid: it IS that grid.
        array_system = intrinsic
        if level:
            array_system = CoordinateSystem.objects.create(name=f"{name}/{level}", creator=creation.user, organization=creation.organization)
        data_array = DataArray.objects.create(level=level, dataset=dataset, coordinate_system=array_system, shape=shape, chunk_shape=shape)
        if level == 0:
            continue
        graph_logic.create_pixel_axes(array_system, axes)
        graph_logic.create_level_edge(
            array_system=array_system,
            intrinsic=intrinsic,
            shape_0=shapes[0],
            shape_level=shape,
            axis_specs=axis_specs,
            ctx=creation,
        )

    return dataset


async def create_array_dataset(ctx: HttpContext, name: str = "ArrayDataset", axes: list | None = None, shapes: list[list[int]] | None = None) -> ArrayDataset:
    """An array dataset with a full coordinate graph. Defaults to a 3x64x64 single-level c/y/x dataset."""
    return await sync_to_async(_seed_array_dataset_sync)(ctx, name, axes or SIMPLE_AXES, shapes or [[3, 64, 64]])


def _seed_physical_space_sync(
    ctx: HttpContext,
    dataset: ArrayDataset,
    axes: list,
    scale: list | None,
    translation: list | None,
    affine: list | None,
    name: str,
) -> CoordinateSystem:
    # The exact path `createCoordinateSystem` runs: a physical space is an ordinary space
    # plus one registration edge, and the transform member IS the kind -- there is no
    # scale+translation sugar (express that as one AFFINE matrix). INFERRED, because a
    # seeded pixel size stands in for numbers read from acquisition metadata.
    if affine is not None:
        transform = AffineTransformInputModel(affine=affine)
    elif scale is not None:
        transform = ScaleTransformInputModel(scale=scale)
    else:
        transform = TranslationTransformInputModel(translation=translation)
    spec = RegistrationPathInputModel(
        transform=transform,
        validity=enums.PlacementValidity.INFERRED,
    )
    return coordinate_system_logic.create_coordinate_system(
        name=f"{dataset.name}/{name}",
        axes=axes,
        registrations=[(dataset.coordinate_system, None, spec)],
        ctx=_creation(ctx),
    )


async def create_physical_space(
    ctx: HttpContext,
    dataset: ArrayDataset,
    axes: list,
    scale: list | None = None,
    translation: list | None = None,
    affine: list | None = None,
    name: str = "physical",
) -> CoordinateSystem:
    """A physical space for a dataset, plus the edge mapping its intrinsic pixels into it."""
    return await sync_to_async(_seed_physical_space_sync)(ctx, dataset, axes, scale, translation, affine, name)


def _seed_lens_sync(ctx: HttpContext, dataset: ArrayDataset, slices: list | None) -> Lens:
    creation = _creation(ctx)
    # An unsliced lens lives in the dataset's own grid: its space IS that space.
    sliced = bool(slices)
    lens_system = dataset.coordinate_system
    if sliced:
        lens_system = CoordinateSystem.objects.create(name=f"{dataset.name}/lens", creator=creation.user, organization=creation.organization)
    lens = Lens.objects.create(dataset=dataset, coordinate_system=lens_system, slices=slices or [])
    if not lens.slices_list:
        return lens
    graph_logic.create_pixel_axes(lens_system, dataset.axes)
    graph_logic.create_lens_edge(
        lens_system=lens_system,
        parent_system=dataset.coordinate_system,
        dataset_axis_names=dataset.axis_names,
        slices=lens.slices_list,
        ctx=creation,
    )
    return lens


async def create_lens(ctx: HttpContext, dataset: ArrayDataset, slices: list | None = None) -> Lens:
    """A lens over an array dataset, with its coordinate system and its edge back to the dataset."""
    return await sync_to_async(_seed_lens_sync)(ctx, dataset, slices)


def _register_into_scene_sync(ctx: HttpContext, scene: Scene, dataset: ArrayDataset | None, system: CoordinateSystem | None):
    """One explicit MANUAL registration: the identity on the axis names shared with the world.

    Layer mutations no longer fabricate placements, so a test that wants a placed layer
    authors the registration first -- exactly the step a real client takes.
    """
    source = system if system is not None else dataset.coordinate_system
    world = scene.world
    world_names = [axis.name for axis in world.axes.all()]
    shared = [axis.name for axis in source.axes.all() if axis.name in world_names]
    return graph_logic.create_identity_registration(
        input_system=source,
        world=world,
        shared=shared,
        name=f"{source.name} -> {scene.name}",
        validity=enums.PlacementValidityChoices.MANUAL.value,
        ctx=_creation(ctx),
    )


async def register_into_scene(ctx: HttpContext, scene: Scene, dataset: ArrayDataset | None = None, *, system: CoordinateSystem | None = None):
    """Register a dataset's intrinsic system (or an explicit system) into a scene's world."""
    return await sync_to_async(_register_into_scene_sync)(ctx, scene, dataset, system)


def _seed_scene_sync(ctx: HttpContext, name: str) -> Scene:
    # An ordinary ownerless SHARED world, adopted by the scene -- the same shape
    # create_scene makes.
    world = CoordinateSystem.objects.create(
        name=f"{name}/world",
        creator=ctx.request.user,
        organization=ctx.request.organization,
    )
    scene = Scene.objects.create(name=name, world=world, organization=ctx.request.organization)
    Axis.objects.bulk_create(
        [
            Axis(coordinate_system=world, order=index, name=n, type=enums.AxisTypeChoices.SPACE.value, unit="micrometer")
            for index, n in enumerate(["z", "y", "x"])
        ]
    )
    return scene


async def create_scene(ctx: HttpContext, name: str = "Scene") -> Scene:
    """A scene with its WORLD coordinate system."""
    return await sync_to_async(_seed_scene_sync)(ctx, name)


#: The grid and encoding a fabriks store's manifest would state. Anisotropic on purpose: a cubic
#: cell size cannot tell a correct component order from a reversed one, so a symmetric fixture
#: passes a transposed implementation.
FABRIKS_GRID = {"cellSize": [128, 128, 64], "levels": 3, "sortKey": "MORTON"}
FABRIKS_ENCODING = {
    "positions": "UINT16_QUANTIZED_PER_CELL",
    "indices": "UINT32",
    "codec": "MESHOPT",
    "compression": "NONE",
    "boundary": "LOCKED",
    "decimation": "QUARTER",
}


def _seed_fabriks_store_sync(ctx: HttpContext, *, axes: list[str] | None, populated: bool):
    """A fabriks store carrying what `fill_info` would have read off its manifest.

    Created directly rather than through the upload path, because no test here has an S3 to
    write a tree to -- and what the tests are about is what the server does with a *finished*
    store, not how the bytes got there.
    """
    from datalayer.models import FabriksStore

    key = f"fabriks-{FabriksStore.objects.count()}"
    return FabriksStore.objects.create(
        path=f"s3://fabriks/{key}",
        bucket="fabriks",
        key=key,
        organization=ctx.request.organization,
        populated=populated,
        spec_version="1" if populated else None,
        grid=FABRIKS_GRID if populated else None,
        encoding=FABRIKS_ENCODING if populated else None,
        axes=axes,
    )


async def create_fabriks_store(ctx: HttpContext, *, axes: list[str] | None = None, populated: bool = True):
    """A finished fabriks store, ready to be registered as a collection."""
    return await sync_to_async(_seed_fabriks_store_sync)(ctx, axes=axes, populated=populated)


def _seed_parquet_store_sync(ctx: HttpContext, *, key: str, columns: list[tuple[str, str]] | None = None, populated: bool = True):
    """A parquet store carrying what `fill_info` would have read off the file.

    The same move `_seed_fabriks_store_sync` makes, and now necessary for the same reason: since
    `ParquetStore.fill_info` DESCRIBEs the object, a store left unpopulated makes
    `createTableDataset` reach for an S3 no unit test has. Before that it read nothing, so an
    unfinished store cost nothing and every test here left one behind.

    `columns=None` records a finished store whose schema was not worth stating -- which is most
    tests, because they are about placement and edges rather than about the file. Pass the pairs
    when the test is about the schema itself.
    """
    from datalayer.models import ParquetStore

    return ParquetStore.objects.create(
        path=f"s3://parquet/{key}",
        bucket="parquet",
        key=key,
        organization=ctx.request.organization,
        populated=populated,
        columns=[{"name": name, "type": dtype, "nullable": True} for name, dtype in columns] if columns is not None else None,
    )


async def create_parquet_store(ctx: HttpContext, *, key: str, columns: list[tuple[str, str]] | None = None, populated: bool = True):
    """A finished parquet store, ready to be registered as a table dataset."""
    return await sync_to_async(_seed_parquet_store_sync)(ctx, key=key, columns=columns, populated=populated)


def index_axis(columns: list[dict]) -> str:
    """The single INDEX coordinate column -- the one a keying source lands on.

    A source keys by supplying ids, and an id is looked up in an enumeration, so the axis it
    produces is the INDEX one. Derived rather than named at each call site: it is a fact about
    the column declaration, and the tests that migrated off `keyedBy` were all naming it by
    hand from the same three fixtures.
    """
    index = [c["name"] for c in columns if c.get("role") == "COORDINATE" and c.get("axisType") == "INDEX"]
    if len(index) != 1:
        raise AssertionError(f"expected exactly one INDEX coordinate column, got {index}")
    return index[0]


def axes_for_columns(columns: list[dict], identified_by: dict[str, list] | None = None, keyed_by: list | None = None) -> list[dict]:
    """The `axes` entry `createTableDataset` wants, derived from a column declaration.

    Every COORDINATE column is an axis and must appear in `axes`, so for most tests the axes
    are a pure function of the columns and stating them by hand would be transcription -- the
    same argument `mikro_next.tables.columns_for` makes for real callers, which derives the
    two lists from one frame.

    ``identified_by`` names the sources per axis; ``keyed_by`` is the shorthand for the common
    case, putting them on the single INDEX axis. Axes named in neither get an empty list, which
    is legal and ordinary (a localization table's `x` axis is identified by nothing).
    """
    identified_by = dict(identified_by or {})
    if keyed_by:
        # The convenience the migration off `keyedBy` needed: put these sources on the axis a
        # keying source produces, which is the INDEX one.
        identified_by.setdefault(index_axis(columns), keyed_by)
    return [
        {"column": column["name"], "type": column["axisType"], "identifiedBy": identified_by.get(column["name"], [])}
        for column in columns
        if column.get("role") == "COORDINATE"
    ]


#: The default role of a column nobody says anything about. A column named in neither `axes`
#: nor `columns` is still a `Column` row -- the file has it -- and this is what it is.
_DEFAULT_ROLE = "ATTRIBUTE"


def split_declaration(columns: list[dict]) -> tuple[list[tuple[str, str]], list[dict], list[dict]]:
    """Split a legacy `ColumnInput` list into the three things `createTableDataset` now wants.

    A legacy entry said two kinds of thing at once::

        {"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}
         \\____________________________/   \\_________________________________________/
          the column, which it still is      which axis it is, which moved to `axes`

    The column half survives unchanged -- every column is declared, with its name and its
    DuckDB type, and the server checks the pair against the Parquet's own account. What moved
    is the axis half: a coordinate column is an axis, and an axis has a position in a space, so
    it is declared in `axes` where the list's order *is* that position.

    Returns:
        ``(store_columns, axes, columns)`` -- the store's `[(name, duckdb type)]` in file
        order, the axes in declaration order, and every column with its name and type.
    """
    store_columns = [(column["name"], column.get("dtype", "DOUBLE")) for column in columns]

    axes = []
    for column in columns:
        if column.get("role") != "COORDINATE":
            continue
        axis = {
            key: column[legacy]
            for key, legacy in (("column", "name"), ("type", "axisType"), ("unit", "unit"),
                                ("longName", "longName"), ("description", "description"))
            if legacy in column and column[legacy] is not None
        }
        # `references` on a COORDINATE column was item 7's product-space case, and it is an
        # identification like any other now: the axis' positions *are* that table's rows.
        if column.get("references") is not None:
            axis["identifiedBy"] = [{"kind": "TABLE", "table": column["references"]}]
        axes.append(axis)

    declared = []
    for column in columns:
        entry = {"name": column["name"], "dtype": column.get("dtype", "DOUBLE")}
        for key in ("unit", "longName", "description", "references"):
            if column.get(key) is not None:
                entry[key] = column[key]
        # COORDINATE is not a role a column may claim: it follows from being named in `axes`.
        # An axis carries its own unit and prose there, so they do not repeat here either.
        if column.get("role") == "COORDINATE":
            entry = {"name": entry["name"], "dtype": entry["dtype"]}
        elif column.get("role") is not None:
            entry["role"] = column["role"]
        declared.append(entry)
    return store_columns, axes, declared


async def table_input(
    ctx: HttpContext,
    name: str,
    columns: list[dict],
    *,
    identified_by: dict[str, list] | None = None,
    keyed_by: list | None = None,
    **extra: object,
) -> dict:
    """Everything `createTableDataset` needs, from one legacy-shaped column list.

    Since 3b the mutation reads a column's name and type off the **file** and takes only what
    the file cannot say, so a test's one constant has to become three things: the store's own
    schema, the axes, and the overrides. :func:`split_declaration` does the splitting; this
    also creates the store carrying that schema, which is now load-bearing -- `columns_for_store`
    reads it on every create, and a store without it makes the create reach for an S3 no unit
    test has.

    ``identified_by``/``keyed_by`` place identifications on axes, exactly as
    :func:`axes_for_columns` did before the columns moved.
    """
    store_columns, axes, overrides = split_declaration(columns)
    # Unique, because two tables of the same name in one test are ordinary and the store path
    # is unique-constrained.
    store = await create_parquet_store(ctx, key=f"{name.replace(' ', '-')}-{uuid.uuid4().hex[:8]}", columns=store_columns)

    sources = dict(identified_by or {})
    if keyed_by:
        sources.setdefault(index_axis(columns), keyed_by)
    for axis in axes:
        # `setdefault`, not assignment: the split may already have derived one from a legacy
        # `references` on that coordinate column.
        axis["identifiedBy"] = [*axis.get("identifiedBy", []), *sources.get(axis["column"], [])]

    return {"name": name, "data": str(store.pk), "axes": axes, "columns": overrides, **extra}


def split_payload(columns: list[dict], *, identified_by: dict[str, list] | None = None, keyed_by: list | None = None) -> dict:
    """The `axes`/`columns` half of a create payload, for a test that builds its store itself.

    :func:`table_input` is the whole payload and creates the store; this is the same split for
    the call sites that already have a store in hand. The store still has to carry the file's
    schema -- see :func:`create_parquet_store` -- or the create has nothing to infer from.
    """
    _, axes, overrides = split_declaration(columns)
    sources = dict(identified_by or {})
    if keyed_by:
        sources.setdefault(index_axis(columns), keyed_by)
    for axis in axes:
        axis["identifiedBy"] = [*axis.get("identifiedBy", []), *sources.get(axis["column"], [])]
    return {"axes": axes, "columns": overrides}
