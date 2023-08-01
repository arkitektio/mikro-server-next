from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class AntibodyInput:
    name: str
    epitope: str | None = None


@strawberry.input
class DeleteAntibodyInput:
    id: strawberry.ID


@strawberry.input
class PinAntibodyInput:
    id: strawberry.ID
    pin: bool


def pin_antibody(
    info: Info,
    input: PinAntibodyInput,
) -> types.Antibody:
    raise NotImplementedError("TODO")


def create_antibody(
    info: Info,
    input: AntibodyInput,
) -> types.Antibody:
    item = models.Antibody.objects.create(
        name=input.name,
    )
    return item


def delete_antibody(
    info: Info,
    input: DeleteAntibodyInput,
) -> strawberry.ID:
    item = models.Antibody.objects.get(id=input.id)
    item.delete()
    return input.id


def ensure_antibody(
    info: Info,
    input: AntibodyInput,
) -> types.Antibody:
    item, _ = models.Antibody.objects.get_or_create(
        name=input.name,
        defaults=dict(
            epitope=input.epitope,
        ),
    )
    return item
