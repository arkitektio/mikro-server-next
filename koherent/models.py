from django.db import models
from authentikate.models import App


# in models.py
class AppHistoryModel(models.Model):
    """
    Abstract model for history models tracking the IP address.
    """

    app = models.ForeignKey(App, on_delete=models.SET_NULL, null=True, blank=True)
    assignation_id = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        abstract = True
