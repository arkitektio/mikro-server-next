"""A derived dataset is placed by where its source is, not by an assumption.

A deconvolution, a segmentation, a projection, a resample: none of them is a fresh
acquisition, and none of them sits anywhere on its own account. Its pixels stand in a
definite relation to the lens they were computed from, and that relation is a spatial fact
-- so it is an edge, like the pyramid scale and the lens crop and the calibration, and not
a label describing one. Recorded that way, the derived dataset inherits its source's
placement: refine the source's registration and the derived data moves with it, because
there is only one copy of the fact.

These tests pin the two things that make the edge more than decoration: the placement
search must be able to *walk* it (it used to dead-end the moment it left the dataset), and
the auto-registration must not paper over it with an assumed identity placement that, being
one hop from world against the lineage's several, would outrank the truth forever.
"""

from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from datalayer.models import ZarrStore
from kante.context import HttpContext

from core import enums, models
from mikro_server.schema import schema
from tests import seed

CREATE_SCENE = """
mutation CreateScene($input: CreateSceneInput!) {
  createScene(input: $input) {
    id
    worldCoordinateSystem { id }
  }
}
"""

REGISTER = """
mutation Register($input: CreateTransformationInput!) {
  createTransformation(input: $input) { id kind }
}
"""

MAKE_LAYER = """
mutation Make($input: CreateIntensityLayerInput!) {
  createIntensityLayer(input: $input) { id }
}
"""

PLACEMENT = """
query Placement($id: ID!) {
  scene(id: $id) {
    layers {
      id
      pathToWorld {
        inverted
        transformation {
          id kind inputAxes outputAxes
          input { id kind }
          output { id kind }
        }
      }
    }
    registrations { id kind name }
  }
}
"""

DERIVED = """
query Derived($id: ID!) {
  adataset(id: $id) {
    id
    derivedFrom { id kind inputAxes outputAxes output { id kind } }
  }
}
"""

_AFFINE_3D = [
    [1.0, 0.0, 0.0, 5.0],
    [0.0, 1.0, 0.0, 5.0],
    [0.0, 0.0, 1.0, 0.0],
]


