from django.db import models
from django.contrib.auth import get_user_model
from koherent.choices import ProvenanceAction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django_choices_field import TextChoicesField
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


import koherent.signals
