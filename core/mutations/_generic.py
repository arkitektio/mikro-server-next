"""Factories for the delete and pin mutations that every entity repeats.

Only the resolver bodies are generated — each entity keeps its own GraphQL
input type (so the schema is unchanged) and its hand-written create/ensure
mutations with explicit field mapping.
"""

from kante.types import Info
import strawberry

from core import scoping


def make_delete(model, input_type):
    """Build a delete resolver: fetch org-scoped by id, delete, return the id."""

    def resolve(info: Info, input: input_type) -> strawberry.ID:
        item = scoping.get_for_org(model, info, id=input.id)
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
