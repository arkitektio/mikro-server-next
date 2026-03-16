from kante.types import Info
import strawberry

from core import types, models, scalars
from datalayer.datalayer import get_current_datalayer
import json
from django.conf import settings
import uuid
import os
import mimetypes


@strawberry.input
class PinFileInput:
    id: strawberry.ID
    pin: bool


def pin_file(
    info: Info,
    input: PinFileInput,
) -> types.File:
    raise NotImplementedError("TODO")


@strawberry.input
class FromFileLike:
    file: scalars.FileLike
    file_name: str
    dataset: strawberry.ID | None = None
    origins: list[strawberry.ID] | None = None


def from_file_like(
    info: Info,
    input: FromFileLike,
) -> types.File:
    store = models.BigFileStore.objects.get(id=input.file)
    store.fill_info()

    dataset = models.Dataset.objects.get(id=input.dataset) if input.dataset else models.Dataset.objects.get_current_default(info)

    table = models.File.objects.create(
        dataset=dataset,
        creator=info.context.request.user,
        organization=info.context.request.organization,
        membership=info.context.request.membership,
        name=store.file_name,
        store=store,
    )

    return table


@strawberry.input
class DeleteFileInput:
    id: strawberry.ID


def delete_file(
    info: Info,
    input: DeleteFileInput,
) -> strawberry.ID:
    item = models.File.objects.get(id=input.id)
    item.delete()
    return input.id
