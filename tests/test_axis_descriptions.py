"""An axis (and a table column) carries an optional free-form description.

The description is authored once, at the input that declares the axis, and travels with
the fact wherever the fact is copied: onto the derived Axis row, and onto the axes a
collection copies when it mints its own space. The table-column case lives with the table
dataset tests.
"""

from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from datalayer.models import ZarrStore
from kante.context import HttpContext

from core import enums, models
from mikro_server.schema import schema
from tests import seed


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_dataset_axis_descriptions_round_trip(authenticated_context: HttpContext):
    """A structural axis declared with a description reads it back; one without reads null."""
    store = await ZarrStore.objects.acreate(
        organization=authenticated_context.request.organization,
        key="described",
        bucket="zarr",
        shape=[2, 32, 32],
        chunks=[2, 32, 32],
        version="3",
        dtype="uint8",
        populated=True,
    )

    with patch("datalayer.models.ZarrStore.fill_info", return_value=None):
        result = await schema.execute(
            """
            mutation Create($input: CreateADatasetInput!) {
              createADataset(input: $input) { id intrinsicSystem { axes { name longName description } } }
            }
            """,
            context_value=authenticated_context,
            variable_values={
                "input": {
                    "name": "Described",
                    "data": str(store.id),
                    "scales": [],
                    "axes": [
                        {"name": "c", "type": "CHANNEL"},
                        {"name": "y", "type": "SPACE", "description": "distance from the coverslip"},
                        {"name": "x", "type": "SPACE", "longName": "fast axis"},
                    ],
                }
            },
        )
    assert not result.errors, result.errors

    axes = {a["name"]: a for a in result.data["createADataset"]["intrinsicSystem"]["axes"]}
    assert axes["y"]["description"] == "distance from the coverslip"
    assert axes["x"]["description"] is None
    assert axes["x"]["longName"] == "fast axis"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_physical_axis_descriptions_round_trip(authenticated_context: HttpContext):
    """A physical space's axis description is stored and read back off the space itself.

    Where this used to also assert the description reached a *bootstrapped world*: there is
    no such world any more. The space declared here is the one a scene composes over, so the
    description a person wrote is read from the same row it was written to, never from a copy.
    """
    dataset = await seed.create_adataset(authenticated_context, "Calibrated", axes=seed.YX_AXES, shapes=[[64, 64]])

    # A calibration is an ordinary space plus one edge into it (RFC-9), so this is
    # `createCoordinateSystem` with a registration rather than a mutation of its own.
    calibrated = await schema.execute(
        """
        mutation Calibrate($input: CreateCoordinateSystemInput!) {
          createCoordinateSystem(input: $input) { id axes { name description } }
        }
        """,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "name": "Calibrated/physical",
                "axes": [
                    {"name": "y", "type": "SPACE", "unit": "micrometer", "description": "distance from the coverslip"},
                    {"name": "x", "type": "SPACE", "unit": "micrometer"},
                ],
                "registrations": [{"dataset": str(dataset.pk), "transform": {"kind": "SCALE", "scale": [0.325, 0.325]}}],
            }
        },
    )
    assert not calibrated.errors, calibrated.errors
    axes = {a["name"]: a for a in calibrated.data["createCoordinateSystem"]["axes"]}
    assert axes["y"]["description"] == "distance from the coverslip"
    assert axes["x"]["description"] is None



@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_mesh_collection_copies_the_source_axes_descriptions(authenticated_context: HttpContext):
    """Defaulted collection axes are copies of the source's -- long_name and description included."""
    dataset = await seed.create_adataset(
        authenticated_context,
        "Labels",
        axes=[
            seed.axis("y", enums.AxisType.SPACE),
            seed.axis("x", enums.AxisType.SPACE),
        ],
        shapes=[[64, 64]],
    )

    def describe_source_axes() -> models.CoordinateSystem:
        intrinsic = dataset.intrinsic_coordinate_system
        intrinsic.axes.filter(name="y").update(description="distance from the coverslip", long_name="slow axis")
        return intrinsic

    intrinsic = await sync_to_async(describe_source_axes)()

    key = "mesh-descriptions"
    catalog = await sync_to_async(models.ParquetStore.objects.create)(path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=authenticated_context.request.organization)

    result = await schema.execute(
        """
        mutation Create($input: CreateMeshCollectionInput!) {
          createMeshCollection(input: $input) { id coordinateSystem { axes { name longName description } } }
        }
        """,
        context_value=authenticated_context,
        variable_values={"input": {"coordinateSystem": str(intrinsic.pk), "version": "v1", "specVersion": "1.0", "catalog": str(catalog.pk)}},
    )
    assert not result.errors, result.errors
    axes = {a["name"]: a for a in result.data["createMeshCollection"]["coordinateSystem"]["axes"]}
    assert axes["y"]["description"] == "distance from the coverslip"
    assert axes["y"]["longName"] == "slow axis"
    assert axes["x"]["description"] is None
