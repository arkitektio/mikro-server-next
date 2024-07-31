from kante.types import Info
import strawberry
from core import types, models
import uuid




@strawberry.input
class SpecimenInput:
    entity: strawberry.ID
    protocol: strawberry.ID | None = None



@strawberry.input
class DeleteSpecimenInput:
    id: strawberry.ID



def create_specimen(
    info: Info,
    input: SpecimenInput,
) -> types.Specimen:
    
    item = models.Specimen.objects.create(
        entity=models.Entity.objects.get(id=input.entity),
        protocol=models.Protocol.objects.get(id=input.protocol),
    )

    return item


def delete_specimen(
    info: Info,
    input: DeleteSpecimenInput,
) -> strawberry.ID:
    item = models.Specimen.objects.get(id=input.id)
    item.delete()
    return input.id

