"""The walkthrough in `docs/what-is-here.md`, run against the real schema.

A doc that names a field the schema does not have is worse than no doc: it reads as verified.
That page is the sequence a frontend runs to get from a click in world space to every record
hanging off it, and every query in it is executed below, in order, against one seeded scene.

What this pins is the **shape of the page**: that each step's query parses, that the fields it
names exist, and that the values have the form the prose promises -- a matrix whose rows are
`outputAxes`, a level path per pyramid level, an anchor whose spokes come back. It does not
re-test the logic behind those fields; `test_placement_queries`, `test_per_index_transforms`,
`test_attribute_plans` and `test_transform_invariance` own that.
"""

from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import models
from mikro_server.schema import schema
from tests import seed


CREATE_DATASET = """
mutation Create($input: CreateArrayDatasetInput!) {
  createArrayDataset(input: $input) {
    id
    intrinsicSystem { id }
  }
}
"""

CREATE_LENS = """
mutation Create($input: CreateLensInput!) { createLens(input: $input) { id } }
"""

MAKE_LAYER = """
mutation Make($input: CreateIntensityLayerInput!) { createIntensityLayer(input: $input) { id } }
"""

# --- step 1 ------------------------------------------------------------------
WHAT_IS_HERE = """
query WhatIsHere($world: ID!, $min: [Float!]!, $max: [Float!]!) {
  coordinateSystem(id: $world) {
    inView(region: {min: $min, max: $max}) {
      source { __typename ... on ArrayDataset { id name } }
      system { id }
      extent { axis min max }
      extentState
      validity
      invariance
      path { transformation { id } inverted }
      anchors { id coordinates }
    }
  }
}
"""

# --- step 2 ------------------------------------------------------------------
PLACEMENT = """
query Placement($scene: ID!) {
  scene(id: $scene) {
    layers {
      id
      placement
      asAffine { matrix inputAxes outputAxes total }
    }
  }
}
"""

PLACEMENT_AT = """
query PlacementAt($scene: ID!, $at: [CoordinateInput!]) {
  scene(id: $scene) {
    layers {
      placement(at: $at)
      asAffine(at: $at) { matrix inputAxes outputAxes total }
    }
  }
}
"""

# --- step 3 ------------------------------------------------------------------
LEVELS = """
query Levels($scene: ID!) {
  scene(id: $scene) {
    layers {
      ... on ImageLayer {
        levelPaths {
          dataArray { id level shape chunkShape store { id key } }
          path { transformation { id } inverted }
        }
      }
    }
  }
}
"""

# --- step 4 ------------------------------------------------------------------
AXIS_ORDER = """
query AxisOrder($scene: ID!) {
  scene(id: $scene) {
    layers {
      ... on ImageLayer {
        levelPaths { dataArray { coordinateSystem { axes { name order type unit } } } }
      }
    }
  }
}
"""

# --- step 5 ------------------------------------------------------------------
ANCHORS = """
query Anchors($lens: ID!) {
  lens(id: $lens) {
    activeAnchors {
      coordinates
      microscope { state { stage { x y z } temperature } }
      omeMetadata { metadata }
      valueHistogram { histogram bins min max p1 p99 }
      channelLabel { label }
      lightGraph { graph { elements { __typename } edges { __typename } } }
      phasorHistograms { axis harmonic bins counts profile calibrated }
      phasorCalibrations { axis harmonic phaseOffset modulationFactor reference }
    }
  }
}
"""

# --- step 6 ------------------------------------------------------------------
PLANS = """
query Plans($system: ID!) { attributePlans(system: $system) { table { id } sample { produces passthrough } } }
"""

# --- step 7 ------------------------------------------------------------------
TRUST = """
query Trust($scene: ID!, $system: ID!) {
  scene(id: $scene) { layers { placementValidity placementInvariance } }
  coordinateSystem(id: $system) { transformVersion }
}
"""


