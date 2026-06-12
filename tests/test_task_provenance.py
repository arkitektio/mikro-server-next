import base64
import json

import pytest
from asgiref.sync import sync_to_async
from koherent.models import Task
from kante.context import HttpContext
from mikro_server.schema import schema


def task_header(task_id="task-1", user="1", parent=None, args=None) -> str:
    """Build a base64url-encoded Rekuest-Task header payload."""
    payload = {
        "id": task_id,
        "parent": parent,
        "args": args if args is not None else {"x": 1},
        "user": user,
        "app": "testapp",
        "action": "actionhash",
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


CREATE_DATASET = """
    mutation($name: String!) {
        createDataset(input: {name: $name}) {
            id
            createdThrough {
                taskId
                assignerSub
                app
                assigner {
                    sub
                }
            }
        }
    }
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_with_task_header(db, authenticated_context: HttpContext):
    """A Rekuest-Task header creates one Task row and stamps createdThrough."""
    authenticated_context.headers["Rekuest-Task"] = task_header()

    result = await schema.execute(
        CREATE_DATASET,
        variable_values={"name": "Task created"},
        context_value=authenticated_context,
    )

    assert result.data, result.errors
    created_through = result.data["createDataset"]["createdThrough"]
    assert created_through is not None
    assert created_through["taskId"] == "task-1"
    assert created_through["assignerSub"] == "1"
    assert created_through["app"] == "testapp"
    assert created_through["assigner"]["sub"] == "1"

    def check_row() -> None:
        task = Task.objects.get(task_id="task-1")
        assert task.args == {"x": 1}
        assert task.organization == authenticated_context.request.organization
        assert task.assigner == authenticated_context.request.user

    await sync_to_async(check_row)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_without_task_header(db, authenticated_context: HttpContext):
    """Without a task header createdThrough stays None and no Task row is made."""
    result = await schema.execute(
        CREATE_DATASET,
        variable_values={"name": "Plain"},
        context_value=authenticated_context,
    )

    assert result.data, result.errors
    assert result.data["createDataset"]["createdThrough"] is None
    assert await sync_to_async(Task.objects.count)() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_task_row_shared_between_mutations(db, authenticated_context: HttpContext):
    """Two creations under the same task share a single Task row."""
    authenticated_context.headers["Rekuest-Task"] = task_header(task_id="task-2")

    for name in ("first", "second"):
        result = await schema.execute(
            CREATE_DATASET,
            variable_values={"name": name},
            context_value=authenticated_context,
        )
        assert result.data, result.errors

    assert await sync_to_async(Task.objects.count)() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_created_through_task(db, authenticated_context: HttpContext):
    """Datasets are filterable by the task id they were created through."""
    authenticated_context.headers["Rekuest-Task"] = task_header(task_id="task-3")

    result = await schema.execute(
        CREATE_DATASET,
        variable_values={"name": "From task"},
        context_value=authenticated_context,
    )
    assert result.data, result.errors

    del authenticated_context.headers["Rekuest-Task"]
    # The context object is reused across executes in tests; a real request
    # starts fresh, so clear the task the previous operation attached.
    authenticated_context.request._task = None
    result = await schema.execute(
        CREATE_DATASET,
        variable_values={"name": "Not from task"},
        context_value=authenticated_context,
    )
    assert result.data, result.errors

    result = await schema.execute(
        """
        query($taskId: String!) {
            datasets(filters: {createdThroughTask: $taskId}) {
                name
            }
        }
        """,
        variable_values={"taskId": "task-3"},
        context_value=authenticated_context,
    )

    assert result.data, result.errors
    assert [d["name"] for d in result.data["datasets"]] == ["From task"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_provenance_entry_links_task(db, authenticated_context: HttpContext):
    """The CREATE history entry links back to the task it happened under."""
    authenticated_context.headers["Rekuest-Task"] = task_header(task_id="task-4")

    result = await schema.execute(
        """
        mutation($name: String!) {
            createDataset(input: {name: $name}) {
                id
                provenanceEntries {
                    kind
                    task {
                        taskId
                    }
                }
            }
        }
        """,
        variable_values={"name": "Audited"},
        context_value=authenticated_context,
    )

    assert result.data, result.errors
    entries = result.data["createDataset"]["provenanceEntries"]
    assert entries, "Expected a CREATE provenance entry"
    assert entries[0]["task"] is not None
    assert entries[0]["task"]["taskId"] == "task-4"
