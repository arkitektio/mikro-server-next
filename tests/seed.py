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


# --- the RFC-5 coordinate graph -------------------------------------------
#
# Seeding an array dataset now means seeding its coordinate systems too: the
# dims, the units and the pyramid scales all live on the graph, not on columns.
# These helpers are the sync mirror of core.mutations.adataset.create_adataset,
# so a test does not have to go through GraphQL to get a well-formed dataset.

from asgiref.sync import sync_to_async  # noqa: E402

from core import enums  # noqa: E402
from core.creation import CreationContext  # noqa: E402
from core.logic import coords as coords_logic  # noqa: E402
from core.logic import graph as graph_logic  # noqa: E402
from core.models import ADataset, Axis, CoordinateSystem, DataArray, Lens, Scene  # noqa: E402
from core.inputs.coords import AxisInputModel  # noqa: E402


def axis(name: str, type_: enums.AxisType, spacing: float = 1.0, unit: str | None = None) -> AxisInputModel:
    """One axis of a test dataset."""
    return AxisInputModel(name=name, type=type_, spacing=spacing, unit=unit, discrete=type_ != enums.AxisType.SPACE)


#: A 2D multi-channel dataset: the minimum an image layer can render.
SIMPLE_AXES = [
    axis("c", enums.AxisType.CHANNEL),
    axis("y", enums.AxisType.SPACE, spacing=0.325, unit="micrometer"),
    axis("x", enums.AxisType.SPACE, spacing=0.325, unit="micrometer"),
]

#: A bare 2D image, no channel axis.
YX_AXES = [
    axis("y", enums.AxisType.SPACE, spacing=0.325, unit="micrometer"),
    axis("x", enums.AxisType.SPACE, spacing=0.325, unit="micrometer"),
]


def _seed_adataset_sync(ctx: HttpContext, name: str, axes: list, shapes: list[list[int]]) -> ADataset:
    """Build a dataset, its coordinate systems, and the edges placing each level in intrinsic space."""
    creation = CreationContext(
        user=ctx.request.user,
        organization=ctx.request.organization,
        membership=ctx.request.membership,
        task=None,
    )
    axis_specs = [coords_logic.AxisSpec(name=a.name, type=a.type.value, unit=a.unit, spacing=a.spacing, discrete=a.discrete) for a in axes]
    coords_logic.assert_axis_type_order(axis_specs)
    base_spacing = [a.spacing for a in axes]

    dataset = ADataset.objects.create(name=name, creator=creation.user, organization=creation.organization)
    intrinsic = CoordinateSystem.objects.create(
        name=f"{name}/intrinsic",
        kind=enums.CoordinateSystemKindChoices.INTRINSIC.value,
        dataset=dataset,
        creator=creation.user,
        organization=creation.organization,
    )
    graph_logic.create_axes(intrinsic, axes)

    for level, shape in enumerate(shapes):
        data_array = DataArray.objects.create(level=level, dataset=dataset, shape=shape, chunk_shape=shape)
        array_system = CoordinateSystem.objects.create(
            name=f"{name}/{level}",
            kind=enums.CoordinateSystemKindChoices.ARRAY.value,
            data_array=data_array,
            creator=creation.user,
            organization=creation.organization,
        )
        graph_logic.create_axes(array_system, axes, as_array_indices=True)
        graph_logic.create_level_edge(
            array_system=array_system,
            intrinsic=intrinsic,
            base_spacing=base_spacing,
            shape_0=shapes[0],
            shape_level=shape,
            axis_specs=axis_specs,
            ctx=creation,
        )

    return dataset


async def create_adataset(ctx: HttpContext, name: str = "ADataset", axes: list | None = None, shapes: list[list[int]] | None = None) -> ADataset:
    """An array dataset with a full coordinate graph. Defaults to a 3x64x64 single-level c/y/x dataset."""
    return await sync_to_async(_seed_adataset_sync)(ctx, name, axes or SIMPLE_AXES, shapes or [[3, 64, 64]])


def _seed_lens_sync(ctx: HttpContext, dataset: ADataset, slices: list | None) -> Lens:
    creation = CreationContext(
        user=ctx.request.user,
        organization=ctx.request.organization,
        membership=ctx.request.membership,
        task=None,
    )
    lens = Lens.objects.create(dataset=dataset, slices=slices or [])
    lens_system = CoordinateSystem.objects.create(
        name=f"{dataset.name}/lens/{lens.pk}",
        kind=enums.CoordinateSystemKindChoices.ARRAY.value,
        lens=lens,
        creator=creation.user,
        organization=creation.organization,
    )
    graph_logic.create_axes(lens_system, dataset.axes, as_array_indices=True)
    base = dataset.data_arrays.order_by("level").first()
    graph_logic.create_lens_edge(
        lens_system=lens_system,
        parent_system=base.coordinate_system,
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
