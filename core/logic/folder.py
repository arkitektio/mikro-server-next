"""Where a newly created container gets filed.

One helper, because four create mutations need the same two-line answer and a fifth
(``create_image_from_array``) has been giving it since long before the others existed:
file it where the client said, or in the user's default folder if the client said nothing.

The column is nullable and unfiled rows are legal -- migration 0007 deliberately does not
backfill -- but nothing *created through the API* is left unfiled, which is what makes the
folder tree a complete view of a user's data rather than a partial one.
"""

from typing import cast

from core import models
from core.creation import CreationContext
from core.scoping import get_for_org
from kante.types import Info


def resolve_folder(info: Info, ctx: CreationContext, folder_id: str | None) -> models.Folder:
    """The folder named by the input, or the user's default folder (created on first use)."""
    if folder_id:
        return cast(models.Folder, get_for_org(models.Folder, info, id=folder_id))
    return cast(models.FolderManager, models.Folder.objects).get_current_default(ctx)