async def _derive(ctx: HttpContext, name: str, *, axes, shape, lens=None, entries=None, **derived_from):
    """Create a dataset through the real mutation, stating the lens(es) it was computed from.

    Either one `lens` plus its transform kwargs, or explicit `entries` for a fusion.
    """
    store = await ZarrStore.objects.acreate(
        organization=ctx.request.organization,
        key=f"derived-{name}",
        bucket="zarr",
        shape=shape,
        chunks=shape,
        version="3",
        dtype="uint8",
        populated=True,
    )

    if entries is None:
        entries = [{"lens": str(lens.pk), **derived_from}]

    # fill_info() reads zarr metadata from S3; stub it so the pre-set shape stays intact.
    with patch("datalayer.models.ZarrStore.fill_info", return_value=None):
        return await schema.execute(
            """
            mutation Derive($input: CreateADatasetInput!) {
              createADataset(input: $input) { id name derivedFrom { id kind inputAxes outputAxes } }
            }
            """,
            context_value=ctx,
            variable_values={
                "input": {
                    "name": name,
                    "data": str(store.id),
                    "scales": [],
                    "axes": [{"name": axis.name, "type": axis.type.value} for axis in axes],
                    "derivedFrom": entries,
                }
            },
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_derived_dataset_walks_to_world_through_its_source(authenticated_context: HttpContext):
    """The path runs through the source's systems, not around them.

    This is the assertion the whole change exists for. The placement search partitions its
    edge universe per dataset, so before the lineage closure the walk crossed the
    derivation edge into the source's lens system and then **dead-ended** -- the source's
    own lens->array->intrinsic edges live in the source's bucket, which was never merged.
    `pathToWorld` came back null for data that is perfectly well placed.
    """
    source = await seed.create_adataset(authenticated_context, "Source")  # (c, y, x)
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    scene_result = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "Sc", "axes": [{"name": "z", "type": "SPACE", "unit": "micrometer"}, {"name": "y", "type": "SPACE", "unit": "micrometer"}, {"name": "x", "type": "SPACE", "unit": "micrometer"}]}})
    assert not scene_result.errors, scene_result.errors
    scene_id = scene_result.data["createScene"]["id"]
    world_id = scene_result.data["createScene"]["worldCoordinateSystem"]["id"]

    # The SOURCE is registered into the scene. The derived dataset never is.
    source_intrinsic = await sync_to_async(lambda: source.intrinsic_coordinate_system)()
    registered = await schema.execute(
        REGISTER,
        context_value=authenticated_context,
        variable_values={"input": {"input": str(source_intrinsic.pk), "output": world_id, "kind": "AFFINE", "affine": _AFFINE_3D, "scene": scene_id}},
    )
    assert not registered.errors, registered.errors

    # A deconvolution: same grid, so the derivation is an identity.
    derived = await _derive(authenticated_context, "Deconvolved", lens=source_lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], kind="IDENTITY")
    assert not derived.errors, derived.errors
    derived_id = derived.data["createADataset"]["id"]

    derived_dataset = await sync_to_async(models.ADataset.objects.get)(pk=derived_id)
    derived_lens = await seed.create_lens(authenticated_context, derived_dataset, slices=[])

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene_id, "lens": str(derived_lens.pk), "intensityAxis": "c"}})
    assert not made.errors, made.errors

    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": scene_id})
    assert not placement.errors, placement.errors

    layer = placement.data["scene"]["layers"][0]
    path = layer["pathToWorld"]
    assert path is not None, "a derived dataset is placed by its source; the walk must cross the derivation edge"

    # It ends in the source's registration -- the derived data inherits it.
    assert path[-1]["transformation"]["output"]["kind"] == "WORLD"
    kinds = [step["transformation"]["input"]["kind"] for step in path]
    assert "INTRINSIC" in kinds, "the walk passes through the source's intrinsic system"

    # And no assumed registration was fabricated for the derived dataset.
    names = [edge["name"] or "" for edge in placement.data["scene"]["registrations"]]
    assert not any("assumed" in name for name in names), f"the derived dataset must inherit, not be pinned: {names}"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unregistered_derived_dataset_pins_its_source_not_itself(authenticated_context: HttpContext):
    """When nothing is registered yet, the assumption is made about the ROOT of the lineage.

    This is the subtle one. Pinning the derived dataset directly would *work* -- it resolves
    to a non-null path, so it looks right -- and it would be wrong: the fabricated edge is
    one hop from world while the truth is several, the placement search is a shortest-path
    BFS, so the assumption would outrank the lineage forever, including a registration
    authored later. The derived data would sit at the identity instead of where its source
    actually is, and nothing would say so.

    So the assumed edge is made about the source, and the derived data inherits it.
    """
    source = await seed.create_adataset(authenticated_context, "Source")  # (c, y, x)
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    derived = await _derive(authenticated_context, "Deconvolved", lens=source_lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], kind="IDENTITY")
    assert not derived.errors, derived.errors
    derived_dataset = await sync_to_async(models.ADataset.objects.get)(pk=derived.data["createADataset"]["id"])
    derived_lens = await seed.create_lens(authenticated_context, derived_dataset, slices=[])

    # Nothing is registered into this scene. The layer over the DERIVED dataset is what
    # triggers the assumed placement.
    scene_result = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "Sc"}})
    assert not scene_result.errors, scene_result.errors
    scene_id = scene_result.data["createScene"]["id"]

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene_id, "lens": str(derived_lens.pk), "intensityAxis": "c"}})
    assert not made.errors, made.errors

    def assumed_edges() -> list[models.Transformation]:
        scene = models.Scene.objects.get(pk=scene_id)
        return list(scene.coordinate_transformations.select_related("input").all())

    edges = await sync_to_async(assumed_edges)()
    assert len(edges) == 1, f"exactly one assumed registration, made about the lineage root: {edges}"

    source_intrinsic = await sync_to_async(lambda: source.intrinsic_coordinate_system)()
    derived_intrinsic = await sync_to_async(lambda: derived_dataset.intrinsic_coordinate_system)()

    assert edges[0].input_id == source_intrinsic.pk, "the assumption belongs to the data the pixels came from"
    assert edges[0].input_id != derived_intrinsic.pk, "pinning the derived dataset would outrank its own lineage: one hop beats several under a shortest-path BFS"

    # And the derived layer still reaches world -- through its source, not around it.
    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": scene_id})
    assert not placement.errors, placement.errors
    path = placement.data["scene"]["layers"][0]["pathToWorld"]
    assert path is not None
    assert path[-1]["transformation"]["output"]["kind"] == "WORLD"
    assert str(source_intrinsic.pk) in [step["transformation"]["input"]["id"] for step in path], "the walk goes through the source's intrinsic system"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_derivation_edge_is_readable_on_the_dataset(authenticated_context: HttpContext):
    """`derivedFrom` is the edge itself, so a client can compose it -- not a label about it."""
    source = await seed.create_adataset(authenticated_context, "Source")
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    derived = await _derive(authenticated_context, "Segmented", lens=source_lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], kind="IDENTITY")
    assert not derived.errors, derived.errors

    result = await schema.execute(DERIVED, context_value=authenticated_context, variable_values={"id": derived.data["createADataset"]["id"]})
    assert not result.errors, result.errors

    edges = result.data["adataset"]["derivedFrom"]
    assert len(edges) == 1
    assert edges[0]["kind"] == "IDENTITY"
    assert edges[0]["inputAxes"] == ["c", "y", "x"]
    assert edges[0]["outputAxes"] == ["c", "y", "x"]

    # An acquired dataset was derived from nothing, and says so.
    plain = await schema.execute(DERIVED, context_value=authenticated_context, variable_values={"id": str(source.pk)})
    assert not plain.errors, plain.errors
    assert plain.data["adataset"]["derivedFrom"] == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_projection_drops_an_axis_as_by_dimension(authenticated_context: HttpContext):
    """A max-z projection is a rank change, and BY_DIMENSION is how a rank change is stated."""
    axes = [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("z", enums.AxisType.SPACE),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    source = await seed.create_adataset(authenticated_context, "Volume", axes=axes, shapes=[[2, 16, 32, 32]])
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    flat_axes = [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    derived = await _derive(
        authenticated_context,
        "MaxZ",
        lens=source_lens,
        axes=flat_axes,
        shape=[2, 32, 32],
        kind="BY_DIMENSION",
        inputAxes=["c", "y", "x"],
        outputAxes=["c", "y", "x"],
    )
    assert not derived.errors, derived.errors

    edge = derived.data["createADataset"]["derivedFrom"][0]
    assert edge["kind"] == "BY_DIMENSION"
    # The projection says nothing about z -- which is exactly the truth, and exactly what a
    # square edge could not have said.
    assert edge["inputAxes"] == ["c", "y", "x"]
    assert edge["outputAxes"] == ["c", "y", "x"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_identity_is_not_a_rank_claim_in_disguise(authenticated_context: HttpContext):
    """IDENTITY says the two grids ARE the same. Between different axes that is a lie.

    IDENTITY carries no parameters, so no rank check would otherwise look at it -- and it
    is the *default* for a derivation. A projection defaulting into an identity would state
    that a 3D volume and its 2D projection are the same space, and nothing downstream could
    tell that apart from a genuine in-place operation.
    """
    axes = [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("z", enums.AxisType.SPACE),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    source = await seed.create_adataset(authenticated_context, "Volume", axes=axes, shapes=[[2, 16, 32, 32]])
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    flat_axes = [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    derived = await _derive(authenticated_context, "MaxZ", lens=source_lens, axes=flat_axes, shape=[2, 32, 32], kind="IDENTITY")

    assert derived.errors, "an identity between (c,z,y,x) and (c,y,x) is a rank change wearing an identity's clothes"
    assert "IDENTITY" in str(derived.errors[0])
