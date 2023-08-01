from strawberry.extensions import SchemaExtension
from koherent.vars import (
    current_assignation_app,
    current_assignation_id,
    current_assignation_user,
)


class KoherentExtension(SchemaExtension):
    def on_operation(self):
        t1 = current_assignation_id.set(
            self.execution_context.context.request.assignation_id
        )
        t2 = current_assignation_app.set(self.execution_context.context.request.app)
        t3 = current_assignation_user.set(self.execution_context.context.request.user)
        yield
        current_assignation_id.reset(t1)
        current_assignation_app.reset(t2)
        current_assignation_user.reset(t3)

        print("GraphQL operation end")
