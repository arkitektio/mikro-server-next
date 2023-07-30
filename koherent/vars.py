import contextvars

current_assignation_id = contextvars.ContextVar("current_assignation_id", default=None)
current_assignation_app = contextvars.ContextVar(
    "current_assignation_app", default=None
)
current_assignation_user = contextvars.ContextVar(
    "current_assignation_user", default=None
)
