from django.db import models  # Create your models here.
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """A reflection on the real User"""

    sub = models.CharField(max_length=1000, null=True, blank=True)
    iss = models.CharField(max_length=1000, null=True, blank=True)
    changed_hash = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        unique_together = ("iss", "sub")
        permissions = [("imitate", "Can imitate me")]


class App(models.Model):
    iss = models.CharField(max_length=2000, null=True, blank=True)
    client_id = models.CharField(unique=True, max_length=2000)
    name = models.CharField(max_length=2000, null=True, blank=True)

    class Meta:
        unique_together = ("iss", "client_id")

    def __str__(self) -> str:
        return f"{self.name}"
