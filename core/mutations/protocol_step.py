from kante.types import Info
import strawberry
from core import types, models, scalars
import uuid



@strawberry.input
class PlateChildInput:
    id: strawberry.ID | None = None
    type: str | None = None
    text: str | None = None
    children: list["PlateChildInput"] | None = None
    value: str | None = None
    color: str | None = None
    fontSize: str | None = None
    backgroundColor: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None




@strawberry.input
class ProtocolStepInput:
    name: str 
    reagents: list[strawberry.ID] | None = None
    description: str | None = None
    plate_children: list[PlateChildInput] | None = None


@strawberry.input
class UpdateProtocolStepInput:
    name: str | None = None
    id: strawberry.ID 
    reagents: list[strawberry.ID] | None = None
    kind: strawberry.ID | None = None
    description: str | None = None
    plate_children: list[PlateChildInput] | None = None



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
    




    step, _ = models.ProtocolStep.objects.get_or_create(
        name=input.name,
        defaults=dict(
            description=input.description or "",
            plate_children=input.plate_children or [],
        ),
    )

    if input.reagents:
        raise NotImplementedError("Reagents are not implemented yet")


    return step


def map_protocol_step(info: Info, input: MapProtocolStepInput) -> types.ProtocolStepMapping:
    
    mapping = models.ProtocolStepMapping.objects.create(
        protocol=models.Protocol.objects.get(id=input.protocol),
        step=models.ProtocolStep.objects.get(id=input.step),
        t=input.t,
    )
    
    return mapping


def child_to_str(child):
    if child.get("children", []) is None:
        return " ".join([child_to_str(c) for c in child["children"]]),
    else:
        return child.get("value", child.get("text", "")) or ""


def plate_children_to_str(children):
    return " ".join([child_to_str(c) for c in children])


def update_protocol_step(
    info: Info,
    input: UpdateProtocolStepInput,
) -> types.ProtocolStep:
    step = models.ProtocolStep.objects.get(id=input.id)
    step.name = input.name if input.name else step.name
    step.description = input.description if input.description else plate_children_to_str([strawberry.asdict(i) for i in input.plate_children])
    step.plate_children = [strawberry.asdict(i) for i in input.plate_children] if input.plate_children else step.plate_children

    
    if input.reagents:
        raise NotImplementedError("Reagents are not implemented yet")

    step.save()
    return step


def delete_protocol_step(
    info: Info,
    input: DeleteProtocolStepInput,
) -> strawberry.ID:
    item = models.ProtocolStep.objects.get(id=input.id)
    item.delete()
    return input.id

