"""Mutations for calibrating a dataset's pixel grid.

A calibration is the *only* way physical space enters the model: one PHYSICAL
coordinate system whose axes carry the units, plus one edge mapping the
dataset's intrinsic pixels into it. The server never parses OME or hardware
metadata -- the ingest worker derives the numbers (pixel size, stage pose) and
calls this. Refining a calibration afterwards is ``updateTransformation`` on
the edge, which bumps its version; the pyramid, the ROIs and their bounding
boxes never move, because they live in pixel space.
"""

from kante.types import Info
import strawberry
from pydantic import BaseModel, Field

import kante
from core import models, types
from core.creation import CreationContext
from core.inputs.coords import CalibrationSpecInputModel, CalibratedAxisInput
from core.logic import graph as graph_logic
from core.mutations._generic import assert_can_delete, dataset_owner
from core.scoping import get_for_org


class CreateCalibrationInputModel(CalibrationSpecInputModel):
    """The calibration spec plus the dataset it applies to."""

    dataset: str = Field(description="The ID of the dataset to calibrate")


@kante.pydantic_input(
    CreateCalibrationInputModel,
    description="Input for calibrating a dataset: creates a PHYSICAL coordinate system (axes carrying the units) and the single edge mapping the dataset's intrinsic pixels into it",
)
class CreateCalibrationInput:
    """Input for calibrating a dataset's pixel grid."""

    dataset: strawberry.ID = strawberry.field(description="The ID of the dataset to calibrate")
    name: str = strawberry.field(default="physical", description="The name of the calibrated space, e.g. 'physical', 'stage' or 'specimen'. Namespaced under the dataset's name")
    axes: list[CalibratedAxisInput] = strawberry.field(description="The physical space's axes, corresponding 1:1 by position to the dataset's pixel axes. Their semantic types must match; the units are theirs alone")
    scale: list[float] | None = strawberry.field(default=None, description="The per-axis pixel size, in each axis' own unit: e.g. 0.325 micrometer per pixel in x. Exclusive with `affine`")
    translation: list[float] | None = strawberry.field(default=None, description="An optional per-axis offset in physical units, e.g. the stage position of pixel (0, ..., 0). Combined with `scale` into a sequence")
    affine: list[list[float]] | None = strawberry.field(default=None, description="A full affine matrix, N x (N+1) with the translation in the last column, for calibrations that shear or rotate. Exclusive with `scale`/`translation`")


def create_calibration(info: Info, input: CreateCalibrationInput) -> types.CoordinateSystem:
    """Calibrate a dataset: create a PHYSICAL system and the edge placing its pixels there."""
    model = input.to_pydantic()

    dataset = get_for_org(models.ADataset, info, id=model.dataset)
    ctx = CreationContext.from_info(info)

    return graph_logic.create_calibration(
        dataset=dataset,
        name=model.name,
        axes=model.axes,
        scale=model.scale,
        translation=model.translation,
        affine=model.affine,
        ctx=ctx,
    )


class DeleteCalibrationInputModel(BaseModel):
    """The calibration to delete, by coordinate system ID."""

    id: str = Field(description="The ID of the PHYSICAL coordinate system to delete")


@kante.pydantic_input(DeleteCalibrationInputModel, description="Input for deleting a calibration (a PHYSICAL coordinate system) by ID")
class DeleteCalibrationInput:
    """Input for deleting a calibration by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the PHYSICAL coordinate system to delete")


def delete_calibration(info: Info, input: DeleteCalibrationInput) -> strawberry.ID:
    """Delete a calibration. Only PHYSICAL systems can be deleted this way.

    A guarded, explicit delete rather than a generic one: a generic delete on
    CoordinateSystem could reach an intrinsic system and take the whole spatial
    graph of a dataset with it.
    """
    model = input.to_pydantic()

    system = get_for_org(models.CoordinateSystem, info, id=model.id)
    # The ownership check, not the derived label: only a system hanging off the
    # `dataset` FK is a calibration, and only that FK is safe to delete through.
    if system.dataset_id is None:
        raise ValueError(f"Coordinate system {system.pk} is {system.kind.value}, not a calibration. Only calibrations can be deleted; other systems cascade with their owner.")

    assert_can_delete(info, system, dataset_owner)
    system.delete()
    return model.id