async def _zarr(ctx: HttpContext, key: str, shape: list[int]) -> models.ZarrStore:
    return await models.ZarrStore.objects.acreate(
        organization=ctx.request.organization,
        key=key,
        bucket="zarr",
        shape=shape,
        chunks=shape,
        version="3",
        dtype="uint8",
        populated=True,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_documented_walkthrough_runs_end_to_end(db, authenticated_context: HttpContext):
    """Each step of `docs/what-is-here.md`, in the order the page runs them."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx, "Click target")
    world = await sync_to_async(lambda: scene.world)()

    # A (z,y,x) stack with a second pyramid level, and one anchor carrying every spoke the
    # page's step-5 query selects. The world is (z,y,x) too, so the identity registration
    # `seed.register_into_scene` writes covers every axis -- which is what makes `total`
    # true below, and the partial case is `test_placement_queries`' to own.
    level0 = await _zarr(ctx, "stack-0", [4, 8, 64, 64])
    level1 = await _zarr(ctx, "stack-1", [4, 4, 32, 32])

    with patch("datalayer.models.ZarrStore.fill_info", return_value=None):
        created = await schema.execute(
            CREATE_DATASET,
            context_value=ctx,
            variable_values={
                "input": {
                    "name": "stack",
                    "data": str(level0.id),
                    "scales": [{"level": 1, "array": str(level1.id), "scaleMethod": "AREA"}],
                    # `tau` is deliberately an axis the world does not have: it makes the
                    # placement matrix non-square, which is the case the page's step-2 advice
                    # about zero columns exists for. It is MICROTIME so the phasor spokes
                    # below have a continuously-sampled axis to sit on.
                    "axes": [
                        {"name": "tau", "type": "MICROTIME"},
                        {"name": "z", "type": "SPACE"},
                        {"name": "y", "type": "SPACE"},
                        {"name": "x", "type": "SPACE"},
                    ],
                    "anchors": [
                        {
                            "axisAnchors": [{"axis": "z", "value": 0}],
                            "microscope": {"stage": {"x": "1.0 micrometer", "y": "2.0 micrometer", "z": "3.0 micrometer"}},
                            "omeMetadata": {"metadataString": '{"Image": {"Name": "stack"}}'},
                            "valueHistogram": {"histogram": [1.0, 2.0], "bins": [0.0, 1.0, 2.0], "min": 0.0, "max": 2.0},
                            "label": {"label": "DAPI"},
                            "phasorHistogram": {"axis": "tau", "harmonic": 1, "counts": [0.0, 1.0, 0.0, 2.0], "bins": 2},
                            "phasorCalibration": {"axis": "tau", "harmonic": 1, "phaseOffset": 0.1, "modulationFactor": 0.9},
                        }
                    ],
                }
            },
        )
    assert not created.errors, str(created.errors and created.errors[0])
    dataset_id = created.data["createArrayDataset"]["id"]
    intrinsic_id = created.data["createArrayDataset"]["intrinsicSystem"]["id"]

    dataset = await sync_to_async(models.ArrayDataset.objects.get)(pk=dataset_id)
    await seed.register_into_scene(ctx, scene, dataset)

    lens = await schema.execute(CREATE_LENS, context_value=ctx, variable_values={"input": {"dataset": dataset_id, "slices": []}})
    assert not lens.errors, lens.errors
    lens_id = lens.data["createLens"]["id"]

    made = await schema.execute(MAKE_LAYER, context_value=ctx, variable_values={"input": {"scene": str(scene.id), "lens": lens_id}})
    assert not made.errors, str(made.errors and made.errors[0])

    # -- step 1: what is here at all -----------------------------------------
    here = await schema.execute(
        WHAT_IS_HERE,
        context_value=ctx,
        variable_values={"world": str(world.pk), "min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
    )
    assert not here.errors, here.errors
    (placement,) = here.data["coordinateSystem"]["inView"]
    assert placement["source"]["id"] == dataset_id, "the dataset registered into this world is in view of a point inside it"
    assert placement["extentState"] == "KNOWN"
    assert {entry["axis"] for entry in placement["extent"]} == {"z", "y", "x"}, "the extent names the axes it constrains"
    assert placement["validity"] == "MANUAL", "the seeded registration was authored"
    assert placement["invariance"] in {"ISOMETRY", "SIMILARITY", "AFFINE", "DIFFEOMORPHIC", "NONE"}
    assert len(placement["anchors"]) == 1, "step 1 already carries the anchors step 5 interprets"
    assert placement["anchors"][0]["coordinates"] == {"z": 0}

    # -- step 2: world -> pixel ----------------------------------------------
    placed = await schema.execute(PLACEMENT, context_value=ctx, variable_values={"scene": str(scene.id)})
    assert not placed.errors, placed.errors
    (layer,) = placed.data["scene"]["layers"]
    assert layer["placement"] == "PLACED"
    affine = layer["asAffine"]
    assert affine["inputAxes"] == ["tau", "z", "y", "x"], "the layer's own grid, in its own order"
    assert affine["outputAxes"] == ["z", "y", "x"], "only the world axes the registration constrains"
    assert affine["total"] is True, "and those are all of them, so the map covers the world"
    assert len(affine["matrix"]) == len(affine["outputAxes"]), "one row per output axis"
    assert all(len(row) == len(affine["inputAxes"]) + 1 for row in affine["matrix"]), "M x (N+1): the last column is the translation"

    # The page tells a client to drop input axes whose column is all zeros before inverting.
    # `tau` is exactly such an axis here: nothing maps it into the world, so a client fixes it
    # from its own viewer state rather than solving for it.
    tau_column = [row[affine["inputAxes"].index("tau")] for row in affine["matrix"]]
    assert tau_column == [0.0, 0.0, 0.0], "an input axis the world does not have contributes nothing"
    live = [name for index, name in enumerate(affine["inputAxes"]) if any(row[index] != 0 for row in affine["matrix"])]
    assert live == ["z", "y", "x"], "what is left is square against outputAxes, and that is what inverts"

    # The same fields take `at`, which is how a per-index registration resolves. Passing one
    # where no scoped edge exists changes nothing -- the page relies on that being harmless.
    at_c = await schema.execute(PLACEMENT_AT, context_value=ctx, variable_values={"scene": str(scene.id), "at": [{"name": "c", "value": 0}]})
    assert not at_c.errors, at_c.errors
    assert at_c.data["scene"]["layers"][0]["placement"] == "PLACED"

    # -- step 3: which pyramid level -----------------------------------------
    levels = await schema.execute(LEVELS, context_value=ctx, variable_values={"scene": str(scene.id)})
    assert not levels.errors, levels.errors
    level_paths = levels.data["scene"]["layers"][0]["levelPaths"]
    assert [entry["dataArray"]["level"] for entry in level_paths] == [0, 1], "one placement per pyramid level"
    assert [entry["dataArray"]["shape"] for entry in level_paths] == [[4, 8, 64, 64], [4, 4, 32, 32]]
    assert all(entry["path"] is not None for entry in level_paths), "the dataset is registered, so every level has a route"
    assert len(level_paths[1]["path"]) > len(level_paths[0]["path"]), "a higher level crosses its own level edge as well as the registration"

    # -- step 4: read the voxel ----------------------------------------------
    ordered = await schema.execute(AXIS_ORDER, context_value=ctx, variable_values={"scene": str(scene.id)})
    assert not ordered.errors, ordered.errors
    axes = ordered.data["scene"]["layers"][0]["levelPaths"][0]["dataArray"]["coordinateSystem"]["axes"]
    assert [axis["name"] for axis in axes] == ["tau", "z", "y", "x"]
    assert [axis["order"] for axis in axes] == [0, 1, 2, 3], "`order` is the index into `shape`, which is how the array is indexed"
    assert all(axis["unit"] is None for axis in axes), "a pixel grid carries no units"

    # `accessGrant` needs STS, so the page's claim that it is a *field* rather than a mutation
    # is checked against the schema rather than executed.
    store_field = schema.as_str()[schema.as_str().find("type ZarrStore") :]
    assert "accessGrant(" in store_field[: store_field.find("\n}")], "the grant is a field on the store"

    # -- step 5: what was pinned here ----------------------------------------
    anchored = await schema.execute(ANCHORS, context_value=ctx, variable_values={"lens": lens_id})
    assert not anchored.errors, str(anchored.errors and anchored.errors[0])
    (anchor,) = anchored.data["lens"]["activeAnchors"]
    assert anchor["coordinates"] == {"z": 0}, "an anchor pins the axes it names and is global along the rest"
    assert anchor["omeMetadata"]["metadata"] == {"Image": {"Name": "stack"}}, "written through createArrayDataset, and readable"
    assert anchor["channelLabel"]["label"] == "DAPI"
    assert anchor["valueHistogram"]["bins"] == [0.0, 1.0, 2.0]
    assert anchor["microscope"]["state"]["stage"]["x"] is not None
    assert [entry["harmonic"] for entry in anchor["phasorCalibrations"]] == [1], "a list, because coordinates cannot pin a harmonic"
    assert [entry["axis"] for entry in anchor["phasorHistograms"]] == ["tau"], "and neither can they pin an axis"

    # -- step 6: the handoff to attribute plans ------------------------------
    plans = await schema.execute(PLANS, context_value=ctx, variable_values={"system": intrinsic_id})
    assert not plans.errors, plans.errors
    assert plans.data["attributePlans"] == [], "nothing dereferences this stack; the query is the handoff, and it runs"

    # -- step 7: trust and staleness -----------------------------------------
    trust = await schema.execute(TRUST, context_value=ctx, variable_values={"scene": str(scene.id), "system": intrinsic_id})
    assert not trust.errors, trust.errors
    assert trust.data["scene"]["layers"][0]["placementValidity"] == "MANUAL", "the weakest edge on the path, and there is one"
    assert trust.data["scene"]["layers"][0]["placementInvariance"] == "ISOMETRY", "an identity registration preserves distances"
    assert trust.data["coordinateSystem"]["transformVersion"] == 0, "an intrinsic system is where the walk to pixels ends"
