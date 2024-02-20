import argparse
from django.core.management.base import BaseCommand, CommandError
from core import models
from django.contrib.auth import get_user_model
import typing as t
from django.conf import settings
from core.datalayer import Datalayer
from core.contrib.inspect import inspect_content


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def handle(self, *args: t.Any, **options: t.Any) -> None:

        datalayer = Datalayer()

        for user in get_user_model().objects.all():

            dataset = models.Dataset.objects.update_or_create(creator=user, name="Test Dataset", description="Test Description")

            print(dataset)

            store = models.BigFileStore.objects.create(key="test", bucket=settings.FILE_BUCKET)


            file = store.put_local_file(datalayer, str(settings.DEMOS_DIR / "cells1.tiff"))

            print(inspect_content(store, datalayer))



            




            print(user.username)



