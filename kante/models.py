from django.db import models
from django.contrib.auth import get_user_model
from .enums import ProvenanceAction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django_choices_field import TextChoicesField

# Create your models here.
