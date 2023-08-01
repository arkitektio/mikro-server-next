from kante.types import Info
import strawberry
from core import types, models, scalars


@strawberry.input
class FluorophoreInput:
    name: str
    emission_wavelength: scalars.Micrometers | None = None
    excitation_wavelength: scalars.Micrometers | None = None


@strawberry.input
class DeleteFluorophoreInput:
    id: strawberry.ID


@strawberry.input
class PinFluorophoreInput:
    id: strawberry.ID
    pin: bool


def pin_fluorophore(
    info: Info,
    input: PinFluorophoreInput,
) -> types.Fluorophore:
    raise NotImplementedError("TODO")


def delete_fluorophore(
    info: Info,
    input: DeleteFluorophoreInput,
) -> strawberry.ID:
    item = models.Fluorophore.objects.get(id=input.id)
    item.delete()
    return input.id


def create_fluorophore(
    info: Info,
    input: FluorophoreInput,
) -> types.Fluorophore:
    item = models.Fluorophore.objects.create(
        name=input.name,
        emission_wavelength=input.emission_wavelength,
        excitation_wavelength=input.excitation_wavelength,
    )
    return item


def ensure_fluorophore(
    info: Info,
    input: FluorophoreInput,
) -> types.Fluorophore:
    item, _ = models.Fluorophore.objects.get_or_create(
        name=input.name,
        defaults=dict(
            emission_wavelength=input.emission_wavelength,
            excitation_wavelength=input.excitation_wavelength,
        ),
    )
    return item
