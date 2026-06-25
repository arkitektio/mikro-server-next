from pydantic import BaseModel, Field
from uuid import uuid4


class TreeNodeInputModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str
    label: str | None = None
    context: str | None = None
    gap: int | None = None
    children: list["TreeNodeInputModel"]


class TreeInputModel(BaseModel):
    id: str = "root"
    children: list[TreeNodeInputModel]


class RenderTreeInputModel(BaseModel):
    tree: TreeInputModel
    name: str
