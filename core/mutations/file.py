from kante.types import Info
import strawberry

from core import types, models, scalars
from datalayer.datalayer import get_current_datalayer
from core.scoping import get_for_org
from core.mutations._generic import make_delete
from koherent.utils import get_or_create_task


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
    store = get_for_org(models.BigFileStore, info, id=input.file)
    store.fill_info()

    dl = get_current_datalayer()

    created_through = get_or_create_task()
    dataset = get_for_org(models.Dataset, info, id=input.dataset) if input.dataset else models.Dataset.objects.get_current_default(info, created_through=created_through)

    file = models.File.objects.create(
        dataset=dataset,
        creator=info.context.request.user,
        organization=info.context.request.organization,
        membership=info.context.request.membership,
        name=store.original_file_name,
        size=dl.get_object_size(store.bucket, store.key),
        content_type=store.content_type,
        store=store,
        created_through=created_through,
    )

    return strawberry.cast(types.File, file)


@strawberry.input
class DeleteFileInput:
    id: strawberry.ID


delete_file = make_delete(models.File, DeleteFileInput)
