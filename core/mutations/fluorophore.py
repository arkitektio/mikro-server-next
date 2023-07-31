from kante.types import Info
import strawberry
from core import types, models, scalars


@strawberry.input
class FluorophoreInput:
    name: str
    emission_wavelength: scalars.Micrometers | None = None
    excitation_wavelength: scalars.Micrometers | None = None


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
