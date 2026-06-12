"""Filters on the tasks query: created window, assigner, parent and app/action search."""

import datetime

import pytest

from koherent.models import Task
from kante.context import HttpContext
from mikro_server.schema import schema

QUERY = """
    query Tasks($filters: TaskFilter) {
        tasks(filters: $filters) { taskId }
    }
"""


async def _seed_task(ctx: HttpContext, task_id: str, **overrides) -> Task:
    fields = dict(
        task_id=task_id,
        assigner=ctx.request.user,
        assigner_sub=ctx.request.user.sub,
        app="mikroscope-app",
        action="acquire-stack",
        args={},
        organization=ctx.request.organization,
    )
    fields.update(overrides)
    return await Task.objects.acreate(**fields)


async def _query_task_ids(ctx: HttpContext, filters: dict) -> set[str]:
    result = await schema.execute(QUERY, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return {t["taskId"] for t in result.data["tasks"]}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_tasks_filter_by_created_window(db, authenticated_context: HttpContext):
    """createdBefore/createdAfter bound the task list by creation time."""
    early = await _seed_task(authenticated_context, "early")
    late = await _seed_task(authenticated_context, "late")
    # created_at is auto_now_add; move one row firmly into the past.
    cutoff = early.created_at - datetime.timedelta(days=1)
    await Task.objects.filter(pk=early.pk).aupdate(created_at=cutoff - datetime.timedelta(days=1))

    assert await _query_task_ids(authenticated_context, {"createdBefore": cutoff.isoformat()}) == {"early"}
    assert await _query_task_ids(authenticated_context, {"createdAfter": cutoff.isoformat()}) == {"late"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_tasks_filter_by_assigner(db, authenticated_context: HttpContext):
    """assigner (sub) and assignerId (database ID) both narrow to the assigning user."""
    await _seed_task(authenticated_context, "mine")
    await _seed_task(authenticated_context, "nobodys", assigner=None, assigner_sub="ghost")

    user = authenticated_context.request.user
    assert await _query_task_ids(authenticated_context, {"assigner": user.sub}) == {"mine"}
    assert await _query_task_ids(authenticated_context, {"assignerId": str(user.id)}) == {"mine"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_tasks_filter_by_parent_id(db, authenticated_context: HttpContext):
    """parentId (FilterLookup) matches the parent task id string."""
    await _seed_task(authenticated_context, "child", parent_id="root-task")
    await _seed_task(authenticated_context, "orphan")

    assert await _query_task_ids(authenticated_context, {"parentId": {"exact": "root-task"}}) == {"child"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_tasks_search_matches_app_or_action(db, authenticated_context: HttpContext):
    """search matches case-insensitively on either app or action."""
    await _seed_task(authenticated_context, "by-app", app="DeconvolutionSuite", action="deblur")
    await _seed_task(authenticated_context, "by-action", app="other", action="Segmentation-Run")

    assert await _query_task_ids(authenticated_context, {"search": "deconvolution"}) == {"by-app"}
    assert await _query_task_ids(authenticated_context, {"search": "segmentation"}) == {"by-action"}
    assert await _query_task_ids(authenticated_context, {"search": "no-such-thing"}) == set()
