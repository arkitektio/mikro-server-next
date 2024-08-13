from kante.types import Info
import strawberry
from core import types, models
import uuid





@strawberry.input
class ProtocolStepInput:
    name: str 
    reagents: list[strawberry.ID] | None = None
    kind: strawberry.ID
    description: str | None = None

@strawberry.input
class MapProtocolStepInput:
    protocol: strawberry.ID
    step: strawberry.ID
    t: int



@strawberry.input
class DeleteProtocolStepInput:
    id: strawberry.ID



def create_protocol_step(
    info: Info,
    input: ProtocolStepInput,
) -> types.ProtocolStep:
    

    input_kind = models.EntityKind.objects.get(id=input.kind)



    step, _ = models.ProtocolStep.objects.update_or_create(
        name=input.name,
        defaults=dict(
            kind=input_kind,
            description=input.description or "",
        ),
    )

    if input.reagents:
        for reagent in input.reagents:
            step.reagents.add(models.Entity.objects.get(id=reagent))

    return step


def map_protocol_step(info: Info, input: MapProtocolStepInput) -> types.ProtocolStepMapping:
    
    mapping = models.ProtocolStepMapping.objects.create(
        protocol=models.Protocol.objects.get(id=input.protocol),
        step=models.ProtocolStep.objects.get(id=input.step),
        t=input.t,
    )
    
    return mapping



def delete_protocol_step(
    info: Info,
    input: DeleteProtocolStepInput,
) -> strawberry.ID:
    item = models.ProtocolStep.objects.get(id=input.id)
    item.delete()
    return input.id

