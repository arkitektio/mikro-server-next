from django.dispatch import receiver
from simple_history.signals import (
    pre_create_historical_record,
)
from koherent.vars import (
    current_assignation_app,
    current_assignation_id,
    current_assignation_user,
)


@receiver(pre_create_historical_record)
def add_history_app(sender, **kwargs):
    history_instance = kwargs["history_instance"]
    history_instance.app = current_assignation_app.get()
    history_instance.assignation_id = current_assignation_id.get()
    history_instance.history_user = current_assignation_user.get()

    # context.request for use only when the simple_history middleware is on and enabled
