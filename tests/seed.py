"""Async ORM seed helpers shared by the filter/ordering test modules.

All helpers create objects in the organization/user of the supplied context
(the identity the static "test" token resolves to, see conftest.py).
"""

from authentikate.models import Membership, User
from kante.context import HttpContext

from core.models import Dataset, File, Image


async def create_dataset(ctx: HttpContext, name: str, **kwargs) -> Dataset:
    return await Dataset.objects.acreate(
        name=name,
        creator=kwargs.pop("creator", ctx.request.user),
        organization=ctx.request.organization,
        membership=kwargs.pop("membership", ctx.request.membership),
        **kwargs,
    )


async def create_image(ctx: HttpContext, name: str, dataset: Dataset, **kwargs) -> Image:
    return await Image.objects.acreate(
        name=name,
        dataset=dataset,
        creator=kwargs.pop("creator", ctx.request.user),
        organization=ctx.request.organization,
        **kwargs,
    )


async def create_file(ctx: HttpContext, name: str, dataset: Dataset, **kwargs) -> File:
    return await File.objects.acreate(
        name=name,
        dataset=dataset,
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
# dims and the pyramid scales all live on the graph, not on columns. The
# intrinsic system is the level-0 pixel grid -- structural axes, no units.
# Physical units only exist on calibrations (PHYSICAL systems), seeded
# separately by create_calibration. These helpers are the sync mirror of
# core.mutations.adataset.create_adataset, so a test does not have to go
# through GraphQL to get a well-formed dataset.

from asgiref.sync import sync_to_async  # noqa: E402

from core import enums  # noqa: E402
from core.creation import CreationContext  # noqa: E402
from core.logic import coords as coords_logic  # noqa: E402
from core.logic import graph as graph_logic  # noqa: E402
from core.models import ADataset, Axis, CoordinateSystem, DataArray, Lens, Scene  # noqa: E402
from core.inputs.coords import AxisInputModel, CalibratedAxisInputModel  # noqa: E402


def axis(name: str, type_: enums.AxisType) -> AxisInputModel:
    """One structural axis of a test dataset's pixel grid."""
    return AxisInputModel(name=name, type=type_)


def calibrated_axis(name: str, type_: enums.AxisType, unit: str) -> CalibratedAxisInputModel:
    """One axis of a calibrated (physical) space."""
    return CalibratedAxisInputModel(name=name, type=type_, unit=unit)


#: A 2D multi-channel dataset: the minimum an image layer can render.
SIMPLE_AXES = [
    axis("c", enums.AxisType.CHANNEL),
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


def _seed_adataset_sync(ctx: HttpContext, name: str, axes: list, shapes: list[list[int]]) -> ADataset:
    """Build a dataset, its coordinate systems, and the edges placing each level in intrinsic pixel space."""
    creation = _creation(ctx)
    axis_specs = [coords_logic.AxisSpec(name=a.name, type=a.type.value) for a in axes]
    coords_logic.assert_axis_type_order(axis_specs)

    dataset = ADataset.objects.create(name=name, creator=creation.user, organization=creation.organization)
    intrinsic = CoordinateSystem.objects.create(
        name=f"{name}/intrinsic",
        kind=enums.CoordinateSystemKindChoices.INTRINSIC.value,
        intrinsic_of=dataset,
        creator=creation.user,
        organization=creation.organization,
    )
    graph_logic.create_pixel_axes(intrinsic, axes)

    for level, shape in enumerate(shapes):
        data_array = DataArray.objects.create(level=level, dataset=dataset, shape=shape, chunk_shape=shape)
        # Level 0 owns no system: the intrinsic system IS the level-0 pixel grid.
        if level == 0:
            continue
        array_system = CoordinateSystem.objects.create(
            name=f"{name}/{level}",
            kind=enums.CoordinateSystemKindChoices.ARRAY.value,
            data_array=data_array,
            creator=creation.user,
            organization=creation.organization,
        )
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


async def create_adataset(ctx: HttpContext, name: str = "ADataset", axes: list | None = None, shapes: list[list[int]] | None = None) -> ADataset:
    """An array dataset with a full coordinate graph. Defaults to a 3x64x64 single-level c/y/x dataset."""
    return await sync_to_async(_seed_adataset_sync)(ctx, name, axes or SIMPLE_AXES, shapes or [[3, 64, 64]])


def _seed_calibration_sync(
    ctx: HttpContext,
    dataset: ADataset,
    axes: list,
    scale: list | None,
    translation: list | None,
    affine: list | None,
    name: str,
) -> CoordinateSystem:
    return graph_logic.create_calibration(
        dataset=dataset,
        name=name,
        axes=axes,
        scale=scale,
        translation=translation,
        affine=affine,
        ctx=_creation(ctx),
    )


async def create_calibration(
    ctx: HttpContext,
    dataset: ADataset,
    axes: list,
    scale: list | None = None,
    translation: list | None = None,
    affine: list | None = None,
    name: str = "physical",
) -> CoordinateSystem:
    """A PHYSICAL system for a dataset, plus the edge mapping its intrinsic pixels into it."""
    return await sync_to_async(_seed_calibration_sync)(ctx, dataset, axes, scale, translation, affine, name)


def _seed_lens_sync(ctx: HttpContext, dataset: ADataset, slices: list | None) -> Lens:
    creation = _creation(ctx)
    lens = Lens.objects.create(dataset=dataset, slices=slices or [])
    # An unsliced lens owns no system: its space is the dataset's intrinsic space.
    if not lens.slices_list:
        return lens
    lens_system = CoordinateSystem.objects.create(
        name=f"{dataset.name}/lens/{lens.pk}",
        kind=enums.CoordinateSystemKindChoices.ARRAY.value,
        lens=lens,
        creator=creation.user,
        organization=creation.organization,
    )
    graph_logic.create_pixel_axes(lens_system, dataset.axes)
    graph_logic.create_lens_edge(
        lens_system=lens_system,
        parent_system=dataset.intrinsic_coordinate_system,
        dataset_dims=dataset.dims_list,
        slices=lens.slices_list,
        ctx=creation,
    )
    return lens


async def create_lens(ctx: HttpContext, dataset: ADataset, slices: list | None = None) -> Lens:
    """A lens over an array dataset, with its coordinate system and its edge back to the dataset."""
    return await sync_to_async(_seed_lens_sync)(ctx, dataset, slices)


def _seed_scene_sync(ctx: HttpContext, name: str) -> Scene:
    scene = Scene.objects.create(name=name, organization=ctx.request.organization)
    world = CoordinateSystem.objects.create(
        name=f"{name}/world",
        kind=enums.CoordinateSystemKindChoices.WORLD.value,
        scene=scene,
        creator=ctx.request.user,
        organization=ctx.request.organization,
    )
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
