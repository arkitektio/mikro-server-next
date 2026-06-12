from kante.types import Info
import strawberry
from core import types, models
import datetime
from core.mutations._generic import make_delete, make_pin
from koherent.utils import get_or_create_task


@strawberry.input
class EraInput:
    name: str
    begin: datetime.datetime | None = None


@strawberry.input
class DeleteEraInput:
    id: strawberry.ID


@strawberry.input
class PinEraInput:
    id: strawberry.ID
    pin: bool


pin_era = make_pin(models.Era, PinEraInput, types.Era)


def create_era(
    info: Info,
    input: EraInput,
) -> types.Era:
    task = get_or_create_task()
    view = models.Era.objects.create(
        name=input.name,
        organization=info.context.request.organization,
        begin=input.begin,
        created_through=task,
        created_through_by_id=task.assigner_id if task else None,
    )
    return view


delete_era = make_delete(models.Era, DeleteEraInput)
