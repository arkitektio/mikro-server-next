"""Async ORM seed helpers shared by the filter/ordering test modules.

All helpers create objects in the organization/user of the supplied context
(the identity the static "test" token resolves to, see conftest.py).
"""

from authentikate.models import Membership, User
from kante.context import HttpContext

from core.models import Dataset, File, Image


async def create_dataset(ctx: HttpContext, name: str, **kwargs) -> Dataset:
    return await Dataset.objects.acreate(
        name=name,
        creator=kwargs.pop("creator", ctx.request.user),
        organization=ctx.request.organization,
        membership=kwargs.pop("membership", ctx.request.membership),
        **kwargs,
    )


async def create_image(ctx: HttpContext, name: str, dataset: Dataset, **kwargs) -> Image:
    return await Image.objects.acreate(
        name=name,
        dataset=dataset,
        creator=kwargs.pop("creator", ctx.request.user),
        organization=ctx.request.organization,
        **kwargs,
    )


async def create_file(ctx: HttpContext, name: str, dataset: Dataset, **kwargs) -> File:
    return await File.objects.acreate(
        name=name,
        dataset=dataset,
        creator=kwargs.pop("creator", ctx.request.user),
        organization=ctx.request.organization,
        membership=kwargs.pop("membership", ctx.request.membership),
        **kwargs,
    )


async def create_other_user(ctx: HttpContext) -> User:
    """A second user (sub='2') in the same organization as the context user."""
    user, _ = await User.objects.aget_or_create(
        sub="2", iss="static_issuer", defaults={"username": "static_issuer_2"}
    )
    await Membership.objects.aget_or_create(user=user, organization=ctx.request.organization)
    return user
