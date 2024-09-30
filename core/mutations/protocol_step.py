import datetime
from kante.types import Info
import strawberry
from core import types, models, scalars, age, enums
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
    kind: enums.ProtocolStepKind
    expression: strawberry.ID 
    entity: strawberry.ID | None = None
    reagent: strawberry.ID | None = None
    description: str | None = None
    performed_at: datetime.datetime | None = None
    performed_by: strawberry.ID | None = None
    used_reagent: strawberry.ID | None = None
    used_reagent_volume: scalars.Microliters | None = None
    used_reagent_mass: scalars.Micrograms | None = None
    used_entity: strawberry.ID | None = None
    description: str | None = None


@strawberry.input
class UpdateProtocolStepInput:
    id: strawberry.ID
    name: str  | None = None
    kind: enums.ProtocolStepKind | None = None
    entity: strawberry.ID | None = None
    reagent: strawberry.ID | None = None
    description: str | None = None
    performed_at: datetime.datetime | None = None
    performed_by: strawberry.ID | None = None
    used_reagent: strawberry.ID | None = None
    used_reagent_volume: scalars.Microliters | None = None
    used_reagent_mass: scalars.Micrograms | None = None
    used_entity: strawberry.ID | None = None
    description: str | None = None




@strawberry.input
class DeleteProtocolStepInput:
    id: strawberry.ID



def create_protocol_step(
    info: Info,
    input: ProtocolStepInput,
) -> types.ProtocolStep:
    


    step = models.ProtocolStep.objects.create(
        name=input.name,
        kind=input.kind,
        for_entity_id=input.entity,
        for_reagent_id=input.reagent,
        description=input.description,
        performed_at=input.performed_at,
        performed_by_id=input.performed_by,
        used_reagent_id=input.used_reagent,
        used_reagent_volume=input.used_reagent_volume,
        used_reagent_mass=input.used_reagent_mass,
        used_entity_id=input.used_entity,
    )

    return step


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

