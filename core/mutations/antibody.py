from kante.types import Info
import strawberry
from core import types, models, scalars


@strawberry.input
class AntibodyInput:
    name: str
    epitope: str | None = None


def create_antibody(
    info: Info,
    input: AntibodyInput,
) -> types.Antibody:
    item = models.Antibody.objects.create(
        name=input.name,
    )
    return item


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
