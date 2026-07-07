"""Factories for the delete and pin mutations that every entity repeats.

Only the resolver bodies are generated — each entity keeps its own GraphQL
input type (so the schema is unchanged) and its hand-written create/ensure
mutations with explicit field mapping.

Deletion is guarded: a caller may only delete a row they own (its ``creator``
or its ``created_through_by`` assigner) unless they hold the ``admin`` role in
the organization. Ownership is expressed per model by an explicit ``owner``
callable that returns the user ids allowed to delete the item; passing
``owner=None`` keeps the historical org-scope-only behaviour (used for shared
catalog resources like instruments that have no per-user owner).
"""

from kante.types import Info
import strawberry

from core import scoping


def user_is_org_admin(info: Info) -> bool:
    """True if the request user holds the ``admin`` role in the active organization."""
    membership = info.context.request.membership
    return "admin" in (getattr(membership, "roles", None) or [])


def assert_can_delete(info: Info, item, owner) -> None:
    """Raise unless the request user may delete ``item``.

    Allowed if the user is an org admin, or their id is among the owner ids
    ``owner(item)`` returns (the item's creator and/or assigner, possibly
    resolved through a parent row).
    """
    if user_is_org_admin(info):
        return
    user_id = info.context.request.user.id
    allowed = {owner_id for owner_id in owner(item) if owner_id is not None}
    if user_id not in allowed:
        raise PermissionError("Only the creator or assignee can delete this")


def self_owner(item):
    """Owner ids for a model carrying its own creator/assigner fields."""
    return (item.creator_id, item.created_through_by_id)


def image_owner(item):
    """Owner ids inherited from the item's parent image (views, render contexts)."""
    return (item.image.creator_id, item.image.created_through_by_id)


def table_owner(item):
    """Owner ids inherited from the item's parent table (accessors)."""
    return (item.table.creator_id, item.table.created_through_by_id)


def dataset_owner(item):
    """Owner ids inherited from the item's parent dataset (lenses, data arrays)."""
    return (item.dataset.creator_id, item.dataset.created_through_by_id)


def make_delete(model, input_type, owner=None):
    """Build a delete resolver: fetch org-scoped by id, guard ownership, delete.

    ``owner`` is an explicit callable returning the user ids allowed to delete
    the fetched item; when ``None`` the delete is only org-scoped (shared
    resources with no per-user owner).
    """

    def resolve(info: Info, input: input_type) -> strawberry.ID:
        item = scoping.get_for_org(model, info, id=input.id)
        if owner is not None:
            assert_can_delete(info, item, owner)
        item.delete()
        return input.id

    resolve.__name__ = f"delete_{model.__name__.lower()}"
    return resolve


def make_pin(model, input_type, return_type):
    """Build a pin resolver toggling the request user on the pinned_by M2M."""

    def resolve(info: Info, input: input_type) -> return_type:
        item = scoping.get_for_org(model, info, id=input.id)
        if input.pin:
            item.pinned_by.add(info.context.request.user)
        else:
            item.pinned_by.remove(info.context.request.user)
        return item

    resolve.__name__ = f"pin_{model.__name__.lower()}"
    return resolve
