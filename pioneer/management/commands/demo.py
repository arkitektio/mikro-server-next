import argparse
from django.core.management.base import BaseCommand, CommandError
from core import models
from django.contrib.auth import get_user_model
import typing as t
from django.conf import settings
from core.datalayer import Datalayer
from core.contrib.inspect import inspector
import os

def upload_file(datalayer: Datalayer, file_path: str, dataset: models.Dataset) -> None:

    basename = os.path.basename(file_path)

    store = models.BigFileStore.objects.create(key=basename, bucket=settings.FILE_BUCKET)
    file = store.put_local_file(datalayer, file_path)

    print("File uploaded")
    print("Inspecting file")
    store.fill_info(inspector=inspector, datalayer=datalayer)
    print("File inspected")

    file = models.File.objects.create(store=store, name=basename, dataset=dataset)

    print(file)


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def handle(self, *args: t.Any, **options: t.Any) -> None:

        datalayer = Datalayer()

        for user in get_user_model().objects.all():

            dataset, _ = models.Dataset.objects.update_or_create(creator=user, name="Test Dataset", description="Test Description")

            print(dataset)

            upload_file(datalayer, str(settings.DEMOS_DIR / "cells1.tiff"), dataset)
            upload_file(datalayer, str(settings.DEMOS_DIR / "test.czi"), dataset)




            




            print(user.username)



